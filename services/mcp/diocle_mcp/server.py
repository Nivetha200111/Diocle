"""MCP server (stdio). Tools: analyze_cobol, verify_conversion, certify_conversion, cobol_lessons.

No model calls: an agent brings its own Java, and GnuCOBOL decides whether it is right.
The verify tools compile and run the COBOL and the Java given to them, so run this server
only for your own agent on your own machine.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections import Counter
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from diocle_analyzer.analyze import analyze, write_sample
from diocle_analyzer.github import clone
from diocle_verifier.verify import verify_sample

REPO_ROOT = Path(__file__).resolve().parents[3]


def allowed_roots() -> list[Path]:
    """Local paths the tools may read and execute: DIOCLE_MCP_ROOTS (comma-separated), default the Diocle repo.
    The verify tools run the code they are pointed at, so an agent steered by a prompt injection must not be able
    to aim them anywhere on the machine."""
    raw = os.environ.get("DIOCLE_MCP_ROOTS", str(REPO_ROOT))
    return [Path(p).expanduser().resolve() for p in raw.split(",") if p.strip()]


def _local(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not any(resolved.is_relative_to(root) for root in allowed_roots()):
        raise PermissionError(f"{path} is outside DIOCLE_MCP_ROOTS")
    return resolved
SKILL = REPO_ROOT / "skills" / "cobol-to-java-semantics" / "SKILL.md"

mcp = FastMCP("diocle", instructions=(
    "Diocle proves a Java conversion of a COBOL batch program behaves exactly like the original, by compiling the "
    "COBOL with GnuCOBOL and running both on the same generated inputs. Use analyze_cobol first, verify_conversion "
    "while fixing, certify_conversion when done. cobol_lessons has proven COBOL-to-Java rules."))


def _source(source: str) -> tuple[Path, dict]:
    if source.startswith("https://"):
        root, sha = clone(source, REPO_ROOT / "runs" / "imports")
        return root, analyze(root, kind="github", location=source.rstrip("/"), commit=sha)
    root = _local(source)
    if not root.is_dir():
        raise ValueError(f"not a directory: {source}")
    return root, analyze(root)


def _summary(report: dict, limit: int = 5) -> dict:
    runs, s = report["runs"], report["summary"]
    failing = [r for r in report["results"] if not r["match"]]
    builds = {side: runs[side]["stderr"][-1500:] for side in ("original", "converted") if not runs[side]["compiled"]}
    crashes = {side: runs[side]["stderr"][-1500:] for side in ("original", "converted")
               if runs[side]["compiled"] and runs[side]["exitCode"] != 0}
    return {
        "passed": s["passed"], "total": s["total"], "stdoutMatches": runs["stdoutMatch"],
        "allMatch": not builds and not crashes and s["total"] > 0 and s["failed"] == 0 and runs["stdoutMatch"],
        "buildErrors": builds or None, "crashes": crashes or None,
        "mismatchedFields": dict(Counter(d["field"] for r in failing for d in r.get("fieldDiffs", [])).most_common()),
        "examples": [{"input": r.get("input"), "diff": r.get("diff")} for r in failing[:limit]],
        "stdout": None if runs["stdoutMatch"] else {"original": runs["original"]["stdout"][-400:],
                                                    "converted": runs["converted"]["stdout"][-400:]},
    }


def _verify(legacy: str, program: str, java_dir: str, main_class: str | None, seed: int, cases: int) -> dict:
    root, report = _source(legacy)
    match = next((p for p in report["programs"] if p["name"] == program.upper()), None)
    if match is None:
        raise ValueError(f"program {program} not found; have {[p['name'] for p in report['programs']]}")
    if not match["convertible"]:
        raise ValueError(f"{program} is not verifiable yet: {match['notConvertibleReason']}")
    with tempfile.TemporaryDirectory(prefix="diocle-mcp-") as tmp:
        sample = write_sample(root, report, match, Path(tmp))
        if main_class:
            meta = json.loads((sample / "sample.json").read_text())
            meta["javaConversion"]["mainClass"] = main_class
            (sample / "sample.json").write_text(json.dumps(meta))
        result = verify_sample(sample, _local(java_dir), seed=seed, random_count=cases)
    return _summary(result)


@mcp.tool()
def analyze_cobol(source: str) -> dict:
    """Analyze a COBOL estate: a local directory, or https://github.com/<owner>/<repo> for allowed owners.
    Returns each program with its input/output files (DD name, copybook, field count), whether Diocle can verify
    it, and findings about legacy arithmetic (ROUNDED, truncation, silent overflow, binary DISPLAY)."""
    _, report = _source(source)
    return {
        "source": report["source"],
        "programs": [{"name": p["name"], "path": p["path"], "verifiable": p["convertible"],
                      "reason": p["notConvertibleReason"], "javaMainClassExpected": "".join(x.capitalize() for x in p["name"].split("-")),
                      "files": [{"dd": f["dd"], "direction": f["direction"], "copybook": f["copybook"],
                                 "layout": f["layout"]} for f in p["files"]]} for p in report["programs"]],
        "findings": [{k: f[k] for k in ("program", "paragraph", "line", "category", "message")} for f in report["findings"]],
    }


@mcp.tool()
def verify_conversion(legacy: str, program: str, java_dir: str, main_class: str | None = None,
                      cases: int = 200, seed: int = 1026) -> dict:
    """Run the original COBOL program (from `legacy`, a directory or allowed GitHub URL) and the Java in `java_dir`
    on the same generated inputs and compare every output field. The Java reads its input path from env
    DD_<input DD> and writes to DD_<output DD>. Returns pass counts, mismatched fields and example diffs."""
    return _verify(legacy, program, java_dir, main_class, seed, min(max(cases, 1), 2000))


@mcp.tool()
def certify_conversion(legacy: str, program: str, java_dir: str, main_class: str | None = None) -> dict:
    """Final check: 1,000 inputs from a fresh random seed that is only revealed in the result, so the Java
    cannot be tuned to it. Certified only if every field of every record and the stdout match."""
    seed = secrets.randbelow(10**9) + 10**6
    result = _verify(legacy, program, java_dir, main_class, seed, 1000)
    return {"certified": result["allMatch"], "seed": seed, **result}


@mcp.tool()
def cobol_lessons() -> str:
    """Proven COBOL-to-Java rules (a SKILL.md). Each was learned by Diocle's repair agent and kept only after the
    fixed Java passed held-out certification against GnuCOBOL."""
    return SKILL.read_text() if SKILL.exists() else "No lessons exported yet: run python -m diocle_converter.skill"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
