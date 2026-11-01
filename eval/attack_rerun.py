"""Re-measurement of the attack arm with the Nov 1 fixes: REDEFINES bodies filled, display output and exit code compared.
The plan is in docs/MEASUREMENT.md ("Re-measurement plan") and was committed before this ran.

  eval/attack_rerun.py [--shard I/N] [--merge]

The same fixed programs, model, translator and breaker as eval/headline_attack.py, on a new held-out seed. Keeps what the first
run did not: every attempt with its input and difference, and the Java, so a result can be read and re-run. Reads the Meta key
from the environment (never printed). Results: eval/results-attack-rerun.json, Java under eval/attack-rerun-java/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

import headline  # sets the plan's environment (default contributor model, no tiers, guard policy-only) and the program list
from headline import HELD_OUT_CASES, PROGRAMS, ROOT, is_infra

OUT = ROOT / "eval" / "results-attack-rerun.json"
JAVA = ROOT / "eval" / "attack-rerun-java"
SEED = 8802  # not used by any earlier run
STOP_USD = 0.30


def spent(results: dict) -> float:
    return round(sum((r.get("costUsd") or 0) for r in results["programs"].values()), 6)


def save(results: dict, out: Path) -> None:
    results["spentUsd"] = spent(results)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=1) + "\n")
    tmp.replace(out)


def unit(name: str, directory: str) -> dict:
    from diocle_converter.breaker import Breaker
    from diocle_converter.client import ModelClient
    from diocle_converter.config import Settings
    from diocle_converter.sources import Program
    from diocle_converter.translate import translate
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import passes, verify_sample

    sample = ROOT / directory
    meta = json.loads((sample / "sample.json").read_text())
    infra = None
    for attempt in (1, 2):
        client = ModelClient(Settings.from_env())
        started = time.time()
        rec: dict = {"seed": SEED, "cases": HELD_OUT_CASES}
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
                    report = verify_sample(sample, ws.root, seed=SEED, random_count=HELD_OUT_CASES)
                    rec["heldOutPassed"] = bool(passes(report))
                    rec["heldOutTotal"] = report["summary"]["total"]
                    if not rec["heldOutPassed"]:
                        first = next((r.get("diff") for r in report["results"] if not r["match"]), None)
                        rec.update(survives=False, attack="not needed: failed the held-out inputs already", heldOutFirstDiff=(first or "")[:300],
                                   heldOutStdoutMatch=report["runs"]["stdoutMatch"])
                    elif "layouts" not in meta:
                        rec.update(survives=None, attack="not applicable: the breaker designs single-file records")
                    else:
                        def verify(java_dir, seed, random_count, cases=None):
                            return verify_sample(sample, java_dir, seed=seed, random_count=random_count, extra_cases=list(cases or []))
                        breaker = Breaker(program, ws, client, verify, meta["layouts"]["input"])
                        broken = breaker.attack(rounds=3, label="rerun")
                        rec.update(attackTried=len(breaker.attempts), attackBroke=len(broken), survives=not broken,
                                   attack="breaker found no breaking input" if not broken else f"breaker broke it with {len(broken)} input(s)",
                                   attempts=breaker.attempts)
                    target = JAVA / name
                    shutil.rmtree(target, ignore_errors=True)
                    shutil.copytree(ws.root, target)
        except Exception as e:  # infrastructure failure: one re-run, logged in the record
            infra = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt == 1:
                continue
            rec = {"survives": None, "infrastructureFailure": infra}
        u = client.usage_summary()
        rec.update(costUsd=u["estimatedCostUsd"], calls=u["calls"], seconds=round(time.time() - started, 1))
        if infra:
            rec["rerunAfterInfrastructureFailure"] = infra
        return rec
    return {"survives": None, "infrastructureFailure": infra, "costUsd": 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    base = {"plan": "docs/MEASUREMENT.md, Re-measurement plan", "model": "muse-spark-1.3-contributor", "heldOutSeed": SEED, "programs": {}}
    if args.merge:
        merged = json.loads(OUT.read_text()) if OUT.exists() else base
        for f in sorted(OUT.parent.glob("results-attack-rerun.shard*.json")):
            merged["programs"].update(json.loads(f.read_text())["programs"])
            f.unlink()
        save(merged, OUT)
        print(f"merged: {len(merged['programs'])} programs, ${merged['spentUsd']:.4f}")
        return 0
    todo, limit, out = PROGRAMS, STOP_USD, OUT
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        out = OUT.with_name(f"results-attack-rerun.shard{i}.json")
        todo, limit = [p for k, p in enumerate(PROGRAMS) if k % n == i], STOP_USD / n
    results = json.loads(out.read_text()) if out.exists() else base
    for name, directory, status in todo:
        if name in results["programs"]:
            continue
        if spent(results) >= limit:
            print(f"stop: spend ${spent(results):.4f} reached ${limit:.2f}; remaining programs stay unrun", flush=True)
            break
        rec = unit(name, directory)
        rec.update(directory=directory, status=status)
        results["programs"][name] = rec
        save(results, out)
        print(f"{name}: heldOut={rec.get('heldOutPassed')} {rec.get('attack')} ${rec.get('costUsd')} | ${results['spentUsd']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
