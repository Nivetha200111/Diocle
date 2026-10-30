"""Smallest reproducers of a run (contracts/minimal-reproducer.schema.json), read-only.

The converter's `run --minimize` (or `python -m diocle_verifier minimize RUN_DIR --case ID`) writes
runs/<id>/reproducers/<case>.json and runs/<id>/regression/<case>/. This module only reads them: no program is built
or run here, no model is called. Visitor runs are withheld like their sources. Every file is size-capped and must be
a record of this contract version for the same case id, or it is ignored.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from . import runs

MAX_FILES = 20
MAX_REPRODUCER_BYTES = 128 * 1024
MAX_CASE_FILE_BYTES = 128 * 1024
CASE_FILES = ("case.json", "input.dat", "expected-output.dat", "expected-stdout.txt")


def _run_path(run_id: str) -> Path | None:
    if not runs.RUN_ID.match(run_id):
        return None
    path = runs.runs_dir() / run_id
    try:
        run = json.loads((path / "run.json").read_text()) | {"_id": run_id}
    except (OSError, ValueError):
        return None
    return None if runs.is_visitor(path, run) else path


def run_reproducers(run_id: str) -> dict | None:
    """{"runId", "reproducers": [...]} (possibly empty), or None for an unknown or withheld run."""
    path = _run_path(run_id)
    if path is None:
        return None
    found = []
    folder = path / "reproducers"
    if folder.is_symlink():
        return {"runId": run_id, "reproducers": []}
    for f in sorted(folder.glob("*.json"))[:MAX_FILES] if folder.is_dir() else []:
        try:
            if f.is_symlink() or f.stat().st_size > MAX_REPRODUCER_BYTES:
                continue
            rec = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("version") == "0.1" and rec.get("id") == f.stem and isinstance(rec.get("reduction"), dict):
            found.append(rec)
    return {"runId": run_id, "reproducers": found}


def regression_case(run_id: str, case_id: str) -> dict | None:
    """The saved regression case for a download: its four files, text as text and bytes as base64."""
    path = _run_path(run_id)
    if path is None or not runs.RUN_ID.match(case_id):
        return None
    if (path / "regression").is_symlink() or (path / "regression" / case_id).is_symlink():
        return None
    folder = path / "regression" / case_id
    files = []
    for name in CASE_FILES:
        f = folder / name
        try:
            if f.is_symlink() or not f.is_file() or f.stat().st_size > MAX_CASE_FILE_BYTES:
                return None
            data = f.read_bytes()
        except OSError:
            return None
        files.append({"name": name, "base64": base64.b64encode(data).decode("ascii")})
    return {"runId": run_id, "case": case_id, "files": files,
            "replay": f"python -m diocle_verifier replay <this folder> --java-dir <java directory>"}
