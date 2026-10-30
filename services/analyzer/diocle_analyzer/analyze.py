"""Analyze a source tree (a cloned repository or a local directory) into an analysis report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import REPORT_VERSION
from .cobol import apply_replacing, parse_copybook, parse_program
import re

from .jcl import SortSpec, group_jobs, is_sort_step, parse_jcl, parse_procs, parse_sort_fields, wire_steps
from .risks import find_risks
from .keyed import SUBSET_VERSION as KEYED_SUBSET, key_problem
from .sqlsubset import SUBSET_VERSION, SqlFacts, analyze_sql, parse_ddl

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
    ddl_tables = [t for p in sorted(root.rglob("*.sql")) if ".git" not in p.parts
                  for t in parse_ddl(p.read_text(errors="replace"), p.relative_to(root).as_posix())]
    sql_members = {name: (path.read_text(errors="replace"), path.relative_to(root).as_posix())
                   for name, path in copybooks.items()}
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
            keyed = None
            if file_name in info.keyed:
                keyed = dict(info.keyed[file_name])
                if layout and not layout.unsupported and not keyed["refusal"] and keyed["recordKey"]:
                    keyed["refusal"] = key_problem(dd, keyed, layout.fields)
            files.append({
                "dd": dd,
                "direction": info.directions.get(file_name, "unknown"),
                "dsn": step.dsns.get(dd) if step else None,
                "organization": info.organizations.get(file_name, "SEQUENTIAL"),
                "copybook": member,
                **({"keyed": _keyed_fact(keyed)} if keyed else {}),
                "layout": ({**layout.as_dict(), "format": "line" if organization == "LINE SEQUENTIAL" else "fixed"}
                           if layout and layout.as_dict() else None),
                **({"unsupported": layout.unsupported} if layout and layout.unsupported else {}),
            })
        sql = analyze_sql(text, sql_members, ddl_tables) if "SQL" in info.exec_blocks else None
        reason = _not_convertible(files, info.copybooks, copybooks, info, program_ids, sql)
        includes = sql.includes if sql else []
        programs.append({
            "name": info.name,
            "path": path.relative_to(root).as_posix(),
            "copybooks": list(dict.fromkeys(info.copybooks + module_copybooks + includes)),
            "copybookPaths": {c: copybooks[c].relative_to(root).as_posix()
                              for c in dict.fromkeys(info.copybooks + module_copybooks + includes) if c in copybooks},
            "modules": modules,
            "job": step.member if step else None,
            **({"resolvedCalls": info.resolved_calls} if info.resolved_calls else {}),
            **({"sql": sql.as_dict()} if sql else {}),
            "files": [{k: v for k, v in f.items() if k != "unsupported"} for f in files],
            **({"displayOnly": True} if _display_only(reason, files) and info.stdout_display else {}),
            "convertible": reason is None,
            "notConvertibleReason": reason,
        })
        dependencies += [{"from": info.name, "to": c, "kind": "copy"} for c in info.copybooks]
        dependencies += [{"from": info.name, "to": c, "kind": "call"} for c in info.calls]
        dependencies += [{"from": info.name, "to": f["dsn"] or f["dd"], "kind": "file"} for f in files]
        if step:
            dependencies.append({"from": step.job, "to": info.name, "kind": "job"})
        findings += find_risks(info.name, text)
    programs_by_name = {p["name"]: p for p in programs}
    # Resolving a SYSIN DD DSN=...(MEMBER) control-statement member: library members with no recognized
    # extension land in `copybooks` by stem (classify()'s content-based bucket, same as any other mainframe
    # library member outside a JCL/COBOL suffix); JCL-suffixed members are included too, for completeness.
    member_by_stem = {**{p.name.upper(): p for p in jcl_members}, **copybooks}
    jobs = [_job_report(job, programs_by_name, program_ids, member_by_stem)
            for job in group_jobs(steps)]
    return {
        "version": REPORT_VERSION,
        "source": {"kind": kind, "location": location or str(root), "commit": commit},
        "programs": programs,
        "dependencies": dependencies,
        "findings": findings,
        "jobs": jobs,
    }


def _resolve_sysin_text(dsn: str, member_by_stem: dict[str, Path]) -> str | None:
    """Text behind a SYSIN DD's DSN: an inline literal is not resolvable from JobStep.dsns (parse_jcl only
    captures DSN= forms), so this handles the DSN=dataset(MEMBER) form, looking the member up by stem the
    same way copybooks are resolved. None if the member cannot be found (an external reference this
    analysis cannot resolve, same convention as a missing copybook: refused with a reason, not guessed)."""
    m = re.search(r"\(([A-Z0-9#@$]+)\)$", dsn.upper())
    member = m.group(1) if m else dsn.upper()
    path = member_by_stem.get(member)
    return path.read_text(errors="replace") if path else None


def _job_report(job, programs_by_name: dict[str, dict], program_ids: set[str],
                member_by_stem: dict[str, Path]) -> dict:
    step_reports = []
    for s in job.steps:
        sort_json = None
        convertible_program = None
        step_reason = None
        if is_sort_step(s):
            kind_ = "sort"
            sysin = s.dsns.get("SYSIN")
            text = _resolve_sysin_text(sysin, member_by_stem) if sysin else None
            spec = (parse_sort_fields(text) if text is not None
                    else SortSpec(unsupported="SYSIN control statement not found or not resolvable"))
            job.sorts[s.step] = spec
            sort_json = {"fields": [list(f) for f in spec.fields], "optionEquals": spec.option_equals,
                        "unsupported": spec.unsupported}
            step_reason = spec.unsupported
        elif s.program in program_ids:
            kind_ = "cobol"
            program = programs_by_name.get(s.program)
            convertible_program = program["convertible"] if program else False
            step_reason = program["notConvertibleReason"] if program else "program not found in the repository"
        else:
            kind_ = "other"
        step_reports.append({
            "step": s.step,
            "proc": s.proc,
            "kind": kind_,
            "program": s.program,
            "dds": dict(s.dsns),
            "sort": sort_json,
            "convertibleProgram": convertible_program,
            "notConvertibleReason": step_reason,
        })
    wiring = [{"fromStep": p.step, "fromDd": p_dd, "toStep": c.step, "toDd": c_dd, "dsn": p.dsns[p_dd]}
              for p, p_dd, c, c_dd in wire_steps(job)]

    kinds = [s["kind"] for s in step_reports]
    reason: str | None = None
    if kinds != ["sort", "cobol"]:
        reason = f"{job.name}: only one SORT step followed by one COBOL step is supported yet"
    else:
        sort_step, cobol_step = job.steps[0], job.steps[1]
        spec = job.sorts.get(sort_step.step)
        cobol_reason = step_reports[1]["notConvertibleReason"]
        if spec and spec.unsupported:
            reason = f"{sort_step.step}: {spec.unsupported}"
        elif cobol_reason:
            reason = f"{cobol_step.step} ({cobol_step.program}): {cobol_reason}"
        elif (cobol := programs_by_name.get(cobol_step.program)) and (
                cobol.get("displayOnly") or any(f["direction"] == "io" for f in cobol["files"])):
            reason = (f"{cobol_step.step} ({cobol_step.program}): the job check compares output files only; a program "
                      "updated in place or compared on stdout converts on its own, not as a JCL job yet")
        elif not any(e["fromStep"] == sort_step.step for e in wiring):
            reason = (f"{job.name}: {sort_step.step}'s output DD is not read by the following COBOL step "
                      "(no matching DSN)")
    return {
        "name": job.name,
        "member": job.member,
        "steps": step_reports,
        "wiring": wiring,
        "convertible": reason is None,
        "notConvertibleReason": reason,
    }


def _display_only(reason: str | None, files: list[dict]) -> bool:
    """Convertible with no output or I-O file: the verifier compares stdout and exit code (see services/verifier)."""
    return reason is None and not any(f["direction"] in ("output", "io") for f in files)


def _keyed_fact(keyed: dict) -> dict:
    """The contract's `keyed` block (analysis-report v0.7). The refusal is carried to the program's reason."""
    fact = {"subset": KEYED_SUBSET, "accessMode": keyed["accessMode"], "fileStatus": keyed["fileStatus"]}
    if isinstance(keyed["recordKey"], dict):
        fact["recordKey"] = keyed["recordKey"]
    elif keyed["recordKey"]:
        fact["recordKey"] = {"field": keyed["recordKey"]}
    if keyed.get("openMode"):
        fact["openMode"] = keyed["openMode"]
    if keyed["refusal"]:
        fact["refusal"] = keyed["refusal"]
    return fact


def _writes_tables(sql: SqlFacts | None) -> bool:
    return bool(sql and any(s.kind in ("insert", "update", "delete") for s in sql.statements))


def _not_convertible(files: list[dict], used: list[str], available: dict[str, Path], info, program_ids: set[str],
                     sql: SqlFacts | None = None) -> str | None:
    missing = [c for c in used if c not in available]
    if missing:
        return f"copybook(s) not found: {', '.join(missing)}"
    unsupported = [b for b in info.exec_blocks if b != "SQL"]
    if unsupported:
        return f"EXEC {'/'.join(unsupported)} needs a transaction adapter, not supported (CICS and IMS are out of scope)"
    if info.exec_blocks:
        if sql is None or sql.refusal:
            return (f"EXEC SQL outside the verified subset ({SUBSET_VERSION}): "
                    + (sql.refusal if sql else "not understood"))
    if info.dynamic_calls:
        return f"dynamic CALL through {', '.join(info.dynamic_calls)}: the called program is only known at run time"
    unknown = [c for c in info.calls if c not in program_ids]
    if unknown:
        return f"CALLs program(s) not in the repository: {', '.join(unknown)}"
    keyed = [f for f in files if f.get("keyed")]
    for f in keyed:
        if f["keyed"].get("refusal"):
            return f"keyed file {f['keyed']['refusal']}"
        if "recordKey" not in f["keyed"] or "offset" not in f["keyed"]["recordKey"]:
            return f"keyed file {f['dd']}: the record layout needed to place the RECORD KEY was not found"
    if keyed and sql is not None:
        return "keyed files together with EXEC SQL are not supported yet"
    inputs = [f for f in files if f["direction"] == "input"]
    outputs = [f for f in files if f["direction"] == "output"]
    updated = [f for f in files if f["direction"] == "io"]
    other = [f["dd"] for f in files if f["direction"] not in ("input", "output", "io")]
    if other:
        return (f"file(s) {', '.join(other)} are opened I-O or never opened in a way that can be compared "
                "(a file opened I-O must be opened I-O everywhere)")
    lines = [f["dd"] for f in updated if f.get("organization") not in ("SEQUENTIAL", "RECORD SEQUENTIAL") and not f.get("keyed")]
    if lines:
        return f"file(s) {', '.join(lines)} opened I-O must be ORGANIZATION SEQUENTIAL (fixed records)"
    if not outputs and not updated:
        if not info.stdout_display and not _writes_tables(sql):
            return "writes no output file to compare"
        if info.console_input:
            return "ACCEPT reads the console: a DISPLAY-only program is compared on stdout, and its console input cannot be varied"
    for f in inputs + outputs + updated:
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


def _write_anyway_meta(sample: Path, report: dict, program: dict, source_name: str, missing: list[str]) -> Path:
    """Convert-anyway sample for a program the analyzer refuses: no layouts, so the verifier cannot certify it. The
    converter reads `convertAnyway.reason` and labels the result compiled-unverified (or failed), never certified."""
    meta = {
        "name": program["name"].lower(),
        "description": f"Imported from {report['source']['location']} (convert anyway: not certifiable)",
        "program": program["name"],
        "source": f"src/{source_name}",
        "modules": [f"src/{cobol_name(m)}" for m in program.get("modules", [])],
        "collation": "ebcdic",
        "copybookDir": "copybooks",
        "javaConversion": {"dir": "java-conversion", "mainClass": main_class(program["name"]),
                           "origin": "none yet: translate with the converter's run command"},
        "convertAnyway": {"reason": program["notConvertibleReason"], "missingCopybooks": missing},
        "import": {"repository": report["source"]["location"], "commit": report["source"].get("commit"),
                   "path": program["path"], "job": program.get("job")},
    }
    (sample / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return sample


def _sample_sql(program: dict, inputs: list[dict]) -> dict:
    """sample.json `sql`: the schema the verifier seeds, and which input fields hold the same keys as table columns
    (so generated input files find some rows and miss others)."""
    facts = program["sql"]
    links = []
    for table in facts["tables"]:
        for column in table["columns"]:
            if column["type"] not in ("CHAR", "VARCHAR"):
                continue
            want = column["name"].replace("_", "-")
            for f in inputs:
                for field in f["layout"]["fields"]:
                    if (field["kind"] == "alnum" and not field.get("redefines") and field["length"] <= column.get("length", 0)
                            and (field["name"] == want or field["name"].split("-", 1)[-1] == want)):
                        links.append({"dd": f["dd"], "field": field["name"], "table": table["name"], "column": column["name"]})
    kinds: dict[str, set[str]] = {}
    for st in facts["statements"]:
        for t in st.get("tables", []):
            if st["kind"] != "declare-table":
                kinds.setdefault(t, set()).add(st["kind"])
    insert_only = {t: 0 for t, k in kinds.items() if k == {"insert"}}  # nothing reads it: seeded empty, no key collisions
    writes = any(st["kind"] in ("insert", "update", "delete") for st in facts["statements"])
    return {"subset": SUBSET_VERSION, "tables": facts["tables"], "keyLinks": links, "writes": writes,
            **({"seedRows": insert_only} if insert_only else {})}


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
    missing = [m for m in program["copybooks"] if m not in copybooks]
    for member in program["copybooks"]:
        if member in copybooks:  # convert-anyway samples may name copybooks the repository does not have
            shutil.copy2(copybooks[member], sample / "copybooks" / f"{member}.cpy")  # PDS members have no extension
    if not program["convertible"]:
        return _write_anyway_meta(sample, report, program, source_name, missing)
    inputs = [f for f in program["files"] if f["direction"] == "input"]
    outputs = [f for f in program["files"] if f["direction"] == "output"]
    updated = [f for f in program["files"] if f["direction"] == "io"]
    single = (len(inputs) == 1 and len(outputs) == 1 and not updated and not program.get("displayOnly")
              and not program.get("sql"))
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
           else {"files": [{"dd": f["dd"], "direction": f["direction"], "layout": f["layout"]}
                           for f in inputs + updated + outputs],
                 **shared_keys(inputs)}),
        **({"displayOnly": True} if program.get("displayOnly") else {}),
        **({"sql": _sample_sql(program, inputs)} if program.get("sql") else {}),
        "import": {"repository": report["source"]["location"], "commit": report["source"].get("commit"),
                   "path": program["path"], "job": program.get("job")},
    }
    (sample / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return sample
