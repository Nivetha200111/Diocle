"""Verified documentation: a Muse Spark model writes a behaviour spec of the COBOL as CLAIMS, and GnuCOBOL checks them.

The model proposes; it never decides. Each claim is one sentence plus 1 to 3 concrete examples (input records as
field values per the program's file layout, and the expected output field values). Every example is validated
against the layout with the breaker's `explain` (the same rules as the breaker and cross-check) and the valid ones
are run on the ORIGINAL COBOL through the verifier (diocle_verifier.claims, in the sandbox when configured). A claim
is confirmed (every example matched), refuted (the COBOL produced something else; the actual value is kept) or
unchecked (an example was invalid for the layout, or the program did not run). Contract: behavior-claims v0.1.
Wording everywhere: "confirmed on the examples tried", never "proven".
"""

from __future__ import annotations

import json
from typing import Callable

from diocle_verifier import claims as verifier
from diocle_verifier.layout import load_fields, record_format

from .breaker import _layout_text, explain
from .client import BudgetExceeded, ModelClient, _call_cost, usage_of
from .config import PRICES, DocCaps
from .sources import Program

MAX_CLAIMS = 10
MAX_EXAMPLES = 3
MAX_INPUT_RECORDS = 5
VERSION = "0.1"

DOCUMENTER = """\
You are Diocle's documenter. Write a behaviour spec of a COBOL batch program as a list of CLAIMS that a program
called GnuCOBOL will then CHECK by running the real program on your examples. Wrong claims are caught and shown
publicly, so write only what you can state precisely, and do not guess.

A claim is one plain-English sentence about OBSERVABLE behaviour: what ends up in the output records (or stdout) for
given input records. Not internal variable names alone: say what a reader of the output file would see. Example
claim: "A negative balance is charged a late fee." Cover the program's main rules: each branch of every condition,
rounding versus truncation, caps and floors, status codes, and what is skipped, copied or counted.

Every claim has 1 to 3 examples, and each example is a concrete test:
- inputs: 1 to 5 input records in file order (use more than one only when the claim is about state across records).
  Each record names EVERY input field.
- expectedRecords: the output records you expect, in order, as field values. Name only the output fields the claim is
  about; others are not compared. Write the expected number the way it would print at the output field's decimals.
- optionally expectedRecordCount (-1 if not stated), expectedStdoutContains ("" if not stated), expectedReturnCode
  (-1 if not stated).
Include BOUNDARY examples: values exactly at a threshold, one unit either side of it, zero, the field maximum, and
exact rounding ties. Work the arithmetic out carefully from the COBOL before you state an expected value.

Hard rules for every input value, or the example is thrown away unrun:
- A numeric value must be a plain decimal number such as "-36.50" or "0.0500": no letters, no spaces, no empty string.
- It must not exceed the field's stated integer digits or decimals; use the stated maximum itself rather than something
  bigger. Never put a negative sign on a field marked unsigned. Overflow beyond the PIC cannot be expressed.
- A text value uses printable ASCII only and stays within the field's length.
Write at most %d claims. Do not invent behaviour the COBOL does not have.
""" % MAX_CLAIMS

_PAIRS = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                                     "required": ["name", "value"], "additionalProperties": False}}

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "behavior_claims",
        "schema": {
            "type": "object",
            "properties": {"claims": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "examples": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "inputs": {"type": "array", "items": _PAIRS},
                            "expectedRecords": {"type": "array", "items": _PAIRS},
                            "expectedRecordCount": {"type": "integer"},
                            "expectedStdoutContains": {"type": "string"},
                            "expectedReturnCode": {"type": "integer"},
                        },
                        "required": ["inputs", "expectedRecords", "expectedRecordCount", "expectedStdoutContains",
                                     "expectedReturnCode"],
                        "additionalProperties": False}},
                },
                "required": ["statement", "examples"], "additionalProperties": False}}},
            "required": ["claims"], "additionalProperties": False,
        },
    },
}


def _empty(program: str, model: str, reason: str) -> dict:
    return {"version": VERSION, "program": program, "model": model, "checkedWith": verifier.CHECKED_WITH,
            "summary": {"claims": 0, "confirmed": 0, "refuted": 0, "unchecked": 0, "examplesRun": 0}, "claims": [],
            "skipped": reason}


def _pairs(value) -> dict[str, str] | None:
    """[{name, value}, ...] to {name: value}; None if it is not that shape."""
    if not isinstance(value, list) or not all(isinstance(p, dict) for p in value):
        return None
    return {str(p.get("name")): p.get("value") for p in value}


