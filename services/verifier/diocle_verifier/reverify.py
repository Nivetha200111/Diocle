"""Independent re-verification of a delivery: every programs/<PROGRAM>/ with a certificate.json.

  python -m diocle_verifier.reverify PROGRAMS_DIR --seed N [--random 1000] [--summary FILE]

For each program it fetches the legacy COBOL and copybooks at the commit the certificate pins,
rebuilds a sample directory, and runs both sides on fresh inputs from a seed the converter never used.
Exit code 0 only if every program matches. Used by the delivery repository's CI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .verify import verify_sample


def fetch_legacy(repository: str, commit: str, cache: Path) -> Path:
    dest = cache / commit
    if not dest.exists():
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", f"{repository}.git", commit], check=True, timeout=180)
        subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)
    return dest


def build_sample(program_dir: Path, legacy: Path, work: Path) -> Path:
    cert = json.loads((program_dir / "certificate.json").read_text())
    meta = json.loads((program_dir / "sample.json").read_text())
    sample = work / cert["program"].lower()
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    shutil.copy2(legacy / cert["legacy"]["path"], sample / meta["source"])
    for path in cert["legacy"]["copybooks"]:
        shutil.copy2(legacy / path, sample / "copybooks" / Path(path).name)
    (sample / "sample.json").write_text(json.dumps(meta))
    return sample


def reverify(programs_dir: Path, seed: int, random_count: int) -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory(prefix="diocle-reverify-") as tmp:
        cache, work = Path(tmp) / "legacy", Path(tmp) / "work"
        cache.mkdir()
        for program_dir in sorted(p.parent for p in programs_dir.glob("*/certificate.json")):
            cert = json.loads((program_dir / "certificate.json").read_text())
            legacy = fetch_legacy(cert["legacy"]["repository"], cert["legacy"]["commit"], cache)
            sample = build_sample(program_dir, legacy, work)
            report = verify_sample(sample, program_dir / "java", seed=seed, random_count=random_count)
            runs, s = report["runs"], report["summary"]
            ok = runs["original"]["compiled"] and runs["converted"]["compiled"] and s["total"] > 0 \
                and s["failed"] == 0 and runs["stdoutMatch"]
            results.append({"program": cert["program"], "passed": s["passed"], "total": s["total"],
                            "stdoutMatch": runs["stdoutMatch"], "ok": bool(ok),
                            "firstMismatch": next((r.get("diff", "") for r in report["results"] if not r["match"]), None),
                            "buildError": next((runs[k]["stderr"][-500:] for k in ("original", "converted") if not runs[k]["compiled"]), None)})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_verifier.reverify", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("programs_dir", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--random", type=int, default=1000)
    parser.add_argument("--summary", type=Path, help="append a Markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    args = parser.parse_args(argv)

    results = reverify(args.programs_dir, args.seed, args.random)
    lines = [f"### Independent re-verification (seed {args.seed}, fresh inputs)", "",
             "| Program | Result | Cases | stdout |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['program']} | {'PASS' if r['ok'] else 'FAIL'} | {r['passed']}/{r['total']} | "
                     f"{'matches' if r['stdoutMatch'] else 'differs'} |")
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['program']}: {r['passed']}/{r['total']}, stdout {'matches' if r['stdoutMatch'] else 'differs'}")
        if not r["ok"]:
            print(f"    {r['buildError'] or r['firstMismatch']}")
    if not results:
        lines.append("| (none) | no programs/*/certificate.json found | | |")
    if args.summary:
        with args.summary.open("a") as f:
            f.write("\n".join(lines) + "\n")
    return 0 if results and all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
