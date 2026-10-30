"""Cross-program checks on COBOL sources: copybook drift and CALL ... USING compatibility.

Static, deterministic, no execution. Used by the whole-repository build check (diocle_verifier.buildcheck). A check that
cannot be made (a USING argument that is not a plain 01/77 item, a layout the analyzer does not model) is reported as
unchecked, never as compatible.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .cobol import _REPLACING, _TOKEN, _VERBS, _entries, apply_replacing, parse_copybook, parse_program, source_lines

RUNTIME_ROUTINE = re.compile(r"^(CEE|ILB|CBL_|C\$|SYSTEM$|DFH|DSN|MQ|CBLTDLI|PLITDLI|ASMTDLI)")
_COPY = re.compile(r"\bCOPY\s+([A-Z0-9-]+)(?:\s+REPLACING\s+(.*?))?\s*\.(?=\s|$)")


@dataclass
class Source:
    program: str  # the delivered program this source belongs to (for reporting)
    path: str  # label shown in findings: repository-relative where known
    text: str
    copybooks: dict[str, tuple[str, str]] = field(default_factory=dict)  # member -> (path label, text)


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def normalize(text: str) -> str:
    """Copybook text without comments, sequence columns or spacing differences."""
    return re.sub(r"\s+", " ", " ".join(c for _, c in source_lines(text))).strip().upper()


def _bytes(f: dict) -> int:
    if f["kind"] == "alnum":
        return f["length"]
    usage, stored = f.get("usage", "display"), f["digits"] + f["scale"]
    if usage == "packed":
        return stored // 2 + 1
    if usage in ("binary", "binary-native"):
        return 2 if stored <= 4 else 4 if stored <= 9 else 8
    if usage == "float":
        return f.get("bytes", 8)
    return stored + (1 if str(f.get("sign", "")).endswith("separate") else 0)


def layouts_of(code_entries: list[str]) -> dict[str, dict | None]:
    """{01/77 item name: layout dict (None when not modelled)} for data description entries (already split on periods)."""
    groups: list[list[str]] = []
    for entry in code_entries:
        m = re.match(r"(\d{1,2})\s+[A-Z0-9-]+", entry)
        if not m:
            continue
        if m.group(1) in ("01", "1", "77"):
            groups.append([entry])
        elif groups:
            groups[-1].append(entry)
    out: dict[str, dict | None] = {}
    for g in groups:
        name = re.match(r"\d+\s+([A-Z0-9-]+)", g[0]).group(1)
        data = [e for e in g if not e.startswith("88")]
        if len(data) == 1:  # an elementary 01/77: the analyzer models records, so wrap it in a one-field record
            rest = re.match(r"\d+\s+[A-Z0-9-]+(.*)", data[0], re.S).group(1)
            text = f"01 W. 05 {name} {rest}."
        else:
            text = " ".join(e.rstrip(".") + "." for e in g)
        layout = parse_copybook(text, code=True)
        out[name] = layout.as_dict()
    return out


def _entries_of(text: str) -> list[str]:
    return _entries(text)


# ---- copybook drift ---------------------------------------------------------------------------------------------

def copybook_drift(sources: list[Source]) -> tuple[list[str], list[dict]]:
    """(every copybook COPYed, drift findings). Content drift: the member's normalized text differs between files.
    Layout drift: for the same COPY with the same REPLACING, the analyzer's record layouts differ."""
    used: dict[str, list[tuple[str, str, str, tuple]]] = {}  # name -> [(program, path, text, replacing)]
    for s in sources:
        info = parse_program(s.text)
        replacing = {}
        for fd, member in info.fd_copybooks.items():
            if member and fd in info.replacing:
                replacing[member] = tuple(info.replacing[fd])
        for name in info.copybooks:
            if name in s.copybooks:
                path, text = s.copybooks[name]
                used.setdefault(name, []).append((s.program, path, text, replacing.get(name, ())))
            else:
                used.setdefault(name, [])
    findings = []
    for name, uses in sorted(used.items()):
        by_print: dict[str, dict] = {}
        for program, path, text, _ in uses:
            v = by_print.setdefault(_fingerprint(normalize(text)), {"programs": [], "paths": []})
            if program not in v["programs"]:
                v["programs"].append(program)
            if path not in v["paths"]:
                v["paths"].append(path)
        # layouts per (REPLACING) group
        layout_drift = None
        groups: dict[tuple, dict[str, dict]] = {}
        for program, path, text, pairs in uses:
            lay = layouts_of(_entries_of(apply_replacing(text, list(pairs))))
            fp = _fingerprint(json.dumps(lay, sort_keys=True))
            g = groups.setdefault(pairs, {}).setdefault(fp, {"programs": [], "paths": [], "lay": lay})
            if program not in g["programs"]:
                g["programs"].append(program)
            if path not in g["paths"]:
                g["paths"].append(path)
        for pairs, versions in groups.items():
            if len(versions) > 1:
                layout_drift = versions
                break
        if layout_drift:
            vs = list(layout_drift.items())
            diff = _layout_difference(vs[0][1]["lay"], vs[1][1]["lay"])
            findings.append({
                "copybook": name, "kind": "layout", "severity": "fail",
                "message": f"COPY {name} gives different record layouts in different files ({diff}); programs that exchange data through it disagree.",
                "versions": [{"fingerprint": fp, "programs": v["programs"], "paths": v["paths"]} for fp, v in vs]})
        elif len(by_print) > 1:
            findings.append({
                "copybook": name, "kind": "content", "severity": "warn",
                "message": f"copybook {name} has {len(by_print)} different texts across files; the layouts the analyzer models are the same, "
                           "but check what else differs (VALUE clauses, unmodelled clauses, comments are ignored).",
                "versions": [{"fingerprint": fp, "programs": v["programs"], "paths": v["paths"]} for fp, v in by_print.items()]})
    return sorted(used), findings


