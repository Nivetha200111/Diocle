"""Analyze a source tree (a cloned repository or a local directory) into an analysis report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import REPORT_VERSION
from .cobol import apply_replacing, parse_copybook, parse_program
import re

from .jcl import parse_jcl, parse_procs
from .risks import find_risks

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "analysis-report.schema.json"
COBOL_SUFFIXES = {".cbl", ".cob", ".cobol"}
COPYBOOK_SUFFIXES = {".cpy", ".copy"}


JCL_SUFFIXES = {".jcl", ".proc", ".prc"}
_PROGRAM = re.compile(r"^.{6}[ ]+(?:IDENTIFICATION|ID)[ ]+DIVISION", re.M)


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes and ".git" not in p.parts)


def _text(path: Path) -> str | None:
    """Text of a source member, or None for binary data (EBCDIC extracts, packed records, images)."""
    data = path.read_bytes()[:65536]
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    return path.read_text(errors="replace") if text and printable / len(text) > 0.97 else None


def classify(root: Path) -> tuple[list[Path], dict[str, Path], list[Path]]:
    """(COBOL programs, copybook candidates by member name, JCL members) for a source tree.

    Mainframe exports are libraries of extension-less members (QMK.PROD.COBOL/ACCTMTCH), so members are
    classified by content when they have no known extension."""
    programs, jcl, other = [], [], {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        suffix = path.suffix.lower()
        if suffix in COBOL_SUFFIXES:
            programs.append(path)
            continue
        if suffix in JCL_SUFFIXES:
            jcl.append(path)
            continue
        if suffix in COPYBOOK_SUFFIXES:
            other.setdefault(path.stem.upper(), path)
            continue
        if suffix in (".md", ".txt", ".json", ".yml", ".yaml", ".xml", ".py", ".sql", ".csv"):
            continue
        text = _text(path)
        if text is None:
            continue
        if _PROGRAM.search(text) and "PROGRAM-ID" in text:
            programs.append(path)
        elif any(line.startswith("//") and not line.startswith("//*") for line in text.splitlines()[:40]):
            jcl.append(path)
        else:
            other.setdefault(path.stem.upper(), path)
    return programs, other, jcl


def analyze(root: Path, *, kind: str = "directory", location: str | None = None, commit: str | None = None) -> dict:
    root = root.resolve()
    sources, copybooks, jcl_members = classify(root)
    parsed = {p: parse_program(p.read_text(errors="replace")) for p in sources}
    program_ids = {info.name for info in parsed.values()}
    by_name = {info.name: (p, info) for p, info in parsed.items()}

    def modules_of(name: str, seen: set[str]) -> list[str]:
        """CALLed programs found in the repository, transitively, as repo-relative paths."""
        out = []
        for callee in by_name[name][1].calls:
            if callee in by_name and callee not in seen:
                seen.add(callee)
                out.append(by_name[callee][0].relative_to(root).as_posix())
                out += modules_of(callee, seen)
        return out
    procs = {proc.name: proc for p in jcl_members for proc in parse_procs(p.read_text(errors="replace"))}
    steps = [s for p in jcl_members for s in parse_jcl(p.read_text(errors="replace"), p.relative_to(root).as_posix(), procs)]
    programs, dependencies, findings = [], [], []
    for path in sources:
        text = path.read_text(errors="replace")
        info = parsed[path]
        modules = modules_of(info.name, {info.name})
        module_copybooks = [c for m in modules for c in parsed[root / m].copybooks]
        step = next((s for s in steps if s.program == info.name), None)
        files = []
        for file_name, dd in info.selects.items():
            if file_name in info.sort_files:
                continue  # SD sort work file
            member = info.fd_copybooks.get(file_name)
            if member in copybooks:
                copybook_text = apply_replacing(copybooks[member].read_text(errors="replace"),
                                                info.replacing.get(file_name, []))
                layout = parse_copybook(copybook_text)
            elif file_name in info.fd_inline:
                layout = parse_copybook(info.fd_inline[file_name], code=True)
            else:
                layout = None
            organization = info.organizations.get(file_name, "SEQUENTIAL")
            if layout and not layout.unsupported:
                binary = [f["name"] for f in layout.fields if f.get("usage", "display") != "display"]
                if organization == "LINE SEQUENTIAL" and binary:
                    layout.unsupported = (f"{', '.join(binary[:3])}: packed or binary data in a LINE SEQUENTIAL file "
                                          "(bytes can look like line breaks); use ORGANIZATION SEQUENTIAL")
            files.append({
                "dd": dd,
                "direction": info.directions.get(file_name, "unknown"),
                "dsn": step.dsns.get(dd) if step else None,
                "organization": info.organizations.get(file_name, "SEQUENTIAL"),
                "copybook": member,
                "layout": ({**layout.as_dict(), "format": "line" if organization == "LINE SEQUENTIAL" else "fixed"}
                           if layout and layout.as_dict() else None),
                **({"unsupported": layout.unsupported} if layout and layout.unsupported else {}),
            })
        reason = _not_convertible(files, info.copybooks, copybooks, info, program_ids)
        programs.append({
            "name": info.name,
            "path": path.relative_to(root).as_posix(),
            "copybooks": list(dict.fromkeys(info.copybooks + module_copybooks)),
            "modules": modules,
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


def _not_convertible(files: list[dict], used: list[str], available: dict[str, Path], info, program_ids: set[str]) -> str | None:
    missing = [c for c in used if c not in available]
    if missing:
        return f"copybook(s) not found: {', '.join(missing)}"
    if info.exec_blocks:
        return f"EXEC {'/'.join(info.exec_blocks)} needs a database or transaction adapter, not supported yet"
    if info.dynamic_calls:
        return f"dynamic CALL through {', '.join(info.dynamic_calls)}: the called program is only known at run time"
    unknown = [c for c in info.calls if c not in program_ids]
    if unknown:
        return f"CALLs program(s) not in the repository: {', '.join(unknown)}"
    keyed = [f"{f['dd']} ({f['organization']})" for f in files if f.get("organization") in ("INDEXED", "RELATIVE")]
    if keyed:
        return f"keyed file(s) {', '.join(keyed)} are not supported yet"
    inputs = [f for f in files if f["direction"] == "input"]
    outputs = [f for f in files if f["direction"] == "output"]
    other = [f["dd"] for f in files if f["direction"] not in ("input", "output")]
    if other:
        return f"file(s) {', '.join(other)} are opened I-O or never opened; update-in-place is not supported yet"
    if not outputs:
        return "writes no output file to compare"
    for f in inputs + outputs:
        if f["layout"] is None:
            return f"{f['dd']}: {f.get('unsupported') or 'record layout not found'}"
    return None


def validate_report(report: dict) -> None:
    import jsonschema

    jsonschema.validate(report, json.loads(CONTRACT.read_text()))


def main_class(program: str) -> str:
    return "".join(part.capitalize() for part in program.split("-"))


def cobol_name(path: str) -> str:
    """File name a compiler recognises: library members (no extension) get .cbl."""
    name = Path(path).name
    return name if Path(name).suffix.lower() in COBOL_SUFFIXES else f"{name}.cbl"


def shared_keys(inputs: list[dict]) -> dict:
    """Key fields that link input files: alphanumeric, same length, same name after the record prefix
    (MS-ACCT-ID and TX-ACCT-ID). Each file is assumed sorted by its first shared key, as sequential
    match-merge programs require."""
    by_suffix: dict[tuple[str, int], list[list[str]]] = {}
    for f in inputs:
        for field in f["layout"]["fields"]:
            if field["kind"] == "alnum" and "-" in field["name"] and not field.get("redefines"):
                suffix = field["name"].split("-", 1)[1]
                by_suffix.setdefault((suffix, field["length"]), []).append([f["dd"], field["name"]])
    groups = [g for g in by_suffix.values() if len({dd for dd, _ in g}) >= 2]
    if not groups:
        return {}
    sorted_by = {}
    for g in groups:
        for dd, name in g:
            sorted_by.setdefault(dd, name)
    return {"sharedKeys": groups, "sortedBy": sorted_by}


def write_sample(root: Path, report: dict, program: dict, out_dir: Path) -> Path:
    """Materialize one convertible program as a Diocle sample directory (the converter's input format)."""
    root = root.resolve()
    sample = out_dir / program["name"].lower()
    (sample / "src").mkdir(parents=True, exist_ok=True)
    (sample / "copybooks").mkdir(exist_ok=True)
    source = root / program["path"]
    _, copybooks, _ = classify(root)
    source_name = cobol_name(program["path"])
    shutil.copy2(source, sample / "src" / source_name)
    for module in program.get("modules", []):
        shutil.copy2(root / module, sample / "src" / cobol_name(module))
    for member in program["copybooks"]:
        shutil.copy2(copybooks[member], sample / "copybooks" / f"{member}.cpy")  # PDS members have no extension
    inputs = [f for f in program["files"] if f["direction"] == "input"]
    outputs = [f for f in program["files"] if f["direction"] == "output"]
    single = len(inputs) == 1 and len(outputs) == 1
    by_direction = {f["direction"]: f for f in program["files"]}
    meta = {
        "name": program["name"].lower(),
        "description": f"Imported from {report['source']['location']}"
                       + (f" at {report['source']['commit'][:12]}" if report["source"].get("commit") else ""),
        "program": program["name"],
        "source": f"src/{source_name}",
        "modules": [f"src/{cobol_name(m)}" for m in program.get("modules", [])],
        "collation": "ebcdic",  # mainframe source: alphanumeric comparisons and sorts follow EBCDIC order
        "copybookDir": "copybooks",
        **({"dd": {"input": by_direction["input"]["dd"], "output": by_direction["output"]["dd"]}} if single else {}),
        "javaConversion": {"dir": "java-conversion", "mainClass": main_class(program["name"]),
                           "origin": "none yet: translate with the converter's run command"},
        "layoutsNote": "Derived from the copybooks by services/analyzer.",
        **({"layouts": {"input": by_direction["input"]["layout"], "output": by_direction["output"]["layout"]}} if single
           else {"files": [{"dd": f["dd"], "direction": f["direction"], "layout": f["layout"]} for f in inputs + outputs],
                 **shared_keys(inputs)}),
        "import": {"repository": report["source"]["location"], "commit": report["source"].get("commit"),
                   "path": program["path"], "job": program.get("job")},
    }
    (sample / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return sample
