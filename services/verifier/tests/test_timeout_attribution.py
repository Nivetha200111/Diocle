"""Who gets the blame when the Java runs past the limit. The Java runs first, so the original has not run yet at that point:
a faithful Java of a program that never ends also never ends, and only running the original tells the two apart. Every
verify path. Samples are synthetic copies with a loop added; the Java is hand-written, no model calls."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import test_jobs as job_helpers
from diocle_verifier import jobs, runners
from diocle_verifier.jobs import verify_job
from diocle_verifier.runners import ProgramTimeout
from diocle_verifier.verify import verify_sample

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
pytestmark = pytest.mark.skipif(shutil.which("cobc") is None or shutil.which("javac") is None, reason="needs GnuCOBOL and a JDK")
LOOP = "           PERFORM UNTIL 1 = 2\n               CONTINUE\n           END-PERFORM\n"
PATHS = ["addfee", "account-match", "display-report", "db2-account-report", "vsam-customer-update"]


@pytest.fixture
def short_limit(monkeypatch):
    real = runners._exec_side
    monkeypatch.setattr(runners, "_exec_side", lambda side, cmd, **k: real(side, cmd, **{**k, "timeout": 4}))


def _copy(tmp: Path, name: str, loop: bool) -> tuple[Path, dict]:
    sample = tmp / "sample"
    shutil.copytree(SAMPLES / name, sample)
    meta = json.loads((sample / "sample.json").read_text())
    if loop:
        source = sample / meta["source"]
        text = source.read_text()
        assert text.count("PROCEDURE DIVISION.\n") == 1
        source.write_text(text.replace("PROCEDURE DIVISION.\n", "PROCEDURE DIVISION.\n" + LOOP))
    return sample, meta


def _java(tmp: Path, main_class: str, body: str = "") -> Path:
    java = tmp / "java-loop"
    java.mkdir()
    (java / f"{main_class}.java").write_text(
        f"public class {main_class} {{ public static void main(String[] a) throws Exception {{ {body} while (true) {{ }} }} }}\n")
    return java


@pytest.mark.parametrize("name", PATHS)
def test_both_sides_looping_is_reported_as_the_original(name, tmp_path, short_limit):
    sample, meta = _copy(tmp_path, name, loop=True)
    with pytest.raises(ProgramTimeout) as e:
        verify_sample(sample, _java(tmp_path, meta["javaConversion"]["mainClass"]), seed=1, random_count=3)
    assert e.value.side == "original"
    assert str(e.value) == "the original program did not terminate within 4 seconds, so there is nothing to compare against"


@pytest.mark.parametrize("name", PATHS)
def test_a_java_that_loops_alone_is_still_the_javas_fault(name, tmp_path, short_limit):
    sample, meta = _copy(tmp_path, name, loop=False)
    with pytest.raises(ProgramTimeout) as e:
        verify_sample(sample, _java(tmp_path, meta["javaConversion"]["mainClass"]), seed=1, random_count=3)
    assert e.value.side == "converted"
    assert "converted Java did not terminate within 4 seconds" in str(e.value)


def test_a_java_that_tampers_then_loops_is_blamed_and_the_original_never_runs(tmp_path, short_limit, monkeypatch):
    """It changes the input the original would read, so it could otherwise make the original look like the one that hangs."""
    sample, meta = _copy(tmp_path, "addfee", loop=True)
    dd = meta["dd"]["input"]
    java = _java(tmp_path, meta["javaConversion"]["mainClass"],
                 f'java.nio.file.Files.writeString(java.nio.file.Path.of(System.getenv("DD_{dd}")), "x");')
    ran = []
    real = runners._exec_side
    monkeypatch.setattr(runners, "_exec_side", lambda side, cmd, **k: (ran.append(side), real(side, cmd, **k))[1])
    with pytest.raises(ProgramTimeout) as e:
        verify_sample(sample, java, seed=1, random_count=3)
    assert e.value.side == "converted" and ran == ["converted"]


def _job_run(tmp: Path, sample: Path, java_source: str):
    job = job_helpers._job()
    dd_paths = {"SORTIN": str(tmp / "SORTIN.seed"), "MSTIN": str(tmp / "MSTIN.seed"),
                "NEWMST": str(tmp / "NEWMST.out"), "EXCOUT": str(tmp / "EXCOUT.out")}
    pipeline = job_helpers._generate_pipeline(job, tmp / "job", dd_paths, java_source=java_source)
    return verify_job(sample, job, pipeline, seed=4242, random_count=3)


SPIN = "public class Acctmtch { public static void main(String[] a) { while (true) { } } }\n"


def test_a_job_with_both_sides_looping_is_reported_as_the_original(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUN_LIMIT", 6)
    sample, _ = _copy(tmp_path, "account-match", loop=True)
    with pytest.raises(ProgramTimeout) as e:
        _job_run(tmp_path, sample, SPIN)
    assert e.value.side == "original" and "did not terminate within 6 seconds" in str(e.value)


def test_a_job_whose_pipeline_loops_alone_stops_at_the_limit_and_is_the_javas_fault(tmp_path, monkeypatch):
    """The converted side had no limit at all: this hung for ever."""
    monkeypatch.setattr(jobs, "RUN_LIMIT", 6)
    sample, _ = _copy(tmp_path, "account-match", loop=False)
    with pytest.raises(ProgramTimeout) as e:
        _job_run(tmp_path, sample, SPIN)
    assert e.value.side == "converted" and "converted Java did not terminate within 6 seconds" in str(e.value)
