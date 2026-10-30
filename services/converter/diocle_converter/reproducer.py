"""Smallest-reproducer evidence for the repair agent (verifier minimize, contracts/minimal-reproducer.schema.json).

When the breaker, or a failed held-out certification, shows the Java differing from the COBOL, the failing input is
reduced deterministically (no model call, so no model cost) and the repair agent is shown the reduced input, the
fields that matter and the first differing bytes instead of a whole batch or a raw record. The reduced input is also
saved as a regression case (runs/<id>/regression/<case>/) and replayed against the repaired Java.

Hard caps (rule 10): oracle runs and seconds per reduction (MINIMIZE_MAX_RUNS, MINIMIZE_MAX_SECONDS) and reductions
per run (MINIMIZE_MAX_CASES). Everything here is additive: any failure to reduce leaves the old evidence in place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_EVIDENCE_CHARS = 1200


def evidence_text(rec: dict) -> str:
    """One compact paragraph for the repair agent's prompt, from a minimal-reproducer record (status minimized)."""
    red, first = rec["reduction"], rec.get("output", {}).get("firstDifference") or {}
    entry = rec["inputs"][0]["records"]
    lines = [f"- {rec['id']}: the failing input was reduced from {red['recordsBefore']} record(s) / {red['bytesBefore']} bytes "
             f"to {red['recordsAfter']} record(s) / {red['bytesAfter']} bytes ({red['oracleRuns']} differential runs"
             + ("" if red["stoppedBy"] == "complete" else f", stopped by the {red['stoppedBy']}") + ")."]
    for i, r in enumerate(entry[:3], 1):
        lines.append(f"  input record {i}: {r['text']!r}")
        needed = [f"{f['name']}={f['value']!r}" for f in r["fields"] if f["role"] == "needed" and not f.get("view")]
        views = [f"{f['name']}={f['value']!r}" for f in r["fields"] if f["role"] == "needed" and f.get("view")]
        if needed or views:
            lines.append("  fields that matter (the rest were blanked or zeroed and the difference stayed): "
                         + ", ".join(needed + views))
    if first:
        lines.append(f"  first difference: output record {first['record']}"
                     + (f", field {first['field']}" if first.get("field") else "")
                     + f", byte {first['offset']}: COBOL {first.get('original', '(no record)')!r} vs Java "
                       f"{first.get('translated', '(no record)')!r}")
    if rec.get("explanation"):
        lines.append(f"  suspected cause ({rec['explanation']['label']}; the {rec['explanation']['source']}'s guess): "
                     f"{rec['explanation']['text']}")
    return "\n".join(lines)[:MAX_EVIDENCE_CHARS]


