"""Whole-repository build check (contracts/build-report.schema.json).

Per-program verification proves each program on its own. This checks the delivered programs TOGETHER:
  - every converted Java file compiled in one `javac -proc:none` run (no network, nothing executed), plus each program alone;
  - top-level class names that collide between programs;
  - copybook drift (same member, different text or different record layout) and CALL ... USING compatibility, from the COBOL
    sources the programs were converted from (diocle_analyzer.interfaces);
  - a dependency graph of programs, copybooks, calls and files.
It is not a behavioural check, and the report says so (`scope.notChecked`).

EXPERIMENTAL: --domain-classes PATH (a directory of .java files, or one .jar) puts the customer's own classes on the javac
classpath so the converted programs are checked to compile beside them. Compile-time only: the classes are never loaded or
run here; a jar is never extracted, only read by javac and listed.

  python -m diocle_verifier.buildcheck --program HRFEE020 JAVA_DIR SAMPLE_DIR [--program ...] [--report analysis-report.json]
                                       [--domain-classes PATH] --out DIR     (writes build-report.json and BUILD-REPORT.md)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from diocle_analyzer.cobol import parse_program
from diocle_analyzer.interfaces import Source, call_findings, copybook_drift

from .runners import safe_env
from .sqlpre import SUPPORT

VERSION = "0.1"
MAX_JAVA_FILES, MAX_JAVA_BYTES = 200, 1_000_000  # per program
MAX_DOMAIN_FILES, MAX_DOMAIN_BYTES, MAX_JAR_BYTES, MAX_JAR_ENTRIES = 500, 5_000_000, 20_000_000, 20_000
JAVAC_SECONDS = 120
MAX_FINDINGS = 200
SCOPE_NOT_CHECKED = [
    "behaviour of the programs together: each program is verified on its own by differential testing against the original COBOL",
    "that the programs' files and datasets line up at run time (JCL step order, DD wiring)",
    "CALL USING arguments that are subscripted, computed, BY VALUE or outside WORKING-STORAGE/LINKAGE items",
    "dynamic CALLs and programs outside this repository",
]
_STRIP = re.compile(r'"""(?:\\.|[^\\])*?"""|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
_TYPE = re.compile(r"\b(?:class|interface|enum|record|@interface)\s+([A-Za-z_$][\w$]*)")
_DIAG = re.compile(r"^([\w./$-]+):(\d+): error: (.*)$")


# ---- Java source scanning --------------------------------------------------------------------------------------

def top_level_types(source: str) -> tuple[str, list[str]]:
    """(package, [top-level type names]) of one Java file, comment- and string-aware, without compiling it."""
    code = _STRIP.sub(" ", source)
    depth, flat = 0, []
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            flat.append(ch)
    text = "".join(flat)
    pkg = re.search(r"\bpackage\s+([\w.]+)\s*;", text)
    return (pkg.group(1) if pkg else ""), _TYPE.findall(text)


def _java_files(root: Path, max_files: int, max_bytes: int) -> list[Path]:
    """Regular .java files under root (symlinks never followed or read), bounded."""
    found, total = [], 0
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(base) / d).is_symlink())
        for name in sorted(files):
            p = Path(base) / name
            if name.endswith(".java") and p.is_file() and not p.is_symlink():
                total += p.stat().st_size
                found.append(p)
                if len(found) > max_files or total > max_bytes:
                    raise ValueError(f"more than {max_files} Java files or {max_bytes} bytes under one directory")
    return found


def _clean(text: str, limit: int = 200) -> str:
    text = re.sub(r"/[\w.@+-]+(?:/[\w.@+-]+)+", "...", text)  # absolute paths out
    return "".join(c if " " <= c <= "~" else "?" for c in text)[:limit]


def _diagnostics(stderr: str) -> list[str]:
    lines, out = stderr.splitlines(), []
    for n, line in enumerate(lines):
        m = _DIAG.match(line)
        if not m:
            continue
        msg = m.group(3)
        for follow in lines[n + 1:n + 5]:
            sym = re.match(r"\s+symbol:\s+(.*)$", follow)
            if sym:
                msg += f" [symbol: {sym.group(1)}]"
                break
        out.append(_clean(f"{m.group(1).removeprefix('./')}:{m.group(2)}: error: {msg}"))
        if len(out) == 20:
            break
    return out


def _argfile(path: Path, files: list[str]) -> str:
    """javac @argfile: one double-quoted path per line (backslash and quote escaped), so spaces are safe, the command line
    never grows with the number of files (no ARG_MAX), and a name starting with '-' is a file because of the './' prefix."""
    lines = []
    for f in files:
        f = f if f.startswith(("/", "./")) else "./" + f
        lines.append('"' + f.replace("\\", "\\\\").replace('"', '\\"') + '"')
    path.write_text("\n".join(lines) + "\n")
    return "@" + str(path)


def _javac(files: list[str], cwd: Path, classpath: str | None = None) -> dict:
    """One javac -proc:none run: {status, javacExit, diagnostics}. No source path, so only the listed files are compiled."""
    with tempfile.TemporaryDirectory(prefix="diocle-bc-out-") as out, tempfile.TemporaryDirectory(prefix="diocle-bc-sp-") as empty:
        cmd = ["javac", "-proc:none", "-encoding", "UTF-8", "-sourcepath", empty, "-d", out,
               *(["-cp", classpath] if classpath else []), _argfile(Path(out).parent / (Path(out).name + ".args"), files)]
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=JAVAC_SECONDS,
                                  env=safe_env(), stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            return {"status": "skipped", "javacExit": None, "diagnostics": [], "note": "javac was not found"}
        except subprocess.TimeoutExpired:
            return {"status": "fail", "javacExit": None, "diagnostics": [], "note": f"javac did not finish within {JAVAC_SECONDS} s"}
    return {"status": "ok" if proc.returncode == 0 else "fail", "javacExit": proc.returncode,
            "diagnostics": [] if proc.returncode == 0 else _diagnostics(proc.stderr)}


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "note"}


# ---- COBOL sources of a program (as the delivery has them) -------------------------------------------------------

def _cobol_sources(name: str, sample_dir: Path, report_program: dict | None) -> list[Source]:
    meta_path = sample_dir / "sample.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    copy_dir = sample_dir / meta.get("copybookDir", "copybooks")
    labels = (report_program or {}).get("copybookPaths", {})
    copybooks = {}
    if copy_dir.is_dir():
        for p in sorted(copy_dir.iterdir()):
            if p.is_file() and not p.is_symlink():
                copybooks[p.stem.upper()] = (labels.get(p.stem.upper(), f"{sample_dir.name}/{copy_dir.name}/{p.name}"),
                                             p.read_text(errors="replace"))
    out = []
    members = [meta.get("source")] + list(meta.get("modules", []))
    for rel in [m for m in members if m]:
        p = (sample_dir / rel).resolve()
        if sample_dir.resolve() not in p.parents or not p.is_file():
            continue  # never read outside the sample directory
        label = (report_program or {}).get("path") if rel == meta.get("source") and report_program else f"{sample_dir.name}/{rel}"
        out.append(Source(name, label, p.read_text(errors="replace"), copybooks))
    return out


# ---- domain classes (EXPERIMENTAL) --------------------------------------------------------------------------------

def _prepare_domain(path: Path, work: Path) -> dict:
    """Confine and stage the customer's classes. Returns {kind, classpath, types: {fq: sha or None}, entries, ownCompile}."""
    if path.is_symlink() or not path.exists():
        raise ValueError("--domain-classes must be an existing directory of .java files or a .jar (not a symlink)")
    if path.is_dir():
        files = _java_files(path, MAX_DOMAIN_FILES, MAX_DOMAIN_BYTES)
        stage = work / "domain-src"
        rels = []
        types: dict[str, str | None] = {}
        for f in files:
            rel = f.relative_to(path)
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, stage / rel)
            rels.append("./" + str(rel))  # a file named -J-Xmx1k.java is a file, never a javac option
            text = f.read_text(errors="replace")
            pkg, names = top_level_types(text)
            for t in names:
                types[f"{pkg}.{t}" if pkg else t] = hashlib.sha256(text.encode()).hexdigest()
        classes = work / "domain-classes"
        classes.mkdir()
        own = {"status": "skipped", "javacExit": None, "diagnostics": []}
        if rels:
            with tempfile.TemporaryDirectory(prefix="diocle-bc-sp-") as empty:
                try:
                    proc = subprocess.run(["javac", "-proc:none", "-encoding", "UTF-8", "-sourcepath", empty, "-d", str(classes),
                                           _argfile(work / "domain.args", rels)],
                                          cwd=stage, capture_output=True, text=True, errors="replace", timeout=JAVAC_SECONDS,
                                          env=safe_env(), stdin=subprocess.DEVNULL)
                    own = {"status": "ok" if proc.returncode == 0 else "fail", "javacExit": proc.returncode,
                           "diagnostics": [] if proc.returncode == 0 else _diagnostics(proc.stderr)}
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    own = {"status": "skipped", "javacExit": None, "diagnostics": []}
        return {"kind": "source", "classpath": str(classes), "types": types, "entries": len(rels), "ownCompile": own}
    if path.suffix != ".jar" or not path.is_file() or path.stat().st_size > MAX_JAR_BYTES or not zipfile.is_zipfile(path):
        raise ValueError("--domain-classes must be an existing directory of .java files or a .jar (not a symlink)")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if len(names) > MAX_JAR_ENTRIES or any(n.startswith("/") or ".." in n.split("/") for n in names):
        raise ValueError("the jar has too many entries or entry names that leave the archive")
    staged = work / "domain.jar"
    # javac reads a STAGED COPY. A relative Class-Path entry in its manifest therefore resolves beside the copy (an empty temp
    # directory), not beside the original. Absolute or file: Class-Path entries are not confined: javac may read those paths as
    # class bytes (read-only, nothing is run). So: the jar is never executed, extracted or modified; its manifest can only make
    # javac read other class files it can already read.
    shutil.copyfile(path, staged)
    types = {n[:-6].replace("/", "."): None for n in names
             if n.endswith(".class") and "$" not in n and not n.endswith(("module-info.class", "package-info.class"))}
    return {"kind": "jar", "classpath": str(staged), "types": types, "entries": len(types),
            "ownCompile": {"status": "skipped", "javacExit": None, "diagnostics": []}}


