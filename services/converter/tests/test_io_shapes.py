"""What the translator is told about files for DISPLAY-only programs and files opened I-O (no model calls)."""
from pathlib import Path

from diocle_converter.prompts import TRANSLATOR
from diocle_converter.repair import summarize_report
from diocle_converter.sources import Program

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def test_existing_shape_keeps_its_exact_wording():
    assert Program.load(SAMPLES / "interest-accrual").io_text() == (
        "Input file paths come from environment variables DD_ACCTIN; write the outputs to DD_INTOUT.")


def test_io_file_is_described_as_update_in_place():
    program = Program.load(SAMPLES / "ledger-rewrite")
    assert program.files == [{"dd": "ACCTMST", "direction": "io"}]
    text = program.io_text()
    assert "DD_ACCTMST names a file the COBOL opens I-O" in text and "write the result back to the same path" in text
    assert "write the outputs to" not in text and "stdout" not in text


def test_display_only_program_is_told_stdout_and_exit_code_are_the_result():
    text = Program.load(SAMPLES / "display-report").io_text()
    assert text.startswith("Input file paths come from environment variables DD_TXNIN.")
    assert "writes no file" in text and "RETURN-CODE" in text and "compared byte for byte" in text


def test_called_module_through_call_identifier_is_translated_with_the_program():
    program = Program.load(SAMPLES / "call-identifier")
    assert list(program.modules) == ["FEECALC.cbl"] and "CALL WS-FEE-PGM" in program.cobol
    assert "FEECALC.cbl" in program.as_text()


def test_the_prompt_template_formats_for_every_shape():
    for sample in ("ledger-rewrite", "display-report", "call-identifier"):
        program = Program.load(SAMPLES / sample)
        TRANSLATOR.format(io=program.io_text(), main_class=program.main_class)


def test_stdout_result_is_summarised_for_the_repair_agent():
    report = {"runs": {"original": {"compiled": True, "exitCode": 4, "stdout": "A\nB\n", "stderr": ""},
                       "converted": {"compiled": True, "exitCode": 4, "stdout": "A\nC\n", "stderr": ""},
                       "stdoutMatch": False, "exitCodeMatch": True},
              "results": [{"program": "P", "inputId": "stdout", "inputSource": "stdout", "outputDd": "stdout", "match": False,
                           "fieldDiffs": [], "diff": "stdout line 2: original 'B' converted 'C'"}],
              "summary": {"total": 1, "passed": 0, "failed": 1}}
    text = summarize_report(report)
    assert "stdout line 2: original 'B' converted 'C'" in text and "stdout original : A" in text
