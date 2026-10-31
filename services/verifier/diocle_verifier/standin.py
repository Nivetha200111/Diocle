"""Stated stand-ins for runtime routines (see standins/*.cbl and the README, "Stand-ins").

When an original program CALLs a routine listed here and none of the sources being compiled defines a program of
that name, the verifier links Diocle's stand-in (a small COBOL program shipped in standins/) into the GnuCOBOL build.
The result is "verified against GnuCOBOL with Diocle's stand-in", never "verified against IBM Language Environment":
the stand-in fixes one documented behaviour and the Java must reproduce it.

Detection is on the source text, so every build path (verify, multi-file and keyed runs, EXEC SQL builds, mutation
testing, claims, minimize, the sandbox and the delivery CI's reverify) links it the same way without the sample having
to say so: a quoted literal 'CEE3ABD' anywhere in the code (CALL 'CEE3ABD', or a CALL identifier whose VALUE is it).
Linking a stand-in a program never reaches changes nothing.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

STANDINS = Path(__file__).resolve().parent / "standins"
ROUTINES = ("CEE3ABD",)
EXIT_CODE = {"CEE3ABD": 16}
NOTE = {"CEE3ABD": ("Diocle's CEE3ABD stand-in, not IBM Language Environment: the run ends at the CALL with exit code 16, "
                    "DISPLAY output and records already written are kept, 'CEE3ABD abend code <n>' goes to stderr "
                    "(not compared)")}


def _code(path: Path) -> str:
    """Fixed-format code area without comment lines (column 7 '*' or '/')."""
    lines = path.read_text(errors="replace").splitlines()
    return "\n".join(l[7:72] for l in lines if not (len(l) > 6 and l[6] in "*/")).upper()


def stand_ins_for(sources: list[Path]) -> list[str]:
    """The stand-in routines these sources call and do not define themselves."""
    codes = [_code(p) for p in sources if p.is_file()]
    defined = {m for c in codes for m in re.findall(r"\bPROGRAM-ID\.\s*['\"]?([A-Z0-9][A-Z0-9-]*)", c)}
    return [r for r in ROUTINES
            if r not in defined and any(re.search(rf"['\"]{r}\s*['\"]", c) for c in codes)]


def stand_in_sources(sources: list[Path], workdir: Path) -> list[Path]:
    """Copies of the stand-ins these sources need, in workdir (the shipped files may sit on a read-only filesystem,
    as in the sandbox), to append to the cobc command after the program and its modules."""
    needed = stand_ins_for(sources)
    if not needed:
        return []
    target = workdir / "diocle-standins"
    target.mkdir(parents=True, exist_ok=True)
    out = []
    for routine in needed:
        dest = target / f"{routine}.cbl"
        shutil.copyfile(STANDINS / f"{routine}.cbl", dest)
        out.append(dest)
    return out


def stand_ins_run(sample_dir: Path, meta: dict) -> dict:
    """The verification report's `runs.standIns` (v0.11): which stand-ins the original was built with, if any."""
    names = stand_ins_for([sample_dir / meta["source"], *(sample_dir / m for m in meta.get("modules", []))])
    return {"standIns": [{"routine": n, "exitCode": EXIT_CODE[n], "note": NOTE[n]} for n in names]} if names else {}
