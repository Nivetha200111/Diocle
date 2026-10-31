"""Runtime routines that Diocle verifies against a stated stand-in, never against IBM's own implementation.

A program that CALLs one of these (and does not ship a program of that name itself) is not refused as "CALLs a
program not in the repository": services/verifier links its stand-in into the GnuCOBOL build of the original, and the
converter tells the model what the Java must do. The claim is "verified against GnuCOBOL with Diocle's stand-in",
the same way EXEC SQL is verified on a SQLite stand-in and keyed files on GnuCOBOL's INDEXED handler.

The behaviour is defined once, in services/verifier/diocle_verifier/standins/ (the COBOL source of each stand-in),
and documented in services/verifier/README.md.
"""

from __future__ import annotations

STAND_INS: dict[str, str] = {
    # IBM Language Environment CEE3ABD (abnormal termination), e.g. CALL 'CEE3ABD' USING ABCODE, TIMING.
    "CEE3ABD": ("Diocle's CEE3ABD stand-in (not IBM Language Environment): the run ends at the CALL with exit code 16; "
                "DISPLAY output and records already written are kept (open files are closed as at STOP RUN); "
                "'CEE3ABD abend code <n>' goes to stderr, which is not compared"),
}


def stand_ins_used(calls: list[str], program_ids: set[str]) -> list[str]:
    """The stand-in routines among these CALL targets that the repository does not define itself."""
    return sorted({c for c in calls if c in STAND_INS and c not in program_ids})
