"""CLI.

  python -m diocle_analyzer PATH_OR_GITHUB_URL [--out report.json] [--samples-dir DIR]

Writes the analysis report (contracts/analysis-report.schema.json) and, with --samples-dir,
one Diocle sample directory per convertible program for the converter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import analyze, validate_report, write_sample
from .github import clone

REPO_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_analyzer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="local directory or https://github.com/<owner>/<repo>")
    parser.add_argument("--out", type=Path, help="write the report here (default: print a summary only)")
    parser.add_argument("--samples-dir", type=Path, help="write a sample directory per convertible program here")
    parser.add_argument("--convert-anyway", action="store_true",
                        help="also write a (non-certifiable) sample for programs that are refused, with the reason")
    args = parser.parse_args(argv)

    if args.source.startswith("https://"):
        root, sha = clone(args.source, REPO_ROOT / "runs" / "imports")
        report = analyze(root, kind="github", location=args.source.rstrip("/").removesuffix(".git"), commit=sha)
    else:
        root = Path(args.source)
        report = analyze(root)
    validate_report(report)

    for p in report["programs"]:
        io = " -> ".join(f"{f['dd']}({len(f['layout']['fields']) if f['layout'] else '?'} fields)" for f in p["files"])
        status = "convertible" if p["convertible"] else f"skipped: {p['notConvertibleReason']}"
        print(f"{p['name']:<10} {p['path']:<28} {io:<40} {status}")
    print(f"{len(report['findings'])} findings, {len(report['dependencies'])} dependency edges")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    if args.samples_dir:
        written: set[str] = set()
        for p in report["programs"]:
            if (p["convertible"] or args.convert_anyway) and p["name"] in written:  # samples are keyed by PROGRAM-ID: the first file wins
                print(f"sample: skipped {p['path']} (PROGRAM-ID {p['name']} already written)")
            elif p["convertible"] or args.convert_anyway:
                written.add(p["name"])
                print(f"sample: {write_sample(root, report, p, args.samples_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
