"""Counterexample minimization and regression cases (contracts/minimal-reproducer.schema.json v0.1).

When the converted Java disagrees with the original COBOL (GnuCOBOL) on some input, shrink that input while the
disagreement stays the same, with no model call:

1. record level: delta debugging (ddmin) over the input records, so a 500-record batch ends as the fewest records
   that still differ (1-minimal when it completes: removing any one more record loses the discrepancy);
2. field level, where the record layout is known: each field is replaced by zero / a smaller number / spaces /
   fewer characters, byte length preserved, and kept only if the discrepancy remains. Fields that cannot be
   simplified are the ones the discrepancy needs (role "needed").

The oracle is the differential harness itself: build both programs once, run both on a candidate input, compare
byte for byte (diff.compare, exit code, stdout). "The same discrepancy" means the same signature: the kind
(exit code, output record, output count, stdout) and the set of output fields that differ in the first differing
record. Hard caps: oracle runs and wall clock; when one is hit the smaller input found so far is returned and
`stoppedBy` says so. Deterministic: no randomness, same inputs give the same reduction.

A regression case (`regression/<id>/`: case.json, input.dat, expected-output.dat, expected-stdout.txt) holds the
minimized input and the bytes GnuCOBOL's output was; `replay` runs it against any Java and needs no COBOL compiler.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .diff import compare
from .inputs import Case, generate_cases
from .layout import Field, _parse_value, format_value, load_fields, parse_record, record_format, record_length
from .multi import is_multi
from .runners import CLOCK, Run, build_cobol, build_java, read_records, run_files, write_records

VERSION = "0.1"
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "minimal-reproducer.schema.json"
DEFAULT_MAX_RUNS = 150
DEFAULT_MAX_SECONDS = 120.0
RUN_TIMEOUT = 30  # seconds for one program run; a hung side counts as not failing
RECORD_SHARE = 0.6  # of the run cap for record-level reduction; the rest is for fields
EXPLANATION_LABEL = "explanation, not proof"


class Refused(RuntimeError):
    """The reduction or replay was not started: it builds and runs programs, which never happens on the API host when a
    verification sandbox is configured, and never on Java the static policy would not run."""


def refuse_if_sandboxed() -> None:
    """Same rule as claims.py and precheck.py: with DIOCLE_SANDBOX_URL set (outside the sandbox itself), nothing is
    built or run here."""
    if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
        raise Refused("a verification sandbox is configured (DIOCLE_SANDBOX_URL): minimize and replay build and run "
                      "programs locally and are not routed through it")


def static_java_policy(java_dir: Path, dd_names: tuple[str, ...]) -> None:
    """The converter guard's deterministic Java policy (only DD files, the clock, collation and printing) before the
    Java is built or run. The verifier does not own that policy, so it is imported; if it cannot be, nothing runs."""
    try:
        from diocle_converter.guard import check_before_running
    except ImportError as e:
        raise Refused("the static Java policy (diocle_converter.guard) is not importable, so the Java is not run") from e
    try:
        check_before_running(Path(java_dir), dd_names)
    except Exception as e:
        raise Refused(str(e)[:500]) from e


class CapReached(Exception):
    def __init__(self, which: str):
        super().__init__(which)
        self.which = which  # "run-cap" | "time-cap"


@dataclass
class Outcome:
    failing: bool
    signature: tuple | None
    original: Run | None = None
    converted: Run | None = None
    results: list[dict] = field(default_factory=list)


def signature(original: Run, converted: Run, results: list[dict], strict: bool = False) -> tuple | None:
    """None when the two sides agree. Otherwise (kind, ...): what kind of disagreement, and which output fields.
    strict also pins the differing values on both sides, so a smaller input cannot "slip" to a different
    manifestation of the fault (e.g. 20.00 vs 0.00 turning into spaces vs 00000)."""
    if original.exit_code != converted.exit_code:
        return ("exit-code",)
    failing = [r for r in results if not r["match"]]
    if failing:
        first = failing[0]
        names = tuple(sorted({d["field"] for d in first.get("fieldDiffs", [])}))
        if not names and "wrote" in first.get("diff", ""):
            return ("output-count",)
        if strict:
            return ("output-record", names, tuple(sorted((d["field"], d["original"], d["converted"])
                                                         for d in first.get("fieldDiffs", []))))
        return ("output-record", names)
    if original.stdout != converted.stdout:
        return ("stdout",)
    return None


def _kind_text(sig: tuple) -> str:
    return {"exit-code": "exit codes differ", "output-count": "the two sides wrote different numbers of records",
            "stdout": "DISPLAY output differs", "output-record": "an output record differs"}[sig[0]]


class Oracle:
    """Builds both programs once; each `check(records)` runs both and compares. Counts runs, enforces the caps."""

    def __init__(self, sample_dir: Path, java_dir: Path, meta: dict, *, max_runs: int, max_seconds: float,
                 strict: bool = False, now: Callable[[], float] = time.monotonic):
        self.sample_dir, self.java_dir, self.meta = sample_dir, java_dir, meta
        self.max_runs, self.max_seconds, self.now = max_runs, max_seconds, now
        self.strict = strict
        self.runs = 0
        self.started = now()
        self.in_spec, self.out_spec = meta["layouts"]["input"], meta["layouts"]["output"]
        self.in_format, self.out_format = record_format(self.in_spec), record_format(self.out_spec)
        self.out_fields = load_fields(self.out_spec)
        self.out_length = record_length(self.out_fields)
        self.dd = meta["dd"]
        self._cache: dict[tuple, Outcome] = {}
        self._tmp = tempfile.TemporaryDirectory(prefix="diocle-minimize-")
        self.work = Path(self._tmp.name)  # the COBOL side's directory (executable, its output)
        self.java_work = self.work / "java-run"  # the Java side's own cwd: it never shares a directory with the COBOL's files
        self.java_work.mkdir()
        self.build_error = ""
        self._cobol = self._java = None

    def close(self) -> None:
        self._tmp.cleanup()

    def elapsed(self) -> float:
        return self.now() - self.started

    def build(self) -> bool:
        meta, sample = self.meta, self.sample_dir
        self._cobol, failed = build_cobol(sample / meta["source"], sample / meta["copybookDir"], self.work,
                                          [sample / m for m in meta.get("modules", [])], meta.get("collation", "ascii"))
        if failed:
            self.build_error = "COBOL did not build: " + failed.stderr[-300:]
            return False
        self._java, failed = build_java(self.java_dir, meta["javaConversion"]["mainClass"], self.java_work)
        if failed:
            self.build_error = "Java did not build: " + failed.stderr[-300:]
            return False
        return True

    def _side(self, cmd, label, input_path, extra_env=None, cwd=None) -> Run:
        try:
            run = run_files(cmd, {self.dd["input"]: input_path}, {self.dd["output"]: (self.out_format, self.out_length)},
                            cwd or self.work, label, extra_env, timeout=RUN_TIMEOUT)
        except Exception:  # a hung or crashed side is "no output", never a spurious agreement
            return Run(True, -9, "", "", [])
        run.output_lines = run.output_files[self.dd["output"]]
        return run

    def check(self, records: list[str], enforce: bool = True) -> Outcome:
        """enforce=False is for the one closing run that shows the kept input's outputs after a cap was hit."""
        key = tuple(records)
        if key in self._cache:
            return self._cache[key]
        if enforce and self.runs >= self.max_runs:
            raise CapReached("run-cap")
        if enforce and self.elapsed() >= self.max_seconds:
            raise CapReached("time-cap")
        self.runs += 1
        path = self.work / "input.dat"
        write_records(path, list(records), self.in_format)
        digest = _sha(path)
        original = self._side(self._cobol, "original", path)
        converted = self._side(self._java, "converted", path,
                               {"DIOCLE_COLLATION": self.meta.get("collation", "ascii").upper()}, self.java_work)
        if _sha(path) != digest:  # residual-risk tripwire: a program rewrote the shared input between or during the runs
            raise Refused("a program modified the shared input file during the differential run; the result is not trusted")
        cases = [Case(f"r{i + 1}", "minimize", r) for i, r in enumerate(records)]
        results = compare(cases, original.output_lines, converted.output_lines, self.out_fields, self.out_format)
        sig = signature(original, converted, results, self.strict)
        outcome = Outcome(sig is not None, sig, original, converted, results)
        self._cache[key] = outcome
        return outcome

    def raw_original_output(self) -> bytes:
        path = self.work / f"original-{self.dd['output']}.out"
        return path.read_bytes() if path.exists() else b""


