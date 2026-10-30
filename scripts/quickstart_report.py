"""Prints the quickstart summary from a stored run record or a verifier report. Stdlib only; reads no key."""
import json
import sys
from pathlib import Path


def run_summary(run_dir: Path, sample: str) -> None:
    r = json.loads((run_dir / "run.json").read_text())
    u = r.get("usage") or {}
    cert = None
    events = run_dir / "events.jsonl"
    if events.exists():
        for line in events.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "certification":
                cert = e
    calls = u.get("modelCalls") or []
    model = r.get("model") or (calls[0].get("model") if calls else None) or "unknown"
    cost = u.get("estimatedCostUsd")
    if cert:
        print(f"held-out certification (round {cert.get('round')}): {cert.get('result', '').splitlines()[0]}  [{'PASS' if cert.get('passed') else 'FAIL'}]")
    else:
        print("no certification event recorded")
    print(f"model: {model} ({u.get('calls', '?')} calls)")
    print(f"tokens: {u.get('inputTokens', '?')} in ({u.get('cachedInputTokens', 0)} cached) / {u.get('outputTokens', '?')} out")
    print("estimated cost: " + ("unknown" if cost is None else f"${cost:.4f}") + " (list prices, not a bill)")
    print(f"Java written to: {run_dir / 'java'}")
    print(f"run record and report: {run_dir / 'run.json'}")
    print(f"next: sh scripts/quickstart.sh --no-key   (re-verify the stored conversion, no model)\n"
          f"      sh scripts/quickstart.sh --sample fee-schedule   (another sample; costs a few cents)" if sample == "interest-accrual" else
          "next: sh scripts/quickstart.sh --no-key")


def verify_summary(report: Path, sample: str, java: str, seconds: str) -> None:
    s = json.loads(report.read_text())["summary"]
    ok = s["failed"] == 0
    print(("RE-VERIFIED" if ok else "NOT VERIFIED") + f"  {s['passed']}/{s['total']} inputs matched, in {seconds} s. No model was called.")
    print(f"Stored Java: {java} (written by a Muse Spark run and checked in; its run record is on the live engine, see samples/{sample}/certified-java/README.md)")
    print("next: put META_MODEL_API_KEY in .env and run sh scripts/quickstart.sh to watch a real conversion (a few cents, capped at $0.10)")


if __name__ == "__main__":
    kind = sys.argv[1]
    if kind == "run":
        run_summary(Path(sys.argv[2]), sys.argv[3])
    elif kind == "verify":
        verify_summary(Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
