"""CLI: python -m diocle_verifier SAMPLE_DIR [--java-dir DIR] [--out report.json]"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .verify import passes, validate_report, verify_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_verifier", description=__doc__)
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("--java-dir", type=Path, help="converted Java sources (default: the sample's javaConversion dir)")
    parser.add_argument("--random", type=int, default=200, help="number of random cases (default 200)")
    parser.add_argument("--seed", type=int, default=1026)
    parser.add_argument("--out", type=Path, help="write the verification report JSON here")
    parser.add_argument("--show", type=int, default=5, help="failing cases to print (default 5)")
    args = parser.parse_args(argv)

    report = verify_sample(args.sample_dir, args.java_dir, seed=args.seed, random_count=args.random)
    validate_report(report)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")

    runs = report["runs"]
    for side in ("original", "converted"):
        if not runs[side]["compiled"]:
            print(f"BUILD FAILED ({side}):\n{runs[side]['stderr']}", file=sys.stderr)
            return 2

    if not runs["exitCodeMatch"]:
        print(f"EXIT CODES DIFFER: original {runs['original']['exitCode']}, converted {runs['converted']['exitCode']}",
              file=sys.stderr)
        for side in ("original", "converted"):
            if runs[side]["stderr"].strip():
                print(f"  {side} stderr: {runs[side]['stderr'].strip()[-2000:]}", file=sys.stderr)

    s = report["summary"]
    status = "PASS" if passes(report) else "FAIL"
    print(f"{status}  {s['passed']}/{s['total']} cases match  (stdout {'matches' if runs['stdoutMatch'] else 'DIFFERS'})")
    failing = [r for r in report["results"] if not r["match"]]
    if failing:
        by_field = Counter(d["field"] for r in failing for d in r.get("fieldDiffs", []))
        print("Mismatched fields: " + ", ".join(f"{name} x{n}" for name, n in by_field.most_common()))
        for r in failing[: args.show]:
            print(f"  {r['inputId']} [{r.get('inputSource', '?')}] input={r.get('input', '')!r}\n      {r.get('diff', '')}")
    if not runs["stdoutMatch"]:
        print(f"  stdout original : {runs['original']['stdout'].strip()}\n  stdout converted: {runs['converted']['stdout'].strip()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
