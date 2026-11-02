import asyncio
from pathlib import Path

from diocle_mcp import server

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
REFERENCE = ROOT / "services" / "verifier" / "tests" / "fixtures" / "reference"


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"analyze_cobol", "verify_conversion", "certify_conversion", "cobol_lessons"}


def test_analyze_and_verify_bring_your_own_java():
    analysis = server.analyze_cobol(str(SAMPLE))
    [program] = analysis["programs"]
    assert program["name"] == "INTACCR" and program["verifiable"]
    assert any(f["category"] == "rounding" for f in analysis["findings"])
    naive = server.verify_conversion(str(SAMPLE), "INTACCR", str(SAMPLE / "java-conversion"), main_class="IntAccr", cases=50)
    assert not naive["allMatch"] and naive["mismatchedFields"] and naive["examples"]
    cert = server.certify_conversion(str(SAMPLE), "INTACCR", str(REFERENCE), main_class="IntAccr")
    assert cert["certified"] and cert["total"] >= 1000 and cert["seed"] >= 10**6


def _report(original: dict, converted: dict, **runs) -> dict:
    return {"results": [], "summary": {"total": 0, "passed": 0, "failed": 0},
            "runs": {"original": {"stdout": "", **original}, "converted": {"stdout": "", **converted},
                     "stdoutMatch": True, "exitCodeMatch": False, **runs}}


def test_tampering_is_the_javas_fault_not_a_build_error_or_crash_of_the_original():
    sentence = "the original was not built or run; verification fails closed: the converted program created planted.out"
    out = server._summary(_report({"compiled": None, "exitCode": None, "stderr": sentence},
                                  {"compiled": True, "exitCode": 0, "stderr": ""},
                                  tampering=["the converted program created planted.out"]))
    assert out["tampering"] == ["the converted program created planted.out"]
    assert out["buildErrors"] is None and out["crashes"] is None and out["allMatch"] is False


def test_an_original_that_does_not_compile_is_still_a_build_error():
    out = server._summary(_report({"compiled": False, "exitCode": 1, "stderr": "syntax error"},
                                  {"compiled": True, "exitCode": 0, "stderr": ""}))
    assert out["buildErrors"] == {"original": "syntax error"} and out["tampering"] is None and out["crashes"]


def test_paths_outside_the_allowed_roots_are_refused(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("DIOCLE_MCP_ROOTS", str(ROOT / "samples"))
    with pytest.raises(PermissionError):
        server.analyze_cobol(str(tmp_path))
    with pytest.raises(PermissionError):
        server.verify_conversion(str(SAMPLE), "INTACCR", str(tmp_path), main_class="IntAccr", cases=1)
