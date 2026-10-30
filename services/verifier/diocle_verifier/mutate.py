"""Mutation testing of a certified Java translation: would the held-out inputs have detected a realistic mistake?

  python -m diocle_verifier mutate RUN_DIR [--max-mutants 40] [--seed 1026]   (writes RUN_DIR/mutation-report.json)

Small, deterministic, source-level faults are seeded into a COPY of the Java (the certified files are never touched):
a flipped comparison, a changed rounding mode, a dropped truncation, a scale off by one, a swapped branch, a
removed `else`, a changed pad or sign byte. Every mutant is compiled and run through the same harness the verifier
uses (the original is built and run once with GnuCOBOL; each mutant is compared with it byte for byte, plus exit
code and stdout) on the same inputs. A mutant the inputs tell apart from the original is "killed"; one they cannot
is "survived". A survivor is a COVERAGE QUESTION (no input exercised the difference, or the change is harmless in a
way the cheap rules cannot see), not automatically a defect, and the score is not a confidence score.

No model is involved anywhere: operators, selection (a seeded shuffle) and the extra inputs for survivors are
deterministic. "equivalent-suspected" comes only from a cheap rule: the mutant's bytecode (javap -c) is identical to
the certified Java's. Contract: contracts/mutation-report.schema.json.
"""

from __future__ import annotations

import bisect
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .diff import compare
from .inputs import Case, _random_value, generate_cases
from .layout import Field, format_record, load_fields, record_format, record_length
from .multi import is_multi
from .runners import CLOCK_ENV, Run, _exec, _run_program, build_cobol, build_java, read_records, write_records

MUTATION_VERSION = "0.1"
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "mutation-report.schema.json"

DEFAULT_MAX_MUTANTS = 40
DEFAULT_MAX_EXTRA = 60
DEFAULT_WALL_CLOCK = 420  # seconds for the whole job, inside the sandbox's own 600 s limit
HARD_MAX_MUTANTS = 60  # the sandbox clamps to these whatever a caller asks for
HARD_MAX_EXTRA = 100
HARD_MAX_WALL_CLOCK = 480
SNIPPET = 200

NOTES = [
    "A surviving mutant is a coverage question, not automatically a defect: either no input exercised the difference "
    "or the change is harmless in a way the cheap rules cannot see.",
    "The score counts detected seeded faults among mutants that compiled and are not suspected equivalent, by the "
    "initial inputs only. It is not a confidence score and not the probability that the translation is correct.",
    "equivalent-suspected means only that the mutant's bytecode is identical to the certified Java's (a cheap "
    "deterministic rule); it is not a proof of equivalence, and mutants it misses count as survivors.",
    "The operators are a sample of realistic faults (comparison, arithmetic, rounding, truncation, scale, branch, "
    "else, loop bound, constants, pad and sign bytes), not all possible faults. No model was used.",
]


# --- scanning the Java source ---------------------------------------------------------------------------------

def mask(text: str) -> str:
    """Same length as `text`, with comments and the inside of string and char literals replaced by '_' (newlines kept),
    so patterns only ever match code."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append("_" * (j - i)); i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else "_" for ch in text[i:j])); i = j
        elif text.startswith('"""', i):
            j = text.find('"""', i + 3)
            j = n if j < 0 else j + 3
            out.append("".join(ch if ch == "\n" else "_" for ch in text[i:j])); i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j, n - 1)
            out.append(c + "_" * (j - i - 1) + (text[j] if j > i else "")); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)[:n].ljust(n, "_")


