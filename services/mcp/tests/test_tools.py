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
