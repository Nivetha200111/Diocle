"""Comparison of original vs converted output: the whole output sequence, record by record, byte for byte.

A record matches only if its bytes are identical (for "line" records, after the trailing spaces a LINE SEQUENTIAL
writer may trim). Fields are parsed only to explain a difference, so +00 and -00 differ even though they are
the same number. Records are paired by their position in the output, not by input: a program that aggregates
(many inputs, one output) or fans out (one input, many outputs) is compared on what it actually wrote.
When the original wrote exactly one record per input, each result names the input that produced it.
"""

from __future__ import annotations

from .inputs import Case
from .layout import Field, parse_record, record_length


def _normal(record: str, fmt: str, length: int) -> str:
    """The bytes that must be equal: "line" records ignore trailing spaces (the writer may trim them)."""
    return record.rstrip("\r\n").rstrip(" ") if fmt == "line" else record


def _field_diffs(o: str, c: str, fields: list[Field], fmt: str) -> list[dict]:
    length = record_length(fields)
    pad = (lambda r: r.rstrip("\r\n").ljust(length)) if fmt == "line" else (lambda r: r)
    o, c = pad(o), pad(c)
    ov, cv = parse_record(o, fields), parse_record(c, fields)
    diffs, pos = [], 0
    for f in fields:
        ro, rc = o[pos : pos + f.length], c[pos : pos + f.length]
        pos += f.length
        if ro == rc:
            continue
        if ov[f.name] != cv[f.name]:
            diffs.append({"field": f.name, "original": str(ov[f.name]).strip() or repr(ov[f.name]),
                          "converted": str(cv[f.name]).strip() or repr(cv[f.name])})
        else:  # same value, different bytes: a sign, zone or padding difference the record would carry
            diffs.append({"field": f.name, "original": repr(ro), "converted": repr(rc),
                          "note": "same value, different bytes"})
    return diffs


def compare(cases: list[Case], original: list[str], converted: list[str], out_fields: list[Field],
            fmt: str = "line") -> list[dict]:
    """fmt "line": text records whose trailing spaces the writer may trim (GnuCOBOL LINE SEQUENTIAL does), so only a
    longer record means a field overflowed. fmt "fixed": byte records, whose length must be exact."""
    one_to_one = len(original) == len(cases)
    expected_length = record_length(out_fields)
    results = []
    for i in range(max(len(original), len(converted))):
        o = original[i] if i < len(original) else None
        c = converted[i] if i < len(converted) else None
        if one_to_one and i < len(cases):
            result = {"program": "", "inputId": cases[i].id, "inputSource": cases[i].source, "input": cases[i].record}
        else:
            result = {"program": "", "inputId": f"output-{i + 1:04d}", "inputSource": "output"}
        if o is not None:
            result["originalOutput"] = o
        if c is not None:
            result["convertedOutput"] = c
        if o is None or c is None:
            result |= {"match": False, "fieldDiffs": [],
                       "diff": f"output record {i + 1}: the {'original' if o is None else 'converted'} program wrote "
                               f"{len(original) if o is None else len(converted)} records, the other wrote more"}
            results.append(result)
            continue
        wrong_length = len(c) > expected_length if fmt == "line" else len(c) != expected_length
        length_note = (f"converted record is {len(c)} bytes, expected {expected_length}: a field overflowed its width "
                       "and shifted the fields after it" if wrong_length else "")
        same = _normal(o, fmt, expected_length) == _normal(c, fmt, expected_length)
        field_diffs = [] if same else _field_diffs(o, c, out_fields, fmt)
        result["match"] = same and not length_note
        result["fieldDiffs"] = field_diffs
        if not result["match"]:
            parts = ([length_note] if length_note else []) + [
                f"{d['field']}: original {d['original']} converted {d['converted']}"
                + (f" ({d['note']})" if d.get("note") else "") for d in field_diffs]
            result["diff"] = "; ".join(parts) or "records differ outside the described fields"
        results.append(result)
    return results
