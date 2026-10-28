"""Analyze a source tree (a cloned repository or a local directory) into an analysis report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import REPORT_VERSION
from .cobol import parse_copybook, parse_program
from .jcl import parse_jcl
from .risks import find_risks

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "analysis-report.schema.json"
COBOL_SUFFIXES = {".cbl", ".cob", ".cobol"}
COPYBOOK_SUFFIXES = {".cpy", ".copy"}


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes and ".git" not in p.parts)


def analyze(root: Path, *, kind: str = "directory", location: str | None = None, commit: str | None = None) -> dict:
    root = root.resolve()
    copybooks = {p.stem.upper(): p for p in _files(root, COPYBOOK_SUFFIXES)}
    steps = [s for p in _files(root, {".jcl"}) for s in parse_jcl(p.read_text(errors="replace"), p.relative_to(root).as_posix())]
    programs, dependencies, findings = [], [], []
    for path in _files(root, COBOL_SUFFIXES):
        text = path.read_text(errors="replace")
        info = parse_program(text)
        step = next((s for s in steps if s.program == info.name), None)
        files = []
        for file_name, dd in info.selects.items():
            member = info.fd_copybooks.get(file_name)
            layout = parse_copybook(copybooks[member].read_text(errors="replace")) if member in copybooks else None
            files.append({
                "dd": dd,
                "direction": info.directions.get(file_name, "unknown"),
                "dsn": step.dsns.get(dd) if step else None,
                "copybook": member,
                "layout": layout.as_dict() if layout else None,
                **({"unsupported": layout.unsupported} if layout and layout.unsupported else {}),
            })
        reason = _not_convertible(files, info.copybooks, copybooks)
        programs.append({
            "name": info.name,
            "path": path.relative_to(root).as_posix(),
            "copybooks": info.copybooks,
            "job": step.member if step else None,
            "files": [{k: v for k, v in f.items() if k != "unsupported"} for f in files],
            "convertible": reason is None,
            "notConvertibleReason": reason,
        })
        dependencies += [{"from": info.name, "to": c, "kind": "copy"} for c in info.copybooks]
        dependencies += [{"from": info.name, "to": c, "kind": "call"} for c in info.calls]
        dependencies += [{"from": info.name, "to": f["dsn"] or f["dd"], "kind": "file"} for f in files]
        if step:
            dependencies.append({"from": step.job, "to": info.name, "kind": "job"})
        findings += find_risks(info.name, text)
    return {
        "version": REPORT_VERSION,
        "source": {"kind": kind, "location": location or str(root), "commit": commit},
        "programs": programs,
        "dependencies": dependencies,
        "findings": findings,
    }


def _not_convertible(files: list[dict], used: list[str], available: dict[str, Path]) -> str | None:
    missing = [c for c in used if c not in available]
    if missing:
        return f"copybook(s) not found: {', '.join(missing)}"
    inputs = [f for f in files if f["direction"] == "input"]
    outputs = [f for f in files if f["direction"] == "output"]
    if len(inputs) != 1 or len(outputs) != 1:
        return f"needs exactly one input and one output file (found {len(inputs)} and {len(outputs)})"
    for f in inputs + outputs:
        if f["layout"] is None:
            return f"{f['dd']}: {f.get('unsupported') or 'record layout not found'}"
    return None


def validate_report(report: dict) -> None:
    import jsonschema

    jsonschema.validate(report, json.loads(CONTRACT.read_text()))


def main_class(program: str) -> str:
    return "".join(part.capitalize() for part in program.split("-"))


def write_sample(root: Path, report: dict, program: dict, out_dir: Path) -> Path:
    """Materialize one convertible program as a Diocle sample directory (the converter's input format)."""
    root = root.resolve()
    sample = out_dir / program["name"].lower()
    (sample / "src").mkdir(parents=True, exist_ok=True)
    (sample / "copybooks").mkdir(exist_ok=True)
    source = root / program["path"]
    shutil.copy2(source, sample / "src" / source.name)
    for member in program["copybooks"]:
        found = next(p for p in _files(root, COPYBOOK_SUFFIXES) if p.stem.upper() == member)
        shutil.copy2(found, sample / "copybooks" / found.name)
    by_direction = {f["direction"]: f for f in program["files"]}
    meta = {
        "name": program["name"].lower(),
        "description": f"Imported from {report['source']['location']}"
                       + (f" at {report['source']['commit'][:12]}" if report["source"].get("commit") else ""),
        "program": program["name"],
        "source": f"src/{source.name}",
        "copybookDir": "copybooks",
        "dd": {"input": by_direction["input"]["dd"], "output": by_direction["output"]["dd"]},
        "javaConversion": {"dir": "java-conversion", "mainClass": main_class(program["name"]),
                           "origin": "none yet: translate with the converter's run command"},
        "layoutsNote": "Derived from the copybooks by services/analyzer.",
        "layouts": {"input": by_direction["input"]["layout"], "output": by_direction["output"]["layout"]},
        "import": {"repository": report["source"]["location"], "commit": report["source"].get("commit"),
                   "path": program["path"], "job": program.get("job")},
    }
    (sample / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return sample
