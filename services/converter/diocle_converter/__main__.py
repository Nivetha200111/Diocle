"""CLI.

  python -m diocle_converter smoke                       one tiny model call to check the key and endpoint
  python -m diocle_converter repair SAMPLE [--java-dir]  verify an existing conversion and repair it (bring your own)
  python -m diocle_converter run SAMPLE                  translate with the Meta model, then verify and repair
  python -m diocle_converter run-job SAMPLE_WITH_JCL     convert a whole SORT-then-COBOL JCL job end to end
  python -m diocle_converter transcribe IMAGE --out DIR [--against SAMPLE]
                                                         photo of a COBOL listing to COBOL (vision model, see vision.py)

repair and run read fix memory (runs/memory.json) and add to it when held-out certification passes.
A guard agent watches every run: its policy refuses to run Java that openly reaches beyond its files, and when
GUARD_MODEL_* is set its model reviews certified Java against the COBOL and can revoke certification (see guard.py).
smoke sends the guard its real request.
Pass --no-memory for a baseline run that neither reads nor writes it, or --memory-read-only to use the lessons
without adding any (visitor imports: code from strangers must not shape later runs).

run-job translates the job's one kind:"cobol" step with the Meta model (one call, same as `run`), generates
the SORT step and the job driver deterministically (diocle_converter.sortgen/pipeline, zero model calls),
and writes one jobPipelines[] entry (contracts/conversion-output.schema.json). It calls the analyzer's CLI
(read-only: services/analyzer/.venv/bin/python -m diocle_analyzer, the same hand-off services/api/deliver.py
already uses) to get the job's jobs[] shape; it never imports analyzer code directly.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .breaker import Breaker
from .client import ModelClient, usage_of
from .config import REPO_ROOT, Settings
from .crosscheck import make_crosschecker, summarize as crosscheck_summary
from .guard import Guard, GuardBlocked, describe_error, gated
from .memory import Memory, lesson_key, render
from .pipeline import generate_pipeline
from .repair import CERT_CASES, CERT_SEED, TEST_CASES, TEST_SEED, RepairAgent, report_passes, summarize_report
from .sources import Program
from .translate import translate
from .workspace import Workspace


def _verifier():
    try:
        from diocle_verifier.verify import validate_report, verify_sample
    except ImportError:
        sys.exit("diocle-verifier is not installed: pip install -e ../verifier")

    def verify(sample_dir: Path, standing_cases: list | None = None):
        """standing_cases (e.g. inputs that once broke the Java) are included in every later test and certification."""
        def run(java_dir: Path, seed: int, random_count: int, extra_cases: list | None = None) -> dict:
            cases = list(standing_cases or []) + list(extra_cases or [])
            report = verify_sample(sample_dir, java_dir, seed=seed, random_count=random_count, extra_cases=cases)
            validate_report(report)
            return report

        return run

    return verify


def _print_event(event: dict) -> None:
    if event["type"] == "agent-step":
        why = f"  why: {event['rationale']}" if event["rationale"] else ""
        print(f"[round {event['round']} · step {event['step']:>2}] {event['tool']} {json.dumps(event['argsSummary'])}{why}")
        print(f"    -> {event['resultSummary'].splitlines()[0] if event['resultSummary'] else ''}")
    elif event["type"] == "guard":
        print(f"[guard{' BLOCKED' if event.get('blocked') else ''}] {event.get('message', '')}")
    elif event["type"] == "certification":
        print(f"=== round {event['round']} certification on held-out inputs: {'PASS' if event['passed'] else 'FAIL'}")
        print("    " + event["result"].replace("\n", "\n    "))
    else:
        print(f"[{event['type']}] {event.get('message', '')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_converter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("smoke")
    for name in ("repair", "run"):
        p = sub.add_parser(name)
        p.add_argument("sample_dir", type=Path)
        p.add_argument("--no-memory", action="store_true", help="baseline: do not read or write fix memory")
        p.add_argument("--memory-read-only", action="store_true", help="use fix memory but never add lessons to it")
        p.add_argument("--breaker", action="store_true", help="after certification, let a breaker agent attack the Java")
        p.add_argument("--crosscheck", action="store_true", help="after certification, Muse Spark Open (CROSSCHECK_MODEL_* or "
                       "OPEN_MODEL_*) independently looks for inputs where the Java differs (about $0.05 per run)")
        p.add_argument("--tiers", action="store_true", help="escalate by task difficulty: after each failed certification "
                       "round the repair agent moves to the next tier (MODEL_TIER_2_ID, MODEL_TIER_3_ID, hosted mode), and "
                       "the breaker attacks at MODEL_TIER_BREAKER (default 2) and a break after certification resumes repair at "
                       "MODEL_TIER_AFTER_BREAK (default 2); hard caps MODEL_ESCALATION_MAX_CALLS / _MAX_USD")
        p.add_argument("--swarm", action="store_true", help="pick up lessons other agents certify while this run is going")
        if name == "repair":
            p.add_argument("--java-dir", type=Path, help="existing Java conversion (default: the sample's javaConversion dir)")
    tr = sub.add_parser("transcribe", help="photo/scan of a COBOL listing to COBOL, gated by the compiler and a differential run")
    tr.add_argument("image", type=Path, help="PNG or JPEG, at most 2 MB")
    tr.add_argument("--out", type=Path, required=True, help="sample directory to write (src/*.cbl, transcription.json)")
    tr.add_argument("--against", type=Path, help="the original sample to prove the transcription identical to")
    job_parser = sub.add_parser("run-job")
    job_parser.add_argument("sample_dir", type=Path)
    args = parser.parse_args(argv)

    if args.command == "transcribe":
        return _transcribe(args)

    settings = Settings.from_env()
    client = ModelClient(settings)
    guard_settings = Settings.guard_from_env()
    guard_client = ModelClient(guard_settings) if guard_settings else None
    print(f"model: {settings.model} ({settings.mode}), reasoning_effort={settings.reasoning_effort}, "
          f"caps: {settings.max_calls_per_run} calls/run, {settings.max_calls_per_round}/round, {settings.max_rounds} rounds")
    print(f"guard: policy on every run; review by {guard_settings.model} ({guard_settings.max_calls_per_run} calls/run)"
          if guard_settings else "guard: policy only (set GUARD_MODEL_* for the model review)")

    if args.command == "smoke":
        return _smoke(client, guard_client)

    if args.command == "run-job":
        return _run_job(args.sample_dir, settings, client)

    program = Program.load(args.sample_dir)
    run_dir = REPO_ROOT / "runs" / f"{args.sample_dir.resolve().name}-{time.strftime('%Y%m%d-%H%M%S')}"
    events: list[dict] = []

    run_dir.mkdir(parents=True)
    base = {"program": program.name, "command": args.command,
            "sample": str(program.sample_dir.resolve().relative_to(REPO_ROOT))}

    def save_live() -> None:  # lets the API show a run while it is still in progress
        tmp = run_dir / "run.json.tmp"
        tmp.write_text(json.dumps({**base, "status": "running", "certified": False, "rounds": [],
                                   "usage": client.usage_summary()}, indent=2) + "\n")
        tmp.replace(run_dir / "run.json")

    def on_event(event: dict) -> None:
        events.append(event)
        with (run_dir / "events.jsonl").open("a") as f:
            f.write(json.dumps(event) + "\n")
        save_live()
        _print_event(event)

    guard = Guard(guard_client, dd_names=tuple(f["dd"] for f in program.files), on_event=on_event)
    save_live()
    print(f"run started runs/{run_dir.name}", flush=True)

    try:
        return _convert(args, settings, client, program, run_dir, base, events, on_event, guard)
    except BaseException as e:  # never leave a run looking "running" forever
        guard.blocked = guard.blocked or isinstance(e, GuardBlocked)
        on_event({"type": "stage", "stage": "done", "message": f"run failed: {_describe(e)}"})
        _atomic_write(run_dir / "run.json", {**base, "status": "not-certified", "certified": False, "rounds": [],
                                             "usage": usage_of(client.calls + (guard_client.calls if guard_client else [])),
                                             "guard": guard.summary(), "error": _describe(e)})
        raise


def _transcribe(args) -> int:
    from .vision import transcribe

    settings = Settings.vision_from_env()
    print(f"vision model: {settings.model if settings else 'off (VISION_MODEL_ID is empty)'}")
    record = transcribe(args.image, args.out, settings=settings, against=args.against)
    cost = record["usage"]["estimatedCostUsd"]
    print(f"status: {record['status']}" + (f" ({record['reason']})" if record.get("reason") else ""))
    print(f"calls: {record['usage']['calls']}, cost: " + ("n/a" if cost is None else f"${cost:.4f}"))
    d = record["differential"]
    if d and d["ran"]:
        print(f"differential vs {d['against']}: {d['matched']}/{d['inputs']} inputs matched, stdout {d['stdoutMatch']}, exit code {d['exitCodeMatch']}")
    print(f"record: {args.out / 'transcription.json'}")
    return 0 if record["status"] in ("verified-identical", "compiled-unchecked") else 1


def _smoke(client: ModelClient, guard_client: ModelClient | None) -> int:
    """One tiny call per model; the guard gets its real request (structured output) on a tiny clean program, so a wrong
    model ID or an unsupported response format shows up here, not as silent "error" reviews later."""
    import tempfile

    ok = True
    for c in [client] + ([guard_client] if guard_client else []):
        if c.settings.model not in PRICES:
            ok = False
            print(f"WARNING: {c.settings.model} has no price in config.PRICES: run costs become unknown and visitor "
                  "imports stop (the budget fails closed)")
    choice = client.chat(role="smoke", round=0, messages=[{"role": "user", "content": "Reply with exactly: DIOCLE OK"}])
    print(f"{client.settings.model}: {choice.message.content}")
    if guard_client:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Smoke.java").write_text('public class Smoke { public static void main(String[] a) { '
                                               'System.out.println(System.getenv("DD_IN")); } }')
            review = Guard(guard_client, ("IN",)).review("       PROGRAM-ID. SMOKE.", Path(tmp))
        print(f"{guard_client.settings.model} (guard review): {review['verdict']} {review['summary'][:200]}")
        ok = ok and review["verdict"] != "error"
    print(json.dumps({k: v for k, v in usage_of(client.calls + (guard_client.calls if guard_client else [])).items()
                      if k != "modelCalls"}))
    return 0 if ok else 1


def _describe(e: BaseException) -> str:
    """Model-provider errors are published by type and HTTP status only: their messages can echo account details."""
    return describe_error(e) if getattr(e, "status_code", None) else f"{type(e).__name__}: {str(e)[:300]}"


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def _convert(args, settings: Settings, client: ModelClient, program: Program, run_dir: Path, base: dict,
             events: list[dict], on_event, guard: Guard) -> int:
    guard.inspect_source(program.as_text())
    if args.command == "repair":
        meta = json.loads((program.sample_dir / "sample.json").read_text())
        source = (args.java_dir or program.sample_dir / meta["javaConversion"]["dir"]).resolve()
        workspace = Workspace.from_copy(source, run_dir / "java")
        translation = None
    else:
        workspace = Workspace(run_dir / "java")
        on_event({"type": "stage", "stage": "translating", "message": f"Translating {program.name} with {settings.model}"})
        translation = translate(program, client, workspace)
        print(f"wrote {translation['file']}; translator notes: {translation['notes'][:400]}")

    memory = None if args.no_memory else Memory(REPO_ROOT / "runs" / "memory.json")
    known = memory.load() if memory else []
    if known:
        on_event({"type": "memory", "message": f"Loaded {len(known)} lessons from earlier certified repairs"})
    standing_cases: list = []
    verify = gated(_verifier()(program.sample_dir, standing_cases), guard)  # the policy is checked before Java runs
    agent = RepairAgent(program, workspace, client, verify, on_event, hints=render(known),
                        memory_feed=memory.load if (memory and args.swarm) else None,
                        known_lessons={lesson_key(l["pattern"]) for l in known}, escalate=bool(args.tiers))
    if args.tiers and not settings.tiers:
        on_event({"type": "stage", "stage": "repairing", "message": "--tiers ignored: no MODEL_TIER_2_ID / "
                  "MODEL_TIER_3_ID configured, or this run is not in hosted mode"})
    on_event({"type": "stage", "stage": "verifying", "message": "Running GnuCOBOL and the Java on the same inputs"})
    try:
        first = verify(workspace.root, TEST_SEED, TEST_CASES)
    except GuardBlocked:  # the repair agent is told why and removes the code
        first = None
        on_event({"type": "stage", "stage": "repairing",
                  "message": "Starting point: the guard refused to run the first Java; repair agent takes over"})
    if first is not None:
        (run_dir / "initial-verification.json").write_text(json.dumps(first, indent=2) + "\n")
        s0 = first["summary"]
        on_event({"type": "stage", "stage": "repairing",
                  "message": f"Starting point: {s0['passed']}/{s0['total']} cases match; repair agent takes over"})
    unverifiable = original_failure(first)
    held_out = verify(workspace.root, CERT_SEED, CERT_CASES) if first is not None and report_passes(first) else None
    if unverifiable:
        on_event({"type": "stage", "stage": "done", "message": f"Not certified: {unverifiable}. Stopped before any repair round."})
        outcome = {"certified": False, "rounds": [], "certificationReport": None, "lessons": []}
    elif held_out is not None and report_passes(held_out):
        print("conversion already passes, including held-out inputs: no repair needed")
        outcome = {"certified": True, "rounds": [], "certificationReport": held_out, "certificationSeed": CERT_SEED,
                   "lessons": []}
        on_event({"type": "certification", "round": 0, "passed": True,
                  "result": summarize_report(held_out, limit=3, for_agent=False)})
    else:
        outcome = agent.run()

    breaker_summary = None
    if args.breaker and outcome["certified"]:
        outcome, breaker_summary = _attack(program, workspace, client, verify, agent, standing_cases, outcome,
                                           run_dir, settings, on_event, tiered=bool(args.tiers))

    crosscheck_result = None
    if args.crosscheck and outcome["certified"]:
        outcome, crosscheck_result = _crosscheck(program, workspace, client, verify, agent, standing_cases, outcome,
                                                 run_dir, settings, on_event)
    if outcome["certified"]:
        guard.review(program.as_text(), workspace.root)
        outcome = guard.apply(outcome)
        if guard.blocked:
            on_event({"type": "stage", "stage": "done", "message": "Not certified: the guard agent blocked this Java"})

    learned = (memory.learn(outcome["lessons"], program=program.name, run_id=run_dir.name)
               if memory and outcome["certified"] and not args.memory_read_only else 0)
    usage = usage_of(client.calls + (guard.client.calls if guard.client else []))
    origin = (f"copied from {source.relative_to(REPO_ROOT)}" if translation is None
              else f"translated by {settings.model}")
    patches = sum(1 for e in events if e.get("tool") == "patch_java" and e["resultSummary"].startswith("applied"))
    (run_dir / "PROVENANCE.md").write_text(
        f"# Provenance of java/\n\n- Started as: {origin}\n"
        f"- Then modified by the Diocle repair agent ({settings.model}, {settings.mode} mode): {patches} applied patches. "
        "See events.jsonl for every step.\n"
        "- Any header comment inside the Java files describes the starting file, not the repaired result.\n"
    )
    _atomic_write_text(run_dir / "events.jsonl", "".join(json.dumps(e) + "\n" for e in events))
    if outcome["certificationReport"]:
        _atomic_write(run_dir / "verification-report.json", outcome["certificationReport"])
    _atomic_write(run_dir / "run.json", {
        **base, "javaOrigin": origin, "translation": translation,
        "status": "certified" if outcome["certified"] else "not-certified", "certified": outcome["certified"],
        "rounds": outcome["rounds"], "certificationSeed": outcome.get("certificationSeed"), "usage": usage,
        "memory": {"enabled": memory is not None, "used": len(known), "learned": learned, "lessons": outcome["lessons"]},
        "breaker": breaker_summary, "crosscheck": crosscheck_result, "swarm": bool(args.swarm and memory),
        "tiers": ({"enabled": True, "configured": [settings.model, *settings.tiers], "escalations": agent.escalations,
                   "breakerModel": settings.tier_model(settings.breaker_tier), "escalatedCalls": client.escalated_calls,
                   "escalatedUsd": round(client.escalated_usd, 6), "capCalls": settings.escalation_max_calls,
                   "capUsd": settings.escalation_max_usd} if args.tiers and settings.tiers else None),
        "guard": guard.summary(), "error": unverifiable,
    })
    print(f"\n{'CERTIFIED' if outcome['certified'] else 'NOT CERTIFIED'}  ·  {usage['calls']} model calls, "
          f"{usage['inputTokens']} in ({usage['cachedInputTokens']} cached) / {usage['outputTokens']} out tokens, est. ${usage['estimatedCostUsd']}")
    if memory:
        print(f"fix memory: used {len(known)} lessons, learned {learned} new")
    print(f"run saved to {run_dir.relative_to(REPO_ROOT)}")
    return 0 if outcome["certified"] else 1


def original_failure(report: dict | None) -> str | None:
    """Why this program can never be verified, when the verifier could not compile the ORIGINAL COBOL (e.g. a missing
    period after PROGRAM-ID that IBM's compiler accepts and GnuCOBOL -std=ibm rejects). The Java cannot fix that, so no
    repair rounds, breaker or review should be paid for."""
    original = ((report or {}).get("runs") or {}).get("original") or {}
    if original.get("compiled") is not False:
        return None
    stderr = original.get("stderr") or ""
    first = next((l.strip() for l in stderr.splitlines() if "error" in l), stderr.strip().splitlines()[0] if stderr.strip() else "")
    first = re.sub(r"^\S*/", "", first)  # keep the file name, not the sandbox's temp path
    return f"the original COBOL does not compile under GnuCOBOL (-std=ibm), so it cannot be verified: {first[:240]}"


def _analyzer_jobs(sample_dir: Path) -> list[dict]:
    """jobs[] from services/analyzer's own CLI (read-only hand-off, same as services/api/deliver.py's
    `analyze()`: a subprocess call into the analyzer's venv, never an import of analyzer code)."""
    analyzer_python = REPO_ROOT / "services" / "analyzer" / ".venv" / "bin" / "python"
    if not analyzer_python.exists():
        raise SystemExit(f"{analyzer_python} not found: set up services/analyzer's venv first "
                         "(pip install -e services/analyzer)")
    out = sample_dir / ".diocle-analysis-report.json"  # scratch file, not part of the sample's committed shape
    subprocess.run([str(analyzer_python), "-m", "diocle_analyzer", str(sample_dir), "--out", str(out)],
                   cwd=REPO_ROOT / "services" / "analyzer", check=True, capture_output=True, text=True)
    report = json.loads(out.read_text())
    out.unlink()
    return report["jobs"]


def _run_job(sample_dir: Path, settings: Settings, client: ModelClient) -> int:
    """Convert one whole SORT-then-COBOL JCL job end to end: translate its one kind:"cobol" step with the
    Meta model (one call), generate the SORT step and the job driver deterministically (zero model calls),
    and write a jobPipelines[] manifest (see contracts/conversion-output.schema.json)."""
    sample_dir = sample_dir.resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    jobs = [j for j in _analyzer_jobs(sample_dir) if j["convertible"]]
    if not jobs:
        raise SystemExit(f"{sample_dir}: no convertible job found (see the analysis report's "
                         "notConvertibleReason for each job)")
    job = jobs[0]
    cobol_step = next(s for s in job["steps"] if s["kind"] == "cobol")
    if cobol_step["program"] != meta["program"]:
        raise SystemExit(f"job {job['name']}'s COBOL step runs {cobol_step['program']!r}, but "
                         f"{sample_dir} is the sample for {meta['program']!r}")

    program = Program.load(sample_dir)
    run_dir = REPO_ROOT / "runs" / f"{sample_dir.name}-job-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True)
    workspace = Workspace(run_dir / "java")
    print(f"Translating {program.name} (job {job['name']}'s {cobol_step['step']} step) with {settings.model}")
    translation = translate(program, client, workspace)
    print(f"wrote {translation['file']}; translator notes: {translation['notes'][:400]}")

    try:
        from diocle_verifier.layout import load_fields, record_length
    except ImportError:
        sys.exit("diocle-verifier is not installed: pip install -e ../verifier (needed for record-length math)")
    # meta["files"] (sample.json) only describes the COBOL program's own DDs (e.g. MSTIN/TXNIN/NEWMST/EXCOUT);
    # a SORT step's DDs (e.g. SORTIN) are JCL-level, not in sample.json, so they inherit the record length
    # of whichever COBOL-side DD they are wired to (SORT never reformats records in this v1 scope -- see
    # pipeline.py's own OUTREC-reformatting guard, which would reject a mismatch if one existed).
    record_lengths = {f["dd"]: record_length(load_fields(f["layout"])) for f in meta["files"]}
    for edge in job["wiring"]:
        if edge["fromDd"] not in record_lengths and edge["toDd"] in record_lengths:
            record_lengths[edge["fromDd"]] = record_lengths[edge["toDd"]]
    sort_step = next((s for s in job["steps"] if s["kind"] == "sort"), None)
    if sort_step is not None:
        sort_dds = [d for d in sort_step["dds"] if d not in ("SYSIN", "SYSOUT")]
        sort_in_dd = sort_dds[0]
        known = next((record_lengths[d] for d in sort_dds if d in record_lengths), None)
        if known is not None:
            for d in sort_dds:
                record_lengths.setdefault(d, known)

    collation = meta.get("collation", "ascii")
    jcl_dir = sample_dir / "jcl"
    wired_dds = {e["toDd"] for e in job["wiring"]}  # these DDs are produced in-job; generate_pipeline wires them
    # Every other DD needs an external path: a fixture file under jcl/<dd>.txt if one exists (e.g.
    # jcl/SORTIN.txt, the real JCL-level fixture the analyzer-agent shipped for the SORT step's own input),
    # else the sample's own "fixtureFiles" (sample.json: the same per-DD seed records the verifier already
    # uses for this program's single-program certification, see diocle_verifier.multi), else a fresh file
    # this run writes nothing into (an unfed input then fails loudly, which is correct: run-job does not
    # invent data the sample does not provide). Outputs always land fresh in run_dir.
    all_dds = {f["dd"]: f["direction"] for f in meta["files"]}
    if sort_step is not None:
        for dd in sort_step["dds"]:
            if dd not in ("SYSIN", "SYSOUT"):
                all_dds.setdefault(dd, "input" if dd == sort_in_dd else "output")
    dd_paths = {}
    for dd, direction in all_dds.items():
        if dd in wired_dds:
            continue
        if direction == "output":
            dd_paths[dd] = str(run_dir / f"{dd}.out")
            continue
        fixture = jcl_dir / f"{dd}.txt"
        if fixture.exists():
            dd_paths[dd] = str(fixture)
        elif dd in meta.get("fixtureFiles", {}):
            seeded = run_dir / f"{dd}.in"
            seeded.write_text("".join(r + "\n" for r in meta["fixtureFiles"][dd]))
            dd_paths[dd] = str(seeded)
        else:
            dd_paths[dd] = str(run_dir / f"{dd}.in")

    pipeline_dir = run_dir / "job"
    manifest = generate_pipeline(job, cobol_main_class=translation["mainClass"], record_lengths=record_lengths,
                                 collation=collation, out_dir=pipeline_dir, dd_paths=dd_paths)
    deterministic_steps = [s["step"] for s in manifest["steps"] if s["origin"] == "deterministic"]
    model_steps = [s["step"] for s in manifest["steps"] if s["origin"] == "model"]
    usage = client.usage_summary()
    print(f"\njob {job['name']}: {len(model_steps)} step(s) translated by the model ({', '.join(model_steps)}), "
          f"{len(deterministic_steps)} step(s) generated deterministically with zero model calls "
          f"({', '.join(deterministic_steps)})")
    print(f"{usage['calls']} model calls, {usage['inputTokens']} in ({usage['cachedInputTokens']} cached) / "
          f"{usage['outputTokens']} out tokens, est. ${usage['estimatedCostUsd']}")
    _atomic_write(run_dir / "job-pipeline.json", {"jobPipelines": [manifest], "usage": usage})
    print(f"job pipeline saved to {run_dir.relative_to(REPO_ROOT)}")
    return 0


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _attack(program, workspace, client, verify, agent, standing_cases, outcome, run_dir, settings, on_event,
            attacker=None, who="Breaker", tiered=False):
    """Breaker cycles: attack; anything that breaks becomes a standing case and the agent repairs and re-certifies.
    The run stays certified only if the last attack found nothing. Bounded by MODEL_MAX_ATTACK_ROUNDS,
    MODEL_MAX_BREAKER_CYCLES and the run's overall call cap."""
    meta = json.loads((program.sample_dir / "sample.json").read_text())
    if "layouts" not in meta and attacker is None:
        on_event({"type": "stage", "stage": "attacking",
                  "message": "Breaker skipped: it designs single-file records, and this program has several files"})
        return outcome, {"rounds": 0, "tried": 0, "broke": 0, "repairCycles": 0, "fixed": False, "counterexamples": [],
                         "skipped": "multi-file program"}
    breaker = attacker or Breaker(program, workspace, client, verify, meta["layouts"]["input"], on_event,
                                  model=settings.tier_model(settings.breaker_tier) if tiered else None)  # tier 2 by default
    found: list[dict] = []
    cycles = 0
    on_event({"type": "stage", "stage": "attacking", "message": f"{who} is designing inputs to break the certified Java"})
    broken = breaker.attack(rounds=1 if attacker else settings.max_attack_rounds, label="crosscheck" if attacker else "attack")
    while broken:
        found += broken
        standing_cases += [b["case"] for b in broken]
        if cycles >= settings.max_breaker_cycles:
            outcome = {**outcome, "certified": False, "lessons": [], "certificationReport": None}
            on_event({"type": "stage", "stage": "done",
                      "message": f"Not certified: {len(broken)} {who.lower()} input(s) still break the Java and the repair budget is spent"})
            break
        cycles += 1
        note = (f"A {who.lower()} found inputs where the Java differs from the COBOL. They are now part of every test "
                "and certification:\n" + "\n".join(f"- input={b['case'].record!r} ({b['why']}): {b['diff']}" for b in broken)
                + "\nFix the root cause, then finish.")
        on_event({"type": "stage", "stage": "repairing", "message": f"Repair agent resumes with {len(broken)} counterexample(s)"})
        outcome = agent.resume(note, extra_rounds=1)
        if not outcome["certified"]:
            break
        on_event({"type": "stage", "stage": "attacking", "message": f"{who} attacks the repaired Java again"})
        broken = breaker.attack(rounds=1, label=f"recheck{cycles}")
    summary = {"rounds": len({a["id"].rsplit("-", 1)[0] for a in breaker.attempts}), "tried": len(breaker.attempts),
               "broke": len(found), "repairCycles": cycles, "fixed": bool(found) and outcome["certified"],
               "counterexamples": [{"input": b["case"].record, "why": b["why"], "diff": b["diff"]} for b in found]}
    if attacker is None:
        _atomic_write(run_dir / "breaker.json", {**summary, "attempts": breaker.attempts})
    return outcome, summary


def _crosscheck(program, workspace, client, verify, agent, standing_cases, outcome, run_dir, settings, on_event):
    """Muse Spark Open independently looks for a divergence. Skipped (and said so) if it is not configured, if the
    run is already on the open model, or if the program has several files. Its model calls are merged into the run's
    usage. Whatever it finds is only a candidate: a case counts only if GnuCOBOL and the Java really differ on it."""
    def skip(reason: str):
        on_event({"type": "crosscheck", "message": f"Cross-check skipped: {reason}"})
        return outcome, {"skipped": reason}

    try:
        cross_settings = settings.for_crosscheck()
    except ValueError:  # e.g. CROSSCHECK_MAX_CALLS=abc: a bonus check must not crash a certified run
        return skip("invalid CROSSCHECK_* setting")
    if cross_settings is None:
        return skip("this run is already on the open model" if settings.mode == "private"
                    else "no CROSSCHECK_MODEL_* or OPEN_MODEL_* configured")
    meta = json.loads((program.sample_dir / "sample.json").read_text())
    if "layouts" not in meta:
        return skip("it designs single-file records, and this program has several files")
    try:
        cross_client = ModelClient(cross_settings)
    except Exception as e:  # client construction (bad base URL etc.)
        return skip(f"could not create the client ({type(e).__name__})")
    checker = make_crosschecker(program, workspace, cross_client, verify, meta["layouts"]["input"], on_event)
    on_event({"type": "stage", "stage": "attacking",
              "message": f"Independent cross-check by {cross_settings.model} ({cross_settings.mode} mode)"})
    standing_before, certified_before = len(standing_cases), outcome
    try:
        outcome, summary = _attack(program, workspace, cross_client, verify, agent, standing_cases, outcome, run_dir,
                                   settings, on_event, attacker=checker, who="Cross-checker")
    except Exception as e:  # a bonus check must not fail a certified run (host down, rate limit, bad answer)...
        on_event({"type": "crosscheck", "message": f"Cross-check unavailable: {type(e).__name__}"})
        if len(standing_cases) > standing_before:  # ...unless it already changed the Java: then it is not certified
            return {**certified_before, "certified": False, "lessons": [], "certificationReport": None}, \
                {"skipped": f"unavailable: {type(e).__name__}"}
        return certified_before, {"skipped": f"unavailable: {type(e).__name__}"}
    finally:
        client.calls.extend(cross_client.calls)  # one usage record per run, priced per call by its own model
    result = crosscheck_summary(checker, cross_settings.model, summary)
    on_event({"type": "crosscheck", "tried": result["casesValid"], "broke": result["mismatches"],
              "message": f"Cross-check: {result['casesValid']} valid cases of {result['casesProposed']} proposed, "
                         f"{result['mismatches']} real mismatch(es)"})
    return outcome, result

if __name__ == "__main__":
    sys.exit(main())
