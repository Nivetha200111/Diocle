"""The verified subset of keyed (INDEXED / VSAM KSDS-style) files: parsing, classification and exact refusal reasons.

Deterministic, no compiler needed. The verifier's seeding and Java support class (DioKsds) implement exactly this subset,
and what is checked is GnuCOBOL's INDEXED file handler (Berkeley DB), not IBM VSAM.

Subset `ksds-subset-1`:
  SELECT f ASSIGN TO dd ORGANIZATION IS INDEXED ACCESS MODE IS SEQUENTIAL | RANDOM | DYNAMIC
         RECORD KEY IS k FILE STATUS IS fs.        (FILE STATUS is required: without it a failing I/O aborts the run)
  k: one elementary RECORD KEY, alphanumeric or unsigned DISPLAY numeric, inside the file's one record layout.
  OPEN INPUT | OUTPUT | I-O (one mode per file); READ f [NEXT] [INTO x]; READ f (by key); WRITE; REWRITE; DELETE f;
  START f KEY IS = | >= | > | NOT < ; CLOSE.
Everything else is refused with the exact reason: ALTERNATE RECORD KEY, WITH DUPLICATES, RELATIVE files, LOCK MODE and
WITH LOCK, READ PREVIOUS, START with < or <=, OPEN EXTEND, group or signed or packed or binary keys, no FILE STATUS,
a file opened more than one way, DECLARATIVES, and keyed files together with EXEC SQL.
"""

from __future__ import annotations

import re

SUBSET_VERSION = "ksds-subset-1"

_STOP = {"MOVE", "IF", "PERFORM", "DISPLAY", "CLOSE", "OPEN", "STOP", "GO", "ADD", "SUBTRACT", "COMPUTE", "WRITE", "REWRITE", "DELETE",
         "READ", "START", "EVALUATE", "CALL", "INITIALIZE", "SET", "ELSE", "END-IF", "END-READ", "END-START", "END-WRITE", "END-REWRITE",
         "END-DELETE", "INVALID", "AT", "NOT", "ACCEPT", "EXIT", "GOBACK", "STRING", "UNSTRING", "INSPECT", "SORT", "MERGE", "RETURN",
         "RELEASE", "CONTINUE", "WHEN", "END-EVALUATE", "END-PERFORM", "."}


def _tokens(code: str) -> list[str]:
    return re.findall(r"'[^']*'|[A-Z0-9][A-Z0-9-]*|>=|<=|<>|[<>=.]|\S", code)


def select_clauses(code: str) -> dict[str, str]:
    return {m.group(1): m.group(2)
            for m in re.finditer(r"\bSELECT\s+([A-Z0-9-]+)(.*?)(?=\bSELECT\s|\bDATA\s+DIVISION\b|$)", code)}


