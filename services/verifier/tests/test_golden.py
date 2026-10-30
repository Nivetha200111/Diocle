"""Golden replay: captured mainframe output is the oracle on its inputs, and GnuCOBOL drift is reported."""
import json
import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

from diocle_verifier.codec import convert_record
from diocle_verifier.layout import format_record, load_fields, parse_record, record_length
from diocle_verifier.verify import passes, verify_sample


def _tool_env(**extra):
    """A small environment for running the compiled programs, but with the toolchain's own PATH, library path and JAVA_HOME
    (a bare PATH=/usr/bin picks the runner's old system Java and cannot find libcob outside the system library path)."""
    keep = {k: os.environ[k] for k in ("PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "JAVA_HOME") if k in os.environ}
    return {**keep, **extra}

ROOT = Path(__file__).resolve().parents[3]
PACKED = ROOT / "samples" / "packed-posting"
REFERENCE = Path(__file__).parent / "fixtures" / "reference"


def _golden_sample(tmp: Path, tamper: bool) -> Path:
    sample = tmp / "packed"
    shutil.copytree(PACKED, sample)
    meta = json.loads((sample / "sample.json").read_text())
    in_f, out_f = load_fields(meta["layouts"]["input"]), load_fields(meta["layouts"]["output"])
    rows = [{"PK-ACCT": f"G{i}", "PK-BAL": Decimal(b), "PK-RATE": Decimal("0.0425"), "PK-DAYS": Decimal(d),
             "PK-ADJ": Decimal(a), "PK-LIMIT": Decimal(50000), "PK-ITEMS": Decimal(3)}
            for i, (b, d, a) in enumerate([("1000.00", 30, "-1.50"), ("-250.75", 31, "0.00"), ("99999.99", -7, "12.34")])]
    records = [format_record(r, in_f) for r in rows]
    # "Mainframe" outputs: produced here by GnuCOBOL, as a stand-in for captures from a real z/OS run.
    exe = tmp / "pkdpost"
    subprocess.run(["cobc", "-x", "-std=ibm", "-I", str(sample / "copybooks"), "-o", str(exe),
                    str(sample / "src" / "PKDPOST.cbl")], check=True, capture_output=True)
    (tmp / "in.dat").write_bytes("".join(records).encode("latin-1"))
    subprocess.run([str(exe)], env=_tool_env(DD_PKIN=str(tmp / "in.dat"), DD_PKOUT=str(tmp / "out.dat")),
                   check=True, capture_output=True)
    out = (tmp / "out.dat").read_bytes()
    n = record_length(out_f)
    outputs = [out[i : i + n] for i in range(0, len(out), n)]
    if tamper:  # the mainframe rounded record 2's interest differently (e.g. ARITH intermediate precision)
        values = parse_record(outputs[1].decode("latin-1"), out_f)
        values["PO-INT"] += Decimal("0.01")
        outputs[1] = format_record(values, out_f).encode("latin-1")
    golden = sample / "golden"
    shutil.rmtree(golden, ignore_errors=True)  # replace the sample's demo set with this test's own
    golden.mkdir()
    (golden / "input.ebcdic").write_bytes(b"".join(convert_record(r.encode("latin-1"), in_f, to_mainframe=True) for r in records))
    (golden / "expected.ebcdic").write_bytes(b"".join(convert_record(o, out_f, to_mainframe=True) for o in outputs))
    meta["golden"] = {"dir": "golden", "input": "input.ebcdic", "expected": "expected.ebcdic", "codepage": "cp037",
                      "source": "test stand-in for a mainframe capture"}
    (sample / "sample.json").write_text(json.dumps(meta))
    return sample


def test_golden_replay_passes_when_java_matches_the_mainframe(tmp_path):
    report = verify_sample(_golden_sample(tmp_path, tamper=False), REFERENCE, random_count=20)
    golden = [r for r in report["results"] if r["inputSource"] == "golden"]
    assert len(golden) == 3 and all(r["oracle"] == "mainframe" and r["match"] for r in golden)
    assert report["runs"]["golden"]["oracleAgreement"] == 3 and passes(report)


def test_the_mainframe_wins_when_gnucobol_drifts(tmp_path):
    report = verify_sample(_golden_sample(tmp_path, tamper=True), REFERENCE, random_count=20)
    failing = [r for r in report["results"] if not r["match"]]
    assert [r["inputId"] for r in failing] == ["golden-0002"] and "PO-INT" in failing[0]["diff"]
    assert report["runs"]["golden"]["oracleAgreement"] == 2
    assert report["runs"]["golden"]["oracleDisagreements"][0]["inputId"] == "golden-0002"
    assert not passes(report)  # Java that matches GnuCOBOL but not the mainframe is not certified


def test_golden_files_that_do_not_line_up_fail_loudly(tmp_path):
    sample = _golden_sample(tmp_path, tamper=False)
    expected = sample / "golden" / "expected.ebcdic"
    expected.write_bytes(expected.read_bytes()[:-42])  # one captured output record missing
    report = verify_sample(sample, REFERENCE, random_count=10)
    golden = [r for r in report["results"] if r["inputSource"] == "golden"]
    assert golden and all(not r["match"] and "one output record per input" in r["diff"] for r in golden)
    assert report["runs"]["golden"]["aligned"] is False and not passes(report)
