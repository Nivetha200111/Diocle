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
