import sys

from diocle_verifier.runners import _exec


def test_stdout_is_decoded_byte_for_byte_not_as_utf8_text():
    code = "import sys; sys.stdout.buffer.write(b'A\\xff\\rB\\r\\nC')"
    proc = _exec([sys.executable, "-c", code])
    assert proc.stdout == "A\xff\rB\r\nC"  # no UnicodeDecodeError, lone CR and CRLF both kept as they were written


def test_stdin_is_closed():
    proc = _exec([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"])
    assert proc.stdout.strip() == "''"


def test_free_format_source_gets_free_and_fixed_does_not(tmp_path):
    from diocle_verifier.runners import format_flags
    for first, flags in ((">>SOURCE FORMAT FREE", ["-free"]), ("      >>SOURCE FORMAT IS FREE", ["-free"]),
                         ('       $SET SOURCEFORMAT"FREE"', ["-free"]), ("       IDENTIFICATION DIVISION.", []),
                         ("      * FREE text in a comment", [])):
        (tmp_path / "p.cbl").write_text("\n" + first + "\n")
        assert format_flags(tmp_path / "p.cbl") == flags, first
    assert format_flags(tmp_path / "missing.cbl") == []


def test_free_format_program_with_long_lines_compiles_and_runs(tmp_path):
    import shutil

    import pytest

    from diocle_verifier.runners import run_cobol
    if not shutil.which("cobc"):
        pytest.skip("GnuCOBOL not installed")
    long_if = '           IF IN-REC(1:1) = "A" MOVE "ACCEPTED" TO OUT-REC ELSE MOVE "REJECTED" TO OUT-REC END-IF'
    assert len(long_if) > 72  # cut off at column 72 when read as fixed format
    source = tmp_path / "FREEP.cbl"
    source.write_text(f""">>SOURCE FORMAT FREE
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FREEP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO INDD ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO OUTDD ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC PIC X(10).
       FD  OUT-F.
       01  OUT-REC PIC X(10).
       WORKING-STORAGE SECTION.
       01  WS-EOF PIC X VALUE "N".
       PROCEDURE DIVISION.
           OPEN INPUT IN-F OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = "Y"
               READ IN-F AT END MOVE "Y" TO WS-EOF NOT AT END
{long_if}
               WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           STOP RUN.
""")
    (tmp_path / "in.txt").write_text("A123456789\nT123456789\n")
    work = tmp_path / "work"
    work.mkdir()
    run = run_cobol(source, tmp_path, {"input": "INDD", "output": "OUTDD"}, tmp_path / "in.txt", work)
    assert run.compiled, run.stderr
    assert [r.rstrip() for r in run.output_lines] == ["ACCEPTED", "REJECTED"]


def test_free_main_links_a_fixed_module_and_the_fixed_cee3abd_stand_in(tmp_path):
    import shutil

    import pytest

    from diocle_verifier.runners import build_cobol
    if not shutil.which("cobc"):
        pytest.skip("GnuCOBOL not installed")
    (tmp_path / "MAINF.cbl").write_text(""">>SOURCE FORMAT FREE
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINF.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-N PIC S9(9) COMP-5 VALUE 16.
       PROCEDURE DIVISION.
           CALL "SUBF"
           IF WS-N = 0 CALL "CEE3ABD" USING WS-N WS-N END-CALL END-IF
           DISPLAY "MAIN DONE" STOP RUN.
""")
    fixed = ["000100 IDENTIFICATION DIVISION.", "000200 PROGRAM-ID. SUBF.", "000300* a fixed-format comment line",
             "000400 PROCEDURE DIVISION.", '000500     DISPLAY "SUB RAN" GOBACK.']
    (tmp_path / "SUBF.cbl").write_text("".join(line.ljust(72) + f"SUBF{i:04d}\n" for i, line in enumerate(fixed, 1)))
    work = tmp_path / "work"
    work.mkdir()
    cmd, failed = build_cobol(tmp_path / "MAINF.cbl", tmp_path, work, modules=[tmp_path / "SUBF.cbl"])
    assert cmd is not None, failed.stderr
    from diocle_verifier.runners import _exec
    assert _exec(cmd).stdout.split() == ["SUB", "RAN", "MAIN", "DONE"]


def test_hyphenated_assign_names_open_the_whole_dd_name(tmp_path):
    import shutil

    import pytest

    from diocle_verifier.runners import assign_flags, run_cobol
    if not shutil.which("cobc"):
        pytest.skip("GnuCOBOL not installed")
    source = tmp_path / "HYPH.cbl"
    source.write_text("""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HYPH.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO INPUT-FILE
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO OUTPUT-FILE
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC PIC X(4).
       FD  OUT-F.
       01  OUT-REC PIC X(4).
       WORKING-STORAGE SECTION.
       01  WS-EOF PIC X VALUE "N".
       PROCEDURE DIVISION.
           OPEN INPUT IN-F OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = "Y"
               READ IN-F AT END MOVE "Y" TO WS-EOF
               NOT AT END MOVE IN-REC TO OUT-REC WRITE OUT-REC END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           STOP RUN.
""")
    assert assign_flags(source) and not assign_flags(tmp_path / "missing.cbl")
    (tmp_path / "in.txt").write_text("AAAA\nBBBB\n")
    work = tmp_path / "work"
    work.mkdir()
    run = run_cobol(source, tmp_path, {"input": "INPUT-FILE", "output": "OUTPUT-FILE"}, tmp_path / "in.txt", work)
    assert run.compiled and run.exit_code == 0, run.stdout + run.stderr  # -std=ibm alone opens DD "FILE" for both
    assert run.output_lines == ["AAAA", "BBBB"]
    plain = tmp_path / "PLAIN.cbl"
    plain.write_text(source.read_text().replace("INPUT-FILE", "INFILE").replace("OUTPUT-FILE", "OUTFILE"))
    assert assign_flags(plain) == []
