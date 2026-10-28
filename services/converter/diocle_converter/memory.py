"""Fix memory: general lessons from certified repairs, offered to later runs as hints.

Only lessons from runs that passed held-out certification are stored, so nothing enters memory
on the model's word alone. Lessons are hints: the next run is still certified from scratch.
"""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_LESSONS = 20  # bounds the prompt cost of memory
MAX_PER_RUN = 8
MAX_CHARS = 300

LESSON_SCHEMA = {
    "type": "array",
    "description": "General lessons for future conversions: COBOL behaviour and the Java that reproduces it. "
                   "No program names, field names, account IDs or test values.",
    "items": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Short name, e.g. 'COMPUTE ROUNDED ties'"},
            "cobol": {"type": "string", "description": "What COBOL / GnuCOBOL actually does"},
            "java": {"type": "string", "description": "How to reproduce it in Java"},
        },
        "required": ["pattern", "cobol", "java"],
        "additionalProperties": False,
    },
}


def lesson_key(pattern: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", pattern.lower()).strip()


def clean_lessons(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    lessons = []
    for item in raw[:MAX_PER_RUN]:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("pattern", "cobol", "java")):
            continue
        lessons.append({k: item[k].strip()[:MAX_CHARS] for k in ("pattern", "cobol", "java")})
    return lessons


@dataclass
class Memory:
    path: Path

    def load(self) -> list[dict]:
        return json.loads(self.path.read_text())["lessons"] if self.path.exists() else []

    @contextmanager
    def _locked(self):
        """Parallel agents (swarm mode) share one memory file; serialize read-modify-write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def learn(self, lessons: list[dict], *, program: str, run_id: str) -> int:
        """Store lessons from a certified run; a lesson with a known pattern replaces the older one. Returns how many were new."""
        with self._locked():
            return self._learn(lessons, program=program, run_id=run_id)

    def _learn(self, lessons: list[dict], *, program: str, run_id: str) -> int:
        stored = {lesson_key(item["pattern"]): item for item in self.load()}
        new = 0
        for lesson in clean_lessons(lessons):
            key = lesson_key(lesson["pattern"])
            new += key not in stored
            stored.pop(key, None)
            stored[key] = {**lesson, "program": program, "run": run_id}
        kept = list(stored.values())[-MAX_LESSONS:]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"lessons": kept}, indent=2) + "\n")
        tmp.replace(self.path)
        return new


def render(lessons: list[dict]) -> str:
    if not lessons:
        return ""
    lines = ["Lessons from earlier certified repairs (hints only; they may not apply here, and certification "
             "still re-tests everything):"]
    lines += [f"- {item['pattern']}: COBOL {item['cobol']} Java: {item['java']}" for item in lessons]
    return "\n".join(lines)