# ---- the check -----------------------------------------------------------------------------------------------------

def build_check(programs: list[dict], report: dict | None = None, domain_classes: Path | None = None) -> dict:
    """programs: [{name, javaDir, sampleDir}] (the certified programs as a delivery has them). report: the analysis report
    (optional; adds repository paths and dataset names). domain_classes: EXPERIMENTAL, see the module docstring."""
    by_name = {p["name"]: p for p in (report or {}).get("programs", [])}
    reasons: list[str] = []
    verdict_fail = verdict_warn = False

    def fail(msg: str) -> None:
        nonlocal verdict_fail
        verdict_fail = True
        reasons.append(msg)

    def warn(msg: str) -> None:
        nonlocal verdict_warn
        verdict_warn = True
        reasons.append(msg)

    with tempfile.TemporaryDirectory(prefix="diocle-buildcheck-") as tmp:
        work = Path(tmp)
        domain = None
        if domain_classes is not None:
            domain = _prepare_domain(Path(domain_classes), work)
        stage = work / "stage"
        prog_reports, all_files, types_by_program = [], [], {}
        support_used: list[str] = []
        for prog in programs:
            name = prog["name"]
            dest = stage / name
            dest.mkdir(parents=True)
            rels, classes, uses_dio = [], [], False
            try:
                files = _java_files(Path(prog["javaDir"]), MAX_JAVA_FILES, MAX_JAVA_BYTES)
            except ValueError:
                files = []
                fail(f"{name}: too many or too large Java files to check")
            for f in files:
                rel = f.relative_to(prog["javaDir"])
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dest / rel)
                text = f.read_text(errors="replace")
                uses_dio = uses_dio or bool(re.search(r"\bDioSql\b", text))
                pkg, names = top_level_types(text)
                for t in names:
                    fq = f"{pkg}.{t}" if pkg else t
                    classes.append(fq)
                    types_by_program.setdefault(fq, {}).setdefault(hashlib.sha256(text.encode()).hexdigest(), []).append(name)
                rels.append(str(rel))
            has_dio_file = any(Path(r).name == "DioSql.java" for r in rels)
            if uses_dio and not has_dio_file:
                support_used.append(name)
            prog_reports.append({"name": name, "mainClass": None, "javaFiles": sorted(rels), "classes": sorted(set(classes)),
                                 "_dir": dest, "_dio": uses_dio and not has_dio_file})
            all_files += [f"{name}/{r}" for r in rels]
        if support_used:
            (stage / "_support").mkdir()
            shutil.copyfile(SUPPORT / "DioSql.java", stage / "_support" / "DioSql.java")
            warn(f"{', '.join(sorted(support_used))} use DioSql, the verifier's own support class, which is not part of the delivered "
                 "programs: they compile only with it added (the generated CI adds it from the pinned Diocle commit)")
        cp = domain["classpath"] if domain else None
        for pr in prog_reports:
            files = [f"{pr['name']}/{r}" for r in pr["javaFiles"]] + (["_support/DioSql.java"] if pr["_dio"] else [])
            single = _javac(files, stage, cp) if files else {"status": "skipped", "javacExit": None, "diagnostics": [], "note": "no Java files"}
            if single["status"] == "fail":
                fail(f"{pr['name']}: its Java does not compile" + (f" ({single['note']})" if single.get("note") else ""))
            elif single["status"] == "skipped":
                warn(f"{pr['name']}: its Java was not compiled ({single.get('note', 'skipped')})")
            pr["compile"] = _public(single)
            pr.pop("_dir"), pr.pop("_dio")
        # class collisions: same fully qualified type, different source
        collisions = []
        for fq, versions in sorted(types_by_program.items()):
            owners = sorted({p for ps in versions.values() for p in ps})
            if len(owners) > 1:
                collisions.append({"class": fq, "between": owners})
                fail(f"class {fq} is declared in {', '.join(owners)}")
            if domain and fq in domain["types"]:
                collisions.append({"class": fq, "between": [*owners, "domain classes"]})
                fail(f"class {fq} in {', '.join(owners)} has the same name as a supplied domain class")
        # One compile of everything, exactly what the generated CI compiles: byte-identical copies are NOT skipped,
        # because javac reports them as duplicate classes there too.
        whole_files = list(all_files)
        if support_used:
            whole_files.append("_support/DioSql.java")
        whole = _javac(whole_files, stage, cp) if whole_files else {"status": "skipped", "javacExit": None, "diagnostics": [], "note": "no Java files"}
        if whole["status"] == "fail":
            fail("compiling all programs together fails" + (f" ({whole['note']})" if whole.get("note") else ""))
        elif whole["status"] == "skipped":
            warn(f"the whole-repository compile was not run ({whole.get('note', 'skipped')})")
        whole_report = {"compile": _public(whole), "sources": len(whole_files)}
        if support_used:
            whole_report["supportClasses"] = ["DioSql.java"]
        if domain:
            whole_report["domainClasses"] = {"kind": domain["kind"], "entries": domain["entries"], "ownCompile": domain["ownCompile"]}
            if domain["ownCompile"]["status"] == "fail":
                warn("the supplied domain classes do not compile on their own; the failure is in them, not in the converted programs")
            if domain["entries"] == 0:
                warn("the supplied domain classes contain no Java sources or classes")
        # COBOL side
        sources: list[Source] = []
        seen_src = set()
        for prog in programs:
            for s in _cobol_sources(prog["name"], Path(prog["sampleDir"]), by_name.get(prog["name"])):
                key = (parse_program(s.text).name, hashlib.sha256(s.text.encode()).hexdigest())
                if key not in seen_src:
                    seen_src.add(key)
                    sources.append(s)
        names, drift = copybook_drift(sources)
        checked, calls = call_findings(sources)
        for d in drift:
            (fail if d["severity"] == "fail" else warn)(d["message"])
        for c in calls:
            if c["severity"] in ("fail", "warn"):
                (fail if c["severity"] == "fail" else warn)(f"{c['file']}:{c['line']}: {c['message']}")
        graph = _graph(sources, programs, report, names)
        for pr in prog_reports:
            pr["mainClass"] = next((p.get("javaConversion", {}).get("mainClass") for p in [_meta(Path(q["sampleDir"])) for q in programs if q["name"] == pr["name"]]), None)
    if not programs:
        warn("no program was given to check")
    truncated = len(calls) > MAX_FINDINGS
    findings = calls[:MAX_FINDINGS]
    if truncated:
        warn(f"{len(calls) - MAX_FINDINGS} more CALL findings were omitted from this report")
    reasons = reasons[:30]
    return {
        "version": VERSION,
        "verdict": "fail" if verdict_fail else "warn" if verdict_warn else "pass",
        "reasons": [_clean(r, 300) for r in reasons],
        "scope": {"checked": [
            f"{len(prog_reports)} program(s): each compiled alone and all {len(whole_files)} Java file(s) compiled together with javac -proc:none",
            "top-level class names across programs" + (" and the supplied domain classes" if domain else ""),
            f"{len(names)} copybook(s) for drift between files (text and analyzer layout)",
            f"{checked} static CALL statement(s): target present, USING count and argument lengths where both sides are plain items"],
            "notChecked": SCOPE_NOT_CHECKED},
        "programs": prog_reports,
        "whole": whole_report,
        "classCollisions": collisions,
        "copybooks": {"names": names, "drift": drift},
        "calls": {"checked": checked, "findings": findings},
        "graph": graph,
    }


