"""Headline before-and-after measurement (plan: docs/MEASUREMENT.md, committed before any model call).

  PYTHONPATH=services/converter:services/verifier:services/analyzer <python with the converter deps> eval/headline.py

For each fixed program: K first translations by the translator alone (no repair, no breaker, no memory), each verified on
1,000 held-out random inputs (seed 8801); then ONE full `run --no-memory --breaker`. Sequential and resumable: results go
to eval/results-headline.json after every unit and finished units are skipped on restart. No new unit starts once the
running estimated spend reaches STOP_USD; the cap is HARD_CAP_USD. Needs the Meta key in the repo-root .env (read
in-process by the converter; this script never reads or prints it). Guard model review and tiers are switched off.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("services/converter", "services/verifier", "services/analyzer"):
    sys.path.insert(0, str(ROOT / p))

# The plan's environment: default contributor model, no tiers, guard policy-only. Empty values win over .env
# because the converter only fills variables that are not set.
os.environ.update({"MODEL_MODE": "hosted", "META_MODEL_ID": "muse-spark-1.3-contributor", "MODEL_TIER_2_ID": "",
                   "MODEL_TIER_3_ID": "", "GUARD_MODEL_API_KEY": "", "GUARD_MODEL_ID": "", "GUARD_MODEL_BASE_URL": "",
                   "GUARD_MAX_CALLS": "0", "CROSSCHECK_MODEL_ID": "", "DOC_MODEL_ID": "", "VISION_MODEL_ID": ""})

OUT = ROOT / "eval" / "results-headline.json"
HELD_OUT_SEED, HELD_OUT_CASES, K = 8801, 1000, 3
HARD_CAP_USD, STOP_USD, RUN_CAP_USD = 1.00, 0.85, 0.25
PROGRAMS = [  # (name, directory, seen-or-unseen); order as in docs/MEASUREMENT.md
    ("BRNCHSUM", "eval/samples/brnchsum", "unseen"), ("CHQCLR", "eval/samples/chqclr", "unseen"),
    ("FXCONV", "eval/samples/fxconv", "unseen"), ("LOANAMRT", "eval/samples/loanamrt", "unseen"),
    ("INTACCR", "samples/interest-accrual", "seen"), ("TXNPOST", "samples/txn-posting", "seen"),
    ("FEESCHD", "samples/fee-schedule", "seen"), ("TXNLIST", "samples/display-report", "seen"),
    ("LDGRWRT", "samples/ledger-rewrite", "seen"), ("FEEPOST", "samples/call-identifier", "seen"),
    ("DAYCTRL", "samples/daily-control", "seen"), ("ACCTRPT", "samples/db2-account-report", "seen"),
    ("ACCTMTCH", "samples/account-match", "seen"), ("PKDPOST", "samples/packed-posting", "seen"),
    ("LOYWAIVE", "samples/loyalty-waiver", "seen"),
]


def spent(results: dict) -> float:
    total = 0.0
    for r in results["programs"].values():
        for t in r.get("firstTry", []):
            total += t.get("costUsd") or 0
        total += (r.get("diocle") or {}).get("costUsd") or 0
    return round(total, 6)


def save(results: dict) -> None:
    results["spentUsd"] = spent(results)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=2) + "\n")
    tmp.replace(OUT)


def is_infra(e: BaseException) -> bool:
    status = getattr(e, "status_code", None)
    return type(e).__name__ in ("APIConnectionError", "APITimeoutError", "ConnectionError", "TimeoutError") \
        or (isinstance(status, int) and (status >= 500 or status == 429))


def first_try(directory: str, trial: int, log: list) -> dict:
    from diocle_converter.client import ModelClient
    from diocle_converter.config import Settings
    from diocle_converter.sources import Program
    from diocle_converter.translate import translate
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import passes, verify_sample

    sample = ROOT / directory
    for attempt in (1, 2):
        client = ModelClient(Settings.from_env())
        started = time.time()
        rec = {"trial": trial, "seed": HELD_OUT_SEED, "cases": HELD_OUT_CASES}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ws = Workspace(Path(tmp) / "java")
                program = Program.load(sample)
                try:
                    translate(program, client, ws)
                    rec["translated"] = True
                except Exception as e:
                    if is_infra(e) and attempt == 1:
                        raise
                    rec.update(translated=False, passed=False, error=f"{type(e).__name__}: {str(e)[:200]}")
                if rec["translated"]:
                    try:
                        report = verify_sample(sample, ws.root, seed=HELD_OUT_SEED, random_count=HELD_OUT_CASES)
                        s, runs = report["summary"], report["runs"]
                        rec.update(passed=passes(report), total=s["total"], failedCases=s["failed"],
                                   compiled=bool(runs["converted"]["compiled"]), exitCodeMatch=runs.get("exitCodeMatch"),
                                   stdoutMatch=runs["stdoutMatch"])
                    except Exception as e:
                        rec.update(passed=False, error=f"verifier {type(e).__name__}: {str(e)[:200]}")
        except Exception as e:  # infrastructure failure on the first attempt: logged, one re-run allowed
            log.append({"unit": f"{directory} first-try {trial}", "reason": f"{type(e).__name__}", "rerun": True})
            rec = None
        if rec is not None:
            u = client.usage_summary()
            rec.update(costUsd=u["estimatedCostUsd"], calls=u["calls"], inputTokens=u["inputTokens"],
                       outputTokens=u["outputTokens"], seconds=round(time.time() - started, 1))
            return rec
    return {"trial": trial, "passed": False, "infrastructureFailure": True, "costUsd": 0.0}


def full_run(directory: str, budget_left: float) -> dict:
    started = time.time()
    cap = round(min(RUN_CAP_USD, budget_left), 3)
    proc = subprocess.run([sys.executable, "-m", "diocle_converter", "run", str(ROOT / directory), "--no-memory", "--breaker",
                           "--max-usd", str(cap)], cwd=ROOT / "services" / "converter", capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in
                               ("services/converter", "services/verifier", "services/analyzer"))})
    m = re.search(r"run saved to runs/(\S+)", proc.stdout) or re.search(r"run started runs/(\S+)", proc.stdout)
    rid = m.group(1) if m else None
    meta = json.loads((ROOT / "runs" / rid / "run.json").read_text()) if rid and (ROOT / "runs" / rid / "run.json").exists() else {}
    br = meta.get("breaker") or {}
    rounds = meta.get("rounds", [])
    initial = None
    if rid and (ROOT / "runs" / rid / "initial-verification.json").exists():
        s = json.loads((ROOT / "runs" / rid / "initial-verification.json").read_text())["summary"]
        initial = {"passed": s["passed"], "total": s["total"]}
    return {"runId": rid, "exitCode": proc.returncode, "certified": bool(meta.get("certified")),
            "status": meta.get("status"), "error": meta.get("error"), "repairRounds": len(rounds),
            "initial200": initial, "breaker": {k: br.get(k) for k in ("rounds", "tried", "broke", "repairCycles", "fixed")} if br else None,
            "modelCalls": (meta.get("usage") or {}).get("calls"), "costUsd": (meta.get("usage") or {}).get("estimatedCostUsd"),
            "inputTokens": (meta.get("usage") or {}).get("inputTokens"), "outputTokens": (meta.get("usage") or {}).get("outputTokens"),
            "runCapUsd": cap, "minutes": round((time.time() - started) / 60, 1),
            "stdoutTail": proc.stdout.strip().splitlines()[-3:] if not meta else None}


def merge() -> int:
    """Combine the shard files (and the sequential file) into eval/results-headline.json: per program, the most complete record wins."""
    merged = json.loads(OUT.read_text()) if OUT.exists() else None
    for f in sorted(OUT.parent.glob("results-headline.shard*.json")):
        d = json.loads(f.read_text())
        if merged is None:
            merged = d
            continue
        known = merged.get("infrastructureLog", [])
        merged["infrastructureLog"] = known + [x for x in d.get("infrastructureLog", []) if x not in known]
        for name, r in d["programs"].items():
            m = merged["programs"].get(name)
            if m is None or (len(r["firstTry"]), r["diocle"] is not None) > (len(m["firstTry"]), m["diocle"] is not None):
                merged["programs"][name] = r
    if merged is None:
        print("nothing to merge", flush=True)
        return 1
    save(merged)
    print(f"merged: {len(merged['programs'])} programs, spend ${merged['spentUsd']:.4f}", flush=True)
    return 0


def main() -> int:
    global OUT
    import argparse
    ap = argparse.ArgumentParser(description="Headline measurement; --shard I/N runs every N-th program (parallel workers), --merge combines the shard files.")
    ap.add_argument("--shard", help="I/N: only programs with index %% N == I; progress goes to results-headline.shardI.json")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.merge:
        return merge()
    todo, limit = PROGRAMS, STOP_USD
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        base = OUT
        OUT = base.with_name(f"results-headline.shard{i}.json")
        if not OUT.exists() and base.exists():
            OUT.write_text(base.read_text())  # start from the progress made before sharding
        todo = [p for k, p in enumerate(PROGRAMS) if k % n == i]
        # Each worker starts from the same base file (its spend is counted in every copy): split only what is left of the stop line.
        done = spent(json.loads(base.read_text())) if base.exists() else 0.0
        limit = done + (STOP_USD - done) / n  # the merged total is checked after the merge
    results = json.loads(OUT.read_text()) if OUT.exists() else {
        "plan": "docs/MEASUREMENT.md", "model": "muse-spark-1.3-contributor", "heldOutSeed": HELD_OUT_SEED,
        "heldOutCases": HELD_OUT_CASES, "k": K, "hardCapUsd": HARD_CAP_USD, "stopUsd": STOP_USD, "memory": False,
        "guard": "policy only", "infrastructureLog": [], "programs": {}}
    for name, directory, status in todo:
        r = results["programs"].setdefault(name, {"directory": directory, "status": status, "firstTry": [], "diocle": None})
        for trial in range(1, K + 1):
            if len(r["firstTry"]) >= trial:
                continue
            if spent(results) >= limit:
                break
            r["firstTry"].append(first_try(directory, trial, results["infrastructureLog"]))
            save(results)
            t = r["firstTry"][-1]
            print(f"{name} first-try {trial}: passed={t.get('passed')} ${t.get('costUsd')} | spend ${results['spentUsd']:.4f}", flush=True)
        if r["diocle"] is None and spent(results) < limit:
            r["diocle"] = full_run(directory, HARD_CAP_USD - spent(results) - 0.01)
            save(results)
            d = r["diocle"]
            print(f"{name} DIOCLE: certified={d['certified']} rounds={d['repairRounds']} ${d['costUsd']} {d['minutes']}min | spend ${results['spentUsd']:.4f}", flush=True)
        if spent(results) >= limit:
            print(f"stop: spend ${spent(results):.4f} reached ${limit:.2f}; programs not reached stay unrun", flush=True)
            break
    save(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
