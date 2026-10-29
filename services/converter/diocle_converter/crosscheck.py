"""Independent cross-check: after certification, Muse Spark Open (open weights, its own host and key) reads the COBOL
and the certified Java and designs inputs where it thinks they disagree. It reuses the breaker's loop: every input it
proposes is validated against the layout and run through GnuCOBOL and the Java. The model's opinion certifies nothing;
only a case that actually differs counts, and it goes to the repair agent like a breaker case.
"""

from __future__ import annotations

from .breaker import Breaker

CROSSCHECK = """\
You are Diocle's independent cross-checker. A different AI wrote a Java translation of a COBOL batch program, and the
translation already passed differential testing against the original compiled with GnuCOBOL. You did not write it and
you must not trust it. Read the COBOL and the Java side by side and find where they could disagree.

Work in two steps.
1. List risky edge cases as concrete input records: sign handling (negative values, zero, negative zero), COMPUTE ROUNDED
   ties versus truncation, high-order overflow without ON SIZE ERROR, empty or all-space fields, boundary comparisons,
   cumulative state across records, and malformed numeric content (spaces or letters in a numeric field).
2. For every field where you believe the Java diverges from the COBOL, name the field and say why in one sentence.

Each field value is a plain string within the field's PIC size. Every case must name every field. Explain each case in
one short sentence. If you cannot find a plausible divergence, say so with an empty "suspected" list; do not invent one.
"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "crosscheck",
        "schema": {
            "type": "object",
            "properties": {
                "cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fields": {"type": "array", "items": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                                "required": ["name", "value"], "additionalProperties": False}},
                            "why": {"type": "string"},
                        },
                        "required": ["fields", "why"],
                        "additionalProperties": False,
                    },
                },
                "suspected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"field": {"type": "string"}, "concern": {"type": "string"}},
                        "required": ["field", "concern"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["cases", "suspected"],
            "additionalProperties": False,
        },
    },
}


def make_crosschecker(program, workspace, client, verify, input_layout, on_event) -> Breaker:
    """A Breaker loop with the cross-checker's role, prompt and schema; one call proposes up to 15 cases."""
    return Breaker(program, workspace, client, verify, input_layout, on_event, per_round=15, role="crosscheck",
                   event_type="crosscheck", system=CROSSCHECK, schema=SCHEMA, label_name="Cross-check")


def summarize(breaker: Breaker, model: str, attack_summary: dict) -> dict:
    """The run.json `crosscheck` entry (contracts/run.schema.json)."""
    return {"model": model, "casesProposed": breaker.proposed_total, "casesValid": len(breaker.attempts),
            "mismatches": attack_summary["broke"], "repairCycles": attack_summary["repairCycles"],
            "fixed": attack_summary["fixed"], "suspected": breaker.suspected, "rejectedBecause": breaker.rejected,
            "counterexamples": attack_summary["counterexamples"]}
