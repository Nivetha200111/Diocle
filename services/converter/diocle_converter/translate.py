"""Role 2B (whole-program for now): translate one COBOL program to Java with structured output."""

from __future__ import annotations

import json

from .client import BudgetExceeded, ModelClient
from .prompts import TRANSLATOR, TRANSLATOR_ADVANCING, TRANSLATOR_ANYWAY, TRANSLATOR_KSDS, TRANSLATOR_SQL
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


def translation_messages(program: Program, anyway_reason: str | None = None, domain_hint: str = "") -> list[dict]:
    """The translator's prompt. distill.py builds its training lines from this, so training and serving cannot drift."""
    reason = anyway_reason or (program.anyway or {}).get("reason")
    user = program.as_text() + ("\n" + program.support_text() if (program.sql or program.ksds) else "")
    missing = (program.anyway or {}).get("missingCopybooks")
    if missing:
        user += f"\n\n=== NOT FOUND (copybooks missing from the repository): {', '.join(missing)} ==="
    system = (TRANSLATOR_ANYWAY.format(reason=reason, io=program.io_text(), main_class=program.main_class) if reason
              else TRANSLATOR.format(io=program.io_text(), main_class=program.main_class) + (TRANSLATOR_SQL if program.sql else "")
              + (TRANSLATOR_KSDS if program.ksds else "") + program.stand_in_text()
              + program.advancing_text(TRANSLATOR_ADVANCING)
              + (domain_hint if not reason else ""))  # EXPERIMENTAL hint: only on the verified path
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class TranslationUnusable(RuntimeError):
    """The model answered but gave no usable translation. The message is a plain sentence for run.json and the run page, and
    never quotes the model's text."""

    plain_message = True  # __main__._describe publishes it as it is


def _read_answer(choice) -> tuple[dict | None, str]:
    """(the translation, "") or (None, why the answer cannot be used). StoredAnswer in eval/distill_glimmer.py has no finish_reason."""
    if getattr(choice, "finish_reason", None) == "length":
        return None, "cut off at the host's output limit"
    try:
        answer = json.loads(choice.message.content)
    except (TypeError, ValueError):  # no text at all, or JSON that does not parse (a cut-off answer from a host that does not say so)
        return None, "cut off or unreadable"
    usable = (isinstance(answer, dict) and isinstance(answer.get("notes"), str)
              and all(isinstance(answer.get(k), str) and answer[k].strip() for k in ("mainClass", "javaSource")))
    return (answer, "") if usable else (None, "unreadable")


def translate(program: Program, client: ModelClient, workspace: Workspace, anyway_reason: str | None = None,
              domain_hint: str = "", retry: bool = False, on_event=None) -> dict:
    """anyway_reason (or a convert-anyway sample): the program cannot be differential-tested; the prompt says why and asks
    for labelled adapter interfaces where plain Java cannot reproduce the COBOL.

    retry: ask once more when the answer is unusable, within the client's call and dollar caps. Off by default because
    eval/headline.py (whose client allows 60 calls) and eval/distill_glimmer.py measure FIRST translations through this
    function: the runs of the product turn it on.

    No max_tokens here: hosted translators legitimately use over 23,000 output tokens, and a limit just under the host's
    32,768 would save about $0.003 of a $0.14 bad answer while raising the dollar cap's up-front estimate fourfold."""
    messages = translation_messages(program, anyway_reason, domain_hint)
    response_format = _response_format(program.main_class)
    choice = client.chat(role="translator", round=0, messages=messages, response_format=response_format)
    result, why = _read_answer(choice)
    if result is None:
        if not retry:
            raise TranslationUnusable(f"The model's answer was {why}, so no Java was produced.")
        if on_event:
            on_event({"type": "stage", "stage": "translating", "message": f"The translator's answer was {why}; trying once more, "
                      "within this run's caps"})
        try:
            choice = client.chat(role="translator", round=0, messages=messages, response_format=response_format)
        except BudgetExceeded as e:
            raise TranslationUnusable(f"The model's answer was {why}, this run's call or spend cap left no room to try again, "
                                      "and no Java was produced.") from e
        result, again = _read_answer(choice)
        if result is None:
            raise TranslationUnusable(f"The model's answer was {why}, and the one retry was {again}, so no Java was produced.")
    workspace.write(f"{result['mainClass']}.java", result["javaSource"])
    return {"mainClass": result["mainClass"], "notes": result["notes"], "file": f"{result['mainClass']}.java"}