def _layout_difference(a: dict, b: dict) -> str:
    for record in sorted(set(a) | set(b)):
        if record not in a or record not in b:
            return f"record {record} is only in one version"
        fa, fb = (a[record] or {}).get("fields", []), (b[record] or {}).get("fields", [])
        if a[record] is None or b[record] is None:
            continue
        for x, y in zip(fa, fb):
            if x != y:
                return f"record {record}, field {x['name']} vs {y['name']}: {_brief(x)} vs {_brief(y)}"
        if len(fa) != len(fb):
            return f"record {record}: {len(fa)} fields vs {len(fb)}"
    return "layouts differ"


def _brief(f: dict) -> str:
    if f["kind"] == "alnum":
        return f"X({f['length']})"
    return f"9({f['digits']})v{f['scale']} {f.get('usage', 'display')}{' signed' if f.get('signed') else ''}"


# ---- CALL ... USING ----------------------------------------------------------------------------------------------

def _expand(code: str, copybooks: dict[str, tuple[str, str]], depth: int = 0) -> str:
    def sub(m: re.Match) -> str:
        entry = copybooks.get(m.group(1))
        if entry is None or depth > 5:
            return " "
        pairs = _REPLACING.findall(m.group(2)) if m.group(2) else []
        body = " ".join(c.strip() for _, c in source_lines(apply_replacing(entry[1], pairs)))
        return " " + _expand(body, copybooks, depth + 1) + " "
    return _COPY.sub(sub, code)


def _sizes(text: str, copybooks: dict[str, tuple[str, str]]) -> dict[str, int | None]:
    """Byte length of each 01/77 item in WORKING-STORAGE and LINKAGE (None = not modelled)."""
    code = _expand(" ".join(c.strip() for _, c in source_lines(text)).upper(), copybooks)
    m = re.search(r"\bWORKING-STORAGE\s+SECTION\s*\.(.*?)(?=\bLINKAGE\s+SECTION\b|\bPROCEDURE\s+DIVISION\b|$)", code, re.S)
    l = re.search(r"\bLINKAGE\s+SECTION\s*\.(.*?)(?=\bPROCEDURE\s+DIVISION\b|$)", code, re.S)
    sizes: dict[str, int | None] = {}
    for part in (m, l):
        if not part:
            continue
        entries = [e.strip() for e in re.split(r"\.(?=\s|$)", part.group(1)) if e.strip()]
        for name, lay in layouts_of(entries).items():
            try:
                sizes[name] = sum(_bytes(f) for f in lay["fields"] if not f.get("redefines")) if lay else None
            except (KeyError, TypeError):
                sizes[name] = None
    return sizes


def _tokens(text: str) -> list[tuple[str, int]]:
    return [(m.group(), n) for n, code in source_lines(text) for m in _TOKEN.finditer(code.upper())]


def _proc_start(tokens: list[tuple[str, int]]) -> int:
    for i in range(len(tokens) - 1):
        if tokens[i][0] == "PROCEDURE" and tokens[i + 1][0] == "DIVISION":
            return i
    return len(tokens)


_SKIP_MODE = {"BY", "REFERENCE", "CONTENT", "VALUE"}
_STOP = {".", "END-CALL", "ON", "NOT", "RETURNING", "GIVING"} | _VERBS


def _using(tokens: list[tuple[str, int]], i: int) -> list[dict]:
    """Arguments of a USING clause starting after tokens[i] == 'USING': [{name, byValue, literal, complex}]."""
    args, mode_value, j = [], False, i + 1
    while j < len(tokens):
        tok = tokens[j][0]
        if tok in _STOP and tok != "VALUE":
            break
        if tok in ("BY",):
            j += 1
            continue
        if tok in ("REFERENCE", "CONTENT"):
            mode_value = False
            j += 1
            continue
        if tok == "VALUE":
            mode_value = True
            j += 1
            continue
        if tok in ("ADDRESS", "LENGTH") and j + 1 < len(tokens) and tokens[j + 1][0] == "OF":
            args.append({"name": None, "byValue": mode_value, "literal": None, "complex": True})
            j += 3
            continue
        arg = {"name": None, "byValue": mode_value, "literal": None, "complex": False}
        if tok[0] in "'\"":
            arg["literal"] = len(tok) - 2
        elif tok == "OMITTED" or tok[0].isdigit() or tok in "+-":
            arg["complex"] = True
        else:
            arg["name"] = tok
        j += 1
        if j < len(tokens) and tokens[j][0] == "(":  # subscript or reference modification
            arg["complex"], arg["name"] = True, None
            while j < len(tokens) and tokens[j][0] != ")":
                j += 1
            j += 1
        args.append(arg)
    return args