def _match(m: str, open_at: int) -> int:
    """Index of the ')' closing the '(' at open_at, or -1."""
    depth = 0
    for k in range(open_at, len(m)):
        if m[k] == "(":
            depth += 1
        elif m[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return -1


def _operand_end(m: str, i: int) -> int:
    j, n = i, len(m)
    if j < n and m[j] == "(":
        close = _match(m, j)
        return close + 1 if close >= 0 else j
    while j < n:
        if m[j].isalnum() or m[j] in "_.":
            j += 1
        elif m[j] == "(" and j > i:
            close = _match(m, j)
            if close < 0:
                break
            j = close + 1
        else:
            break
    return j


@dataclass(frozen=True)
class Edit:
    operator: str
    start: int
    end: int
    replacement: str
    description: str


@dataclass(frozen=True)
class Mutant:
    id: str
    operator: str
    file: str
    line: int
    start: int
    end: int
    replacement: str
    description: str
    original: str  # the source line before / after, trimmed
    mutated: str


_REL = {">": ">=", ">=": ">", "<": "<=", "<=": "<", "==": "!=", "!=": "=="}
_ARITH = {"+": "-", "-": "+", "*": "/", "/": "*"}
_ROUND = {"HALF_UP": ("HALF_EVEN", "DOWN"), "HALF_EVEN": ("HALF_UP",), "DOWN": ("HALF_UP", "FLOOR"), "UP": ("DOWN",),
          "FLOOR": ("DOWN",), "CEILING": ("FLOOR",), "HALF_DOWN": ("HALF_UP",)}
_BYTE = {"0x20": "0x30", "0x30": "0x20", "0x2b": "0x2d", "0x2d": "0x2b"}


def _edits(text: str) -> list[Edit]:
    m = mask(text)
    found: list[Edit] = []

    def add(op, s, e, rep, desc):
        if text[s:e] != rep:
            found.append(Edit(op, s, e, rep, desc))

    for x in re.finditer(r"(?<=\s)(>=|<=|>|<|==|!=)(?=\s)", m):
        add("relational-swap", x.start(), x.end(), _REL[x.group()], f"comparison `{x.group()}` changed to `{_REL[x.group()]}`")
    for x in re.finditer(r"(?<=\s)([+\-*/])(?=\s)", m):
        line_start = text.rfind("\n", 0, x.start()) + 1
        line_end = text.find("\n", x.start())
        if x.group() == "+" and '"' in text[line_start : line_end if line_end >= 0 else len(text)]:
            continue  # string concatenation: the swap would not compile
        add("arithmetic-swap", x.start(), x.end(), _ARITH[x.group()], f"operator `{x.group()}` changed to `{_ARITH[x.group()]}`")
    for x in re.finditer(r"(?<=\s)(\+=|-=)(?=\s)", m):
        rep = "-=" if x.group() == "+=" else "+="
        add("arithmetic-swap", x.start(), x.end(), rep, f"operator `{x.group()}` changed to `{rep}`")
    for x in re.finditer(r"RoundingMode\.(\w+)", m):
        for alt in _ROUND.get(x.group(1), ()):
            add("rounding-mode", x.start(1), x.end(1), alt, f"rounding mode {x.group(1)} changed to {alt}")
    for x in re.finditer(r"\.(remainder|mod)\(", m):
        close = _match(m, x.end() - 1)
        if close > 0:
            add("remove-truncation", x.start(), close + 1, "", f"truncation `.{x.group(1)}(...)` removed (no wrap on overflow)")
    for x in re.finditer(r"(?<=\s)%(?=\s)", m):
        i = x.end()
        while i < len(m) and m[i] == " ":
            i += 1
        j = _operand_end(m, i)
        if j > i:
            add("remove-truncation", x.start() - 1, j, "", "modulo truncation `% ...` removed (no wrap on overflow)")
    for x in re.finditer(r"(setScale|movePointLeft|movePointRight)\(\s*(-?\d+)", m):
        n = int(x.group(2))
        for d in (1, -1):
            add("scale-off-by-one", x.start(2), x.end(2), str(n + d), f"{x.group(1)} argument {n} changed to {n + d}")
    lines = m.split("\n")
    offset = 0
    for line in lines:
        trigger = re.search(r"(?<=\s)(>=|<=|>|<|==|!=)(?=\s)|substring\(|repeat\(|charAt\(", line)
        if trigger and not re.search(r"\bstatic\s+final\b|\bimport\b", line):
            for x in re.finditer(r"(?<![\w.])(\d+)(?![\w.])", line):
                n = int(x.group(1))
                for d in (1, -1):
                    if n + d >= 0:
                        add("boundary-constant", offset + x.start(), offset + x.end(), str(n + d),
                            f"constant {n} changed to {n + d}")
        offset += len(line) + 1
    for x in re.finditer(r"\b(if|while)\s*\(", m):
        close = _match(m, x.end() - 1)
        if close > 0:
            cond = text[x.end() : close]
            if cond.strip() not in ("true", "false", ""):
                add("negate-condition", x.end(), close, f"!({cond})", f"`{x.group(1)}` condition negated")
    for x in re.finditer(r"\bfor\s*\([^;]*;\s*[\w.]+\s*<\s*([^;]+?)\s*;", m):
        add("loop-bound", x.start(1), x.end(1), f"({text[x.start(1) : x.end(1)]}) - 1", "loop stops one iteration early (last record skipped)")
    for x in re.finditer(r"\belse\s*(?=\{)", m):
        add("remove-else", x.start(), x.end(), "else if (false) ", "`else` branch made unreachable")
    for x in re.finditer(r"\.equals\(", m):
        add("string-compare", x.start(), x.end(), ".equalsIgnoreCase(", "`equals` changed to `equalsIgnoreCase`")
    for x in re.finditer(r"\.(trim|stripTrailing|stripLeading|strip)\(\)", m):
        add("string-compare", x.start(), x.end(), "", f"`.{x.group(1)}()` removed")
    for x in re.finditer(r"'_'", m):
        lit = text[x.start() : x.end()]
        if lit in ("' '", "'0'"):
            rep = "'0'" if lit == "' '" else "' '"
            add("pad-char", x.start(), x.end(), rep, f"character {lit} changed to {rep}")
    for x in re.finditer(r"\b0[xX](20|30|2[bB]|2[dD])\b", m):
        key = "0x" + x.group(1).lower()
        rep = _BYTE[key]
        add("pad-char", x.start(), x.end(), rep, f"byte {key} changed to {rep} (pad or sign byte)")
    return found


def generate_mutants(java_dir: Path, *, seed: int, max_mutants: int) -> tuple[list[Mutant], int]:
    """(selected mutants, number of mutants the operators could place). Selection: each operator's candidates are
    shuffled with the seed, then taken round-robin, so one operator cannot crowd the others out; the result is a pure
    function of (source, seed)."""
    per_op: dict[str, list[tuple[str, Edit]]] = {}
    texts: dict[str, str] = {}
    for path in sorted(java_dir.rglob("*.java")):
        rel = path.relative_to(java_dir).as_posix()
        texts[rel] = path.read_text(encoding="utf-8", errors="surrogateescape")
        for e in _edits(texts[rel]):
            per_op.setdefault(e.operator, []).append((rel, e))
    total = sum(len(v) for v in per_op.values())
    rng = random.Random(seed)
    for op in sorted(per_op):
        rng.shuffle(per_op[op])
    chosen: list[tuple[str, Edit]] = []
    while len(chosen) < max_mutants and any(per_op.values()):
        for op in sorted(per_op):
            if per_op[op] and len(chosen) < max_mutants:
                chosen.append(per_op[op].pop())
    chosen.sort(key=lambda c: (c[0], c[1].start, c[1].replacement))
    mutants = []
    for k, (rel, e) in enumerate(chosen, 1):
        text = texts[rel]
        starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        line_no = bisect.bisect_right(starts, e.start)
        line_start = starts[line_no - 1]
        line_end = text.find("\n", line_start)
        line_end = len(text) if line_end < 0 else line_end
        before = text[line_start:line_end]
        after = (text[:e.start] + e.replacement + text[e.end:])[line_start : line_end + len(e.replacement) - (e.end - e.start)]
        mutants.append(Mutant(f"m{k:03d}", e.operator, rel, line_no, e.start, e.end, e.replacement, e.description,
                              before.strip()[:SNIPPET], after.split("\n")[0].strip()[:SNIPPET]))
    return mutants, total


# --- inputs ---------------------------------------------------------------------------------------------------

def extra_cases(fields: list[Field], seed: int, count: int) -> list[Case]:
    """Deterministic extra inputs aimed at what a first set tends to miss: the value just below and above each
    field's boundary, pairs of fields at their extremes together, and a record repeated or with blank keys (duplicate
    and missing keys). No model."""
    rng = random.Random(f"extra:{seed}")
    numeric = [f for f in fields if f.kind == "numeric"]
    base = lambda: {f.name: _random_value(f, rng, 0) for f in fields}  # noqa: E731
    candidates: list[dict] = []
    for f in numeric:
        near = [f.max_value - f.unit, f.max_value, f.unit * 2, f.unit * 5, f.max_value / 2, Decimal(0), f.unit]
        near = [v.quantize(f.unit) if f.scale >= 0 else v for v in near]
        if f.signed:
            near += [-v for v in near if v != 0]
        for v in near:
            for _ in range(2):
                candidates.append({**base(), f.name: v})
    for a in range(len(numeric)):
        for b in range(a + 1, len(numeric)):
            for va in ("zero", "max", "unit"):
                for vb in ("zero", "max", "unit"):
                    pick = lambda f, w: Decimal(0) if w == "zero" else f.max_value if w == "max" else f.unit  # noqa: E731
                    candidates.append({**base(), numeric[a].name: pick(numeric[a], va), numeric[b].name: pick(numeric[b], vb)})
    for f in fields:
        if f.kind == "alnum":
            candidates.append({**base(), f.name: " " * f.length})
            for v in f.values:
                candidates.append({**base(), f.name: v})
    rng.shuffle(candidates)
    picked = candidates[:count]
    ordered: list[str] = []
    for i, c in enumerate(picked):
        record = format_record(c, fields)
        ordered += [record, record] if i % 3 == 0 else [record]  # every third record repeated (duplicate keys)
    return [Case(f"extra-{i + 1:04d}", "boundary", r) for i, r in enumerate(ordered)]


# --- running mutants ------------------------------------------------------------------------------------------

def _bytecode(classes: Path) -> dict[str, str] | None:
    """javap -c -p of every class, without the source-file header: two builds with identical text behave identically."""
    out = {}
    for path in sorted(classes.rglob("*.class")):
        rel = path.relative_to(classes).with_suffix("").as_posix().replace("/", ".")
        proc = _exec(["javap", "-c", "-p", "-cp", str(classes), rel], timeout=60)
        if proc.returncode != 0:
            return None
        out[rel] = "\n".join(l for l in proc.stdout.splitlines() if not l.startswith("Compiled from"))
    return out


def _detect(cases: list[Case], original: Run, mutant: Run, out_fields: list[Field], fmt: str) -> str | None:
    """Id of the first input that tells the mutant apart from the original, or "exit-code" / "stdout"; None if none does."""
    for r in compare(cases, original.output_lines, mutant.output_lines, out_fields, fmt):
        if not r["match"]:
            return r["inputId"]
    if mutant.exit_code != original.exit_code:
        return "exit-code"
    if mutant.stdout != original.stdout:
        return "stdout"
    return None


def _short(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return (lines[0] if lines else "")[:160]


def mutate_local(sample_dir: Path, java_dir: Path, *, seed: int = 1026, max_mutants: int = DEFAULT_MAX_MUTANTS,
                 max_extra: int = DEFAULT_MAX_EXTRA, wall_clock: int = DEFAULT_WALL_CLOCK, input_seed: int = 1026,
                 random_count: int = 200, mutant_timeout: int | None = None) -> dict:
    """Build the report for one single-file sample and its Java. Runs everything on this machine (the sandbox calls this)."""
    started = time.time()
    max_mutants = max(1, min(int(max_mutants), HARD_MAX_MUTANTS))
    max_extra = max(0, min(int(max_extra), HARD_MAX_EXTRA))
    wall_clock = max(10, min(int(wall_clock), HARD_MAX_WALL_CLOCK))
    sample_dir, java_dir = Path(sample_dir).resolve(), Path(java_dir).resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    report: dict = {
        "version": MUTATION_VERSION, "runId": None, "program": meta.get("program"), "status": "ok", "reason": None,
        "seed": seed, "inputs": {"initial": 0, "seed": input_seed},
        "counts": {"generated": 0, "run": 0, "killed": 0, "survived": 0, "notCompiled": 0, "equivalentSuspected": 0,
                   "timeout": 0, "error": 0, "notRun": 0, "score": None},
        "mutants": [], "augmented": {"extraInputs": 0, "survivorsRerun": 0, "extraKills": 0, "stillSurviving": 0, "modelCalls": 0},
        "caps": {"maxMutants": max_mutants, "maxExtraInputs": max_extra, "wallClockSeconds": wall_clock,
                 "mutantTimeoutSeconds": 10, "budgetExhausted": False},
        "seconds": 0.0, "notes": list(NOTES),
    }

    def finish(status: str | None = None, reason: str | None = None) -> dict:
        if status:
            report["status"], report["reason"] = status, reason
        report["seconds"] = round(time.time() - started, 1)
        return report

    if is_multi(meta):
        return finish("unsupported", "mutation testing covers single-input, single-output programs; this sample has "
                                     "several files, a database, keyed files, I-O files or DISPLAY-only output")
    if not list(java_dir.rglob("*.java")):
        return finish("unsupported", "no Java sources")
    in_fields, out_fields = load_fields(meta["layouts"]["input"]), load_fields(meta["layouts"]["output"])
    in_format = record_format(meta["layouts"]["input"])
    out_format = (record_format(meta["layouts"]["output"]), record_length(out_fields))
    fmt = out_format[0]
    collation = meta.get("collation", "ascii")
    main_class, dd = meta["javaConversion"]["mainClass"], meta["dd"]
    env = {"DIOCLE_COLLATION": collation.upper()}

    fixtures = [Case(f"fixture-{c['id']}", "fixture", c["record"]) for c in meta.get("fixtureCases", [])]
    corpus = [Case(f"corpus-{i + 1:04d}", "corpus", r) for i, r in enumerate(
        r for path in meta.get("corpus", []) for r in read_records(sample_dir / path, in_format, record_length(in_fields)))]
    cases = fixtures + corpus + generate_cases(in_fields, seed=input_seed, random_count=random_count)
    report["inputs"]["initial"] = len(cases)

    with tempfile.TemporaryDirectory(prefix="diocle-mutate-") as tmp:
        work = Path(tmp)
        main_in = work / "initial.dat"
        write_records(main_in, [c.record for c in cases], in_format)
        cmd_o, failed = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                    [sample_dir / m for m in meta.get("modules", [])], collation)
        if cmd_o is None:
            return finish("baseline-failed", "the original COBOL did not compile")
        original = _run_program(cmd_o, dd, main_in, work, "original", out_format)

        base_work = work / "baseline"
        base_work.mkdir()
        cmd_b, failed = build_java(java_dir, main_class, base_work)
        if cmd_b is None:
            return finish("baseline-failed", "the certified Java did not compile here")
        t0 = time.time()
        baseline = _run_program(cmd_b, dd, main_in, base_work, "converted", out_format, env)
        baseline_seconds = time.time() - t0
        if _detect(cases, original, baseline, out_fields, fmt) is not None:
            return finish("baseline-failed", "the unmutated Java does not match the original on these inputs, so "
                                             "mutants cannot be judged")
        base_code = _bytecode(base_work / "classes")
        timeout = mutant_timeout or int(min(30, max(10, 10 * baseline_seconds)))
        report["caps"]["mutantTimeoutSeconds"] = timeout

        mutants, generated = generate_mutants(java_dir, seed=seed, max_mutants=max_mutants)
        report["counts"]["generated"] = generated
        survivors: list[tuple[dict, Mutant]] = []
        deadline = started + wall_clock - 30  # leave the augmentation and the report some time
        for k, mu in enumerate(mutants):
            if time.time() > deadline:
                report["counts"]["notRun"] = len(mutants) - k
                report["caps"]["budgetExhausted"] = True
                break
            entry = {"id": mu.id, "operator": mu.operator, "location": {"file": mu.file, "line": mu.line},
                     "original": mu.original, "mutated": mu.mutated, "description": mu.description,
                     "outcome": "error", "killedBy": None}
            report["mutants"].append(entry)
            report["counts"]["run"] += 1
            mdir = work / f"mut-{mu.id}"
            try:
                shutil.copytree(java_dir, mdir / "src")
                target = mdir / "src" / mu.file
                text = target.read_text(encoding="utf-8", errors="surrogateescape")
                target.write_text(text[: mu.start] + mu.replacement + text[mu.end :], encoding="utf-8", errors="surrogateescape")
                (mdir / "run").mkdir()
                cmd_m, build_failed = build_java(mdir / "src", main_class, mdir / "run")
                if cmd_m is None:
                    entry.update(outcome="not-compiled", note=_short(build_failed.stderr or build_failed.stdout))
                    continue
                if base_code is not None and _bytecode(mdir / "run" / "classes") == base_code:
                    entry.update(outcome="equivalent-suspected", note="bytecode identical to the certified Java")
                    continue
                try:
                    run = _run_program(cmd_m, dd, main_in, mdir / "run", "converted", out_format, env, timeout)
                except subprocess.TimeoutExpired:
                    entry.update(outcome="timeout", note=f"no result within {timeout} s")
                    continue
                killer = _detect(cases, original, run, out_fields, fmt)
                if killer:
                    entry.update(outcome="killed", killedBy=killer)
                else:
                    entry.update(outcome="survived")
                    survivors.append((entry, mu))
            except Exception as e:  # the harness failed, not the mutant: reported, excluded from the score
                entry.update(outcome="error", note=f"{type(e).__name__}: {str(e)[:120]}")
            finally:
                shutil.rmtree(mdir, ignore_errors=True)

        # Survivors only: one shared pool of extra inputs, the original built once and run once on it.
        if survivors and max_extra > 0 and time.time() < started + wall_clock:
            extra = extra_cases(in_fields, seed, max_extra)
            extra_in = work / "extra.dat"
            write_records(extra_in, [c.record for c in extra], in_format)
            original_x = _run_program(cmd_o, dd, extra_in, work, "original-extra", out_format)
            baseline_x = _run_program(cmd_b, dd, extra_in, base_work, "converted-extra", out_format, env)
            report["augmented"]["extraInputs"] = len(extra)
            if _detect(extra, original_x, baseline_x, out_fields, fmt) is not None:
                report["notes"].append("The certified Java disagreed with the original on one of the extra inputs, so "
                                       "augmentation was skipped; that is a finding to re-verify, not a mutation result.")
                report["augmented"]["extraInputs"] = 0
            else:
                for entry, mu in survivors:
                    if time.time() > started + wall_clock:
                        break
                    report["augmented"]["survivorsRerun"] += 1
                    mdir = work / f"mutx-{mu.id}"
                    try:
                        shutil.copytree(java_dir, mdir / "src")
                        target = mdir / "src" / mu.file
                        text = target.read_text(encoding="utf-8", errors="surrogateescape")
                        target.write_text(text[: mu.start] + mu.replacement + text[mu.end :], encoding="utf-8", errors="surrogateescape")
                        (mdir / "run").mkdir()
                        cmd_m, _ = build_java(mdir / "src", main_class, mdir / "run")
                        try:
                            run = _run_program(cmd_m, dd, extra_in, mdir / "run", "converted", out_format, env, timeout) if cmd_m else None
                        except subprocess.TimeoutExpired:
                            entry.update(augmentedOutcome="killed", augmentedKilledBy="timeout")
                            report["augmented"]["extraKills"] += 1
                            continue
                        killer = _detect(extra, original_x, run, out_fields, fmt) if run else None
                        if killer:
                            entry.update(augmentedOutcome="killed", augmentedKilledBy=killer)
                            report["augmented"]["extraKills"] += 1
                        else:
                            entry.update(augmentedOutcome="survived", augmentedKilledBy=None)
                    except Exception as e:
                        entry.update(note=f"augmentation failed: {type(e).__name__}")
                    finally:
                        shutil.rmtree(mdir, ignore_errors=True)
                report["augmented"]["stillSurviving"] = report["augmented"]["survivorsRerun"] - report["augmented"]["extraKills"]

    c = report["counts"]
    outcomes = [m["outcome"] for m in report["mutants"]]
    c["killed"], c["survived"] = outcomes.count("killed"), outcomes.count("survived")
    c["notCompiled"], c["equivalentSuspected"] = outcomes.count("not-compiled"), outcomes.count("equivalent-suspected")
    c["timeout"], c["error"] = outcomes.count("timeout"), outcomes.count("error")
    scored = c["killed"] + c["timeout"] + c["survived"]
    c["score"] = round((c["killed"] + c["timeout"]) / scored, 3) if scored else None
    return finish()


def mutate_sample(sample_dir: Path, java_dir: Path, *, seed: int = 1026, max_mutants: int = DEFAULT_MAX_MUTANTS,
                  max_extra: int = DEFAULT_MAX_EXTRA, wall_clock: int = DEFAULT_WALL_CLOCK, input_seed: int = 1026,
                  random_count: int = 200) -> dict:
    """With DIOCLE_SANDBOX_URL set, the job runs in the sandbox container (model-written Java never runs on the API host)."""
    if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
        from .sandbox import remote_mutation
        return remote_mutation(Path(sample_dir).resolve(), Path(java_dir).resolve(), {
            "seed": seed, "maxMutants": max_mutants, "maxExtra": max_extra, "wallClock": wall_clock,
            "inputSeed": input_seed, "randomCount": random_count})
    return mutate_local(sample_dir, java_dir, seed=seed, max_mutants=max_mutants, max_extra=max_extra,
                        wall_clock=wall_clock, input_seed=input_seed, random_count=random_count)


def validate_report(report: dict) -> None:
    import jsonschema

    jsonschema.validate(report, json.loads(CONTRACT.read_text()))


def mutate_run(run_dir: Path, *, seed: int = 1026, max_mutants: int = DEFAULT_MAX_MUTANTS, max_extra: int = DEFAULT_MAX_EXTRA,
               wall_clock: int = DEFAULT_WALL_CLOCK, random_count: int = 1000, repo_root: Path | None = None) -> dict:
    """The run's certified Java (RUN_DIR/java) against its sample, on the inputs of its certification seed."""
    run_dir = Path(run_dir).resolve()
    run = json.loads((run_dir / "run.json").read_text())
    root = repo_root or Path(__file__).resolve().parents[3]
    sample = Path(run.get("sample", ""))
    sample = sample if sample.is_absolute() else root / sample
    if not run.get("certified"):
        raise ValueError("mutation testing needs a certified run")
    if not (sample / "sample.json").exists() or not (run_dir / "java").is_dir():
        raise ValueError("the run's sample or Java is missing")
    report = mutate_sample(sample, run_dir / "java", seed=seed, max_mutants=max_mutants, max_extra=max_extra,
                           wall_clock=wall_clock, input_seed=int(run.get("certificationSeed") or 1026),
                           random_count=random_count)
    report["runId"] = run_dir.name
    validate_report(report)
    return report
