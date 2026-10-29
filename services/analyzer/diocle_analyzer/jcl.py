"""JCL reading: which program each job step runs and the dataset behind each DD name.

Handles in-stream EXEC PGM= steps and cataloged procedures (EXEC procname / EXEC PROC=procname) from a
procedure library, with symbolic parameters (&NAME or &NAME.) taken from the PROC defaults and overridden
on the EXEC statement, and DD overrides (//STEP.DDNAME DD ...) from the calling job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class JobStep:
    job: str
    member: str  # JCL member the job came from
    program: str
    dsns: dict[str, str]  # DD name -> DSN
    proc: str | None = None
    step: str = ""


@dataclass
class Proc:
    name: str
    defaults: dict[str, str] = field(default_factory=dict)
    steps: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)  # (step, program, dd -> dsn)


@dataclass
class SortSpec:
    """A parsed SORT control statement (v1 scope: fixed-offset keys, CH/ZD/PD/BI, optional OPTION EQUALS)."""
    fields: list[tuple[int, int, str, str]] = field(default_factory=list)  # (start, length, format, "A"|"D")
    option_equals: bool = False
    unsupported: str | None = None


@dataclass
class Job:
    name: str  # the //jobname JOB card
    member: str
    steps: list[JobStep] = field(default_factory=list)  # source/EXEC order
    sorts: dict[str, SortSpec] = field(default_factory=dict)  # step name -> parsed spec, SORT-utility steps only


SORT_PROGRAMS = {"SORT", "SYNCSORT", "DFSORT"}
_SORT_KEY_FORMATS = {"CH", "ZD", "PD", "BI"}


def _statements(text: str) -> list[str]:
    """JCL statements with continuations joined (a line ending in ',' continues on the next // line)."""
    out, current = [], ""
    for raw in text.splitlines():
        line = raw[:72].rstrip()
        if not line.startswith("//") or line.startswith("//*"):
            continue
        if current and current.rstrip().endswith(","):
            current += line[2:].strip()
        else:
            if current:
                out.append(current)
            current = line
    if current:
        out.append(current)
    return out


def _params(text: str) -> dict[str, str]:
    return {k: v.strip("'") for k, v in re.findall(r"([A-Z][A-Z0-9#@$]*)=('[^']*'|[^,\s]*)", text)}


def _substitute(value: str, symbols: dict[str, str]) -> str:
    return re.sub(r"&([A-Z][A-Z0-9#@$]*)\.?", lambda m: symbols.get(m.group(1), m.group(0)), value)


def parse_procs(text: str) -> list[Proc]:
    procs, current, step = [], None, None
    for stmt in _statements(text):
        m = re.match(r"//(\S+)\s+PROC\b\s*(.*)", stmt)
        if m:
            current = Proc(m.group(1), _params(m.group(2)))
            procs.append(current)
            continue
        if current is None:
            continue
        m = re.match(r"//(\S+)\s+EXEC\s+PGM=([A-Z0-9#@$]+)", stmt)
        if m:
            step = (m.group(1), m.group(2), {})
            current.steps.append(step)
            continue
        m = re.match(r"//(\S+)\s+DD\s+.*?\bDSN=([^,\s]+)", stmt)
        if m and step:
            step[2][m.group(1)] = m.group(2)
    return procs


def parse_jcl(text: str, member: str, procs: dict[str, Proc] | None = None) -> list[JobStep]:
    procs = procs or {}
    if any(re.match(r"//\S+\s+PROC\b", stmt) for stmt in _statements(text)):
        return []  # a cataloged procedure: its steps count only where a job EXECs it
    job, steps, current = member, [], None
    for stmt in _statements(text):
        m = re.match(r"//(\S+)\s+JOB\b", stmt)
        if m:
            job = m.group(1)
            continue
        m = re.match(r"//(\S*)\s+EXEC\s+PGM=([A-Z0-9#@$]+)", stmt)
        if m:
            current = JobStep(job, member, m.group(2), {}, step=m.group(1))
            steps.append(current)
            continue
        m = re.match(r"//(\S*)\s+EXEC\s+(?:PROC=)?([A-Z0-9#@$]+)\s*,?(.*)", stmt)
        if m and m.group(2) in procs:
            proc = procs[m.group(2)]
            symbols = {**proc.defaults, **_params(m.group(3))}
            current = None
            for step_name, program, dds in proc.steps:
                steps.append(JobStep(job, member, program, {dd: _substitute(dsn, symbols) for dd, dsn in dds.items()},
                                     proc=proc.name, step=step_name))
            continue
        m = re.match(r"//(?:(\S+)\.)?(\S+)\s+DD\s+.*?\bDSN=([^,\s]+)", stmt)
        if m:
            proc_step, dd, dsn = m.groups()
            if proc_step:  # //STEP.DDNAME DD overrides a dataset inside the procedure
                for s in steps:
                    if s.proc and s.step == proc_step:
                        s.dsns[dd] = dsn
            elif current:
                current.dsns[dd] = dsn
    return steps


def is_sort_step(step: JobStep) -> bool:
    return step.program in SORT_PROGRAMS


def parse_sort_fields(text: str) -> SortSpec:
    """Parse a SORT control statement: SORT FIELDS=(...) and optional OPTION EQUALS.

    v1 scope: one or more fixed-offset keys (start,length,format,A|D), formats CH/ZD/PD/BI, ascending or
    descending. Anything else (INCLUDE/OMIT COND=, OUTREC/INREC, SUM FIELDS=, MERGE, variable-length input,
    an unsupported key format) sets .unsupported to a specific reason instead of guessing.
    """
    upper = text.upper()
    if re.search(r"\bMERGE\s+FIELDS=", upper):
        return SortSpec(unsupported="MERGE is not supported yet, only SORT")
    if re.search(r"\b(INCLUDE|OMIT)\s+COND=", upper):
        return SortSpec(unsupported="INCLUDE/OMIT COND= is not supported yet")
    if re.search(r"\bOUTREC\s+FIELDS=", upper) or re.search(r"\bINREC\s+FIELDS=", upper):
        return SortSpec(unsupported="OUTREC/INREC reformatting is not supported yet")
    if re.search(r"\bSUM\s+FIELDS=", upper):
        return SortSpec(unsupported="SUM FIELDS= is not supported yet")
    m = re.search(r"\bSORT\s+FIELDS=\(([^)]*)\)", upper)
    if not m:
        return SortSpec(unsupported="no SORT FIELDS= control statement found")
    fields: list[tuple[int, int, str, str]] = []
    tokens = [t.strip() for t in m.group(1).split(",")]
    if len(tokens) % 4 != 0:
        return SortSpec(unsupported=f"SORT FIELDS=({m.group(1)}): expected (start,length,format,A|D) tuples")
    for i in range(0, len(tokens), 4):
        start_s, length_s, fmt, order = tokens[i:i + 4]
        if not start_s.isdigit() or not length_s.isdigit():
            return SortSpec(unsupported=f"SORT FIELDS=({m.group(1)}): non-numeric start or length")
        if fmt not in _SORT_KEY_FORMATS:
            return SortSpec(unsupported=f"SORT key format {fmt!r} is not supported yet (only CH/ZD/PD/BI)")
        if order not in ("A", "D"):
            return SortSpec(unsupported=f"SORT key order {order!r} is not supported yet (only A/D)")
        fields.append((int(start_s), int(length_s), fmt, order))
    option_equals = bool(re.search(r"\bOPTION\s+EQUALS\b", upper))
    return SortSpec(fields=fields, option_equals=option_equals)


def group_jobs(steps: list[JobStep]) -> list[Job]:
    """Group parse_jcl()'s flat step list by (job, member), preserving source/EXEC order.

    Stable grouping by first occurrence, not a sort: step order is execution order and is semantically
    meaningful. parse_jcl() itself is unchanged; this is a pure post-processing pass over its output.
    """
    jobs: dict[tuple[str, str], Job] = {}
    order: list[tuple[str, str]] = []
    for step in steps:
        key = (step.job, step.member)
        if key not in jobs:
            jobs[key] = Job(name=step.job, member=step.member)
            order.append(key)
        jobs[key].steps.append(step)
    return [jobs[key] for key in order]


def _base_dsn(dsn: str) -> str:
    """Strip a trailing GDG relative-generation qualifier, e.g. FOO(0) / FOO(+1) / FOO(-1) -> FOO."""
    return re.sub(r"\([+-]?\d+\)$", "", dsn)


def wire_steps(job: Job) -> list[tuple[JobStep, str, JobStep, str]]:
    """(producer_step, producer_dd, consumer_step, consumer_dd) for every DSN one step writes and a later
    step in the same job reads. GDG relative generations are normalized by stripping the (0)/(+1)/(-1)
    qualifier before comparing; full GDG generation arithmetic beyond an exact base-DSN match is out of
    scope for v1 and never raises, it just does not match.
    """
    edges: list[tuple[JobStep, str, JobStep, str]] = []
    for i, producer in enumerate(job.steps):
        for p_dd, p_dsn in producer.dsns.items():
            p_base = _base_dsn(p_dsn)
            for consumer in job.steps[i + 1:]:
                for c_dd, c_dsn in consumer.dsns.items():
                    if _base_dsn(c_dsn) == p_base:
                        edges.append((producer, p_dd, consumer, c_dd))
    return edges