def _meta(sample_dir: Path) -> dict:
    p = sample_dir / "sample.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def _graph(sources: list[Source], programs: list[dict], report: dict | None, copybooks: list[str]) -> dict:
    nodes: dict[str, str] = {p["name"]: "program" for p in programs}
    edges: set[tuple[str, str, str]] = set()
    dsn = {}
    for rp in (report or {}).get("programs", []):
        for f in rp.get("files", []):
            dsn[(rp["name"], f["dd"])] = f.get("dsn") or f["dd"]
    for s in sources:
        info = parse_program(s.text)
        nodes.setdefault(info.name, "program")
        for c in info.copybooks:
            nodes[c] = "copybook"
            edges.add((info.name, c, "copy"))
        for callee in info.calls:
            nodes.setdefault(callee, "external")
            edges.add((info.name, callee, "call"))
        for dd in info.selects.values():
            fid = dsn.get((info.name, dd), dd)
            nodes.setdefault(fid, "file")
            edges.add((info.name, fid, "file"))
    # a callee that is a program of the repository is a program, not external
    for s in sources:
        nodes[parse_program(s.text).name] = "program"
    return {"nodes": [{"id": k, "kind": v} for k, v in sorted(nodes.items())],
            "edges": [{"from": a, "to": b, "kind": k} for a, b, k in sorted(edges)]}