@dataclass
class Minimizing:
    sample_dir: Path
    java_dir: Path  # the workspace: always the Java as it is NOW (pre-fix when reducing, repaired when replaying)
    run_dir: Path
    max_runs: int = 150
    max_seconds: float = 120.0
    max_cases: int = 3
    on_event: Callable[[dict], None] = lambda event: None
    gate: Callable[[Path], None] | None = None  # the guard's policy check (raises if the Java may not be run)
    minimize_fn: Callable | None = None  # tests inject a double; default is diocle_verifier.minimize.minimize
    replay_fn: Callable | None = None
    records: list[dict] = field(default_factory=list)
    used: int = 0

    @staticmethod
    def available() -> str | None:
        """None when reductions can run here, else why not. They build and run both programs, so they follow the
        verifier's rule: never on the API host when a sandbox is configured."""
        if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
            return "a verification sandbox is configured and the reduction runs programs locally"
        return None

    def _minimize(self, *args, **kwargs) -> dict:
        if self.minimize_fn:
            return self.minimize_fn(*args, **kwargs)
        from diocle_verifier.minimize import minimize
        return minimize(*args, **kwargs)

    def _save(self, rec: dict) -> None:
        from diocle_verifier.minimize import save_reproducer
        save_reproducer(self.run_dir, rec)

    def _reduce(self, case_id: str, contexts: list[list[str]], hint: list[str], source: str, why: str = "") -> str | None:
        if self.used >= self.max_cases:
            return None
        self.used += 1
        try:
            if self.gate:
                self.gate(self.java_dir)
            rec = self._minimize(self.sample_dir, self.java_dir, case_id, contexts, source=source, hint=hint,
                                 max_runs=self.max_runs, max_seconds=self.max_seconds, out_dir=self.run_dir,
                                 explanation={"text": why, "source": "breaker"} if why else None)
            if rec["status"] == "minimized":
                self._save(rec)
        except Exception as e:  # additive: the old evidence stays
            self.on_event({"type": "stage", "stage": "repairing", "message": f"Reduction of {case_id} skipped: {type(e).__name__}"})
            return None
        self.records.append(rec)
        red = rec["reduction"]
        self.on_event({"type": "stage", "stage": "repairing",
                       "message": (f"Smallest reproducer for {case_id}: {red['recordsBefore']} -> {red['recordsAfter']} "
                                   f"record(s) in {red['oracleRuns']} differential runs" if rec["status"] == "minimized"
                                   else f"Reduction of {case_id}: {rec['status']} ({rec.get('reason', '')[:120]})")})
        return evidence_text(rec) if rec["status"] == "minimized" else None

    def reproduce(self, broken: list[dict], standard: Callable[[str], list[str]] | None = None) -> dict[str, str]:
        """Breaker counterexamples (items with 'case', 'why', 'diff') -> {case id: evidence text}, for those reduced.
        standard(record) is a larger starting input tried when the lone record does not reproduce (state-dependent)."""
        out = {}
        for b in broken:
            case = b["case"]
            contexts = [[case.record]]
            try:
                contexts += [standard(case.record)] if standard else []
            except Exception:  # no larger starting input available: the lone record is all there is
                pass
            text = self._reduce(case.id, contexts, [], "breaker", b.get("why", ""))
            if text:
                out[case.id] = text
        return out

    def certification_evidence(self, report: dict, label: str) -> str:
        """For a failed held-out certification: the first failing input reduced against the whole batch."""
        results = report.get("results", [])
        if not results or not all(isinstance(r.get("input"), str) for r in results):
            return ""  # outputs that do not map one to one to inputs: no per-input reduction
        failing = [r for r in results if not r["match"]]
        if not failing:
            return ""
        text = self._reduce(f"heldout-{label}-{failing[0]['inputId']}", [[r["input"] for r in results]],
                            [r["input"] for r in failing[:3]], "held-out")
        return f"\nSmallest reproducer (deterministic reduction, no model call):\n{text}" if text else ""

    def recheck(self) -> list[dict]:
        """Replay every saved regression case against the Java as it is now; record the result next to each reproducer.
        Returns the cases that still fail."""
        from diocle_verifier.minimize import replay, save_reproducer
        run_replay = self.replay_fn or replay
        failing = []
        for rec in self.records:
            reg = rec.get("regression")
            if rec["status"] != "minimized" or not reg:
                continue
            try:
                if self.gate:
                    self.gate(self.java_dir)
                result = run_replay(self.run_dir / reg["dir"], self.java_dir)
            except Exception as e:  # a refused or unrunnable Java did not pass the regression case
                result = {"passed": False, "detail": f"not replayed: {type(e).__name__}"}
            reg["afterRepair"] = {"passed": bool(result["passed"]), "detail": str(result.get("detail", ""))[:300]}
            try:
                save_reproducer(self.run_dir, rec)
            except Exception:
                pass
            if not result["passed"]:
                failing.append(result)
        return failing

    def summaries(self) -> list[dict]:
        out = []
        for r in self.records:
            red, after = r["reduction"], (r.get("regression") or {}).get("afterRepair")
            out.append({"id": r["id"], "status": r["status"], "recordsBefore": red["recordsBefore"],
                        "recordsAfter": red["recordsAfter"], "oracleRuns": red["oracleRuns"],
                        "afterRepairPassed": None if after is None else after["passed"]})
        return out
