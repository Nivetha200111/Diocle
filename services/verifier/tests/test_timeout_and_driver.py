"""Plain messages for the two ways verification cannot even start: the original never ends, or the SQLite JDBC driver is
missing. Neither may look like a pass or like '0 of 0 cases', and neither may leak a raw TimeoutExpired."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from diocle_verifier import reverify, sqlrun
from diocle_verifier.runners import ProgramTimeout, VerifierUnavailable, _run_program, build_cobol, run_files
from diocle_verifier.verify import verify_sample

SQL_SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "db2-account-report"
LOOP = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. SPIN.
       PROCEDURE DIVISION.
           PERFORM UNTIL 1 = 2
               CONTINUE
           END-PERFORM.
           STOP RUN.
"""


def test_original_timeout_message_is_a_sentence(tmp_path):
    inp = tmp_path / "in.dat"
    inp.write_text("")
    with pytest.raises(ProgramTimeout) as e:
        _run_program([sys.executable, "-c", "import time; time.sleep(30)"], {"input": "IN", "output": "OUT"}, inp, tmp_path,
                     "original", timeout=1)
    assert str(e.value) == "the original program did not terminate within 1 seconds, so there is nothing to compare against"
    assert "Command" not in str(e.value) and "TimeoutExpired" not in str(e.value)
    assert isinstance(e.value, subprocess.TimeoutExpired)  # callers that tolerate a timeout (mutation testing) still do


def test_converted_timeout_names_the_java(tmp_path):
    with pytest.raises(ProgramTimeout) as e:
        run_files([sys.executable, "-c", "import time; time.sleep(30)"], {}, {}, tmp_path, "converted", timeout=1)
    assert "converted Java did not terminate within 1 seconds" in str(e.value)


@pytest.mark.toolchain
@pytest.mark.skipif(shutil.which("cobc") is None, reason="needs GnuCOBOL")
def test_real_infinite_loop_original_is_reported_plainly(tmp_path):
    src = tmp_path / "spin.cbl"
    src.write_text(LOOP)
    cmd, failure = build_cobol(src, tmp_path, tmp_path)
    assert cmd and failure is None
    with pytest.raises(ProgramTimeout, match="the original program did not terminate within 2 seconds"):
        run_files(cmd, {}, {}, tmp_path, "original", timeout=2)


def test_missing_jdbc_driver_is_an_error_not_a_zero_case_result(monkeypatch):
    monkeypatch.setattr(sqlrun, "jdbc_jar", lambda: None)
    with pytest.raises(VerifierUnavailable) as e:
        verify_sample(SQL_SAMPLE, seed=1, random_count=2)
    assert "SQLite JDBC driver is not installed" in str(e.value) and "scripts/fetch-sqlite-jdbc.sh" in str(e.value)


def test_reverify_records_a_timeout_as_not_ok(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise ProgramTimeout("original", ["x"], 7)

    monkeypatch.setattr(reverify, "check_certificate", lambda *a, **k: None)
    monkeypatch.setattr(reverify, "fetch_legacy", lambda *a, **k: tmp_path)
    monkeypatch.setattr(reverify, "build_sample", lambda *a, **k: tmp_path)
    monkeypatch.setattr(reverify, "verify_sample", boom)
    prog = tmp_path / "progs" / "P1"
    prog.mkdir(parents=True)
    (prog / "certificate.json").write_text('{"program": "P1", "legacy": {"repository": "r", "commit": "c"}}')
    [r] = reverify.reverify(tmp_path / "progs", 1, 1)
    assert r["ok"] is False and r["total"] == 0 and "did not terminate within 7 seconds" in r["buildError"]
