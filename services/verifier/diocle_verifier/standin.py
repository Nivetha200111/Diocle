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
    """The code without comments, read the way the analyzer reads it: columns 8-72 of fixed-format source, whole lines
    of free-format source (>>SOURCE FORMAT FREE, compiled with -free), so the two agree on what a program calls."""
    from diocle_analyzer.cobol import source_lines  # as in reverify.py: only here, the package has no hard dependency

    return "\n".join(code for _, code in source_lines(path.read_text(errors="replace"))).upper()


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


END_CHECK = "stand-in-end"


def _counts(records: dict[str, int]) -> str:
    return ", ".join(f"{dd} {n}" for dd, n in records.items()) or "none"


def ended_at_stand_in(sample_dir: Path, meta: dict, original, inputs: dict[str, int], outputs: dict[str, int]) -> dict | None:
    """The report's `runs.endedAtStandIn` (v0.12) when the original's run ended at a stand-in, else None.

    Every input goes into one run, so the inputs after that point, if any, ran on neither side, and "k of k match" would
    overstate what was tested. Both signs are needed: the stand-in's exit code and its stderr line, so a program that was
    built with the stand-in but never reached it (or that sets RETURN-CODE 16 itself) stays certifiable. How many records
    it read is not known, only what it was given and what it wrote, so this fails closed even if it read them all."""
    if not original.compiled:
        return None
    for routine in stand_ins_for([sample_dir / meta["source"], *(sample_dir / m for m in meta.get("modules", []))]):
        said = re.search(rf"^{routine} abend code (\S+)", original.stderr, re.M)
        if said and original.exit_code == EXIT_CODE[routine]:
            reason = (f"the original ended at Diocle's {routine} stand-in (exit code {original.exit_code}, abend code "
                      f"{said.group(1)}) with records written: {_counts(outputs)}; records supplied: {_counts(inputs)}. Input "
                      "after that point, if any, ran on neither side, so this run cannot certify the program, whatever "
                      "else matched. This is not a fault of the converted Java.")
            return {"routine": routine, "exitCode": original.exit_code, "abendCode": said.group(1),
                    "inputRecords": inputs, "outputRecords": outputs, "reason": reason}
    return None


def end_result(program: str, ended: dict) -> dict:
    """One failing result, so every reader of the report's results and summary fails closed and shows the reason."""
    return {"program": program, "inputId": END_CHECK, "match": False, "fieldDiffs": [], "diff": ended["reason"]}
