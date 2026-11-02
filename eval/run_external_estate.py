"""Run the external estate exactly as docs/EXTERNAL_ESTATE.md pins it, before any tuning.

  services/verifier/.venv/bin/python eval/run_external_estate.py

Imports openmainframeproject/cobol-programming-course once (analyzer, pinned commit in the report),
then accounts for every program in the report: refused (analyzer reason, quoted), certified, or not
certified. Convertible programs run as a user would: `diocle_converter run <sample> --breaker
--no-memory` under the normal caps, then five fresh seeds if certified. Writes
eval/results-external-estate.json and refuses to overwrite it. Nothing here changes the product.
The estate clone and derived samples stay in git-ignored runs/external-estate/ (no estate source is
committed). Needs GnuCOBOL, a JDK and .env keys, like every real conversion.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "verifier"))
from diocle_verifier.verify import passes, verify_sample  # noqa: E402

ESTATE_URL = "https://github.com/openmainframeproject/cobol-programming-course"
PINNED_COMMIT = "780b1c9624e066b9d784a738896e493282c5fbf4"
WORK = ROOT / "runs" / "external-estate"
REPORT = WORK / "report.json"
SAMPLES = WORK / "samples"
OUT = ROOT / "eval" / "results-external-estate.json"
FRESH_SEEDS = [9001, 9002, 9003, 9004, 9005]


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def import_estate() -> dict:
    """Analyze the estate once, as found. Returns the analyzer report."""
    if REPORT.exists():
        return json.loads(REPORT.read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DIOCLE_IMPORT_OWNERS": "openmainframeproject"}
    proc = _run([str(ROOT / "services/analyzer/.venv/bin/python"), "-m", "diocle_analyzer", ESTATE_URL,
                 "--out", str(REPORT), "--samples-dir", str(SAMPLES)],
                cwd=ROOT / "services" / "analyzer", env=env)
    if proc.returncode != 0 or not REPORT.exists():
        sys.exit(f"analyzer import failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(REPORT.read_text())


def convert(sample: Path, program: str) -> dict:
    started = time.time()
    proc = _run([str(ROOT / "services/converter/.venv/bin/python"), "-m", "diocle_converter", "run",
                 str(sample), "--breaker", "--no-memory"], cwd=ROOT / "services" / "converter")
    m = re.search(r"run saved to runs/(\S+)", proc.stdout) or re.search(r"run started runs/(\S+)", proc.stdout)
    run_id = m.group(1) if m else None
    meta = json.loads((ROOT / "runs" / run_id / "run.json").read_text()) if run_id else {}
    result = {"program": program, "runId": run_id, "exitCode": proc.returncode,
              "certified": meta.get("certified", False), "error": meta.get("error"),
              "rounds": len(meta.get("rounds", [])),
              "usage": {k: v for k, v in meta.get("usage", {}).items() if k != "modelCalls"},
              "breaker": meta.get("breaker"), "minutes": round((time.time() - started) / 60, 1),
              "freshSeeds": []}
    if result["certified"]:
        for seed in FRESH_SEEDS:
            report = verify_sample(sample, ROOT / "runs" / run_id / "java", seed=seed, random_count=1000)
            failing = [r for r in report["results"] if not r["match"]]
            result["freshSeeds"].append({"seed": seed, "passed": passes(report),
                                         "cases": report["summary"]["total"],
                                         "failed": report["summary"]["failed"],
                                         "exitCodeMatch": report["runs"]["exitCodeMatch"],
                                         "stdoutMatch": report["runs"]["stdoutMatch"],
                                         "firstMismatch": failing[0].get("diff") if failing else None})
    print(json.dumps({k: result[k] for k in ("program", "certified", "rounds", "minutes")}), flush=True)
    return result


if __name__ == "__main__":
    if OUT.exists():
        sys.exit(f"{OUT.name} exists; results are never overwritten (a re-run is a separate, dated file)")
    report = import_estate()
    commit = (report.get("source") or {}).get("commit")
    if commit and not commit.startswith(PINNED_COMMIT[:12]):
        sys.exit(f"estate moved: report pins {commit}, protocol pins {PINNED_COMMIT}; "
                 "re-pin docs/EXTERNAL_ESTATE.md before running, do not silently follow the move")
    samples = {json.loads((s / "sample.json").read_text())["program"]: s
               for s in sorted(SAMPLES.iterdir()) if (s / "sample.json").exists()}
    converted_samples: set[Path] = set()
    results = []
    for program in report["programs"]:
        name = program["name"]
        if not program["convertible"]:
            results.append({"program": name, "path": program["path"], "outcome": "refused",
                            "reason": program["notConvertibleReason"]})
            print(json.dumps({"program": name, "outcome": "refused"}), flush=True)
        elif name not in samples:
            results.append({"program": name, "path": program["path"], "outcome": "not-run",
                            "reason": "analyzer marked it convertible but wrote no sample"})
        elif samples[name] in converted_samples:
            # Two sources can share one PROGRAM-ID (CBLC1.cobol is CBL0006 again); the analyzer
            # writes one sample per PROGRAM-ID, so converting it twice would count one program twice.
            results.append({"program": name, "path": program["path"], "outcome": "duplicate",
                            "reason": f"same PROGRAM-ID as an earlier source; sample {samples[name].name} already converted"})
        else:
            converted_samples.add(samples[name])
            results.append({"path": program["path"], "outcome": "converted",
                            **convert(samples[name], name)})
    OUT.write_text(json.dumps({"estate": ESTATE_URL, "pinnedCommit": PINNED_COMMIT,
                               "analyzedCommit": commit, "memory": False,
                               "converterFlags": ["--breaker", "--no-memory"],
                               "freshSeeds": FRESH_SEEDS, "results": results}, indent=2) + "\n")
    tally = {}
    for r in results:
        key = r["outcome"] if r["outcome"] != "converted" else ("certified" if r["certified"] else "not certified")
        tally[key] = tally.get(key, 0) + 1
    print(json.dumps({"programs": len(results), **tally}))