# ---- Markdown ---------------------------------------------------------------------------------------------------

def _md(text: object) -> str:
    """Report text into Markdown: only a conservative character set survives (no links, HTML, tables or code fences)."""
    return re.sub(r"[^A-Za-z0-9 _.,:;'/=+$-]", "?", str(text))


def render_markdown(r: dict) -> str:
    icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}[r["verdict"]]
    out = [f"# Build report: {icon}", "",
           "Whole-repository build check by Diocle (`contracts/build-report.schema.json` v" + r["version"] + "). "
           "Each program is certified on its own; this checks them together."]
    if r["reasons"]:
        out += ["", "## Why", ""] + [f"- {_md(x)}" for x in r["reasons"]]
    out += ["", "## Programs compiled together", "", "| Program | Java files | Classes | Alone |", "|---|---|---|---|"]
    for p in r["programs"]:
        out.append(f"| {_md(p['name'])} | {len(p['javaFiles'])} | {_md(', '.join(p['classes']))} | {p['compile']['status']} |")
    w = r["whole"]
    out += ["", f"All {w['sources']} source file(s) in one javac run: **{w['compile']['status']}**"
            + (f" (exit {w['compile']['javacExit']})" if w["compile"].get("javacExit") is not None else "")]
    for d in w["compile"]["diagnostics"]:
        out.append(f"- `{_md(d)}`")
    for p in r["programs"]:
        for d in p["compile"]["diagnostics"]:
            out.append(f"- {_md(p['name'])} alone: `{_md(d)}`")
    if w.get("domainClasses"):
        dc = w["domainClasses"]
        out += ["", f"Domain classes (EXPERIMENTAL, compile-time classpath only): {dc['kind']}, {dc['entries']} entr(ies); "
                f"compiled alone: {dc['ownCompile']['status']}."]
    if r["classCollisions"]:
        out += ["", "## Class-name collisions", ""] + [f"- `{_md(c['class'])}` in {_md(', '.join(c['between']))}" for c in r["classCollisions"]]
    if r["copybooks"]["drift"]:
        out += ["", "## Copybook drift", ""]
        for d in r["copybooks"]["drift"]:
            out.append(f"- **{d['severity']}** `{_md(d['copybook'])}` ({d['kind']}): {_md(d['message'])}")
            for v in d["versions"]:
                out.append(f"  - {v['fingerprint']}: {_md(', '.join(v['programs']))} ({_md(', '.join(v['paths']))})")
    shown = [c for c in r["calls"]["findings"] if c["severity"] != "info"]
    out += ["", f"## CALLs ({r['calls']['checked']} static CALL statement(s) examined)", ""]
    out += [f"- **{c['severity']}** {_md(c['file'])}:{c['line']}: {_md(c['message'])}" for c in shown] or ["- no mismatch found among the checked arguments"]
    info = len(r["calls"]["findings"]) - len(shown)
    if info:
        out.append(f"- {info} informational note(s) (runtime routines, arguments that could not be compared) are in build-report.json")
    out += ["", f"## Dependency graph", "", f"{len(r['graph']['nodes'])} nodes, {len(r['graph']['edges'])} edges (full graph in build-report.json).",
            "", "## What was checked", ""] + [f"- {_md(x)}" for x in r["scope"]["checked"]]
    out += ["", "## What was NOT checked", ""] + [f"- {_md(x)}" for x in r["scope"]["notChecked"]]
    return "\n".join(out) + "\n"


def validate(report: dict) -> None:
    import jsonschema

    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "build-report.schema.json").read_text())
    jsonschema.validate(report, schema)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_verifier.buildcheck", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--program", nargs=3, action="append", metavar=("NAME", "JAVA_DIR", "SAMPLE_DIR"), required=True)
    parser.add_argument("--report", type=Path, help="the analysis report (repository paths and dataset names in the graph)")
    parser.add_argument("--domain-classes", type=Path, help="EXPERIMENTAL: a directory of .java files or a .jar of your own classes, "
                        "put on the javac classpath (compile-time only; never loaded or run)")
    parser.add_argument("--out", type=Path, required=True, help="directory for build-report.json and BUILD-REPORT.md")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text()) if args.report else None
    try:
        result = build_check([{"name": n, "javaDir": j, "sampleDir": s} for n, j, s in args.program], report, args.domain_classes)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    validate(result)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "build-report.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.out / "BUILD-REPORT.md").write_text(render_markdown(result))
    print(f"build check: {result['verdict']}" + "".join(f"\n  - {r}" for r in result["reasons"]))
    return 1 if result["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
