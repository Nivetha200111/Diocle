"""Read converter runs from disk (runs/<id>/) and shape them per contracts/run.schema.json."""

from __future__ import annotations

import difflib
import json
import os
import re
import stat
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # no leading dot, so never "." or ".."


def runs_dir() -> Path:
    return Path(os.environ.get("DIOCLE_RUNS_DIR", REPO_ROOT / "runs"))


def _created_at(run_id: str) -> str | None:
    match = re.search(r"(\d{8}-\d{6})$", run_id)
    return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").isoformat() if match else None


def _verification(path: Path, limit: int = 8) -> dict | None:
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    failing = [r for r in report["results"] if not r["match"]]
    return {
        **report["summary"],
        "stdoutMatch": report["runs"]["stdoutMatch"],
        "failingExamples": [
            {"inputId": r["inputId"], "inputSource": r.get("inputSource", ""), "diff": r.get("diff", ""),
             "fieldDiffs": r.get("fieldDiffs", [])}
            for r in failing[:limit]
        ],
    }


STALE_SECONDS = 30 * 60  # no model call takes this long; a "running" run silent for longer was cut off


def _status(run: dict, path: Path | None = None) -> str:
    status = run.get("status") or ("certified" if run["certified"] else "not-certified")
    if status == "running" and path is not None:
        touched = [f.stat().st_mtime for f in (path / "run.json", path / "events.jsonl") if f.exists()]
        if touched and time.time() - max(touched) > STALE_SECONDS:
            return "interrupted"  # the engine restarted or the job was stopped mid-run
    return status


def is_visitor(path: Path, run: dict) -> bool:
    """A visitor's run: marked by its delivery, or (for runs saved before the marker, or caught before it is written)
    sampled from a visitor delivery's checkout. When the delivery record cannot be read, assume visitor: that only
    withholds sources and public re-verification."""
    if (path / "visitor").exists():
        return True
    deliveries = (runs_dir() / "deliveries").resolve()
    try:
        rel = _sample_dir(run).resolve().relative_to(deliveries)
    except ValueError:
        return False
    try:
        return bool(json.loads((deliveries / rel.parts[0] / "delivery.json").read_text()).get("public"))
    except (OSError, ValueError, IndexError):
        return True


def _agents_model(calls: list[dict]) -> str | None:
    """The model the run's agents used; the guard and the cross-check use their own models and do not define the run's mode."""
    return next((c["model"] for c in calls if c.get("role") not in ("guard", "crosscheck")), None)


def _sample_dir(run: dict) -> Path:
    if run.get("sample"):
        return REPO_ROOT / run["sample"]
    return REPO_ROOT / "samples" / re.sub(r"-\d{8}-\d{6}$", "", run["_id"])  # runs saved before "sample" was recorded


def _cobol_lines(sample: Path) -> int:
    """Non-blank, non-comment lines (fixed format: '*' or '/' in column 7) of the program and its copybooks."""
    meta = sample / "sample.json"
    if not meta.exists():
        return 0
    info = json.loads(meta.read_text())
    files = [sample / info["source"]]
    if info.get("copybookDir"):
        files += sorted((sample / info["copybookDir"]).glob("*.cpy"))
    lines = [line for f in files if f.exists() for line in f.read_text(encoding="latin-1").splitlines()]
    return sum(1 for line in lines if line.strip() and line[6:7] not in ("*", "/"))


def _efficiency(run: dict, events: list[dict]) -> dict:
    usage = run.get("usage", {})
    input_tokens, cached = usage.get("inputTokens", 0), usage.get("cachedInputTokens", 0)
    cost = usage.get("estimatedCostUsd")
    lines = _cobol_lines(_sample_dir(run))
    return {
        "cobolLines": lines,
        "modelCalls": usage.get("calls", 0),
        "toolSteps": sum(1 for e in events if e["type"] == "agent-step"),
        "patchesApplied": sum(1 for e in events if e.get("tool") == "patch_java"
                              and e.get("resultSummary", "").startswith("applied")),
        "cacheHitRate": round(cached / input_tokens, 4) if input_tokens else 0.0,
        "totalTokens": input_tokens + usage.get("outputTokens", 0),
        "modelTimeMs": sum(c.get("latencyMs", 0) for c in usage.get("modelCalls", [])),
        "estimatedCostUsd": cost,
        "costPer1kLinesUsd": round(cost / lines * 1000, 6) if cost is not None and lines else None,
    }


def _events(path: Path) -> list[dict]:
    events_file = path / "events.jsonl"
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a line still being appended by a live run
    return events


def _java_origin_dir(run: dict) -> Path | None:
    origin = run.get("javaOrigin", "")
    if origin.startswith("copied from "):
        return REPO_ROOT / origin.removeprefix("copied from ")
    if run.get("command") == "repair" and not origin:  # runs saved before provenance was recorded
        sample = _sample_dir(run)
        meta = sample / "sample.json"
        if meta.exists():
            return sample / json.loads(meta.read_text())["javaConversion"]["dir"]
    return None


def _java_diff(run: dict, run_path: Path) -> str | None:
    before_dir, after_dir = _java_origin_dir(run), run_path / "java"
    if not before_dir or not before_dir.exists() or not after_dir.exists():
        return None
    chunks = []
    for after in sorted(after_dir.rglob("*.java")):
        rel = after.relative_to(after_dir)
        before = before_dir / rel
        old = before.read_text().splitlines(keepends=True) if before.exists() else []
        chunks += difflib.unified_diff(old, after.read_text().splitlines(keepends=True), f"before/{rel}", f"after/{rel}")
    return "".join(chunks)


