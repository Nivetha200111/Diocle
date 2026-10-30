"""Regression tests for the reviewer's findings on the printout intake (scripted model; real cobc where marked)."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from diocle_converter.vision import MAX_IMAGE_BYTES, ImageRejected, compile_check, differential, load_image, transcribe, unsafe_calls
from test_vision import COBOL, LOYALTY, OK, PNG, needs_cobc, setup, valid


def orig_copy(tmp_path):
    dest = tmp_path / "orig"
    shutil.copytree(LOYALTY, dest)
    return dest


@needs_cobc
def test_out_equal_to_against_is_refused_and_original_untouched(tmp_path):
    """Regression: --out == --against used to overwrite the original and compare the transcription with itself."""
    orig = orig_copy(tmp_path)
    before = (orig / "src" / "LOYWAIVE.cbl").read_text()
    bad = before.replace("MOVE 4.50 TO LO-FEE", "MOVE 4.05 TO LO-FEE")
    img, settings, client, sdk = setup(tmp_path, [f"```cobol\n{bad}```"])
    for out in (orig, orig / "src", tmp_path):  # same, inside, containing
        record = transcribe(img, out, settings=settings, client=client, against=orig, log=lambda m: None)
        assert record["status"] == "refused" and "overlaps" in record["reason"]
    assert sdk.requests == [] and (orig / "src" / "LOYWAIVE.cbl").read_text() == before
    assert not (orig / "transcription.json").exists()


def test_non_empty_out_is_never_overwritten(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL])
    out = tmp_path / "out"
    (out / "src").mkdir(parents=True)
    (out / "src" / "DEMO.cbl").write_text("keep me")
    record = transcribe(img, out, settings=settings, client=client, check=OK, log=lambda m: None)
    assert record["status"] == "refused" and "not an empty directory" in record["reason"] and sdk.requests == []
    assert (out / "src" / "DEMO.cbl").read_text() == "keep me" and not (out / "transcription.json").exists()


@needs_cobc
def test_original_is_snapshotted_before_anything_is_written(tmp_path):
    orig = orig_copy(tmp_path)
    seen = {}

    def spy(against, src, **k):
        seen["against"] = against
        return differential(against, src, random_count=50)

    text = (orig / "src" / "LOYWAIVE.cbl").read_text()
    img, settings, client, _ = setup(tmp_path, [f"```cobol\n{text}```"])
    record = transcribe(img, tmp_path / "new", settings=settings, client=client, against=orig, run_model_code=True, diff=spy, log=lambda m: None)
    assert seen["against"] != orig and record["differential"]["against"] == str(orig)
    assert record["status"] == "verified-identical"


@pytest.mark.parametrize("line", [
    "           CALL 'SYSTEM' USING WS-CMD",
    '           CALL "system" USING WS-CMD',
    "           CALL 'CBL_DELETE_FILE' USING WS-F",
    "           CALL WS-PROG",
    "           CALL 'OTHERPGM'",
    "           CALL 'C$SLEEP' USING 1",
])
def test_dangerous_calls_are_refused_not_compiled_not_written(tmp_path, line):
    img, settings, client, sdk = setup(tmp_path, [f"```cobol\n       PROGRAM-ID. EVIL.\n{line}\n```"])
    called = []
    record = transcribe(img, tmp_path / "out", settings=settings, client=client,
                        check=lambda s, c: called.append(1) or OK(s, c), log=lambda m: None)
    assert record["status"] == "refused" and called == [] and record["source"] is None
    assert not (tmp_path / "out" / "src").exists()
    valid(record)


def test_calls_in_comments_and_listed_modules_are_allowed():
    assert unsafe_calls("      * CALL 'SYSTEM' is mentioned in a comment\n           STOP RUN.\n") is None
    assert unsafe_calls("           CALL 'SUBPGM' USING X\n", {"SUBPGM"}) is None


@needs_cobc
def test_vacuous_pass_is_not_verified(tmp_path):
    """Both sides write nothing: that proves nothing and must not say verified-identical."""
    orig = orig_copy(tmp_path)
    quiet = (orig / "src" / "LOYWAIVE.cbl").read_text().replace("WRITE LO-REC.", "CONTINUE.")
    assert "CONTINUE." in quiet
    (orig / "src" / "LOYWAIVE.cbl").write_text(quiet)
    img, settings, client, _ = setup(tmp_path, [f"```cobol\n{quiet}```"])
    record = transcribe(img, tmp_path / "new", settings=settings, client=client, against=orig, run_model_code=True, log=lambda m: None)
    assert record["status"] == "compiled-unchecked" and "nothing to compare" in record["reason"]
    assert record["differential"]["ran"] is False
    valid(record)


@needs_cobc
def test_infinite_loop_times_out_and_is_reported(tmp_path):
    orig = (LOYALTY / "src" / "LOYWAIVE.cbl").read_text()
    looping = orig.replace("           STOP RUN.",
                           "           PERFORM UNTIL 1 = 2\n               CONTINUE\n           END-PERFORM\n           STOP RUN.")
    assert looping != orig
    img, settings, client, _ = setup(tmp_path, [f"```cobol\n{looping}```"])
    record = transcribe(img, tmp_path / "new", settings=settings, client=client, against=LOYALTY, run_model_code=True, timeout=3,
                        log=lambda m: None)
    assert record["status"] == "compiled-unchecked" and record["differential"]["ran"] is False
    assert "timed out" in record["differential"]["reason"] and (tmp_path / "new" / "transcription.json").exists()
    valid(record)


def test_compile_timeout_is_a_failed_compile(tmp_path, monkeypatch):
    import diocle_verifier.runners as runners

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("cobc", 1)

    monkeypatch.setattr(runners, "_exec", hang)
    result = compile_check(tmp_path / "x.cbl", None, timeout=1)
    assert result["ok"] is False and "did not finish" in result["errors"]


def test_exit_codes_distinguish_every_status():
    from diocle_converter.__main__ import EXIT_CODES
    assert EXIT_CODES["verified-identical"] == 0
    others = [v for k, v in EXIT_CODES.items() if k != "verified-identical"]
    assert all(others) and len(set(others)) == len(others)


def test_image_that_grows_after_stat_is_rejected(tmp_path, monkeypatch):
    img = tmp_path / "a.png"
    img.write_bytes(PNG + b"\0" * (MAX_IMAGE_BYTES + 1))
    real_stat = Path.stat
    # Report a small size but keep every other field (is_file() calls stat() too, and which pathlib calls
    # stat() varies by Python version), so only the size check is fooled and the read-back check must catch it.
    def lying_stat(self, *a, **k):
        st = real_stat(self, *a, **k)
        if self != img:
            return st
        fields = {n: getattr(st, n) for n in dir(st) if n.startswith("st_")}
        fields["st_size"] = 10
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path, "stat", lying_stat)
    with pytest.raises(ImageRejected):
        load_image(img)
