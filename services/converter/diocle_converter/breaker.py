"""Breaker agent: after certification, a second model call tries to design inputs that make the Java disagree
with the COBOL. GnuCOBOL decides; any input that breaks the Java is handed back to the repair agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

from diocle_verifier.inputs import Case
from diocle_verifier.layout import Field, format_record, load_fields

from .client import BudgetExceeded, ModelClient
from .sources import Program
from .workspace import Workspace

BREAKER = """\
You are Diocle's breaker agent. A Java translation of a COBOL batch program has just passed differential testing
against the original compiled with GnuCOBOL. Your job is to prove it wrong: design input records on which the Java's
output will differ from the COBOL's.

Read the COBOL for the semantics that are easy to get subtly wrong: COMPUTE ROUNDED ties (half away from zero,
including negatives), COMPUTE without ROUNDED (truncation), silent high-order overflow without ON SIZE ERROR,
boundary comparisons (NOT <, >=), sign handling of zero, cumulative state across records, edited DISPLAY output.
Then read the Java for places where it might not match. Prefer exact boundary values and exact ties over random ones.

Each field value is a plain string: numbers like "-36.50" or "0.0500" within the field's PIC size, text within its
length. Every case must name every field. Explain each case in one short sentence.
"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "attack",
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
            },
            "required": ["cases"],
            "additionalProperties": False,
        },
    },
}

# verify(java_dir, seed, random_count, extra_cases) -> verification report
VerifyWithCases = Callable[..., dict]


def to_record(fields: list[Field], values: dict[str, str]) -> str | None:
    """Format a model-proposed case with the input layout; None if any value is missing or does not fit."""
    parsed = {}
    for f in fields:
        raw = values.get(f.name)
        if raw is None:
            return None
        if f.kind == "alnum":
            if len(raw) > f.length:
                return None
            parsed[f.name] = raw
            continue
        try:
            number = Decimal(raw.strip().replace("+", ""))
        except InvalidOperation:
            return None
        if number.normalize().as_tuple().exponent < -f.scale:  # more decimals than the PIC holds
            return None
        parsed[f.name] = number
    try:
        return format_record(parsed, fields)
    except ValueError:
        return None


def _layout_text(fields: list[Field]) -> str:
    rows = []
    for f in fields:
        if f.kind == "alnum":
            rows.append(f"- {f.name}: text, {f.length} chars" + (f", known values {list(f.values)}" if f.values else ""))
        else:
            rows.append(f"- {f.name}: number, {f.digits} integer digits, {f.scale} decimals, "
                        f"{'signed' if f.signed else 'unsigned'}, max {f.max_value}")
    return "\n".join(rows)


@dataclass
class Breaker:
    program: Program
    workspace: Workspace
    client: ModelClient
    verify: VerifyWithCases
    input_layout: dict
    on_event: Callable[[dict], None] = lambda event: None
    per_round: int = 12
    attempts: list[dict] = field(default_factory=list)

    def attack(self, rounds: int = 3, label: str = "attack") -> list[dict]:
        """Up to `rounds` attack rounds; stops at the first round that breaks the Java. Returns the breaking cases."""
        fields = load_fields(self.input_layout)
        java = "\n".join(f"=== {f} ===\n{self.workspace.read(f)}" for f in self.workspace.list_files())
        messages = [
            {"role": "system", "content": BREAKER},
            {"role": "user", "content": f"COBOL (source of truth):\n{self.program.as_text()}\n\n"
             f"Certified Java:\n{java}\n\nInput record fields, in order:\n{_layout_text(fields)}\n\n"
             f"Design up to {self.per_round} cases."},
        ]
        for round_no in range(1, rounds + 1):
            try:
                choice = self.client.chat(role="breaker", round=round_no, messages=messages, response_format=SCHEMA)
            except BudgetExceeded as e:
                self.on_event({"type": "breaker", "round": round_no, "message": f"budget: {e}", "tried": 0, "broke": 0})
                return []
            messages.append({"role": "assistant", "content": choice.message.content or "{}"})
            try:
                proposed = json.loads(choice.message.content or "{}").get("cases", [])[: self.per_round]
            except json.JSONDecodeError:
                proposed = []
            cases, why = [], {}
            for i, item in enumerate(proposed):
                record = to_record(fields, {f["name"]: f["value"] for f in item.get("fields", []) if isinstance(f, dict)})
                if record:
                    case_id = f"breaker-{label}-r{round_no}-{i + 1:02d}"
                    cases.append(Case(case_id, "model", record))
                    why[case_id] = item.get("why", "")
            report = self.verify(self.workspace.root, 1026, 0, cases)
            broken = [r for r in report["results"] if r.get("inputSource") == "model" and not r["match"]]
            for r in report["results"]:
                if r.get("inputSource") == "model":
                    self.attempts.append({"id": r["inputId"], "input": r.get("input"), "why": why.get(r["inputId"], ""),
                                          "broke": not r["match"], "diff": r.get("diff", "")})
            self.on_event({"type": "breaker", "round": round_no, "tried": len(cases), "broke": len(broken),
                           "message": (f"Breaker round {round_no}: {len(broken)} of {len(cases)} designed inputs break the Java"
                                       if broken else f"Breaker round {round_no}: all {len(cases)} designed inputs match the COBOL")
                                      + (f" ({len(proposed) - len(cases)} rejected as invalid for the layout)" if len(proposed) > len(cases) else "")})
            if broken:
                return [{"case": next(c for c in cases if c.id == r["inputId"]), "why": why.get(r["inputId"], ""),
                         "diff": r.get("diff", "")} for r in broken]
            messages.append({"role": "user", "content": "All of those matched the COBOL exactly. Attack a different "
                             "behaviour of the program this time."})
        return []
