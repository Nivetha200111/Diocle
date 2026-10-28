"""Export fix memory as an agent skill (SKILL.md) that any coding agent can load.

  python -m diocle_converter.skill [--out PATH]

Every lesson in it was saved only after a run passed held-out certification against GnuCOBOL;
the skill lists which run taught each one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import REPO_ROOT
from .memory import Memory


def render_skill(lessons: list[dict]) -> str:
    lines = [
        "---",
        "name: cobol-to-java-semantics",
        "description: Reproduce GnuCOBOL arithmetic and record formatting exactly when translating COBOL batch programs "
        "to Java. Use when converting or reviewing COBOL-to-Java code, especially COMPUTE, ROUNDED, PIC clauses, "
        "SIGN LEADING SEPARATE fields, COMP counters and fixed-width records.",
        "---",
        "",
        "# COBOL to Java: semantics proven against GnuCOBOL",
        "",
        "Diocle's repair agent wrote these lessons while fixing real conversions. Each one was kept only after the "
        "fixed Java matched the original COBOL, compiled with GnuCOBOL 3.2 (-std=ibm), on 1,000 held-out inputs.",
        "",
        "Treat them as rules of thumb, not proof: after converting, run the original and the Java on the same inputs "
        "and compare every output field.",
        "",
        "## Lessons",
        "",
    ]
    for item in lessons:
        lines += [
            f"### {item['pattern']}",
            f"- **COBOL:** {item['cobol']}",
            f"- **Java:** {item['java']}",
            f"- *Learned from {item.get('program', '?')}, run `{item.get('run', '?')}`*",
            "",
        ]
    if not lessons:
        lines.append("_No certified lessons yet._")
    lines += [
        "## Always",
        "- Use `java.math.BigDecimal` for every decimal value; never `float`, `double` or `Math.round`.",
        "- Never special-case particular inputs or expected outputs.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_converter.skill", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "skills" / "cobol-to-java-semantics" / "SKILL.md")
    args = parser.parse_args(argv)
    lessons = Memory(REPO_ROOT / "runs" / "memory.json").load()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_skill(lessons))
    print(f"wrote {args.out} with {len(lessons)} lessons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