def _parse(content: str) -> list[dict] | None:
    """The claims list of a model answer, or None when it is malformed or holds no usable claim."""
    try:
        answer = json.loads(content or "")
    except (json.JSONDecodeError, TypeError):
        return None
    raw = answer.get("claims") if isinstance(answer, dict) else None
    if not isinstance(raw, list):
        return None
    claims = [c for c in raw if isinstance(c, dict) and isinstance(c.get("statement"), str) and c["statement"].strip()]
    return claims[:MAX_CLAIMS] or None


def _prompt(program: Program, in_fields, out_fields) -> list[dict]:
    meta = json.loads((program.sample_dir / "sample.json").read_text())
    shape = "one record per line of text" if record_format(meta["layouts"]["input"]) == "line" else "fixed-length records"
    return [{"role": "system", "content": DOCUMENTER},
            {"role": "user", "content": f"COBOL:\n{program.as_text()}\n\nInput file ({shape}); fields in order:\n"
             f"{_layout_text(in_fields)}\n\nOutput record fields, in order:\n{_layout_text(out_fields)}\n\n"
             "Write the claims."}]


def _expected(example: dict) -> dict:
    """The contract's `expected` object from a model example (-1 and empty mean 'not stated')."""
    expected: dict = {}
    records = [_pairs(r) for r in example.get("expectedRecords", []) if isinstance(r, list)]
    records = [r for r in records if r]
    if records:
        expected["records"] = records[:5]
    count = example.get("expectedRecordCount")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        expected["outputRecordCount"] = count
    text = example.get("expectedStdoutContains")
    if isinstance(text, str) and text:
        expected["stdoutContains"] = text[:200]
    code = example.get("expectedReturnCode")
    if isinstance(code, int) and not isinstance(code, bool) and code >= 0:
        expected["returnCode"] = code
    return expected


def _clip(values: dict | None) -> dict:
    return {str(k)[:60]: (v if isinstance(v, str) else "<not a string>")[:200] for k, v in (values or {}).items()}


