"""Meta vs Meta: three Meta models attack the same stored Java, and GnuCOBOL decides every result. Protocol: docs/META_TOURNAMENT.md,
committed before this ran.

  eval/meta_tournament.py --max-total-usd 10 [--workers 4] [--plan]

Reads the keys from the environment (never printed). The Java is fixed: eval/attack-rerun-java/. Results: eval/results-meta-tournament.json,
which this script refuses to overwrite. Partial results stay in runs/meta-tournament.partial.json (git-ignored) and a re-run resumes from them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import headline  # noqa: E402  sets the plan's environment: no tiers, guard policy-only, and the program list
from headline import PROGRAMS, ROOT  # noqa: E402

OUT = ROOT / "eval" / "results-meta-tournament.json"
PARTIAL = ROOT / "runs" / "meta-tournament.partial.json"
JAVA = ROOT / "eval" / "attack-rerun-java"
BASELINE = ROOT / "eval" / "results-attack-rerun.json"
HELD_OUT_SEED, HELD_OUT_CASES = 8803, 1000  # free check before any attack; not used by an earlier run
ATTACK_ROUNDS = 3
# name, what to read from the environment, hard dollar cap per attack (--max-usd fails closed), cheapest first
ATTACKERS = (
    ("muse-spark-1.3-contributor", "META_MODEL", 0.10),
    ("accounts/fireworks/models/muse-spark-open", "OPEN_MODEL", 0.60),
    ("muse-wonder-1.0", "META_MODEL", 1.40),
)
_lock = threading.Lock()


def attackable() -> list[tuple[str, str]]:
    """The programs the Nov 2 re-measurement could attack: they passed held-out inputs and the breaker could run. Fixed before this ran."""
    results = json.loads(BASELINE.read_text())["programs"]
    return [(name, directory) for name, directory, _ in PROGRAMS
            if results.get(name, {}).get("heldOutPassed") and results[name].get("survives") is not None]


def differed_fields(diff: str) -> list[str]:
    """Which output fields a stored difference names, e.g. 'CL-FEE: original ...; X: ...'. A mismatch with no field name counts as 'other'."""
    found = re.findall(r"(?:^|; )([A-Z][A-Z0-9-]+): original", diff or "")
    return sorted(set(found)) or ["other"]


def score(programs: dict, attackers: list[str]) -> dict:
    """Per attacker: programs attacked, programs broken, the ones only it broke, inputs tried and spend. Counts only, no winner."""
    out = {}
    for a in attackers:
        ran = {p: r["attacks"][a] for p, r in programs.items() if a in r.get("attacks", {}) and r["attacks"][a].get("ran")}
        broke = [p for p, x in ran.items() if x["broke"]]
        only = [p for p in broke if not any(programs[p]["attacks"].get(o, {}).get("broke") for o in attackers if o != a)]
        out[a] = {"attacked": len(ran), "broke": len(broke), "programsBroken": sorted(broke), "onlyThisModelBroke": sorted(only),
                  "inputsTried": sum(x["tried"] for x in ran.values()), "inputsThatBroke": sum(x["broke"] for x in ran.values()),
                  "costUsd": round(sum(x.get("costUsd") or 0 for x in ran.values()), 6)}
    return out


def _settings(model: str, prefix: str, cap: float):
    import os
    from diocle_converter.config import Settings
    base = Settings.from_env()
    return replace(base, mode="private" if prefix == "OPEN_MODEL" else "hosted", base_url=os.environ[f"{prefix}_BASE_URL"],
                   api_key=os.environ[f"{prefix}_API_KEY"], model=model, tiers=(), max_usd=cap)


def attack(name: str, directory: str, model: str, prefix: str, cap: float) -> dict:
    from diocle_converter.breaker import Breaker
    from diocle_converter.client import ModelClient
    from diocle_converter.sources import Program
    from diocle_converter.workspace import Workspace
    from diocle_verifier.verify import verify_sample

    sample = ROOT / directory
    meta = json.loads((sample / "sample.json").read_text())
    client = ModelClient(_settings(model, prefix, cap))
    started = time.time()
    rec: dict = {"ran": True, "capUsd": cap}
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.from_copy(JAVA / name, Path(tmp) / "java")

        def verify(java_dir, seed, random_count, cases=None):
            return verify_sample(sample, java_dir, seed=seed, random_count=random_count, extra_cases=list(cases or []))

        events: list[str] = []
        breaker = Breaker(Program.load(sample), ws, client, verify, meta["layouts"]["input"],
                          on_event=lambda e: events.append(str(e.get("message", ""))[:200]))
        try:
            broken = breaker.attack(rounds=ATTACK_ROUNDS, label="tournament")
        except Exception as e:  # recorded, never retried silently: a provider failure is not a result about the Java
            return {"ran": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "costUsd": client.usage_summary()["estimatedCostUsd"]}
    hits = [a for a in breaker.attempts if a["broke"]]
    usage = client.usage_summary()
    rec.update(tried=len(breaker.attempts), broke=len(hits), survived=not broken, proposed=breaker.proposed_total,
               rejected=breaker.rejected, costUsd=usage["estimatedCostUsd"], calls=usage["calls"], seconds=round(time.time() - started, 1),
               fieldsDiffered=sorted({f for a in hits for f in differed_fields(a.get("diff", ""))}),
               stoppedBy=next((m for m in events if m.startswith("budget")), None), breaks=hits[:12],
               outputTokens=usage.get("outputTokens"))
    return rec


def baseline(name: str, directory: str) -> dict:
    from diocle_verifier.verify import passes, verify_sample
    report = verify_sample(ROOT / directory, JAVA / name, seed=HELD_OUT_SEED, random_count=HELD_OUT_CASES)
    return {"seed": HELD_OUT_SEED, "passed": bool(passes(report)), "total": report["summary"]["total"]}


def save(results: dict, attackers: list[str]) -> None:
    results["spentUsd"] = round(sum(x.get("costUsd") or 0 for r in results["programs"].values() for x in r.get("attacks", {}).values()), 6)
    results["score"] = score(results["programs"], attackers)
    PARTIAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = PARTIAL.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=1) + "\n")
    tmp.replace(PARTIAL)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-total-usd", type=float, help="the approved ceiling (required for a run)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--plan", action="store_true", help="free: print the programs and check the stored Java still passes")
    args = ap.parse_args()
    programs = attackable()
    if OUT.exists():
        sys.exit(f"{OUT.name} exists: results are never overwritten")
    if args.plan:
        for name, directory in programs:
            print(name, baseline(name, directory))
        return 0
    if args.max_total_usd is None:
        ap.error("a real run spends model credits: pass the approved --max-total-usd, or --plan")
    names = [a[0] for a in ATTACKERS]
    results = json.loads(PARTIAL.read_text()) if PARTIAL.exists() else {
        "plan": "docs/META_TOURNAMENT.md", "javaFrom": "eval/attack-rerun-java (Muse Spark, Nov 2)", "attackRounds": ATTACK_ROUNDS,
        "attackers": names, "maxTotalUsd": args.max_total_usd, "decidedBy": "GnuCOBOL", "programs": {}}
    if results["maxTotalUsd"] != args.max_total_usd:
        sys.exit("a resume must use the same ceiling")
    for name, directory in programs:
        if name not in results["programs"]:
            results["programs"][name] = {"directory": directory, "baseline": baseline(name, directory), "attacks": {}}
    save(results, names)
    planned: list[tuple] = []
    for model, prefix, cap in ATTACKERS:  # cheapest attacker first, so the ceiling can only cut the dearest
        for name, directory in programs:
            if results["programs"][name]["baseline"]["passed"] and model not in results["programs"][name]["attacks"]:
                planned.append((name, directory, model, prefix, cap))
    reserved = [0.0]

    def job(item: tuple) -> None:
        name, directory, model, prefix, cap = item
        while True:  # wait for running attacks to free their reservation; "not run" only if none is left to wait for
            with _lock:
                if results["spentUsd"] + reserved[0] + cap <= args.max_total_usd:
                    reserved[0] += cap
                    break
                if reserved[0] == 0:
                    results["programs"][name]["attacks"][model] = {"ran": False, "error": "not run: the ceiling left no room for this attack's cap"}
                    save(results, names)
                    print(f"{name} {model}: not run (ceiling)", flush=True)
                    return
            time.sleep(5)
        rec = attack(name, directory, model, prefix, cap)
        with _lock:
            reserved[0] -= cap
            results["programs"][name]["attacks"][model] = rec
            save(results, names)
            print(f"{name} {model}: tried {rec.get('tried')} broke {rec.get('broke')} ${rec.get('costUsd')} | ${results['spentUsd']:.4f} {rec.get('error') or ''}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(job, planned))
    OUT.write_text(json.dumps(results, indent=1) + "\n")
    print(json.dumps(results["score"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
