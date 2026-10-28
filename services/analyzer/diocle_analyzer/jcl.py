"""Minimal JCL reading: which program each job runs and the dataset behind each DD name."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class JobStep:
    job: str
    member: str  # JCL file name
    program: str
    dsns: dict[str, str]  # DD name -> DSN


def parse_jcl(text: str, member: str) -> list[JobStep]:
    job, steps, current = member, [], None
    for line in text.splitlines():
        if line.startswith("//*") or not line.startswith("//"):
            continue
        m = re.match(r"//(\S+)\s+JOB\b", line)
        if m:
            job = m.group(1)
            continue
        m = re.match(r"//\S*\s+EXEC\s+PGM=([A-Z0-9#@$]+)", line)
        if m:
            current = JobStep(job, member, m.group(1), {})
            steps.append(current)
            continue
        m = re.match(r"//(\S+)\s+DD\s+.*?\bDSN=([^,\s]+)", line)
        if m and current:
            current.dsns[m.group(1)] = m.group(2)
    return steps
