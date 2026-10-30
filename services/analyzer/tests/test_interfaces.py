"""Cross-program checks: CALL ... USING compatibility and copybook drift (pure functions, no files)."""
from diocle_analyzer.interfaces import Source, call_findings, copybook_drift, layouts_of

CALLER = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-AMT        PIC S9(7)V99 COMP-3.
       01  WS-NAME       PIC X(20).
       PROCEDURE DIVISION.
           CALL 'SUBPGM' USING WS-AMT BY CONTENT WS-NAME.
           CALL 'SUBPGM' USING WS-AMT.
           STOP RUN.
"""
CALLEE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBPGM.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-AMT        PIC S9(9)V99 COMP-3.
       01  LK-NAME       PIC X(20).
       PROCEDURE DIVISION USING LK-AMT LK-NAME.
           GOBACK.
"""


def test_call_findings_report_length_and_arity_with_lines():
    checked, findings = call_findings([Source("MAINPGM", "a.cbl", CALLER), Source("SUBPGM", "b.cbl", CALLEE)])
    assert checked == 2
    assert [(f["kind"], f["severity"], f["line"]) for f in findings] == [("length", "fail", 8), ("arity", "fail", 9)]


def test_elementary_and_group_items_get_byte_lengths_in_the_layout_helper():
    entries = ["01 A PIC S9(7)V99 COMP-3", "01 G", "05 X PIC X(3)", "05 N PIC 9(4) COMP", "77 Z PIC X(2)"]
    lay = layouts_of(entries)
    assert [f["name"] for f in lay["G"]["fields"]] == ["X", "N"] and set(lay) == {"A", "G", "Z"}


def test_copybook_drift_needs_two_different_layouts_under_the_same_name():
    prog = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P{n}.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       COPY REC.\n       PROCEDURE DIVISION.\n           GOBACK.\n"
    a = "       01  R.\n           05  F PIC X(4).\n"
    b = "       01  R.\n           05  F PIC X(5).\n"
    names, drift = copybook_drift([Source("P1", "p1.cbl", prog.format(n=1), {"REC": ("c/REC.cpy", a)}),
                                   Source("P2", "p2.cbl", prog.format(n=2), {"REC": ("d/REC.cpy", b)})])
    assert names == ["REC"] and [(d["kind"], d["severity"]) for d in drift] == [("layout", "fail")]
    assert copybook_drift([Source("P1", "p1.cbl", prog.format(n=1), {"REC": ("c/REC.cpy", a)}),
                           Source("P2", "p2.cbl", prog.format(n=2), {"REC": ("d/REC.cpy", a)})])[1] == []
