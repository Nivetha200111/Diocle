"""Run the frozen evaluation: convert each unseen program as a user would, then re-verify on fresh seeds.

  services/verifier/.venv/bin/python eval/run_eval.py

Writes eval/results.json. Model calls go through the converter's normal caps; nothing here changes the product.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "verifier"))
from diocle_verifier.verify import passes, verify_sample  # noqa: E402

FRESH_SEEDS = [9001, 9002, 9003, 9004, 9005]


def run(sample: Path) -> dict:
    started = time.time()
    proc = subprocess.run([str(ROOT / "services/converter/.venv/bin/python"), "-m", "diocle_converter", "run", str(sample),
                           "--breaker"], cwd=ROOT / "services" / "converter", capture_output=True, text=True)
    m = re.search(r"run saved to runs/(\S+)", proc.stdout) or re.search(r"run started runs/(\S+)", proc.stdout)
    run_id = m.group(1) if m else None
    meta = json.loads((ROOT / "runs" / run_id / "run.json").read_text()) if run_id else {}
    result = {"program": sample.name.upper(), "runId": run_id, "exitCode": proc.returncode,
              "certified": meta.get("certified", False), "error": meta.get("error"),
              "rounds": len(meta.get("rounds", [])), "usage": {k: v for k, v in meta.get("usage", {}).items() if k != "modelCalls"},
              "breaker": meta.get("breaker"), "minutes": round((time.time() - started) / 60, 1), "freshSeeds": []}
    if result["certified"]:
        for seed in FRESH_SEEDS:
            report = verify_sample(sample, ROOT / "runs" / run_id / "java", seed=seed, random_count=1000)
            failing = [r for r in report["results"] if not r["match"]]
            result["freshSeeds"].append({"seed": seed, "passed": passes(report), "cases": report["summary"]["total"],
                                         "failed": report["summary"]["failed"],
                                         "exitCodeMatch": report["runs"]["exitCodeMatch"], "stdoutMatch": report["runs"]["stdoutMatch"],
                                         "firstMismatch": failing[0].get("diff") if failing else None})
    elif run_id:
        last = (ROOT / "runs" / run_id / "events.jsonl").read_text().splitlines()[-3:]
        result["lastEvents"] = [json.loads(l).get("message") or json.loads(l).get("result", "")[:300] for l in last]
    print(json.dumps({k: result[k] for k in ("program", "certified", "rounds", "minutes")}), flush=True)
    return result


if __name__ == "__main__":
    tag = subprocess.run(["git", "describe", "--tags", "--always"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    results = [run(s) for s in sorted((ROOT / "eval" / "samples").iterdir()) if (s / "sample.json").exists()]
    (ROOT / "eval" / "results.json").write_text(json.dumps({"diocle": tag, "freshSeeds": FRESH_SEEDS, "results": results},
                                                           indent=2) + "\n")