def keyed_files(code: str, organizations: dict[str, str]) -> dict[str, dict]:
    """File name -> {"accessMode", "recordKey" (field name), "fileStatus", "refusal" (exact reason or None)} for every
    INDEXED or RELATIVE file. Offsets and lengths are added by the analyzer from the record layout."""
    out: dict[str, dict] = {}
    clauses = select_clauses(code)
    for name, org in organizations.items():
        if org not in ("INDEXED", "RELATIVE"):
            continue
        text = clauses.get(name, "")
        access = re.search(r"\bACCESS\s+(?:MODE\s+)?(?:IS\s+)?(SEQUENTIAL|RANDOM|DYNAMIC)\b", text)
        key = re.search(r"(?<!ALTERNATE )\bRECORD\s+KEY\s+(?:IS\s+)?([A-Z0-9-]+)", text)
        status = re.search(r"\bFILE\s+STATUS\s+(?:IS\s+)?([A-Z0-9-]+)", text)
        refusal = None
        if org == "RELATIVE":
            refusal = f"{name}: RELATIVE files are not supported (only ORGANIZATION INDEXED with one record key)"
        elif re.search(r"\bALTERNATE\s+(?:RECORD\s+)?KEY\b", text):
            refusal = f"{name}: ALTERNATE RECORD KEY is not supported (one record key only)"
        elif re.search(r"\bDUPLICATES\b", text):
            refusal = f"{name}: WITH DUPLICATES is not supported (record keys must be unique)"
        elif re.search(r"\bLOCK\s+MODE\b|\bPASSWORD\b|\bSHARING\b", text):
            refusal = f"{name}: LOCK MODE / record locking is not supported"
        elif not key:
            refusal = f"{name}: no RECORD KEY clause found"
        elif not status:
            refusal = (f"{name}: no FILE STATUS clause: a failing keyed I/O would abort the original program, "
                       "and its status codes could not be compared")
        out[name] = {"accessMode": access.group(1) if access else "SEQUENTIAL", "recordKey": key.group(1) if key else None,
                     "fileStatus": status.group(1) if status else None, "refusal": refusal}
    if not out:
        return out
    tokens = _tokens(code)
    modes: dict[str, set[str]] = {}
    for i, tok in enumerate(tokens):
        if tok == "OPEN":
            mode = None
            for word in tokens[i + 1:]:
                if word in ("INPUT", "OUTPUT", "EXTEND", "I-O"):
                    mode = word
                elif word in out and mode:
                    modes.setdefault(word, set()).add(mode)
                else:
                    break
        elif tok in ("START", "READ", "DELETE", "WRITE", "REWRITE") and i + 1 < len(tokens) and tokens[i + 1] in out:
            name = tokens[i + 1]
            if out[name]["refusal"]:
                continue
            tail = []
            for word in tokens[i + 2:]:
                if word in _STOP and word not in ("NOT", "AT", "INVALID"):
                    break
                tail.append(word)
                if len(tail) > 14:
                    break
            reason = None
            if tok == "START":
                reason = _start_refusal(name, tail)
            elif tok == "READ":
                if "PREVIOUS" in tail:
                    reason = f"{name}: READ PREVIOUS is not supported"
                elif "LOCK" in tail or "KEPT" in tail:
                    reason = f"{name}: READ ... WITH LOCK is not supported"
                elif "KEY" in tail:
                    reason = f"{name}: READ ... KEY IS (reading by an alternate key) is not supported"
            if reason:
                out[name]["refusal"] = reason
        elif tok == "DELETE" and i + 1 < len(tokens) and tokens[i + 1] == "FILE":
            for word in tokens[i + 2:i + 6]:
                if word in out and not out[word]["refusal"]:
                    out[word]["refusal"] = f"{word}: DELETE FILE is not supported"
    for name, seen in modes.items():
        if out[name]["refusal"]:
            continue
        if "EXTEND" in seen:
            out[name]["refusal"] = f"{name}: OPEN EXTEND on a keyed file is not supported"
        elif len(seen) > 1:
            out[name]["refusal"] = (f"{name}: the keyed file is opened more than one way ({', '.join(sorted(seen))}); "
                                    "one OPEN mode per file is supported")
        else:
            out[name]["openMode"] = next(iter(seen))
    if "DECLARATIVES" in tokens:
        for name in out:
            if not out[name]["refusal"]:
                out[name]["refusal"] = f"{name}: DECLARATIVES / USE AFTER ERROR procedures are not supported"
    return out


def _start_refusal(name: str, tail: list[str]) -> str | None:
    if "KEY" not in tail:
        return None  # START f: KEY IS = the record key
    rest = [w for w in tail[tail.index("KEY") + 1:] if w != "IS"]
    words = " ".join(rest[:5])
    if re.match(r"(=|EQUAL( TO)?|>|GREATER( THAN)?|>=|GREATER( THAN)? OR EQUAL( TO)?|NOT <|NOT LESS( THAN)?)\b|^(=|>|>=|NOT <)", words):
        if re.match(r"(NOT <|NOT LESS)", words) or not re.match(r"(<|LESS)", words):
            return None
    return f"{name}: START with KEY {rest[0] if rest else '?'} is not supported (only =, >, >= and NOT <)"


def key_problem(name: str, facts: dict, layout_fields: list[dict]) -> str | None:
    """Reason the record key cannot be used (not an elementary alphanumeric or unsigned DISPLAY numeric field of the
    record), else None. Adds recordKey offset and length to facts."""
    key = facts["recordKey"]
    offset = 0
    for f in layout_fields:
        if f.get("redefines"):
            continue
        width = field_bytes(f)
        if f["name"] == key:
            if f.get("occurs"):
                return f"{name}: RECORD KEY {key} is inside an OCCURS table"
            if f["kind"] == "numeric" and (f.get("usage", "display") != "display" or f.get("signed")):
                return (f"{name}: RECORD KEY {key} is a signed, packed or binary numeric field: only alphanumeric and "
                        "unsigned DISPLAY numeric keys are supported")
            facts["recordKey"] = {"field": key, "offset": offset, "length": width}
            return None
        offset += width
    return f"{name}: RECORD KEY {key} is not an elementary field of the file's record layout (group keys are not supported)"


def field_bytes(f: dict) -> int:
    if f["kind"] == "alnum":
        return f["length"]
    stored = f["digits"] + f["scale"]
    usage = f.get("usage", "display")
    if usage == "packed":
        return stored // 2 + 1
    if usage in ("binary", "binary-native"):
        return 2 if stored <= 4 else 4 if stored <= 9 else 8
    if usage == "float":
        return f.get("bytes", 8)
    return stored + (1 if str(f.get("sign", "")).endswith("separate") else 0)