def document(program: Program, client: ModelClient, caps: DocCaps, on_event: Callable[[dict], None] = lambda e: None,
             run_original=verifier.run_original) -> dict:
    """The behavior-claims document for `program`. Never raises for a model or sandbox problem: `skipped` or
    `unchecked` says what happened. `client` carries the documenter's own settings (model, hard call cap)."""
    model = client.settings.model
    meta = json.loads((program.sample_dir / "sample.json").read_text())
    why = verifier.unsupported(meta)
    if why:
        return _empty(program.name, model, why)
    if model not in PRICES:  # fail closed: an unpriced model cannot be held to the dollar cap
        return _empty(program.name, model, f"{model} has no known price, so the cost cap cannot be enforced")
    in_fields, out_fields = load_fields(meta["layouts"]["input"]), load_fields(meta["layouts"]["output"])
    messages = _prompt(program, in_fields, out_fields)
    price = PRICES[model]
    worst = (sum(len(m["content"]) for m in messages) / 3 * price[0] + caps.max_output_tokens * price[2]) / 1e6
    if worst > caps.max_usd:
        return _empty(program.name, model, f"one call could cost up to ${worst:.3f}, over the ${caps.max_usd:.2f} cap")

    proposed, spent = None, 0.0
    for round_no in range(1, caps.max_calls + 1):
        if round_no > 1 and spent + worst > caps.max_usd:
            on_event({"type": "behavior", "message": "Documenter: no second call, it could pass the dollar cap"})
            break
        try:
            choice = client.chat(role="document", round=round_no, messages=messages, response_format=SCHEMA,
                                 max_tokens=caps.max_output_tokens)
        except BudgetExceeded as e:
            on_event({"type": "behavior", "message": f"Documenter: budget: {e}"})
            break
        spent += _call_cost(client.calls[-1]) or caps.max_usd
        content = choice.message.content or ""
        proposed = _parse(content)
        if proposed:
            break
        on_event({"type": "behavior", "message": f"Documenter round {round_no}: the answer had no usable claims"})
        messages += [{"role": "assistant", "content": content or "{}"},
                     {"role": "user", "content": "That was not valid. Answer again with the JSON object, at least one claim."}]
    usage = usage_of(client.calls)
    short = {k: usage[k] for k in ("calls", "inputTokens", "outputTokens", "estimatedCostUsd")}
    if not proposed:
        return {**_empty(program.name, model, "the model produced no usable claims"), "usage": short}

    # Build the claims, validating every example against the input layout with the breaker's rules.
    built: list[dict] = []
    to_run: list[dict] = []
    for ci, raw in enumerate(proposed, 1):
        examples = []
        for ei, ex in enumerate([e for e in raw.get("examples", []) if isinstance(e, dict)][:MAX_EXAMPLES], 1):
            eid = f"C{ci}-E{ei}"
            inputs = [_pairs(r) for r in ex.get("inputs", []) if isinstance(r, list)][:MAX_INPUT_RECORDS] \
                if isinstance(ex.get("inputs"), list) else []
            entry = {"id": eid, "inputs": [_clip(r) for r in inputs if r] or [{}], "expected": _expected(ex),
                     "status": "unchecked", "mismatches": []}
            entry["expected"] = {k: ([_clip(r) for r in v] if k == "records" else v) for k, v in entry["expected"].items()}
            records, reason = [], None
            for r in inputs:
                record, reason = explain(in_fields, r or {})
                if reason:
                    break
                records.append(record)
            if not inputs or all(not r for r in inputs):
                reason = "the example gives no input record"
            if reason:
                entry["reason"] = f"invalid for the input layout: {reason}"
            else:
                to_run.append({"id": eid, "records": records})
            examples.append(entry)
        built.append({"id": f"C{ci}", "statement": raw["statement"].strip()[:400], "status": "unchecked", "examples": examples})

    runs: dict[str, dict] = {}
    if to_run:
        try:
            runs = {r["id"]: r for r in run_original(program.sample_dir, to_run)}
        except Exception as e:  # sandbox down or busy: the examples are unchecked, nothing is guessed
            on_event({"type": "behavior", "message": f"Documenter: the verifier could not run the examples ({type(e).__name__})"})
            runs = {x["id"]: {"id": x["id"], "ran": False, "records": [], "stdout": "", "returnCode": None,
                              "error": "the verifier could not run the original COBOL"} for x in to_run}
    for claim in built:
        for entry in claim["examples"]:
            run = runs.get(entry["id"])
            if run is None:
                continue
            verdict = verifier.judge(entry["expected"], run, out_fields)
            entry["status"], entry["mismatches"] = verdict["status"], verdict["mismatches"]
            if verdict["actual"] is not None:
                entry["actual"] = verdict["actual"]
            if verdict["reason"]:
                entry["reason"] = verdict["reason"]
        claim["status"] = verifier.claim_status([e["status"] for e in claim["examples"]])
        if claim["status"] == "unchecked" and not claim["examples"]:
            claim["reason"] = "the model gave no example"
    return {"version": VERSION, "program": program.name, "model": model, "checkedWith": verifier.CHECKED_WITH,
            "summary": verifier.summarize(built), "claims": built, "usage": short}


def to_markdown(doc: dict) -> str:
    """The spec as Markdown, badges included. The same wording rules as the dashboard."""
    s = doc["summary"]
    lines = [f"# Behaviour spec: {doc['program']}", "",
             f"{s['confirmed']} of {s['claims']} claims confirmed on the examples tried "
             f"({s['refuted']} refuted, {s['unchecked']} unchecked).", "",
             f"Written by {doc['model']}; every example was run on the original COBOL ({doc['checkedWith']}). "
             "GnuCOBOL decided, not the model. \"Confirmed\" means the examples tried matched, not that the claim is proven.", ""]
    if doc.get("skipped"):
        return "\n".join(lines + [f"Not written: {doc['skipped']}", ""])
    for c in doc["claims"]:
        lines += [f"## {c['id']} [{c['status'].upper()}] {c['statement']}", ""]
        if c.get("reason"):
            lines += [f"Unchecked: {c['reason']}", ""]
        for e in c["examples"]:
            lines.append(f"- {e['id']} [{e['status'].upper()}]")
            lines.append(f"  - input: {json.dumps(e['inputs'])}")
            lines.append(f"  - expected: {json.dumps(e['expected'])}")
            if e.get("actual") is not None:
                lines.append(f"  - actual: {json.dumps({k: v for k, v in e['actual'].items() if k != 'stdout'})}")
            for m in e.get("mismatches", []):
                lines.append(f"  - differed at {m['what']}: expected {m['expected']}, GnuCOBOL produced {m['actual']}")
            if e.get("reason"):
                lines.append(f"  - unchecked: {e['reason']}")
        lines.append("")
    return "\n".join(lines)