def list_runs() -> list[dict]:
    root = runs_dir()
    if not root.exists():
        return []
    items = []
    for path in sorted(root.iterdir(), reverse=True):
        meta = path / "run.json"
        if not meta.exists():
            continue
        try:
            run = json.loads(meta.read_text()) | {"_id": path.name}
        except json.JSONDecodeError:
            continue  # being written
        usage = run.get("usage", {})
        calls = usage.get("modelCalls", [])
        items.append({
            "id": path.name, "program": run["program"], "command": run["command"], "certified": run["certified"],
            "status": _status(run, path), "visitor": is_visitor(path, run),
            "createdAt": _created_at(path.name), "rounds": len(run.get("rounds", [])),
            "calls": usage.get("calls", 0), "estimatedCostUsd": usage.get("estimatedCostUsd"),
            "model": _agents_model(calls), "efficiency": _efficiency(run, _events(path)),
            "memory": run.get("memory"),
        })
    return items


SOURCE_MAX_BYTES = 200_000
SOURCE_MAX_FILES = 40


def _read_capped(f: Path) -> tuple[bytes, bool] | None:
    """A regular file's first SOURCE_MAX_BYTES, opened without following a final symlink; None for anything else."""
    try:
        fd = os.open(f, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, SOURCE_MAX_BYTES + 1)
    finally:
        os.close(fd)
    return data[:SOURCE_MAX_BYTES], len(data) > SOURCE_MAX_BYTES


def _source_files(base: Path, files: list[Path]) -> list[dict]:
    """Regular files inside base only (no symlinks out), each capped, for reading side by side."""
    out = []
    root = base.resolve()
    for f in files[:SOURCE_MAX_FILES]:
        if f.is_symlink() or not f.resolve().is_relative_to(root):
            continue
        read = _read_capped(f)
        if read is None:
            continue
        out.append({"path": f.relative_to(base).as_posix(), "text": read[0].decode("latin-1"), "truncated": read[1]})
    return out


def _sample_roots() -> list[Path]:
    return [(REPO_ROOT / "samples").resolve(), (REPO_ROOT / "eval" / "samples").resolve(),
            (runs_dir() / "deliveries").resolve()]


def get_source(run_id: str) -> dict | None:
    """contracts/run.schema.json $defs.source: the original COBOL next to the run's Java. Visitor runs are not served:
    their code comes from repositories Diocle does not control."""
    if not RUN_ID.match(run_id):
        return None
    path = runs_dir() / run_id
    meta = path / "run.json"
    if not meta.exists():
        return None
    try:
        run = json.loads(meta.read_text()) | {"_id": run_id}
    except json.JSONDecodeError:
        return None
    if is_visitor(path, run):
        return None
    sample = _sample_dir(run)
    cobol: list[dict] = []
    if any(sample.resolve().is_relative_to(r) for r in _sample_roots()):
        try:
            info = json.loads((sample / "sample.json").read_text())
            files = [sample / info["source"]]
            if info.get("copybookDir"):
                files += sorted((sample / info["copybookDir"]).glob("*.cpy"))
            cobol = _source_files(sample, files)
        except (OSError, ValueError, KeyError, TypeError):
            cobol = []  # no readable sample: show the Java alone
    java_dir = path / "java"
    java = []
    if java_dir.is_dir() and not java_dir.is_symlink() and java_dir.resolve().is_relative_to(path.resolve()):
        java = _source_files(java_dir, sorted(java_dir.rglob("*.java")))
    return {"runId": run_id, "program": run["program"], "cobol": cobol, "java": java}


def get_run(run_id: str) -> dict | None:
    if not RUN_ID.match(run_id):
        return None
    path = runs_dir() / run_id
    meta = path / "run.json"
    if not meta.exists():
        return None
    try:
        run = json.loads(meta.read_text()) | {"_id": run_id}
    except json.JSONDecodeError:
        return None  # caught mid-write; the next poll will see it
    events = _events(path)
    calls = run.get("usage", {}).get("modelCalls", [])
    origin = run.get("javaOrigin") or (
        f"copied from {_java_origin_dir(run).relative_to(REPO_ROOT)}" if _java_origin_dir(run) else "unknown"
    )
    return {
        "id": run_id,
        "program": run["program"],
        "command": run["command"],
        "createdAt": _created_at(run_id),
        "certified": run["certified"],
        "status": _status(run, path),
        "visitor": is_visitor(path, run),
        "certificationSeed": run.get("certificationSeed"),
        "error": run.get("error"),
        "javaOrigin": origin,
        "rounds": run.get("rounds", []),
        "events": events,
        "before": _verification(path / "initial-verification.json"),
        "after": _verification(path / "verification-report.json"),
        "usage": {"cachedInputTokens": 0, **run.get("usage", {"calls": 0, "inputTokens": 0, "outputTokens": 0})},
        "model": _agents_model(calls),
        "javaDiff": _java_diff(run, path),
        "efficiency": _efficiency(run, events),
        "memory": run.get("memory"),
        "breaker": run.get("breaker"),
        "crosscheck": run.get("crosscheck"),
        "guard": run.get("guard"),
        "swarm": run.get("swarm", False),
    }
