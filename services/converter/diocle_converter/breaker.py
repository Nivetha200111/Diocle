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


def explain(fields: list[Field], values: dict[str, str]) -> tuple[str | None, str | None]:
    """(record, None) for a case that fits the input layout, else (None, why it was rejected)."""
    parsed = {}
    for f in fields:
        raw = values.get(f.name)
        if not isinstance(raw, str):
            return None, f"{f.name}: missing or not a string"
        if f.kind == "alnum":
            # one byte per character and no line breaks, or the record framing shifts and fakes a mismatch
            if len(raw) > f.length:
                return None, f"{f.name}: text longer than {f.length}"
            if not all(" " <= ch <= "~" for ch in raw):
                return None, f"{f.name}: non-printable or non-ASCII character"
            parsed[f.name] = raw
            continue
        try:
            number = Decimal(raw.strip().replace("+", ""))
        except InvalidOperation:
            return None, f"{f.name}: not a number"
        if not number.is_finite():
            return None, f"{f.name}: not a finite number"
        if number.normalize().as_tuple().exponent < -f.scale:  # too many decimals
            return None, f"{f.name}: more than {f.scale} decimals"
        parsed[f.name] = number
    try:
        return format_record(parsed, fields), None
    except ValueError:
        return None, "value does not fit its field (too many digits, or a sign on an unsigned field)"


def to_record(fields: list[Field], values: dict[str, str]) -> str | None:
    """Format a model-proposed case with the input layout; None if any value is missing or does not fit."""
    return explain(fields, values)[0]


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
    role: str = "breaker"  # the cross-checker (crosscheck.py) reuses this loop with its own role, prompt and schema
    event_type: str = "breaker"
    system: str = BREAKER
    schema: dict = field(default_factory=lambda: SCHEMA)
    rejected: dict[str, int] = field(default_factory=dict)  # why proposed cases did not fit the layout, counted
    proposed_total: int = 0  # cases the model proposed, valid or not
    label_name: str = "Breaker"
    model: str | None = None  # a higher tier's model ID for the attacker (--tiers); None is the run's default
    suspected: list[dict] = field(default_factory=list)  # fields the model says may diverge (opinion, never evidence)

    def attack(self, rounds: int = 3, label: str = "attack") -> list[dict]:
        """Up to `rounds` attack rounds; stops at the first round that breaks the Java. Returns the breaking cases."""
        fields = load_fields(self.input_layout)
        java = "\n".join(f"=== {f} ===\n{self.workspace.read(f)}" for f in self.workspace.list_files())
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": f"COBOL (source of truth):\n{self.program.as_text()}\n\n"
             f"Certified Java:\n{java}\n\nInput record fields, in order:\n{_layout_text(fields)}\n\n"
             f"Design up to {self.per_round} cases."},
        ]
        for round_no in range(1, rounds + 1):
            try:
                choice = self.client.chat(role=self.role, round=round_no, messages=messages, response_format=self.schema,
                                          model=None if self.client.escalation_exhausted() else self.model)
            except BudgetExceeded as e:
                self.on_event({"type": self.event_type, "round": round_no, "message": f"budget: {e}", "tried": 0, "broke": 0})
                return []
            messages.append({"role": "assistant", "content": choice.message.content or "{}"})
            try:
                answer = json.loads(choice.message.content or "{}")
                proposed = answer.get("cases", [])
                suspected = answer.get("suspected", [])
                self.suspected += [{"field": str(x.get("field", ""))[:80], "concern": str(x.get("concern", ""))[:300]}
                                   for x in suspected[:10] if isinstance(x, dict)] if isinstance(suspected, list) else []
            except (json.JSONDecodeError, AttributeError):
                proposed = []
            proposed = [p for p in proposed if isinstance(p, dict)][: self.per_round] if isinstance(proposed, list) else []
            self.proposed_total += len(proposed)
            cases, why = [], {}
            for i, item in enumerate(proposed):
                pairs = item.get("fields") if isinstance(item.get("fields"), list) else []
                record, reason = explain(fields, {f.get("name"): f.get("value") for f in pairs if isinstance(f, dict)})
                if reason:
                    key = reason.split(": ", 1)[-1] if ": " in reason else reason
                    self.rejected[key] = self.rejected.get(key, 0) + 1
                if record:
                    case_id = f"breaker-{label}-r{round_no}-{i + 1:02d}"
                    cases.append(Case(case_id, "model", record))
                    why[case_id] = str(item.get("why", ""))[:300]
            report = self.verify(self.workspace.root, 1026, 0, cases)
            designed = [r for r in report["results"] if r.get("inputSource") == "model"]
            failing = [r for r in report["results"] if not r["match"]]
            if not designed:
                # Outputs that do not map one to one to inputs (aggregation, fan-out): a difference anywhere in
                # this round's output counts against the round's designed inputs together.
                first = failing[0].get("diff", "") if failing else ""
                designed = [{"inputId": c.id, "input": c.record, "match": not failing, "diff": first} for c in cases]
            broken = [r for r in designed if not r["match"]]
            for r in designed:
                self.attempts.append({"id": r["inputId"], "input": r.get("input"), "why": why.get(r["inputId"], ""),
                                      "broke": not r["match"], "diff": r.get("diff", "")})
            self.on_event({"type": self.event_type, "round": round_no, "tried": len(cases), "broke": len(broken),
                           "message": (f"{self.label_name} round {round_no}: {len(broken)} of {len(cases)} designed inputs break the Java"
                                       if broken else f"{self.label_name} round {round_no}: all {len(cases)} designed inputs match the COBOL")
                                      + (f" ({len(proposed) - len(cases)} rejected as invalid for the layout)" if len(proposed) > len(cases) else "")})
            if broken:
                return [{"case": next(c for c in cases if c.id == r["inputId"]), "why": why.get(r["inputId"], ""),
                         "diff": r.get("diff", "")} for r in broken]
            messages.append({"role": "user", "content": "All of those matched the COBOL exactly. Attack a different "
                             "behaviour of the program this time."})
        return []
