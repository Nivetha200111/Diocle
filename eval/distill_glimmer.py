"""Verified distillation, Muse Spark Open to Muse Glimmer (plan: docs/DISTILLATION.md, committed before any model call).

  PYTHONPATH=services/converter:services/verifier:services/analyzer <python with the converter deps> eval/distill_glimmer.py STAGE

  harvest [--generate N]   teacher writes programs and Java; gates decide what may be learned. Resumable. Caps in the plan.
  dataset                  writes eval/distill/train.jsonl from what passed; fails if a held-out program leaks in.
  train [--go]             one Fireworks fine-tuning job. Without --go it prints the plan and spends nothing.
  evaluate --approve-usd X --max-minutes M --accelerator A --accelerator-count C --usd-per-gpu-hour R
                           base vs tuned on one paid deployment, deleted when this ends. Needs the owner's OK (rule 10).

Results go to eval/results-distillation.json (contracts/distillation-report.schema.json) after every unit. The Fireworks
account name never goes into a result file: it can be derived from an email address.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("services/converter", "services/verifier", "services/analyzer"):
    sys.path.insert(0, str(ROOT / p))

# Open weights only, on low effort (reasoning bills as output). Empty values win over .env: no guard or tier model here.
os.environ.update({"MODEL_MODE": "private", "MODEL_REASONING_EFFORT": "low", "MODEL_TIER_2_ID": "", "MODEL_TIER_3_ID": "",
                   "GUARD_MODEL_API_KEY": "", "GUARD_MODEL_ID": "", "GUARD_MODEL_BASE_URL": "", "GUARD_MAX_CALLS": "0",
                   "CROSSCHECK_MODEL_ID": "", "DOC_MODEL_ID": "", "VISION_MODEL_ID": ""})

from diocle_converter import distill  # noqa: E402

OUT = ROOT / "eval" / "results-distillation.json"
DIR = ROOT / "eval" / "distill"
HARVEST, TRAIN = DIR / "harvest.json", DIR / "train.jsonl"
WORK = ROOT / "runs" / "distill"
SCHEMA = ROOT / "contracts" / "distillation-report.schema.json"
QUARRYSTONE = Path(os.environ.get("DIOCLE_QUARRYSTONE_SAMPLES", ROOT / "runs/deliveries/delivery-20261101-011738/samples"))

STOP_USD, HARD_CAP_USD, PROGRAM_CAP_USD = 7.00, 8.00, 0.25
MAX_GENERATED, WORKERS = 120, 6
BASE_MODEL = "accounts/fireworks/models/muse-glimmer-30b"
DATASET_ID, JOB_ID, OUTPUT_MODEL = "diocle-distill-v1", "diocle-distill-v1", "diocle-glimmer-v1"
EPOCHS, LORA_RANK = 3, 8
EVAL_SEED, EVAL_CASES, K = 8801, 1000, 3
HELD_OUT_DIRS = {"BRNCHSUM": "eval/samples/brnchsum", "CHQCLR": "eval/samples/chqclr", "FXCONV": "eval/samples/fxconv",
                 "LOANAMRT": "eval/samples/loanamrt"}
REPOSITORY = ("account-match", "addfee", "call-identifier", "daily-control", "display-report", "fee-schedule", "interest-accrual",
              "ledger-rewrite", "loyalty-waiver", "packed-posting", "txn-posting")
LIMITS = ["Small dataset: Meta's post-training guide suggests roughly 500 or more examples.",
          "Passing 1,000 generated inputs is not a proof; generated inputs are well-formed and the breaker is not run on training examples.",
          "Answers only: no reasoning traces in the training data.",
          "The tuned model runs only on a paid dedicated deployment; it is not on the public site.",
          "Hosted Muse Spark outputs are refused as training data (Meta Model API terms, section 10.1(ix))."]

lock = threading.Lock()
verify_lock = threading.BoundedSemaphore(3)  # builds and 1,000 inputs are CPU heavy; each test has its own temp directory


def load(path: Path, default: dict) -> dict:
    return json.loads(path.read_text()) if path.exists() else default


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def held_out_sources() -> dict[str, str]:
    from diocle_converter.sources import Program
    return {name: Program.load(ROOT / d).as_text() for name, d in HELD_OUT_DIRS.items()}


def teacher_settings():
    from diocle_converter.config import Settings
    s = Settings.from_env()
    if distill.TEACHER_MARK not in s.model:
        raise SystemExit("OPEN_MODEL_ID is not Muse Spark Open: refused")
    return replace(s, max_usd=PROGRAM_CAP_USD, max_calls_per_run=3, max_calls_per_round=3)  # write, fix once, translate


def teach(sample: Path, client, unit: dict, held: dict[str, str]) -> None:
    """Translate once, gate, and store the example on `unit` if it passes. Sets unit["gate"] to the refusing gate otherwise."""
    from diocle_converter.client import BudgetExceeded
    from diocle_converter.guard import GuardBlocked, check_before_running
    from diocle_converter.sources import Program
    from diocle_converter.translate import translate
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import verify_sample

    program = Program.load(sample)
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "java")
        try:
            result = translate(program, client, ws)
        except BudgetExceeded:
            unit["gate"] = "spend-cap"
            return
        except Exception as e:
            unit.update(gate="translation-failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
            return
        try:
            distill.check_teacher_calls(client.calls)
        except distill.NotOpenWeights as e:
            unit.update(gate="not-open-weights", detail=str(e))
            return
        try:
            check_before_running(ws.root, tuple(f["dd"] for f in program.files))
        except GuardBlocked as e:
            unit.update(gate="policy-blocked", detail=str(e)[:300])
            return
        with verify_lock:
            try:
                report = verify_sample(sample, ws.root, seed=distill.ORACLE_SEED, random_count=distill.ORACLE_CASES)
            except Exception as e:
                unit.update(gate="differential-failed", detail=f"verifier {type(e).__name__}: {str(e)[:200]}")
                return
        ok, gate = distill.passes_oracle(report)
        unit.update(total=report["summary"]["total"], failedCases=report["summary"]["failed"])
        if not ok:
            unit["gate"] = gate
            return
        java = (ws.root / result["file"]).read_text()
    unit.update(gate=None, line=distill.training_line(program, result, java))


def harvest_unit(kind: str, name: str, state: dict, held: dict[str, str], topic: tuple | None, directory: Path | None) -> None:
    from diocle_converter.client import ModelClient

    with lock:
        if name in state["units"] or state["spentUsd"] >= STOP_USD:
            return
    client = ModelClient(teacher_settings())
    unit = {"kind": kind, "name": name}
    started = time.time()
    try:
        if kind == "generated":
            _, domain, technique = topic
            unit.update(domain=domain, technique=technique)
            sample = generate(name, domain, technique, client, unit, held, state)
        else:
            sample = directory
            if not distill.oracle_can_see(sample):
                unit["gate"] = "weak-oracle"
        if sample is not None and unit.get("gate", "") == "":
            teach(sample, client, unit, held)
        elif sample is None and "gate" not in unit:
            unit["gate"] = "generation-failed"
    except Exception as e:  # one bad unit must not stop the harvest; it is counted, not hidden
        unit.update(gate=unit.get("gate") or "translation-failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
    usage = client.usage_summary()
    unit.update(costUsd=usage["estimatedCostUsd"], calls=usage["calls"], inputTokens=usage["inputTokens"],
                outputTokens=usage["outputTokens"], models=sorted({c.model for c in client.calls}), seconds=round(time.time() - started, 1))
    with lock:
        state["units"][name] = unit
        state["spentUsd"] = round(state.get("pilotUsd", 0) + sum(u.get("costUsd") or 0 for u in state["units"].values()), 6)
        atomic_write(HARVEST, json.dumps(state, indent=1, ensure_ascii=False) + "\n")
        print(f"{name}: {unit.get('gate') or 'PASSED'} ${unit['costUsd']} {unit['seconds']}s | spend ${state['spentUsd']:.3f}", flush=True)


def generate(name: str, domain: str, technique: str, client, unit: dict, held: dict[str, str], state: dict) -> Path | None:
    """Teacher writes a new synthetic COBOL program. Returns its sample directory, or None with unit['gate'] set."""
    messages = distill.generation_messages(name, domain, technique)
    for attempt in (1, 2):
        choice = client.chat(role="generator", round=attempt - 1, messages=messages, response_format=distill.generation_format())
        try:
            answer = json.loads(choice.message.content)
        except (TypeError, ValueError):
            unit["gate"] = "generation-failed"
            return None
        if not distill.contained(answer["cobol"]):
            unit["gate"] = "analyzer-refused"
            unit["detail"] = "touches other files or uses CALL, ACCEPT or EXEC"
            return None
        repo = distill.write_generated(name, answer, WORK / "repos" / name)
        errors = distill.compile_errors(repo, name)
        if errors is None:
            break
        if attempt == 2:
            unit.update(gate="does-not-compile", detail=errors[:300])
            return None
        messages = distill.fix_messages(messages, choice.message.content, errors)
    sample = distill.sample_from_repo(repo, name, WORK / "samples")
    if sample is None:
        unit["gate"] = "analyzer-refused"
        return None
    if not distill.oracle_can_see(sample):
        unit["gate"] = "weak-oracle"
        return None
    text = answer["cobol"] + answer["inputCopybook"] + answer["outputCopybook"]
    who, score = distill.closest(text, held)
    if score >= distill.HELD_OUT_SIMILARITY:
        unit.update(gate="too-similar", detail=f"{score:.2f} to held-out {who}")
        return None
    with lock:
        seen = {n: u["source"] for n, u in state["units"].items() if u.get("source")}
    who, score = distill.closest(text, seen)
    if score >= distill.GENERATED_SIMILARITY:
        unit.update(gate="too-similar", detail=f"{score:.2f} to {who}")
        return None
    unit.update(source=text, gate="")
    return sample


def retry_unreached(state: dict) -> None:
    """Second pass (see Deviations): generated programs whose Java never met a real comparison go round again. A program
    whose Java differed on real records stays rejected: that is the oracle's answer, not a prompt problem."""
    if "firstPassRejected" in state:
        return
    units = state["units"]
    state["firstPassRejected"] = {g: sum(u.get("gate") == g for u in units.values()) for g in distill.GATES}
    state["pilotUsd"] = state["spentUsd"]
    for name in [n for n, u in units.items() if u["kind"] == "generated" and not u.get("line") and not u.get("total")]:
        del units[name]
    state["pilotUsd"] = round(state["pilotUsd"] - sum(u.get("costUsd") or 0 for u in units.values()), 6)


