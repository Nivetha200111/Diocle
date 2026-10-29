"""Independent re-verification of a delivery: every programs/<PROGRAM>/ with a certificate.json.

  python -m diocle_verifier.reverify PROGRAMS_DIR --seed N --expect-legacy URL [--random 1000] [--summary FILE]

For each program it fetches the legacy COBOL and copybooks at the commit the certificate pins (only from
the repository CI expects), re-derives the record layouts from those copybooks with the analyzer instead of
trusting the pull request's sample.json, and runs both sides on fresh inputs from a seed the converter never
used. Exit code 0 only if every program matches. Used by the delivery repository's CI.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .verify import passes, verify_sample


GITHUB_REPO = re.compile(r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class Untrusted(ValueError):
    """The certificate asks for something CI must not do."""


def check_certificate(cert: dict, expect_legacy: str | None) -> None:
    legacy = cert["legacy"]
    repo, commit = legacy["repository"], legacy["commit"]
    if not (GITHUB_REPO.match(repo) or Path(repo).is_absolute()):  # absolute local paths are for tests only
        raise Untrusted(f"legacy repository must be https://github.com/<owner>/<repo>: {repo!r}")
    if expect_legacy is not None and repo.rstrip("/") != expect_legacy.rstrip("/"):
        raise Untrusted(f"certificate names legacy repository {repo!r}, CI expects {expect_legacy!r}")
    if not SHA.match(commit):
        raise Untrusted(f"legacy commit must be a full 40-character SHA: {commit!r}")


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise Untrusted(f"path escapes the legacy checkout: {relative!r}")
    return path


def fetch_legacy(repository: str, commit: str, cache: Path) -> Path:
    dest = cache / commit
    if not dest.exists():
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", "--", f"{repository}.git", commit],
                       check=True, timeout=180)
        subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)
    return dest


def build_sample(program_dir: Path, legacy: Path, work: Path) -> Path:
    """Rebuild the sample from the legacy checkout. Layouts and DD names come from the analyzer, not the PR."""
    from diocle_analyzer.analyze import analyze, classify, cobol_name

    cert = json.loads((program_dir / "certificate.json").read_text())
    claimed = json.loads((program_dir / "sample.json").read_text())
    source = _inside(legacy, cert["legacy"]["path"])
    report = analyze(legacy)
    program = next((p for p in report["programs"] if p["path"] == source.relative_to(legacy.resolve()).as_posix()), None)
    if program is None or program["name"] != cert["program"] or not program["convertible"]:
        raise Untrusted(f"{cert['legacy']['path']} is not the verifiable program {cert['program']} in the legacy commit")
    from diocle_analyzer.analyze import shared_keys

    inputs = [f for f in program["files"] if f["direction"] == "input"]
    outputs = [f for f in program["files"] if f["direction"] == "output"]
    updated = [f for f in program["files"] if f["direction"] == "io"]
    display_only = bool(program.get("displayOnly"))
    if len(inputs) == 1 and len(outputs) == 1 and not updated and not display_only:
        derived_io = {"dd": {"input": inputs[0]["dd"], "output": outputs[0]["dd"]},
                      "layouts": {"input": inputs[0]["layout"], "output": outputs[0]["layout"]}}
        claimed_io = {"dd": claimed.get("dd"), "layouts": claimed.get("layouts")}
    else:
        derived_io = {"files": [{"dd": f["dd"], "direction": f["direction"], "layout": f["layout"]}
                                for f in inputs + updated + outputs],
                      **shared_keys(inputs), **({"displayOnly": True} if display_only else {})}
        claimed_io = {k: claimed.get(k) for k in derived_io}
    if claimed_io != derived_io or bool(claimed.get("displayOnly")) != display_only:
        raise Untrusted("sample.json files, layouts or keys differ from what the legacy copybooks define")
    sample = work / cert["program"].lower()
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    source_name = cobol_name(cert["legacy"]["path"])
    shutil.copy2(source, sample / "src" / source_name)
    _, resolved, _ = classify(legacy)
    for member in program["copybooks"]:  # what the analyzer resolved, not paths the pull request names
        shutil.copy2(resolved[member], sample / "copybooks" / f"{member}.cpy")
    if sorted(cert["legacy"].get("modules", [])) != sorted(program.get("modules", [])):
        raise Untrusted("certificate modules differ from the programs it CALLs")
    for path in program.get("modules", []):
        module = _inside(legacy, path)
        shutil.copy2(module, sample / "src" / cobol_name(path))
    meta = {"program": cert["program"], "source": f"src/{source_name}", "copybookDir": "copybooks",
            "modules": [f"src/{cobol_name(m)}" for m in program.get("modules", [])],
            "collation": "ebcdic",  # legacy code is mainframe code: CI always compares in EBCDIC order
            **derived_io,
            "javaConversion": {"dir": "java", "mainClass": cert["java"]["mainClass"]}}
    (sample / "sample.json").write_text(json.dumps(meta))
    return sample


def reverify(programs_dir: Path, seed: int, random_count: int, expect_legacy: str | None = None) -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory(prefix="diocle-reverify-") as tmp:
        cache, work = Path(tmp) / "legacy", Path(tmp) / "work"
        cache.mkdir()
        for program_dir in sorted(p.parent for p in programs_dir.glob("*/certificate.json")):
            cert = json.loads((program_dir / "certificate.json").read_text())
            try:
                check_certificate(cert, expect_legacy)
                legacy = fetch_legacy(cert["legacy"]["repository"], cert["legacy"]["commit"], cache)
                sample = build_sample(program_dir, legacy, work)
            except Untrusted as e:
                results.append({"program": cert.get("program", program_dir.name), "passed": 0, "total": 0,
                                "stdoutMatch": False, "ok": False, "firstMismatch": None, "buildError": f"rejected: {e}"})
                continue
            report = verify_sample(sample, program_dir / "java", seed=seed, random_count=random_count)
            runs, s = report["runs"], report["summary"]
            ok = passes(report)
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
    parser.add_argument("--expect-legacy", required=True, help="the only legacy repository certificates may name")
    parser.add_argument("--summary", type=Path, help="append a Markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    args = parser.parse_args(argv)

    results = reverify(args.programs_dir, args.seed, args.random, args.expect_legacy)
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
