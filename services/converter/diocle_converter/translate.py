"""Role 2B (whole-program for now): translate one COBOL program to Java with structured output."""

from __future__ import annotations

import json

from .client import ModelClient
from .prompts import TRANSLATOR
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


def translate(program: Program, client: ModelClient, workspace: Workspace) -> dict:
    messages = [
        {"role": "system", "content": TRANSLATOR.format(io=program.io_text(), main_class=program.main_class)},
        {"role": "user", "content": program.as_text()},
    ]
    choice = client.chat(role="translator", round=0, messages=messages, response_format=_response_format(program.main_class))
    result = json.loads(choice.message.content)
    workspace.write(f"{result['mainClass']}.java", result["javaSource"])
    return {"mainClass": result["mainClass"], "notes": result["notes"], "file": f"{result['mainClass']}.java"}