def interface(source: Source) -> dict:
    """{id, using: [names], sizes, calls: [{callee, line, args, dynamicName}]} for one program."""
    info = parse_program(source.text)
    tokens = _tokens(source.text)
    start = _proc_start(tokens)
    using: list[str] = []
    k = start + 2
    if k < len(tokens) and tokens[k][0] == "USING":
        for tok, _ in tokens[k + 1:]:
            if tok in (".", "RETURNING"):
                break
            if tok not in _SKIP_MODE:
                using.append(tok)
    calls = []
    for i in range(start, len(tokens)):
        if tokens[i][0] != "CALL" or i + 1 >= len(tokens):
            continue
        target, line = tokens[i + 1]
        if target[0] in "'\"":
            callee, dynamic = target[1:-1], None
        elif target in info.resolved_calls:
            callee, dynamic = info.resolved_calls[target], None
        else:
            callee, dynamic = None, target
        args = []
        j = i + 2
        while j < len(tokens) and tokens[j][0] not in ("USING", ".") and tokens[j][0] not in _VERBS:
            j += 1
        if j < len(tokens) and tokens[j][0] == "USING":
            args = _using(tokens, j)
        calls.append({"callee": callee, "dynamic": dynamic, "line": line, "args": args})
    return {"id": info.name, "using": using, "sizes": _sizes(source.text, source.copybooks), "calls": calls}


def call_findings(sources: list[Source]) -> tuple[int, list[dict]]:
    """(static CALL statements examined, findings). Every static CALL must name a program in `sources`; the callee's
    USING parameters must be satisfiable by the caller's arguments."""
    ifaces = [(s, interface(s)) for s in sources]
    by_id = {i["id"]: i for _, i in ifaces}
    findings, checked = [], 0

    def add(sev, kind, s, i, callee, line, msg):
        findings.append({"severity": sev, "kind": kind, "caller": s.program, "callee": callee or "?", "file": s.path,
                         "line": line, "message": msg})
    for s, i in ifaces:
        for c in i["calls"]:
            if c["callee"] is None:
                add("warn", "dynamic", s, i, c["dynamic"], c["line"],
                    f"CALL {c['dynamic']}: the target is only known at run time, so its presence and parameters were not checked")
                continue
            checked += 1
            callee = by_id.get(c["callee"])
            if callee is None:
                if RUNTIME_ROUTINE.match(c["callee"]):
                    add("info", "runtime-routine", s, i, c["callee"], c["line"],
                        f"CALL '{c['callee']}' is a runtime or system routine, not a program of this repository; not checked")
                else:
                    add("fail", "unresolved", s, i, c["callee"], c["line"],
                        f"CALL '{c['callee']}' names no program in this repository")
                continue
            args, params = c["args"], callee["using"]
            if len(args) < len(params):
                add("fail", "arity", s, i, c["callee"], c["line"],
                    f"CALL '{c['callee']}' passes {len(args)} argument(s) but {c['callee']} expects {len(params)} in PROCEDURE DIVISION USING")
                continue
            if len(args) > len(params):
                add("warn", "arity", s, i, c["callee"], c["line"],
                    f"CALL '{c['callee']}' passes {len(args)} argument(s) but {c['callee']} declares only {len(params)}")
            unchecked = 0
            for n, (arg, param) in enumerate(zip(args, params), 1):
                have = arg["literal"] if arg["literal"] is not None else (i["sizes"].get(arg["name"]) if arg["name"] else None)
                want = callee["sizes"].get(param)
                if arg["byValue"] or have is None or want is None:
                    unchecked += 1
                    continue
                if want > have:
                    add("fail", "length", s, i, c["callee"], c["line"],
                        f"CALL '{c['callee']}' argument {n} ({arg['name'] or 'literal'}) is {have} bytes but {param} in {c['callee']} is {want}: "
                        "the callee reads or writes past the caller's item")
                elif want < have:
                    add("warn", "length", s, i, c["callee"], c["line"],
                        f"CALL '{c['callee']}' argument {n} ({arg['name'] or 'literal'}) is {have} bytes but {param} in {c['callee']} is {want}: "
                        "the callee sees only the first bytes")
            if unchecked:
                add("info", "unchecked-argument", s, i, c["callee"], c["line"],
                    f"CALL '{c['callee']}': {unchecked} of {len(params)} argument length(s) could not be compared "
                    "(subscripted or computed argument, BY VALUE, a layout the analyzer does not model, or an item outside WORKING-STORAGE/LINKAGE)")
    return checked, findings
