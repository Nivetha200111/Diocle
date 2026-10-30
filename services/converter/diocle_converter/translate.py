"""Role 2B (whole-program for now): translate one COBOL program to Java with structured output."""

from __future__ import annotations

import json

from .client import ModelClient
from .prompts import TRANSLATOR, TRANSLATOR_ANYWAY, TRANSLATOR_KSDS, TRANSLATOR_SQL
from .sources import Program
from .workspace import Workspace


def _response_format(main_class: str) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "java_translation",
            "schema": {
                "type": "object",
                "properties": {
                    "mainClass": {"type": "string", "enum": [main_class],
                                  "description": "Public class name with main(); file is <mainClass>.java"},
                    "javaSource": {"type": "string"},
                    "notes": {"type": "string", "description": "COBOL semantics you had to be careful about"},
                },
                "required": ["mainClass", "javaSource", "notes"],
                "additionalProperties": False,
            },
        },
    }


def translate(program: Program, client: ModelClient, workspace: Workspace, anyway_reason: str | None = None,
              domain_hint: str = "") -> dict:
    """anyway_reason (or a convert-anyway sample): the program cannot be differential-tested; the prompt says why and asks
    for labelled adapter interfaces where plain Java cannot reproduce the COBOL."""
    reason = anyway_reason or (program.anyway or {}).get("reason")
    user = program.as_text() + ("\n" + program.support_text() if (program.sql or program.ksds) else "")
    missing = (program.anyway or {}).get("missingCopybooks")
    if missing:
        user += f"\n\n=== NOT FOUND (copybooks missing from the repository): {', '.join(missing)} ==="
    system = (TRANSLATOR_ANYWAY.format(reason=reason, io=program.io_text(), main_class=program.main_class) if reason
              else TRANSLATOR.format(io=program.io_text(), main_class=program.main_class) + (TRANSLATOR_SQL if program.sql else "")
              + (TRANSLATOR_KSDS if program.ksds else "")
              + (domain_hint if not reason else ""))  # EXPERIMENTAL hint: only on the verified path
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    choice = client.chat(role="translator", round=0, messages=messages, response_format=_response_format(program.main_class))
    result = json.loads(choice.message.content)
    workspace.write(f"{result['mainClass']}.java", result["javaSource"])
    return {"mainClass": result["mainClass"], "notes": result["notes"], "file": f"{result['mainClass']}.java"}
