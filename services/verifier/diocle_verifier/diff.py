"""Field-by-field comparison of original vs converted output records."""

from __future__ import annotations

from .inputs import Case
from .layout import Field, parse_record, record_length


def compare(cases: list[Case], original: list[str], converted: list[str], out_fields: list[Field]) -> list[dict]:
    results = []
    for i, case in enumerate(cases):
        o = original[i] if i < len(original) else None
        c = converted[i] if i < len(converted) else None
        result = {"program": "", "inputId": case.id, "inputSource": case.source, "input": case.record}
        if o is not None:
            result["originalOutput"] = o
        if c is not None:
            result["convertedOutput"] = c
        if o is None or c is None:
            missing = "original" if o is None else "converted"
            result |= {"match": False, "fieldDiffs": [], "diff": f"no {missing} output record"}
            results.append(result)
            continue
        ov, cv = parse_record(o, out_fields), parse_record(c, out_fields)
        field_diffs = [
            {"field": f.name, "original": str(ov[f.name]).strip() or repr(ov[f.name]), "converted": str(cv[f.name]).strip() or repr(cv[f.name])}
            for f in out_fields
            if ov[f.name] != cv[f.name]
        ]
        expected_length = record_length(out_fields)
        length_note = (
            f"converted record is {len(c)} bytes, expected {expected_length}: a field overflowed its width and shifted the fields after it"
            if len(c) != expected_length
            else ""
        )
        result["match"] = not field_diffs and not length_note
        result["fieldDiffs"] = field_diffs
        if not result["match"]:
            parts = ([length_note] if length_note else []) + [
                f"{d['field']}: original {d['original']} converted {d['converted']}" for d in field_diffs
            ]
            result["diff"] = "; ".join(parts)
        results.append(result)
    for j in range(len(cases), max(len(original), len(converted))):
        results.append({"program": "", "inputId": f"extra-{j + 1:04d}", "match": False, "diff": "extra output record"})
    return results
