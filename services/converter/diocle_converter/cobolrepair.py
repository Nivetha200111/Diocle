"""Convert-anyway: make an original COBOL program compile under GnuCOBOL -std=ibm, so it can be verified at all.

IBM's compiler accepts things GnuCOBOL -std=ibm rejects (for example PROGRAM-ID without its period). Two steps, cheapest first:

1. deterministic_fixes(): mechanical edits that cannot change what the program does (listed below, each one proven safe).
2. CobolRepairAgent: a bounded Meta-model loop with compile_cobol / patch_cobol tools.

THE RULE (enforced in check_patch, stated in the README and in the model's prompt): the patched COBOL may differ from the
original by at most COBOL_REPAIR_MAX_LINES lines (default 20) and at most COBOL_REPAIR_MAX_SHARE of its lines (default 10%);
and in the PROCEDURE DIVISION a patch may only touch lines within DIAG_WINDOW (2) lines of a line the compiler reported.
Nothing here decides that the patch is faithful: whoever reads the result must still confirm it ("certified against the
repaired COBOL" is never plain "certified").

The user's file is never overwritten: the patched text goes to a copy of the sample (<name>.repaired.cbl).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .client import BudgetExceeded, ModelClient, usage_of
from .prompts import COBOL_REPAIR

DIAG_WINDOW = 2
_DIAG_LINE = re.compile(r"^([\w.$-]+):(\d+): error")
_NEXT_PARAGRAPH = re.compile(r"^\s*(ENVIRONMENT|DATA|PROCEDURE|AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY)\b")
_PROGRAM_ID = re.compile(r"^(?P<lead>.{6}[ ]\s*PROGRAM-ID\.?\s+)(?P<name>[A-Za-z0-9][A-Za-z0-9-]*)(?P<tail>\s*)$")


@dataclass(frozen=True)
class Limits:
    max_lines: int = 20
    max_share: float = 0.10
    max_calls: int = 8

    @classmethod
    def from_env(cls) -> "Limits":
        def num(name, default, cast):
            try:
                return cast(os.environ.get(name, "") or default)
            except ValueError:
                return default

        return cls(num("COBOL_REPAIR_MAX_LINES", 20, int), num("COBOL_REPAIR_MAX_SHARE", 0.10, float),
                   num("COBOL_REPAIR_MAX_CALLS", 8, int))


def deterministic_fixes(text: str) -> tuple[str, list[str]]:
    """Mechanical fixes, each proven not to change behaviour. Returns (new text, one phrase per fix).

    1. A missing period after the program name in PROGRAM-ID: when the next code line starts a new header paragraph or
       division, the period only ends the sentence the next line would otherwise be read into. A period at the end of
       that line is added (only when the line is shorter than column 72)."""
    lines = text.split("\n")
    fixes = []
    for i, line in enumerate(lines):
        if len(line) > 6 and line[6] in "*/":
            continue
        m = _PROGRAM_ID.match(line.rstrip("\r"))
        if not m or line.rstrip().endswith(".") or len(line.rstrip()) >= 72:
            continue
        nxt = next((l for l in lines[i + 1:] if l[6:7] not in ("*", "/") and l.strip()), "")
        if not _NEXT_PARAGRAPH.match(nxt[7:] if len(nxt) > 7 else nxt):
            continue
        lines[i] = line.rstrip() + "."
        fixes.append(f"added the missing period after PROGRAM-ID {m.group('name')} (line {i + 1})")
        break
    return "\n".join(lines), fixes


def diagnostic_lines(diagnostics: list[str]) -> list[int]:
    return [int(m.group(2)) for d in diagnostics if (m := _DIAG_LINE.match(d))]


def diagnostic_files(diagnostics: list[str]) -> set[str]:
    return {m.group(1) for d in diagnostics if (m := _DIAG_LINE.match(d))}


def changed_lines(old: str, new: str) -> int:
    ops = difflib.SequenceMatcher(None, old.split("\n"), new.split("\n"), autojunk=False).get_opcodes()
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")


def unified_diff(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        f"a/{name}", f"b/{name}"))


def _procedure_start(lines: list[str]) -> int:
    return next((i for i, l in enumerate(lines) if re.match(r"^.{6}[ ]\s*PROCEDURE\s+DIVISION\b", l)), len(lines))


def check_patch(previous: str, candidate: str, original: str, diag_lines: list[int], limits: Limits) -> str | None:
    """None when the patch obeys THE RULE, else the reason it is rejected (told to the model)."""
    total = changed_lines(original, candidate)
    allowed = min(limits.max_lines, int(limits.max_share * max(1, len(original.split("\n")))))
    if total > allowed:
        return (f"rejected: the patched file would differ from the original by {total} lines; at most {allowed} are allowed "
                f"({limits.max_lines} lines or {int(limits.max_share * 100)}% of the file, whichever is smaller)")
    prev_lines = previous.split("\n")
    proc = _procedure_start(prev_lines)
    ops = difflib.SequenceMatcher(None, prev_lines, candidate.split("\n"), autojunk=False).get_opcodes()
    for tag, i1, i2, _, _ in ops:
        if tag == "equal":
            continue
        touched = range(i1, max(i2, i1 + 1))  # an insertion touches the line it lands before
        for idx in touched:
            if idx >= proc and not any(abs((idx + 1) - d) <= DIAG_WINDOW for d in diag_lines):
                return (f"rejected: line {idx + 1} is in the PROCEDURE DIVISION and not within {DIAG_WINDOW} lines of a line "
                        f"the compiler reported ({sorted(set(diag_lines))}); only fix what the compiler reports")
    return None


@dataclass
class RepairResult:
    method: str  # deterministic | model
    outcome: str  # compiles | still-fails | rejected | cap-reached
    text: str
    diagnostics: list[str]
    fixes: list[str] = field(default_factory=list)
    rounds: int = 0

    def record(self, original: str, name: str, client: ModelClient | None, calls_before: int, patched_file: str) -> dict:
        usage = usage_of(client.calls[calls_before:]) if client else {"calls": 0, "estimatedCostUsd": 0.0}
        return {"method": self.method, "outcome": self.outcome, "diff": unified_diff(original, self.text, name)[:20000],
                "diagnostics": self.diagnostics[:8], "fixes": self.fixes[:10],
                "changedLines": changed_lines(original, self.text), "rounds": self.rounds,
                "modelCalls": usage["calls"], "estimatedCostUsd": usage["estimatedCostUsd"], "patchedFile": patched_file}


# compile(text) -> (ok, cleaned diagnostics, sure): sure is False when the compiler could not give an answer (sandbox busy)
Compile = Callable[[str], tuple[bool, list[str], bool]]


def _tool(name: str, description: str, properties: dict | None = None) -> dict:
    params = {"type": "object", "properties": properties or {}, "required": list(properties or {}), "additionalProperties": False}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


TOOLS = [
    _tool("read_cobol", "Read the current working copy of the COBOL program with line numbers."),
    _tool("compile_cobol", "Compile the working copy with GnuCOBOL (-std=ibm); returns the compiler's diagnostics."),
    _tool("patch_cobol", "Replace one exact, unique snippet of the working copy. Subject to the size and diagnostic rules.",
          {"old_text": {"type": "string"}, "new_text": {"type": "string"},
           "rationale": {"type": "string", "description": "One sentence: which diagnostic this fixes"}}),
    _tool("finish", "End: say whether it now compiles.", {"ok": {"type": "boolean"}, "summary": {"type": "string"}}),
]


@dataclass
class CobolRepairAgent:
    original: str
    copybooks_text: str
    compile: Compile
    client: ModelClient
    diagnostics: list[str]
    limits: Limits = field(default_factory=Limits)
    escalate: bool = False
    on_event: Callable[[dict], None] = lambda event: None
    text: str = ""
    fixes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.text = self.text or self.original

    def _model_for(self, step: int) -> str | None:
        s = self.client.settings
        if not (self.escalate and s.tiers and step > 3) or self.client.escalation_exhausted():
            return None
        return s.tier_model(2)

    def _execute(self, name: str, args: dict) -> str:
        if name == "read_cobol":
            return "\n".join(f"{n:>5}| {l}" for n, l in enumerate(self.text.split("\n"), 1))
        if name == "compile_cobol":
            ok, diags, sure = self.compile(self.text)
            self.diagnostics = diags or self.diagnostics
            if ok:
                return "compiles OK. Call finish."
            return ("diagnostics:\n" + "\n".join(diags)) if diags else "the compiler gave no answer; try again"
        if name == "patch_cobol":
            old, new = args["old_text"], args["new_text"]
            count = self.text.count(old)
            if not old or count != 1:
                return f"rejected: old_text must occur exactly once (found {count})"
            candidate = self.text.replace(old, new, 1)
            why = check_patch(self.text, candidate, self.original, diagnostic_lines(self.diagnostics), self.limits)
            if why:
                return why
            self.text = candidate
            self.fixes.append((args.get("rationale") or "patched").strip()[:200])
            return "applied. Now compile_cobol."
        raise ValueError(f"unknown tool {name!r}")

    def run(self) -> RepairResult:
        messages = [{"role": "system", "content": COBOL_REPAIR},
                    {"role": "user", "content": "Compiler diagnostics (cleaned):\n" + "\n".join(self.diagnostics)
                     + f"\n\nProgram (with line numbers):\n{self._execute('read_cobol', {})}"
                     + (f"\n\nCopybooks:\n{self.copybooks_text}" if self.copybooks_text else "")}]
        outcome, rounds = "cap-reached", 0
        for step in range(1, self.limits.max_calls + 1):
            try:
                choice = self.client.chat(role="cobol-repair", round=1, messages=messages, tools=TOOLS, model=self._model_for(step))
            except BudgetExceeded as e:
                self.on_event({"type": "budget", "round": 1, "message": str(e)})
                break
            rounds = step
            message = choice.message
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                messages.append({"role": "user", "content": "Use the tools, or call finish."})
                continue
            finished = False
            for call in message.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = "done" if call.function.name == "finish" else self._execute(call.function.name, args)
                except Exception as e:  # tool errors go back to the model
                    args, result = {}, f"error: {e}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                self.on_event({"type": "agent-step", "round": 1, "step": step, "tool": call.function.name,
                               "rationale": args.get("rationale") or "", "resultSummary": result[:300],
                               "argsSummary": {k: str(v)[:117] for k, v in args.items() if k != "rationale"}})
                finished = finished or call.function.name == "finish"
            if finished:
                outcome = "still-fails"
                break
        # The model's word is not the answer: the compiler is.
        ok, diags, sure = self.compile(self.text)
        if ok and self.text != self.original:
            outcome = "compiles"
        elif outcome != "cap-reached":
            outcome = "still-fails"
        return RepairResult("model", outcome, self.text, [] if ok else diags or self.diagnostics, self.fixes, rounds)


def make_patched_sample(sample: Path, source_rel: str, text: str) -> Path:
    """Copy `sample` to <sample>.repaired and put the patched COBOL there as <name>.repaired.cbl (sample.json points at it);
    the patched file also lands beside the original in `sample`, so a person finds it next to the code. The original file
    is not touched."""
    patched_name = f"{Path(source_rel).stem}.repaired.cbl"
    dest = sample.parent / f"{sample.name}.repaired"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(sample, dest)
    (dest / Path(source_rel).parent / patched_name).write_text(text)
    (sample / Path(source_rel).parent / patched_name).write_text(text)
    meta = json.loads((dest / "sample.json").read_text())
    meta["source"] = (Path(source_rel).parent / patched_name).as_posix()
    meta["cobolRepaired"] = {"original": source_rel}
    (dest / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return dest


def repair_original(sample: Path, client: ModelClient, *, escalate: bool, on_event, compile_check, limits: Limits | None = None
                    ) -> tuple[Path | None, dict | None, str | None]:
    """Returns (patched sample dir or None, cobolRepair record or None, reason the original cannot be verified or None).

    compile_check(sample_dir) -> (status "ok"|"fail"|"unknown", cleaned diagnostics). A program that compiles, or whose
    compile status is unknown, is left alone (None, None, None). Model use only after the deterministic fixes failed."""
    limits = limits or Limits.from_env()
    meta = json.loads((sample / "sample.json").read_text())
    source_rel = meta["source"]
    original = (sample / source_rel).read_text()
    status, diags = compile_check(sample)
    if status != "fail":
        return None, None, None
    name = Path(source_rel).name
    first_diags = list(diags)
    calls_before = len(client.calls)

    def compile_text(text: str) -> tuple[bool, list[str], bool]:
        tmp = make_patched_sample(sample, source_rel, text)
        st, ds = compile_check(tmp)
        return st == "ok", ds, st != "unknown"

    # 1. deterministic
    fixed, fixes = deterministic_fixes(original)
    result = None
    if fixes:
        ok, ds, sure = compile_text(fixed)
        on_event({"type": "stage", "stage": "repairing-cobol", "message": "Deterministic COBOL fix: " + "; ".join(fixes)})
        if ok:
            result = RepairResult("deterministic", "compiles", fixed, [], fixes, 0)
        else:
            diags = ds or diags
    if result is None:
        foreign = diagnostic_files(diags) - {name, f"{Path(source_rel).stem}.repaired.cbl"}
        if foreign:
            reason = (f"the original does not compile under GnuCOBOL -std=ibm; the compiler points at another file "
                      f"({', '.join(sorted(foreign))}), which is not repaired")
            return None, None, reason
        copybooks = "\n".join(f"=== {p.name} ===\n{p.read_text()}"
                              for p in sorted((sample / meta["copybookDir"]).glob("*.cpy")))
        on_event({"type": "stage", "stage": "repairing-cobol",
                  "message": "Asking the model to fix only what the compiler reports (bounded)"})
        agent = CobolRepairAgent(original, copybooks, compile_text, client, diags, limits, escalate, on_event,
                                 text=fixed if fixes else original)
        agent.fixes = list(fixes)
        result = agent.run()
        if fixes:
            result.fixes = fixes + [f for f in result.fixes if f not in fixes]
    record = result.record(original, name, client, calls_before, f"{Path(source_rel).stem}.repaired.cbl")
    record["diagnostics"] = first_diags[:8]  # what was wrong at the start
    if result.outcome == "compiles":
        return make_patched_sample(sample, source_rel, result.text), record, None
    shutil.rmtree(sample.parent / f"{sample.name}.repaired", ignore_errors=True)  # nothing half-repaired is left around
    (sample / Path(source_rel).parent / f"{Path(source_rel).stem}.repaired.cbl").unlink(missing_ok=True)
    reason = ("the original does not compile under GnuCOBOL -std=ibm and Muse could not make it compile within the rules ("
              + (first_diags[0] if first_diags else "no diagnostic") + ")")
    return None, record, reason
