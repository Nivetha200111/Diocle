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


def _alnum_fields(text: str) -> set[str]:
    code = " ".join(c.strip() for _, c in source_lines(text))
    return set(re.findall(r"\b\d\d\s+([A-Z0-9-]+)\s+PIC(?:TURE)?\s+(?:IS\s+)?X", code))


def _source_findings(program: str, text: str) -> list[dict]:
    """Code cut at column 72. Sources with sequence numbers in columns 73-80 are normal; there a cut only shows when
    the text past column 72 is not a sequence number."""
    out = []
    is_sequence_number = lambda l: len(l[72:80]) == 8 and l[72:80].isdigit()  # a full 8-digit field, not a spilled digit
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > 72 and line[6:7] not in ("*", "/") and line[71] != " " and line[72] != " ":
            if is_sequence_number(line) and len(line) <= 80:
                continue
            out.append({"program": program, "line": number, "paragraph": None, "category": "source", "severity": "high",
                        "message": f"Code runs past column 72: '{line[64:72].strip()}|{line[72:].strip()}' - GnuCOBOL and "
                                   "IBM COBOL ignore everything after column 72, so the statement is silently cut."})
    return out


def _environment_findings(program: str, text: str) -> list[dict]:
    out = []
    code_lines = source_lines(text)
    alnum = _alnum_fields(text)
    for number, code in code_lines:
        stripped = code.strip()
        base = {"program": program, "line": number, "paragraph": None}
        if re.search(r"\bACCEPT\b.*\bFROM\s+(DATE|TIME|DAY|DAY-OF-WEEK)\b|\bFUNCTION\s+(CURRENT-DATE|WHEN-COMPILED)\b", stripped):
            out.append({**base, "category": "clock", "severity": "medium",
                        "message": "Reads the clock: output depends on when it runs. Diocle pins the date and time "
                                   "for both sides (COB_CURRENT_DATE / DIOCLE_CLOCK)."})
        if re.search(r"\b(USAGE\s+)?COMP(UTATIONAL)?-[12]\b", stripped):
            out.append({**base, "category": "float", "severity": "high",
                        "message": "COMP-1/COMP-2 floating point: IBM hexadecimal float on z/OS, IEEE in GnuCOBOL and "
                                   "Java. GnuCOBOL cannot prove mainframe results; certify against mainframe golden files."})
        if re.search(r"^(SORT|MERGE)\b", stripped):
            out.append({**base, "category": "collation", "severity": "high",
                        "message": "SORT/MERGE on the mainframe orders keys in EBCDIC (lowercase < uppercase < digits), "
                                   "ASCII orders digits first. Verify with the EBCDIC collating sequence."})
        compare = re.search(r"\b(IF|WHEN|UNTIL)\b(.*?)(<|>|\bLESS\b|\bGREATER\b)(.*)", stripped)
        if compare and any(re.search(rf"\b{re.escape(f)}\b", compare.group(2) + compare.group(4)) for f in alnum):
            out.append({**base, "category": "collation", "severity": "medium",
                        "message": "Ordering comparison on alphanumeric data: EBCDIC and ASCII order letters and digits "
                                   "differently, so the branch taken can change after migration."})
    return out


def find_risks(program: str, text: str) -> list[dict]:
    findings = _source_findings(program, text) + _environment_findings(program, text)
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
                                 "message": f"DISPLAY of binary field(s) {', '.join(sorted(shown))}: IBM COBOL shows the PIC digits, not the binary width. Diocle's oracle is compiled to match (-fpretty-display)."})
    return findings
