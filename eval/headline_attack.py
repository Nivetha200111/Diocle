"""Headline measurement, optional step (c) of docs/MEASUREMENT.md: the breaker applied to FIRST translations.

  PYTHONPATH=services/converter:services/verifier:services/analyzer <python with the converter deps> eval/headline_attack.py [--shard I/N | --merge]

For each fixed program: ONE fresh first translation by the translator alone (no repair, no memory), verified on the same 1,000
held-out inputs (seed 8801) as the first-try arm; if it passes, the same breaker agent the full runs use attacks it (up to 3
rounds). A first translation "survives" only if it passes the held-out inputs AND the breaker finds no input that breaks it.
This puts both arms under the same attack standard: it measures how many translations a normal random-test suite would accept
that are still wrong (the "proof gap"). Programs the breaker cannot attack (several files) are reported as not applicable.
Results go to eval/results-headline-attack[.shardI].json, resumable; a unit costs about $0.02 to $0.04. Needs the Meta key in
the repo-root .env (read in-process by the converter; this script never reads or prints it). Guard review and tiers are off.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import headline  # sets the plan's environment (default contributor model, no tiers, guard policy-only) and the program list
from headline import HELD_OUT_CASES, HELD_OUT_SEED, PROGRAMS, ROOT, is_infra

OUT = ROOT / "eval" / "results-headline-attack.json"
STOP_USD = 0.45  # this step's own spend line; the whole measurement stays under the $1.00 cap of the plan


def spent(results: dict) -> float:
    return round(sum((r.get("costUsd") or 0) for r in results["programs"].values()), 6)


def save(results: dict) -> None:
    results["spentUsd"] = spent(results)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=2) + "\n")
    tmp.replace(OUT)


def unit(directory: str) -> dict:
    from diocle_converter.breaker import Breaker
    from diocle_converter.client import ModelClient
    from diocle_converter.config import Settings
    from diocle_converter.sources import Program
    from diocle_converter.translate import translate
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import passes, verify_sample

    sample = ROOT / directory
    meta = json.loads((sample / "sample.json").read_text())
    for attempt in (1, 2):
        client = ModelClient(Settings.from_env())
        started = time.time()
        rec: dict = {"seed": HELD_OUT_SEED, "cases": HELD_OUT_CASES}
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
                    rec.update(translated=False, heldOutPassed=False, survives=False, error=f"{type(e).__name__}: {str(e)[:200]}")
                if rec.get("translated"):
                    report = verify_sample(sample, ws.root, seed=HELD_OUT_SEED, random_count=HELD_OUT_CASES)
                    rec["heldOutPassed"] = bool(passes(report))
                    rec["heldOutTotal"] = report["summary"]["total"]
                    if not rec["heldOutPassed"]:
                        rec.update(survives=False, attack="not needed: failed the held-out inputs already")
                    elif "layouts" not in meta:
                        rec.update(survives=None, attack="not applicable: the breaker designs single-file records")
                    else:
                        def verify(java_dir, seed, random_count, cases=None):
                            return verify_sample(sample, java_dir, seed=seed, random_count=random_count, extra_cases=list(cases or []))
                        breaker = Breaker(program, ws, client, verify, meta["layouts"]["input"])
                        broken = breaker.attack(rounds=3, label="headline")
                        rec.update(attackTried=len(breaker.attempts), attackBroke=len(broken), survives=not broken,
                                   attack="breaker found no breaking input" if not broken else f"breaker broke it with {len(broken)} input(s)",
                                   firstBreak=(str(broken[0]["why"])[:200] if broken else None))
        except Exception as e:  # infrastructure failure on the first attempt: one re-run, logged by the caller
            rec = {"infrastructureFailure": f"{type(e).__name__}", "rerun": attempt == 1}
            if attempt == 1:
                continue
        u = client.usage_summary()
        rec.update(costUsd=u["estimatedCostUsd"], calls=u["calls"], seconds=round(time.time() - started, 1))
        return rec
    return {"survives": None, "infrastructureFailure": True, "costUsd": 0.0}


def merge() -> int:
    merged = json.loads(OUT.read_text()) if OUT.exists() else {"plan": "docs/MEASUREMENT.md step (c)", "programs": {}}
    for f in sorted(OUT.parent.glob("results-headline-attack.shard*.json")):
        merged["programs"].update(json.loads(f.read_text())["programs"])
    save(merged)
    n = merged["programs"]
    ok = [r for r in n.values() if r.get("survives") is not None]
    print(f"merged: {len(n)} programs, {len(ok)} attackable, spend ${merged['spentUsd']:.4f}")
    return 0


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.merge:
        return merge()
    todo, limit = PROGRAMS, STOP_USD
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        OUT = OUT.with_name(f"results-headline-attack.shard{i}.json")
        todo, limit = [p for k, p in enumerate(PROGRAMS) if k % n == i], STOP_USD / n
    results = json.loads(OUT.read_text()) if OUT.exists() else {"plan": "docs/MEASUREMENT.md step (c)", "model": "muse-spark-1.3-contributor",
                                                                 "heldOutSeed": HELD_OUT_SEED, "programs": {}}
    for name, directory, status in todo:
        if name in results["programs"] and results["programs"][name].get("translated") is not None:
            continue
        if spent(results) >= limit:
            print(f"stop: spend ${spent(results):.4f} reached ${limit:.2f}; remaining programs stay unrun", flush=True)
            break
        rec = unit(directory)
        rec.update(directory=directory, status=status)
        results["programs"][name] = rec
        save(results)
        print(f"{name} ({status}): heldOut={rec.get('heldOutPassed')} attack={rec.get('attack')} survives={rec.get('survives')} "
              f"${rec.get('costUsd')} | spend ${results['spentUsd']:.4f}", flush=True)
    save(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
