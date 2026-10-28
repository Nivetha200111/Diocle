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
