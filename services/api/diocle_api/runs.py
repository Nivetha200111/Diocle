"""Read converter runs from disk (runs/<id>/) and shape them per contracts/run.schema.json."""

from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def runs_dir() -> Path:
    return Path(os.environ.get("DIOCLE_RUNS_DIR", REPO_ROOT / "runs"))


def _created_at(run_id: str) -> str | None:
    match = re.search(r"(\d{8}-\d{6})$", run_id)
    return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").isoformat() if match else None


def _verification(path: Path, limit: int = 8) -> dict | None:
    if not path.exists():
        return None
    report = json.loads(path.read_text())
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


def _java_origin_dir(run: dict) -> Path | None:
    origin = run.get("javaOrigin", "")
    if origin.startswith("copied from "):
        return REPO_ROOT / origin.removeprefix("copied from ")
    if run.get("command") == "repair" and not origin:  # runs saved before provenance was recorded
        sample = REPO_ROOT / "samples" / re.sub(r"-\d{8}-\d{6}$", "", run["_id"])
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
        run = json.loads(meta.read_text())
        usage = run.get("usage", {})
        items.append({
            "id": path.name, "program": run["program"], "command": run["command"], "certified": run["certified"],
            "createdAt": _created_at(path.name), "rounds": len(run.get("rounds", [])),
            "calls": usage.get("calls", 0), "estimatedCostUsd": usage.get("estimatedCostUsd"),
        })
    return items


def get_run(run_id: str) -> dict | None:
    if not RUN_ID.match(run_id):
        return None
    path = runs_dir() / run_id
    meta = path / "run.json"
    if not meta.exists():
        return None
    run = json.loads(meta.read_text()) | {"_id": run_id}
    events_file = path / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().splitlines() if line.strip()] if events_file.exists() else []
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
        "javaOrigin": origin,
        "rounds": run.get("rounds", []),
        "events": events,
        "before": _verification(path / "initial-verification.json"),
        "after": _verification(path / "verification-report.json"),
        "usage": {"cachedInputTokens": 0, **run.get("usage", {"calls": 0, "inputTokens": 0, "outputTokens": 0})},
        "model": calls[0]["model"] if calls else None,
        "javaDiff": _java_diff(run, path),
    }