def harvest(generated: int, second_pass: bool = False) -> int:
    if generated > MAX_GENERATED:
        raise SystemExit(f"--generate is capped at {MAX_GENERATED}")
    state = load(HARVEST, {"teacher": teacher_settings().model, "reasoningEffort": "low", "spentUsd": 0.0, "units": {}})
    if second_pass:
        retry_unreached(state)
        atomic_write(HARVEST, json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    held = held_out_sources()
    jobs = [("repository", name.upper(), None, ROOT / "samples" / name) for name in REPOSITORY]
    jobs += [("repository", p.name.upper(), None, p) for p in sorted(QUARRYSTONE.glob("qv*")) if (p / "sample.json").exists()]
    jobs += [("generated", t[0], t, None) for t in distill.topics(generated)]
    print(f"{len(jobs)} units, cap ${HARD_CAP_USD:.2f}, stop at ${STOP_USD:.2f}, already spent ${state['spentUsd']:.3f}", flush=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        for f in [pool.submit(harvest_unit, kind, name, state, held, topic, directory) for kind, name, topic, directory in jobs]:
            f.result()
    report()
    return 0


def lines_from(state: dict) -> list[dict]:
    return [state["units"][n]["line"] for n in sorted(state["units"]) if state["units"][n].get("line")]


def dataset() -> int:
    state = load(HARVEST, {"units": {}})
    lines = lines_from(state)
    distill.check_no_leak(lines, held_out_sources())
    data = distill.dataset_bytes(lines)
    atomic_write(TRAIN, data.decode())
    print(f"{len(lines)} examples, {len(data):,} bytes, sha256 {distill.sha256(data)}, about "
          f"{distill.estimate_training_tokens(data, EPOCHS):,} training tokens over {EPOCHS} epochs", flush=True)
    report()
    return 0


def train(go: bool) -> int:
    data = TRAIN.read_bytes()
    lines = [json.loads(x) for x in data.decode().splitlines()]
    distill.check_no_leak(lines, held_out_sources())  # again: the file may have been edited since `dataset`
    tokens = distill.estimate_training_tokens(data, EPOCHS)
    if tokens > distill.MAX_TRAINING_TOKENS:
        raise SystemExit(f"about {tokens:,} training tokens is over the {distill.MAX_TRAINING_TOKENS:,} cap")
    print(f"{len(lines)} examples, about {tokens:,} tokens, {BASE_MODEL}, rank {LORA_RANK}, {EPOCHS} epochs", flush=True)
    if not go:
        print("dry run: pass --go to upload and start the job", flush=True)
        return 0
    fw = distill.Fireworks.from_env()
    record = load(DIR / "training.json", {})
    if not record.get("jobId"):
        fw.upload_dataset(DATASET_ID, data, len(lines))
        distill.wait_for(lambda: fw.dataset(DATASET_ID), lambda d: d.get("state") == "READY", every=10, limit=600)
        fw.create_job(JOB_ID, BASE_MODEL, DATASET_ID, OUTPUT_MODEL, EPOCHS, LORA_RANK)
        record = {"status": "running", "jobId": JOB_ID, "outputModel": OUTPUT_MODEL, "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        atomic_write(DIR / "training.json", json.dumps(record, indent=1) + "\n")
    job = distill.wait_for(lambda: fw.job(JOB_ID), lambda j: j.get("state") in ("JOB_STATE_COMPLETED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"),
                           every=60, limit=4 * 3600)
    record.update(status="completed" if job["state"] == "JOB_STATE_COMPLETED" else "failed", hostState=job["state"],
                  finishedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    atomic_write(DIR / "training.json", json.dumps(record, indent=1) + "\n")
    print(f"training {record['status']}", flush=True)
    report()
    return 0 if record["status"] == "completed" else 1


def first_try(directory: str, model: str, trial: int, settings, results: dict) -> dict:
    """Same harness as eval/headline.py, plus the Java policy before any build. Model-written Java runs on this machine."""
    from diocle_converter.client import ModelClient
    from diocle_converter.guard import GuardBlocked, check_before_running
    from diocle_converter.sources import Program
    from diocle_converter.translate import translate
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import passes, verify_sample

    sample = ROOT / directory
    rec = {"trial": trial, "passed": False, "translated": False, "compiled": False}
    started = time.time()
    client = ModelClient(replace(settings, model=model, max_calls_per_run=1))
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "java")
        program = Program.load(sample)
        try:
            translate(program, client, ws)
            rec["translated"] = True
        except Exception as e:
            if type(e).__name__ in ("APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError"):
                raise
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        if rec["translated"]:
            try:
                check_before_running(ws.root, tuple(f["dd"] for f in program.files))
                with verify_lock:
                    report = verify_sample(sample, ws.root, seed=EVAL_SEED, random_count=EVAL_CASES)
                s, runs = report["summary"], report["runs"]
                rec.update(passed=passes(report), total=s["total"], failedCases=s["failed"], compiled=bool(runs["converted"]["compiled"]),
                           exitCodeMatch=runs.get("exitCodeMatch"), stdoutMatch=runs["stdoutMatch"])
            except GuardBlocked as e:
                rec.update(blockedByPolicy=True, error=str(e)[:300])
            except Exception as e:
                rec["error"] = f"verifier {type(e).__name__}: {str(e)[:200]}"
    u = client.usage_summary()
    rec.update(outputTokens=u["outputTokens"], seconds=round(time.time() - started, 1))
    return rec


def evaluate(args) -> int:
    from diocle_converter.config import Settings

    training = load(DIR / "training.json", {})
    if training.get("status") != "completed":
        raise SystemExit("no completed training job")
    usd_per_minute = args.usd_per_gpu_hour * args.accelerator_count / 60
    limit_minutes = min(args.max_minutes, args.approve_usd / usd_per_minute)
    print(f"limit: {limit_minutes:.0f} min, about ${limit_minutes * usd_per_minute:.2f}", flush=True)
    fw = distill.Fireworks.from_env()
    deployment = fw.create_deployment(BASE_MODEL, args.accelerator, args.accelerator_count)
    deployment_id = deployment["name"].rsplit("/", 1)[-1]
    started = time.monotonic()
    state = load(DIR / "evaluation.json", {"status": "partial", "seed": EVAL_SEED, "cases": EVAL_CASES, "k": K, "programs": {}, "infrastructureLog": [],
                                           "deployment": {"accelerator": args.accelerator, "acceleratorCount": args.accelerator_count}})
    deleted = threading.Event()

    def finish() -> None:
        with lock:
            if deleted.is_set():
                return
            deleted.set()
        try:
            fw.delete_deployment(deployment_id)
            state["deployment"]["deleted"] = True
            print("deployment deleted", flush=True)
        except Exception as e:  # say so plainly: this one bills until it scales to zero
            state["deployment"]["deleted"] = False
            print(f"DELETE FAILED, delete it by hand on Fireworks: {type(e).__name__}: {str(e)[:200]}", flush=True)
        minutes = (time.monotonic() - started) / 60
        previous = state["deployment"].get("minutes", 0)
        state["deployment"].update(minutes=round(previous + minutes, 1), estimatedUsd=round((previous + minutes) * usd_per_minute, 2))

    watchdog = threading.Timer(limit_minutes * 60, finish)
    watchdog.daemon = True
    watchdog.start()
    try:
        distill.wait_for(lambda: fw.deployment(deployment_id), lambda d: d.get("state") == "READY", every=20, limit=1200)
        fw.load_adapter(deployment_id, OUTPUT_MODEL)
        time.sleep(30)
        suffix = f"#accounts/{fw.account}/deployments/{deployment_id}"
        models = {"base": BASE_MODEL + suffix, "tuned": f"accounts/{fw.account}/models/{OUTPUT_MODEL}{suffix}"}
        settings = replace(Settings.from_env(), mode="private", base_url="https://api.fireworks.ai/inference/v1")

        def unit(name: str, which: str, trial: int) -> None:
            for attempt in (1, 2):
                if deleted.is_set():
                    return
                try:
                    rec = first_try(HELD_OUT_DIRS[name], models[which], trial, settings, state)
                    break
                except Exception as e:
                    with lock:
                        state["infrastructureLog"].append({"unit": f"{name} {which} {trial}", "reason": type(e).__name__, "rerun": attempt == 1})
                    rec = {"trial": trial, "passed": False, "infrastructureFailure": True}
            if deleted.is_set() and rec.get("infrastructureFailure"):
                return  # the cap ended it: not reached, not a failure
            with lock:
                state["programs"][name][which].append(rec)
                atomic_write(DIR / "evaluation.json", json.dumps(state, indent=1) + "\n")
                print(f"{name} {which} {trial}: passed={rec['passed']} compiled={rec.get('compiled')} {rec.get('seconds')}s", flush=True)

        jobs = []
        for name in HELD_OUT_DIRS:
            state["programs"].setdefault(name, {"base": [], "tuned": []})
            for trial in range(1, K + 1):
                for which in ("base", "tuned"):
                    if not any(r["trial"] == trial for r in state["programs"][name][which]):
                        jobs.append((name, which, trial))
        with ThreadPoolExecutor(WORKERS) as pool:
            for f in [pool.submit(unit, *j) for j in jobs]:
                f.result()
        complete = all(len(p[w]) == K for p in state["programs"].values() for w in ("base", "tuned"))
        state["status"] = "complete" if complete else "partial"
    finally:
        watchdog.cancel()
        finish()
        atomic_write(DIR / "evaluation.json", json.dumps(state, indent=1) + "\n")
        report()
    return 0


def total(programs: dict, which: str) -> dict:
    rows = [(n, r) for n, p in programs.items() for r in p[which]]
    return {"attempts": len(rows), "passed": sum(r["passed"] for _, r in rows), "compiled": sum(bool(r.get("compiled")) for _, r in rows),
            "programsWithAPass": len({n for n, r in rows if r["passed"]})}


def report() -> None:
    import jsonschema

    state = load(HARVEST, {"teacher": os.environ.get("OPEN_MODEL_ID", distill.TEACHER_MARK), "reasoningEffort": "low", "spentUsd": 0.0, "units": {}})
    units = state["units"].values()
    passed = [u for u in units if u.get("line")]
    data = distill.dataset_bytes(lines_from(state))
    training = load(DIR / "training.json", {"status": "not-run"})
    evaluation = load(DIR / "evaluation.json", {"status": "not-run"})
    if evaluation.get("programs"):
        evaluation["totals"] = {w: total(evaluation["programs"], w) for w in ("base", "tuned")}
    result = {
        "version": "0.1",
        "teacher": {"model": state["teacher"], "host": "fireworks", "reasoningEffort": state["reasoningEffort"]},
        "student": {"baseModel": BASE_MODEL},
        "dataset": {"examples": len(passed), "repositoryPrograms": sum(u["kind"] == "repository" for u in passed),
                    "generatedPrograms": sum(u["kind"] == "generated" for u in passed), "sha256": distill.sha256(data),
                    "heldOut": list(distill.HELD_OUT),
                    "oracle": {"seed": distill.ORACLE_SEED, "cases": distill.ORACLE_CASES, "minRecords": distill.MIN_RECORDS},
                    "rejected": {g: sum(u.get("gate") == g for u in units) for g in distill.GATES},
                    "firstPassRejected": state.get("firstPassRejected", {})},
        "training": {"host": "fireworks", "loraRank": LORA_RANK, "epochs": EPOCHS,
                     "trainingTokensEstimate": distill.estimate_training_tokens(data, EPOCHS), **training},
        "evaluation": evaluation,
        "spend": {"teacherUsd": state["spentUsd"], "deploymentUsd": (evaluation.get("deployment") or {}).get("estimatedUsd", 0), "trainingUsd": None},
        "limits": LIMITS,
    }
    jsonschema.validate(result, json.loads(SCHEMA.read_text()))
    atomic_write(OUT, json.dumps(result, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="stage", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--generate", type=int, default=0)
    h.add_argument("--second-pass", action="store_true", help="retry generated programs whose Java never met a real comparison")
    sub.add_parser("dataset")
    t = sub.add_parser("train")
    t.add_argument("--go", action="store_true")
    e = sub.add_parser("evaluate")
    e.add_argument("--approve-usd", type=float, required=True)
    e.add_argument("--max-minutes", type=float, required=True)
    e.add_argument("--accelerator", required=True)
    e.add_argument("--accelerator-count", type=int, default=1)
    e.add_argument("--usd-per-gpu-hour", type=float, required=True)
    args = ap.parse_args()
    if args.stage == "harvest":
        return harvest(args.generate, args.second_pass)
    if args.stage == "dataset":
        return dataset()
    if args.stage == "train":
        return train(args.go)
    return evaluate(args)


if __name__ == "__main__":
    sys.exit(main())
