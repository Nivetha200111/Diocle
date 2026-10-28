"""Role 2C: tool-using repair agent. It edits only the Java workspace; only the verifier can certify."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .client import BudgetExceeded, ModelClient
from .memory import LESSON_SCHEMA, clean_lessons, lesson_key
from .prompts import REPAIR
from .sources import Program
from .workspace import Workspace

# verify(java_dir, seed, random_count) -> verification report (contracts/verification-report.schema.json)
Verify = Callable[[Path, int, int], dict]

TEST_SEED, TEST_CASES = 1026, 200
CERT_SEED, CERT_CASES = 4242, 1000  # held out: the agent never sees results for these inputs


def _tool(name: str, description: str, properties: dict | None = None) -> dict:
    params = {"type": "object", "properties": properties or {}, "required": list(properties or {}), "additionalProperties": False}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


TOOLS = [
    _tool("run_differential_test", "Run original COBOL and the Java on the same test inputs; returns mismatches."),
    _tool("read_cobol_source", "Read the original COBOL program and its copybooks."),
    _tool("list_java_files", "List the Java files in the workspace."),
    _tool("read_java_file", "Read one Java file.", {"path": {"type": "string"}}),
    _tool(
        "patch_java",
        "Replace one exact, unique snippet of a Java file.",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string", "description": "Exact text that occurs once in the file"},
            "new_text": {"type": "string"},
            "rationale": {"type": "string", "description": "One sentence: which COBOL semantics this fixes"},
        },
    ),
    _tool("compile_java", "Compile the workspace with javac; returns errors if any."),
    _tool("finish", "End this round and request certification.",
          {"summary": {"type": "string"}, "lessons": LESSON_SCHEMA}),
]


def summarize_report(report: dict, limit: int = 6, for_agent: bool = True) -> str:
    runs = report["runs"]
    for side in ("original", "converted"):
        if not runs[side]["compiled"]:
            return f"{side} did not compile:\n{runs[side]['stderr'][-3000:]}"
        if runs[side]["exitCode"] != 0:
            return f"{side} crashed (exit {runs[side]['exitCode']}):\n{runs[side]['stderr'][-3000:]}"
    s = report["summary"]
    lines = [f"{s['passed']}/{s['total']} cases match; stdout {'matches' if runs['stdoutMatch'] else 'differs'}."]
    failing = [r for r in report["results"] if not r["match"]]
    if failing:
        counts = Counter(d["field"] for r in failing for d in r.get("fieldDiffs", []))
        lines.append("Mismatched fields: " + ", ".join(f"{f} x{n}" for f, n in counts.most_common()))
        for r in failing[:limit]:
            lines.append(f"- {r['inputId']} input={r.get('input', '')!r}: {r.get('diff', '')}")
    if not runs["stdoutMatch"]:
        lines.append(f"stdout original : {runs['original']['stdout'].strip()[:300]}")
        lines.append(f"stdout converted: {runs['converted']['stdout'].strip()[:300]}")
    if for_agent and not failing and runs["stdoutMatch"]:
        lines.append("All cases match. Call finish now; do not refactor further.")
    return "\n".join(lines)[:4000]


def report_passes(report: dict) -> bool:
    runs = report["runs"]
    return (
        runs["original"]["compiled"] and runs["converted"]["compiled"] and runs["converted"]["exitCode"] == 0
        and report["summary"]["total"] > 0 and report["summary"]["failed"] == 0 and runs["stdoutMatch"]
    )


@dataclass
class RepairAgent:
    program: Program
    workspace: Workspace
    client: ModelClient
    verify: Verify
    on_event: Callable[[dict], None] = lambda event: None
    hints: str = ""  # rendered fix memory from earlier certified runs
    # Swarm mode: returns all lessons in shared memory; new ones (certified by other agents) are passed on mid-run.
    memory_feed: Callable[[], list[dict]] | None = None
    known_lessons: set[str] = field(default_factory=set)
    rounds: list[dict] = field(default_factory=list)
    lessons: list[dict] = field(default_factory=list)  # from the latest finish call
    messages: list[dict] = field(default_factory=list)

    def _execute(self, name: str, args: dict) -> str:
        if name == "run_differential_test":
            return summarize_report(self.verify(self.workspace.root, TEST_SEED, TEST_CASES))
        if name == "read_cobol_source":
            return self.program.as_text()
        if name == "list_java_files":
            return "\n".join(self.workspace.list_files())
        if name == "read_java_file":
            return self.workspace.read(args["path"])
        if name == "patch_java":
            return self.workspace.patch(args["path"], args["old_text"], args["new_text"])
        if name == "compile_java":
            ok, output = self.workspace.compile()
            return "compiled OK" if ok else f"compile errors:\n{output}"
        raise ValueError(f"unknown tool {name!r}")

    def run(self) -> dict:
        initial = self.verify(self.workspace.root, TEST_SEED, TEST_CASES)
        # Everything the agent needs up front, stable content first so later calls hit the prompt cache.
        java = "\n".join(f"=== {f} ===\n{self.workspace.read(f)}" for f in self.workspace.list_files())
        self.messages = [
            {"role": "system", "content": REPAIR},
            {"role": "user", "content": (f"{self.hints}\n\n" if self.hints else "")
             + f"Original COBOL (source of truth):\n{self.program.as_text()}\n\n"
             f"Current Java workspace:\n{java}\n\nCurrent differential test result:\n{summarize_report(initial)}"},
        ]
        return self._rounds(self.client.settings.max_rounds)

    def resume(self, note: str, extra_rounds: int = 2) -> dict:
        """Continue the same conversation with new evidence (e.g. inputs a breaker agent found), then re-certify."""
        self.messages.append({"role": "user", "content": note})
        return self._rounds(extra_rounds)

    def _rounds(self, count: int) -> dict:
        certification = None
        start = len(self.rounds) + 1
        for round_no in range(start, start + count):
            finished = self._round(round_no, self.messages)
            self.on_event({"type": "stage", "stage": "certifying", "round": round_no,
                           "message": f"Round {round_no}: certifying on {CERT_CASES} held-out inputs the agent has not seen"})
            certification = self.verify(self.workspace.root, CERT_SEED + round_no, CERT_CASES)
            passed = report_passes(certification)
            self.rounds.append({"round": round_no, "finishedByAgent": finished, "certified": passed,
                                "summary": certification["summary"]})
            self.on_event({"type": "certification", "round": round_no, "passed": passed,
                           "result": summarize_report(certification, limit=3, for_agent=False)})
            if passed:
                break
            self.messages.append({"role": "user", "content": "Certification on held-out inputs failed:\n"
                                  f"{summarize_report(certification)}\nContinue fixing."})
        certified = bool(certification and report_passes(certification))
        return {"certified": certified, "rounds": self.rounds, "certificationReport": certification,
                "lessons": self.lessons if certified else []}

    def _share_new_lessons(self, round_no: int, messages: list[dict]) -> None:
        if self.memory_feed is None:
            return
        new = [l for l in self.memory_feed() if lesson_key(l["pattern"]) not in self.known_lessons]
        if not new:
            return
        self.known_lessons.update(lesson_key(l["pattern"]) for l in new)
        sources = sorted({l.get("program", "another agent") for l in new})
        messages.append({"role": "user", "content": "Shared memory update: other agents in this migration just passed "
                         "held-out certification and recorded these lessons (hints only):\n"
                         + "\n".join(f"- {l['pattern']}: COBOL {l['cobol']} Java: {l['java']}" for l in new)})
        self.on_event({"type": "memory", "round": round_no,
                       "message": f"Received {len(new)} new lesson(s) from {', '.join(sources)} mid-run"})

    def _round(self, round_no: int, messages: list[dict]) -> bool:
        for step in range(1, self.client.settings.max_calls_per_round + 1):
            self._share_new_lessons(round_no, messages)
            try:
                choice = self.client.chat(role="repair", round=round_no, messages=messages, tools=TOOLS)
            except BudgetExceeded as e:
                self.on_event({"type": "budget", "round": round_no, "message": str(e)})
                return False
            message = choice.message
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                messages.append({"role": "user", "content": "Use the tools to make progress, or call finish."})
                continue
            done = False
            for call in message.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = "round finished" if name == "finish" else self._execute(name, args)
                    if name == "finish":
                        self.lessons = clean_lessons(args.get("lessons"))
                except Exception as e:  # tool errors go back to the model, not up the stack
                    args, result = {}, f"error: {e}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                self.on_event({
                    "type": "agent-step", "round": round_no, "step": step, "tool": name,
                    "rationale": args.get("rationale") or (message.content or "").strip()[:300],
                    "argsSummary": {k: (v if len(str(v)) < 120 else str(v)[:117] + "...") for k, v in args.items() if k != "rationale"},
                    "resultSummary": result[:300],
                })
                done = done or name == "finish"
            if done:
                return True
        return False