# --- record level ----------------------------------------------------------------------------------------------

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ddmin(items: list, test: Callable[[list], bool], state: dict | None = None) -> list:
    """Zeller's ddmin: a sublist (order kept) for which test() is still true and that is 1-minimal when it
    completes. `test(items)` must already be true. If test() raises CapReached, state["best"] holds the smallest
    failing sublist found so far (state is updated as it goes)."""
    state = state if state is not None else {}
    state["best"] = list(items)

    def attempt(candidate: list) -> bool:
        if test(candidate):
            state["best"] = candidate
            return True
        return False

    n = 2
    while len(state["best"]) >= 2:
        best = state["best"]
        size = len(best)
        chunk = -(-size // n)
        parts = [best[i : i + chunk] for i in range(0, size, chunk)]
        if any(attempt(p) for p in parts):
            n = 2
            continue
        if n > 2:
            if any(attempt([x for j, p in enumerate(parts) if j != i for x in p]) for i in range(len(parts))):
                n = max(n - 1, 2)
                continue
        if n >= size:
            break
        n = min(size, n * 2)
    if len(state["best"]) == 1:
        attempt([])  # the last record is removable only if the program differs on an empty input
    return state["best"]


# --- field level -----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class View:
    name: str
    offset: int
    length: int
    field: Field
    redefines: str = ""


def overlay(spec: dict) -> list[View]:
    """Every field of the record, including REDEFINES views (load_fields drops those), with byte offsets.
    The analyzer lists each REDEFINES item separately, so consecutive items that redefine the same field are read as
    one alternative layout laid out in sequence; when the next one would run past the redefined field's length, a
    new alternative starts at the redefined field again (CHQCLR: two views of the 39-byte body). A name that is
    off here is cosmetic: replacement bytes are always checked by the differential run itself."""
    views, offsets, lengths, cursor, pos = [], {}, {}, {}, 0
    for f in spec["fields"]:
        base = f.get("redefines")
        parsed = load_fields({"fields": [{k: v for k, v in f.items() if k != "redefines"}]})[0]
        if base:
            if base not in offsets:
                raise ValueError(f"{f['name']}: redefines unknown field {base}")
            start = cursor.get(base, offsets[base])
            if start + parsed.length > offsets[base] + lengths[base]:
                start = offsets[base]
            offset, cursor[base] = start, start + parsed.length
        else:
            offset, pos = pos, pos + parsed.length
        offsets.setdefault(f["name"], offset)
        lengths.setdefault(f["name"], parsed.length)
        views.append(View(f["name"], offset, parsed.length, parsed, base or ""))
    return views


def _printable(raw: str) -> str:
    return "".join(c if " " <= c <= "~" else "." for c in raw)


def _numeric_value(v: View, raw: str) -> Decimal | None:
    try:
        return _parse_value(v.field, raw)
    except Exception:
        return None


def candidates(v: View, raw: str, line_format: bool) -> list[str]:
    """Replacement bytes for one field, simplest first; same length as the field; never the current bytes."""
    f, out = v.field, []
    if f.kind == "alnum":
        out.append(" " * f.length)
        keep = raw.rstrip(" ")
        if len(keep) > 1:
            out.append(keep[: (len(keep) + 1) // 2].ljust(f.length))
    else:
        value = _numeric_value(v, raw)
        try:
            out.append(format_value(f, Decimal(0)))
        except ValueError:
            pass
        if value is not None and value != 0 and f.usage != "float":
            unit = f.unit
            for target in (unit if value > 0 else -unit,
                           value.to_integral_value(rounding="ROUND_DOWN"),
                           _leading_digit(value)):
                try:
                    out.append(format_value(f, target))
                except ValueError:
                    pass
        if f.usage == "display" and not f.signed:
            out.append(" " * f.length)
    seen, result = {raw}, []
    for c in out:
        if len(c) != f.length or c in seen or (line_format and ("\n" in c or "\r" in c)):
            continue
        seen.add(c)
        result.append(c)
    return result


def _leading_digit(value: Decimal) -> Decimal:
    """Same sign and magnitude order, every digit after the first one zeroed (e.g. 1234.56 -> 1000.00)."""
    sign, digits, exp = value.as_tuple()[0], value.as_tuple()[1], value.as_tuple()[2]
    return Decimal((sign, (digits[0],) + (0,) * (len(digits) - 1), exp)) if digits else value


def _unparseable(record: str, fields: list[Field]) -> set[str]:
    return {n for n, x in parse_record(record, fields).items() if isinstance(x, str) and any(
        f.name == n and f.kind == "numeric" for f in fields)}


def _is_neutral(v: View, raw: str) -> bool:
    if v.field.kind == "alnum":
        return raw.strip(" ") == ""
    value = _numeric_value(v, raw)
    return raw.strip(" ") == "" or (value is not None and value == 0)


def simplify_fields(records: list[str], views: list[View], primary: list[Field], line_format: bool,
                    still_fails: Callable[[list[str]], bool], state: dict | None = None) -> list[str]:
    """Greedy, one pass, record by record and field by field (coarse primary fields before REDEFINES views).
    state (updated as it goes, so a cap loses nothing): records, tried {(record, field, offset): True}, simplified."""
    state = state if state is not None else {}
    state.update(records=list(records), tried={}, simplified=0)
    cur = state["records"]
    ordered = [v for v in views if not v.redefines] + [v for v in views if v.redefines]
    for idx in range(len(cur)):
        for v in ordered:
            rec = cur[idx]
            raw = rec[v.offset : v.offset + v.length]
            if _is_neutral(v, raw):
                continue
            before_bad = _unparseable(rec, primary)
            for repl in candidates(v, raw, line_format):
                cand = rec[: v.offset] + repl + rec[v.offset + v.length :]
                assert len(cand) == len(rec), "layout length changed"
                if _unparseable(cand, primary) - before_bad:
                    continue  # would turn a valid number into an invalid one: a different, uninteresting input
                state["tried"][(idx, v.name, v.offset)] = True
                if still_fails(cur[:idx] + [cand] + cur[idx + 1 :]):
                    cur[idx] = cand
                    state["simplified"] += 1
                    break
    return cur


# --- reporting -------------------------------------------------------------------------------------------------

def _field_entries(rec: str, views: list[View], tried: dict, idx: int) -> list[dict]:
    entries = []
    for v in views:
        raw = rec[v.offset : v.offset + v.length]
        value = _numeric_value(v, raw) if v.field.kind == "numeric" else None
        if v.field.kind == "numeric" and value is not None:
            shown = format(value, "f")
        else:
            shown = raw if raw.isprintable() else "x'" + raw.encode("latin-1").hex() + "'"
        role = ("neutral" if _is_neutral(v, raw) else "needed" if tried.get((idx, v.name, v.offset)) else "unchanged")
        entries.append({"name": v.name, "offset": v.offset, "length": v.length, "value": shown, "role": role,
                        **({"view": v.redefines} if v.redefines else {})})
    return entries


def first_difference(original: list[str], converted: list[str], fields: list[Field], fmt: str) -> dict | None:
    def norm(r: str) -> str:
        return r.rstrip("\r\n").rstrip(" ") if fmt == "line" else r

    for i in range(max(len(original), len(converted))):
        o = original[i] if i < len(original) else None
        c = converted[i] if i < len(converted) else None
        if o is not None and c is not None and norm(o) == norm(c) and (fmt == "line" or len(o) == len(c)):
            continue
        out: dict = {"record": i + 1, "offset": 0}
        if o is not None and c is not None:
            a, b = norm(o), norm(c)
            off = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            out["offset"] = off
            pos = 0
            for f in fields:
                if pos <= off < pos + f.length:
                    out |= {"field": f.name, "fieldOffset": off - pos}
                    break
                pos += f.length
        if o is not None:
            out["original"] = _printable(o)[:200]
        if c is not None:
            out["translated"] = _printable(c)[:200]
        return out
    return None


def _side(run: Run, records: list[str]) -> dict:
    return {"records": [_printable(r)[:400] for r in records[:20]], "stdout": run.stdout[:2000], "exitCode": run.exit_code}


def _bytes_of(records: list[str], fmt: str) -> int:
    return sum(len(r) + (1 if fmt == "line" else 0) for r in records)


def minimize(sample_dir: Path, java_dir: Path, case_id: str, contexts: list[list[str]], *, source: str = "manual",
             hint: list[str] | None = None, max_runs: int = DEFAULT_MAX_RUNS, max_seconds: float = DEFAULT_MAX_SECONDS,
             explanation: dict | None = None, out_dir: Path | None = None, strict: bool = False, origin: str = "",
             now: Callable[[], float] = time.monotonic) -> dict:
    """Reduce the first context (a list of input records) on which the Java differs from the COBOL.
    contexts: candidate starting inputs, tried in order; hint: records to try alone first (e.g. the failing inputs
    the report names). With out_dir, the regression case is written to out_dir/regression/<case_id>/.
    Returns a minimal-reproducer record (status minimized | not-reproduced | unsupported)."""
    refuse_if_sandboxed()
    sample_dir, java_dir = Path(sample_dir).resolve(), Path(java_dir).resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    base = {"version": VERSION, "id": case_id, "program": meta.get("program", sample_dir.name), "source": source,
            "signatureMode": "strict" if strict else "fields", **({"origin": origin[:300]} if origin else {})}

    def done(status: str, reason: str, runs: int = 0, elapsed: float = 0.0) -> dict:
        return {**base, "status": status, "reason": reason,
                "reduction": {"recordsBefore": len(contexts[0]) if contexts else 0, "recordsAfter": 0, "oracleRuns": runs,
                              "maxOracleRuns": max_runs, "wallClockSeconds": round(elapsed, 2),
                              "maxWallClockSeconds": max_seconds, "stoppedBy": "complete"}}

    if "layouts" not in meta or is_multi(meta):
        return done("unsupported", "the minimizer handles programs with one input file and one output file compared "
                    "record by record; this program has several files, an SQL or keyed file, or DISPLAY-only output")
    if "layouts" in meta:
        static_java_policy(java_dir, tuple(meta["dd"].values()))  # before anything is built or run
    oracle = Oracle(sample_dir, java_dir, meta, max_runs=max_runs, max_seconds=max_seconds, strict=strict, now=now)
    try:
        if not oracle.build():
            return done("unsupported", oracle.build_error, elapsed=oracle.elapsed())
        primary, line_format = load_fields(oracle.in_spec), oracle.in_format == "line"
        try:
            views = overlay(oracle.in_spec)
        except (ValueError, KeyError):
            views = []  # layout not expressible field by field: records only
        stopped, origin, start, first = "complete", None, None, None
        try:
            for ctx in contexts:
                for records in ([[h] for h in (hint or []) if len(ctx) > 1] + [ctx]):
                    outcome = oracle.check(records)
                    if outcome.failing:
                        origin, start, first = ctx, records, outcome
                        break
                if start is not None:
                    break
        except CapReached as e:
            return done("not-reproduced", f"stopped by the {e.which} before the discrepancy was reproduced",
                        oracle.runs, oracle.elapsed())
        if start is None:
            return done("not-reproduced", "the Java produced the same output as the COBOL on every starting input tried",
                        oracle.runs, oracle.elapsed())
        target = first.signature

        def still_fails(candidate: list[str]) -> bool:
            return oracle.check(candidate).signature == target

        record_cap = int(max_runs * RECORD_SHARE)

        def record_test(candidate: list[str]) -> bool:
            if oracle.runs >= record_cap:
                raise CapReached("run-cap")
            return still_fails(candidate)

        current, record_minimal = list(start), False
        rec_state: dict = {}
        field_state: dict = {"tried": {}, "simplified": 0}
        try:
            current = ddmin(current, record_test, rec_state)
            record_minimal = True
        except CapReached as e:
            stopped, current = e.which, rec_state["best"]
        if stopped == "complete" and views and len(current) <= 8:
            try:
                current = simplify_fields(current, views, primary, line_format, still_fails, field_state)
            except CapReached as e:
                stopped, current = e.which, field_state["records"]
        final = oracle.check(current, enforce=False)
        return _record(base, oracle, meta, final, current, views, field_state["tried"], field_state["simplified"],
                       origin, stopped, record_minimal, explanation, out_dir, case_id)
    finally:
        oracle.close()


def _record(base, oracle, meta, final, current, views, tried, simplified, origin, stopped,
            record_minimal, explanation, out_dir, case_id) -> dict:
    sig = final.signature
    in_fmt = oracle.in_format
    in_len = record_length(load_fields(oracle.in_spec))
    entries = [{"hex": r.encode("latin-1").hex(), "text": _printable(r),
                "fields": _field_entries(r, views, tried, i) if views else []} for i, r in enumerate(current)]
    needed = sum(f["role"] == "needed" for e in entries for f in e["fields"])
    diff = first_difference(final.original.output_lines, final.converted.output_lines, oracle.out_fields, oracle.out_format)
    record: dict = {
        **base, "status": "minimized",
        "discrepancy": {"kind": sig[0] if sig else "output-record", "summary": (_kind_text(sig) if sig else "") + (
            ": " + ", ".join(sig[1]) if sig and sig[0] == "output-record" and sig[1] else ""),
                        **({"fields": list(sig[1])} if sig and sig[0] == "output-record" and sig[1] else {})},
        "reduction": {"recordsBefore": len(origin), "recordsAfter": len(current),
                      "bytesBefore": _bytes_of(origin, in_fmt),
                      "bytesAfter": _bytes_of(current, in_fmt), "oracleRuns": oracle.runs, "maxOracleRuns": oracle.max_runs,
                      "wallClockSeconds": round(oracle.elapsed(), 2), "maxWallClockSeconds": oracle.max_seconds,
                      "stoppedBy": stopped, "recordMinimal": record_minimal and stopped == "complete",
                      "fieldsSimplified": simplified, "fieldsKept": needed},
        "inputs": [{"dd": oracle.dd["input"], "format": in_fmt, "recordLength": in_len, "records": entries}],
        "output": {"original": _side(final.original, final.original.output_lines),
                   "translated": _side(final.converted, final.converted.output_lines),
                   **({"firstDifference": diff} if diff else {})},
    }
    if explanation:
        record["explanation"] = {"text": str(explanation["text"])[:600], "label": EXPLANATION_LABEL,
                                 "source": explanation["source"]}
    if out_dir is not None:
        record["regression"] = write_regression(Path(out_dir), case_id, meta, oracle, current)
    return record


# --- regression cases -------------------------------------------------------------------------------------------

def write_regression(run_dir: Path, case_id: str, meta: dict, oracle: Oracle, records: list[str]) -> dict:
    """Save the minimized input and what GnuCOBOL wrote for it. The expected bytes come from the original program,
    run again here on exactly this input, never from the Java."""
    case_dir = run_dir / "regression" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    path = oracle.work / "input.dat"
    write_records(path, records, oracle.in_format)
    original = oracle._side(oracle._cobol, "original", path)
    expected = oracle.raw_original_output()
    (case_dir / "input.dat").write_bytes(path.read_bytes())
    (case_dir / "expected-output.dat").write_bytes(expected)
    (case_dir / "expected-stdout.txt").write_bytes(original.stdout.encode("latin-1"))
    case = {
        "version": VERSION, "id": case_id, "program": meta.get("program", ""), "dd": meta["dd"],
        "mainClass": meta["javaConversion"]["mainClass"], "collation": meta.get("collation", "ascii"),
        "clock": CLOCK, "input": {"file": "input.dat", "format": oracle.in_format, "records": len(records)},
        "expected": {"file": "expected-output.dat", "format": oracle.out_format, "recordLength": oracle.out_length,
                     "stdout": "expected-stdout.txt", "exitCode": original.exit_code},
        "outputLayout": meta["layouts"]["output"],
        "note": "expected-output.dat and expected-stdout.txt were written by the original COBOL compiled with GnuCOBOL"
                " (cobc -std=ibm) on input.dat",
    }
    (case_dir / "case.json").write_text(json.dumps(case, indent=2) + "\n")
    rel = f"regression/{case_id}"
    return {"dir": rel, "files": [f"{rel}/{n}" for n in ("case.json", "input.dat", "expected-output.dat", "expected-stdout.txt")],
            "replay": f"python -m diocle_verifier replay {rel} --java-dir <java directory>", "afterRepair": None}


def replay(case_dir: Path, java_dir: Path) -> dict:
    """Run one saved regression case against a Java directory: same input, DD wiring, clock and collation as when it
    was saved; passes only if every output record, stdout and the exit code equal what GnuCOBOL produced."""
    refuse_if_sandboxed()
    case_dir, java_dir = Path(case_dir), Path(java_dir)
    case = json.loads((case_dir / "case.json").read_text())
    out = {"id": case["id"], "passed": False, "detail": ""}
    static_java_policy(java_dir, tuple(case["dd"].values()))
    saved = {n: _sha(case_dir / n) for n in (case["input"]["file"], case["expected"]["file"], case["expected"]["stdout"], "case.json")}
    with tempfile.TemporaryDirectory(prefix="diocle-replay-") as tmp:
        work = Path(tmp) / "java-run"  # the Java's own scratch directory; the input copy sits beside it, not in it
        work.mkdir()
        cmd, failed = build_java(java_dir, case["mainClass"], work)
        if failed:
            return {**out, "detail": "Java did not build: " + failed.stderr[-300:]}
        exp = case["expected"]
        fmt, length = exp["format"], exp["recordLength"]
        dd_in, dd_out = case["dd"]["input"], case["dd"]["output"]
        input_path = work.parent / "input.dat"
        input_path.write_bytes((case_dir / case["input"]["file"]).read_bytes())
        try:
            run = run_files(cmd, {dd_in: input_path}, {dd_out: (fmt, length)}, work, "replay",
                            {"DIOCLE_COLLATION": case["collation"].upper()}, timeout=RUN_TIMEOUT)
        except Exception as e:  # timeout
            return {**out, "detail": f"Java did not finish: {type(e).__name__}"}
        want = read_records(case_dir / exp["file"], fmt, length)
        got = run.output_files[dd_out]
        fields = load_fields(case["outputLayout"])
        diff = first_difference(want, got, fields, fmt)
        want_out = (case_dir / exp["stdout"]).read_bytes().decode("latin-1")
        problems = []
        if saved != {n: _sha(case_dir / n) for n in saved} or _sha(input_path) != saved[case["input"]["file"]]:
            problems.append("the Java modified the saved case files")
        if run.exit_code != exp["exitCode"]:
            problems.append(f"exit code {run.exit_code}, GnuCOBOL gave {exp['exitCode']}")
        if diff:
            where = f"output record {diff['record']}" + (f" field {diff['field']}" if diff.get("field") else "")
            problems.append(f"{where}: expected {diff.get('original', '(none)')!r}, got {diff.get('translated', '(none)')!r}")
        if run.stdout != want_out:
            problems.append("DISPLAY output differs")
        return {**out, "passed": not problems, "detail": "; ".join(problems) or "matches what GnuCOBOL produced",
                **({"firstDifference": diff} if diff else {})}


def replay_all(run_dir: Path, java_dir: Path) -> list[dict]:
    refuse_if_sandboxed()
    root = Path(run_dir) / "regression"
    if root.is_symlink():
        return []
    return [replay(d, java_dir) for d in sorted(root.iterdir()) if (d / "case.json").is_file()] if root.is_dir() else []


# --- run directories --------------------------------------------------------------------------------------------

def reconstruct_cases(sample_dir: Path, meta: dict, seed: int = 1026, random_count: int = 200) -> list[str]:
    """The standard verification inputs (fixtures, corpus, generated), as verify_sample builds them (golden aside)."""
    in_fields = load_fields(meta["layouts"]["input"])
    fixtures = [c["record"] for c in meta.get("fixtureCases", [])]
    fmt, length = record_format(meta["layouts"]["input"]), record_length(in_fields)
    corpus = [r for p in meta.get("corpus", []) for r in read_records(sample_dir / p, fmt, length)]
    return fixtures + corpus + [c.record for c in generate_cases(in_fields, seed=seed, random_count=random_count)]


def locate_case(run_dir: Path, case_id: str, sample_dir: Path, meta: dict,
                from_report: bool = False) -> tuple[list[list[str]], list[str], str]:
    """(contexts, hint, source) for a case id found in the run's breaker.json or verification reports.
    from_report: start from the whole verification report's input list (the batch), not the lone breaker record."""
    def load(name):
        try:
            return json.loads((run_dir / name).read_text())
        except (OSError, ValueError):
            return None

    breaker = load("breaker.json")
    for a in ([] if from_report else (breaker or {}).get("attempts", [])):
        if a.get("id") == case_id and isinstance(a.get("input"), str):
            return [[a["input"]], reconstruct_cases(sample_dir, meta) + [a["input"]]], [], "breaker"
    for name, source in (("verification-report.json", "held-out"), ("initial-verification.json", "initial-test")):
        report = load(name)
        results = (report or {}).get("results", [])
        if any(r.get("inputId") == case_id for r in results):
            everything = [r["input"] for r in results if isinstance(r.get("input"), str)]
            failing = [r["input"] for r in results if not r["match"] and isinstance(r.get("input"), str)]
            mine = next(r.get("input") for r in results if r.get("inputId") == case_id)
            hint = ([mine] if isinstance(mine, str) else []) + failing[:2]
            if len(everything) == len(results):
                return [everything], hint, source
            if isinstance(mine, str):
                return [[mine]], [], source
    raise KeyError(f"case {case_id!r} not found in {run_dir.name} (breaker.json attempts or verification reports)")


def explanation_from_run(run_dir: Path, case_id: str) -> dict | None:
    """Reuse an existing diagnosis: the repair agent's first patch rationale after it resumed with counterexamples,
    else the breaker's own one-sentence reason. Both are opinions. No model call."""
    try:
        events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        events = []
    resumed = False
    for e in events:
        if e.get("type") == "stage" and "resumes with" in str(e.get("message", "")):
            resumed = True
        elif resumed and e.get("tool") == "patch_java" and e.get("rationale"):
            return {"text": str(e["rationale"]), "source": "repair-agent"}
    try:
        for a in json.loads((run_dir / "breaker.json").read_text()).get("attempts", []):
            if a.get("id") == case_id and a.get("why"):
                return {"text": str(a["why"]), "source": "breaker"}
    except (OSError, ValueError):
        pass
    return None


def minimize_run(run_dir: Path, case_id: str, *, sample_dir: Path | None = None, java_dir: Path | None = None,
                 max_runs: int = DEFAULT_MAX_RUNS, max_seconds: float = DEFAULT_MAX_SECONDS,
                 strict: bool = False, from_report: bool = False) -> dict:
    """Minimize one case of a saved run and save runs/<id>/reproducers/<case>.json plus regression/<case>/."""
    refuse_if_sandboxed()
    run_dir = Path(run_dir).resolve()
    run = json.loads((run_dir / "run.json").read_text())
    root = Path(__file__).resolve().parents[3]
    sample_dir = Path(sample_dir) if sample_dir else root / run["sample"]
    meta = json.loads((sample_dir / "sample.json").read_text())
    contexts, hint, source = locate_case(run_dir, case_id, sample_dir, meta, from_report)
    record = minimize(sample_dir, java_dir or run_dir / "java", case_id, contexts, source=source, hint=hint,
                      max_runs=max_runs, max_seconds=max_seconds, explanation=explanation_from_run(run_dir, case_id),
                      out_dir=run_dir, strict=strict)
    save_reproducer(run_dir, record)
    return record


def save_reproducer(run_dir: Path, record: dict) -> Path:
    validate(record)
    folder = Path(run_dir) / "reproducers"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record['id']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def validate(record: dict) -> None:
    import jsonschema

    jsonschema.validate(record, json.loads(CONTRACT.read_text()))


def validate_case(case: dict) -> None:
    import jsonschema

    schema = json.loads(CONTRACT.read_text())
    jsonschema.validate(case, {"$ref": "#/$defs/regressionCase", "$defs": schema["$defs"]})
