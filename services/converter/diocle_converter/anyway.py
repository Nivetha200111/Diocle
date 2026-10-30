"""Convert-anyway mode: translate and compile-check what the verifier cannot certify, and label it for what it is.

Opt-in only (`--convert-anyway` or DIOCLE_CONVERT_ANYWAY=1; never reachable from a visitor import). The mode changes what
happens to a program that would otherwise be refused or skipped; a program that verifies normally is certified normally.

Assurance labels (contracts/run.schema.json `assurance`):
  certified                          differential test passed against the original COBOL
  certified-against-repaired-cobol   the original did not compile; the COBOL was patched (cobolrepair.py), Java passed
                                     against the PATCHED COBOL
  compiled-unverified                Java compiles with javac; no differential test ran (reason stated); never executed here
  failed                             no compiling Java within the caps, or the differential test ran and the Java differs
Only `certified` is certified. The run's `certified` boolean is true for that label alone.
"""

from __future__ import annotations

import json
import os

from .client import BudgetExceeded, ModelClient
from .workspace import Workspace

CERTIFIED = "certified"
REPAIRED = "certified-against-repaired-cobol"
UNVERIFIED = "compiled-unverified"
FAILED = "failed"
LABELS = (CERTIFIED, REPAIRED, UNVERIFIED, FAILED)

COMPILE_FIX_ROUNDS = 3  # javac-fix model calls after the translation; each is also bound by the run's call and dollar caps


def enabled(flag: bool = False) -> bool:
    return bool(flag) or os.environ.get("DIOCLE_CONVERT_ANYWAY") == "1"


def repaired_wording(repair: dict) -> str:
    return (f"The original did not compile under GnuCOBOL. Muse changed {repair['changedLines']} line(s) (diff in the run "
            "record) so it compiles; the Java was verified against the patched COBOL, not the original. A person must "
            "confirm the patch preserves what the IBM compiler accepted.")


def unverified_wording(reason: str) -> str:
    return f"Java compiles; a developer must review it; the differential test could not run because {reason}"


def _fix_schema() -> dict:
    return {"type": "json_schema", "json_schema": {"name": "java_fix", "schema": {
        "type": "object", "properties": {"javaSource": {"type": "string"}}, "required": ["javaSource"],
        "additionalProperties": False}}}


def compile_with_fixes(workspace: Workspace, client: ModelClient, main_class: str, on_event, rounds: int = COMPILE_FIX_ROUNDS
                       ) -> tuple[bool, str, int]:
    """javac the workspace; on errors ask the model (same client, same caps) to return the fixed single file, a bounded
    number of times. Returns (compiled, last compiler output, fix rounds used). Never runs the Java."""
    ok, output = workspace.compile()
    used = 0
    while not ok and used < rounds:
        used += 1
        current = workspace.read(f"{main_class}.java")
        on_event({"type": "stage", "stage": "compiling", "message": f"javac failed; compile-fix round {used}/{rounds}"})
        try:
            choice = client.chat(role="compile-fix", round=used, response_format=_fix_schema(), messages=[
                {"role": "system", "content": "Fix the Java compile errors. Change only what the errors require; keep every "
                 "ADAPTER REQUIRED interface and comment. Return the complete corrected file."},
                {"role": "user", "content": f"javac output:\n{output}\n\n=== {main_class}.java ===\n{current}"}])
            workspace.write(f"{main_class}.java", json.loads(choice.message.content)["javaSource"])
        except BudgetExceeded as e:
            on_event({"type": "budget", "round": used, "message": str(e)})
            break
        except (ValueError, KeyError, TypeError):
            continue
        ok, output = workspace.compile()
    return ok, output, used
