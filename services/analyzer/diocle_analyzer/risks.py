"""Rule-based findings: legacy arithmetic and display behaviour a conversion must reproduce exactly."""

from __future__ import annotations

import re

from .cobol import source_lines

_PARAGRAPH = re.compile(r"^ {0,3}([A-Z0-9][A-Z0-9-]*)\.\s*$")


def _statements(text: str) -> list[tuple[int, str | None, str]]:
    """(first line, paragraph, statement text) for COMPUTE and DISPLAY statements in the PROCEDURE DIVISION."""
    out, paragraph, current = [], None, None
    in_procedure = False
    for number, code in source_lines(text):
        if "PROCEDURE DIVISION" in code:
            in_procedure = True
            continue
        if not in_procedure:
            continue
        m = _PARAGRAPH.match(code)
        if m:
            paragraph = m.group(1)
            continue
        stripped = code.strip()
        verb = stripped.split()[0] if stripped else ""
        if verb in ("COMPUTE", "DISPLAY"):
            current = [number, paragraph, stripped]
            out.append(current)
        elif current is not None and not re.match(r"(IF|ELSE|END-|WHEN|EVALUATE|MOVE|ADD|PERFORM|WRITE|READ|SET|CLOSE|OPEN|STOP|MULTIPLY|SUBTRACT|DIVIDE|GO)\b", stripped):
            current[2] += " " + stripped  # continuation of the previous statement
        else:
            current = None
    return [tuple(s) for s in out]


def _comp_fields(text: str) -> set[str]:
    code = " ".join(c.strip() for _, c in source_lines(text))
    return set(re.findall(r"\b\d\d\s+([A-Z0-9-]+)\s+PIC\s+\S+\s+(?:USAGE\s+)?COMP(?:UTATIONAL)?\b(?!-)", code))


def find_risks(program: str, text: str) -> list[dict]:
    findings = []
    comp = _comp_fields(text)
    for line, paragraph, stmt in _statements(text):
        base = {"program": program, "line": line, "paragraph": paragraph}
        if stmt.startswith("COMPUTE"):
            target = stmt.split()[1]
            if " ROUNDED" in stmt:
                findings.append({**base, "category": "rounding", "severity": "medium",
                                 "message": f"COMPUTE {target} ROUNDED rounds half away from zero (not banker's rounding, not Math.round on negatives)."})
            else:
                findings.append({**base, "category": "truncation", "severity": "medium",
                                 "message": f"COMPUTE {target} has no ROUNDED: the result is truncated toward zero to the target's scale."})
            if "SIZE ERROR" not in stmt:
                findings.append({**base, "category": "overflow", "severity": "high",
                                 "message": f"COMPUTE {target} has no ON SIZE ERROR: on overflow the high-order digits are silently dropped."})
        elif stmt.startswith("DISPLAY"):
            shown = [name for name in comp if re.search(rf"\b{re.escape(name)}\b", stmt)]
            if shown:
                findings.append({**base, "category": "display", "severity": "low",
                                 "message": f"DISPLAY of binary field(s) {', '.join(sorted(shown))}: GnuCOBOL prints the full binary width, not the PIC digit count."})
    return findings
