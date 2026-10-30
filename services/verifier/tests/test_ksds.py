"""Keyed (INDEXED) files: DioKsds against GnuCOBOL's real indexed-file handler, seeding, and the two sides compared.

GnuCOBOL (with its Berkeley DB indexed handler), javac and the verifier are real here; the Java next to the COBOL is a
hand-written fixture (a test double for a model's output), and the deliberately wrong variants prove the keyed-file
comparison catches errors. Tests skip when this machine's cobc has no indexed-file handler."""

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_verifier import ksds, sandbox
from diocle_verifier.verify import passes, validate_report, verify_sample

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "vsam-customer-update"
PROBE = Path(__file__).resolve().parent / "ksds"
SUPPORT = Path(ksds.__file__).resolve().parent / "dbsupport"
needs_engine = pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac") and ksds.indexed_handler()),
                                  reason="needs GnuCOBOL with an indexed-file handler (cobc --info) and a JDK")
META = json.loads((SAMPLE / "sample.json").read_text())


# --- DioKsds against the real handler ---------------------------------------------------------------------------

_EXE: dict = {}


def _probe_cobol(mode: str, colseq: bool) -> Path:
    if (mode, colseq) not in _EXE:
        d = Path(tempfile.mkdtemp(prefix="ksds-probe-"))
        text = (PROBE / "probe.cob.tmpl").read_text().replace("@MODE@", mode)
        if mode == "RANDOM":  # these statements do not compile in RANDOM access
            for code in ("RN", "S1", "S2", "S3"):
                text = re.sub(r"             WHEN '%s'\n(?:               .*\n)+" % code, "", text)
        (d / "p.cob").write_text(text)
        cmd = ["cobc", "-x", "-std=ibm", "-fbinary-truncate", "-fpretty-display"] + (["-fdefault-colseq=EBCDIC"] if colseq else [])
        subprocess.run([*cmd, "-o", str(d / "p"), str(d / "p.cob")], check=True, capture_output=True)
        _EXE[(mode, colseq)] = d / "p"
    return _EXE[(mode, colseq)]


@pytest.fixture(scope="module")
def probe_classes(tmp_path_factory):
    out = tmp_path_factory.mktemp("probe-classes")
    subprocess.run(["javac", "-d", str(out), str(SUPPORT / "DioKsds.java"), str(PROBE / "KsdsProbe.java")], check=True, capture_output=True)
    return out


def _line(op, mode="", key="", data=""):
    return f"{op:<2}{mode:<2}{key:<4}{data:<6}"


KEYS = ["A001", "b001", "1001", " 001", "B002", "a002", "Z999"]


def _ops(rng: random.Random, access: str, n: int) -> list[tuple]:
    ops = []
    for _ in range(n):
        r, k = rng.random(), rng.choice(KEYS)
        d = "".join(rng.choice("abcdefgh") for _ in range(6))
        if r < 0.07:
            ops.append(("OP", rng.choice(["IN", "OU", "IO", "IO", "OU"])))
        elif r < 0.12:
            ops.append(("CL",))
        elif r < 0.35:
            ops.append(("WR", "", k, d))
        elif r < 0.45:
            ops.append(("RW", "", k, d))
        elif r < 0.55:
            ops.append(("DL", "", k))
        elif r < 0.70 or access == "RANDOM":
            ops.append(("RK", "", k))
        elif r < 0.85:
            ops.append(("RN",))
        else:
            ops.append((rng.choice(["S1", "S2", "S3"]), "", k))
    return ops


def _conformance(access: str, colseq: bool, probe_classes, count: int, base: int):
    exe = _probe_cobol(access, colseq)
    bad = []
    for i in range(count):
        ops = _ops(random.Random(base + i), access, 60)
        if i % 2 == 0:  # most sequences start from an existing file
            ops = [("OP", "OU"), ("WR", "", "A001", "seed01"), ("WR", "", "b001", "seed02"), ("WR", "", "1001", "seed03"),
                   ("CL",), ("OP", "IO" if i % 4 == 0 else "IN")] + ops
        d = Path(tempfile.mkdtemp(prefix="ksds-fuzz-"))
        (d / "ops.txt").write_text("\n".join(_line(*o) for o in ops) + "\n")
        env = dict(os.environ, DD_KFILE=str(d / "kf.dat"), DD_OPSIN=str(d / "ops.txt"))
        cobol = subprocess.run([str(exe)], env=env, capture_output=True, text=True, cwd=d).stdout.splitlines()
        jenv = dict(os.environ, DD_KFILE=str(d / "kf.raw"))
        java = subprocess.run(["java", "-cp", str(probe_classes), "KsdsProbe", access, str(d / "ops.txt")], env=jenv,
                              capture_output=True, text=True, cwd=d)
        assert java.returncode == 0, java.stderr[:300]
        out = java.stdout.splitlines()
        if out and out[-1] == "KEYCHANGE":  # a sequential REWRITE that changes the key is outside the subset (DioKsds throws)
            out.pop()
            cobol = cobol[: len(out)]
        if cobol != out:
            j = next((k for k, (x, y) in enumerate(zip(cobol, out)) if x != y), min(len(cobol), len(out)))
            bad.append((access, i, j, ops[j] if j < len(ops) else None, cobol[j:j + 1], out[j:j + 1]))
        shutil.rmtree(d, ignore_errors=True)
    assert not bad, bad[:3]


@needs_engine
@pytest.mark.parametrize("access", ["SEQUENTIAL", "RANDOM", "DYNAMIC"])
def test_dioksds_matches_the_real_handler_on_random_operation_sequences(access, probe_classes):
    """Statuses and records of every OPEN/CLOSE/WRITE/REWRITE/DELETE/READ/READ NEXT/START, including misuse, agree."""
    _conformance(access, False, probe_classes, 40, 1000)


@needs_engine
def test_key_order_is_bytewise_even_with_the_ebcdic_collating_sequence(probe_classes):
    """The verifier compiles with -fdefault-colseq=EBCDIC for mainframe programs. GnuCOBOL's indexed handler still orders
    keys by raw bytes, so DioKsds (byte order) agrees with it under that flag too, for START and READ NEXT."""
    _conformance("DYNAMIC", True, probe_classes, 40, 9000)
    exe = _probe_cobol("DYNAMIC", True)
    d = Path(tempfile.mkdtemp(prefix="ksds-order-"))
    ops = [("OP", "OU")] + [("WR", "", k, "x") for k in ("A001", "b001", "1001", " 001", "B002")] + [("CL",), ("OP", "IN")] + [("RN",)] * 5
    (d / "ops.txt").write_text("\n".join(_line(*o) for o in ops) + "\n")
    out = subprocess.run([str(exe)], env=dict(os.environ, DD_KFILE=str(d / "k"), DD_OPSIN=str(d / "ops.txt")), capture_output=True,
                         text=True, cwd=d).stdout
    keys = [l.split("XX")[1][:4] for l in out.splitlines() if l.startswith("RN 00")]
    assert keys == sorted(keys) == [" 001", "1001", "A001", "B002", "b001"]  # not the EBCDIC order (blank, lower, upper, digits)


# --- seeding and the canonical dump -----------------------------------------------------------------------------

def test_seeding_is_deterministic_sorted_unique_with_boundary_and_order_sensitive_keys():
    a, b = ksds.plan_seeds(META, 5, 200), ksds.plan_seeds(META, 5, 200)
    assert a.seeds == b.seeds and a.hits == b.hits and a.misses == b.misses
    assert ksds.plan_seeds(META, 6, 200).seeds != a.seeds
    recs = a.seeds["CUSTMAST"]
    keys = [r[2:8] for r in recs]
    assert keys == sorted(keys) and len(set(keys)) == len(keys) and all(len(r) == 38 for r in recs)
    assert "999999" in keys and "      " in keys  # boundary keys
    assert not set(keys) & set(a.misses["CUSTMAST"]) and a.misses["CUSTMAST"]
    assert keys != sorted(keys, key=lambda k: k.encode("cp037"))  # ASCII and EBCDIC order disagree on these keys


@needs_engine
def test_canonical_dump_round_trips_through_the_real_indexed_file(tmp_path):
    plan = ksds.plan_seeds(META, 7, 120)
    tools, err = ksds._build_tools(plan, tmp_path)
    assert err is None
    seq, kf, back = tmp_path / "s.raw", tmp_path / "k.dat", tmp_path / "b.raw"
    seq.write_bytes("".join(plan.seeds["CUSTMAST"]).encode("latin-1"))
    assert ksds._tool_run(tools["CUSTMAST"]["load"], seq, kf, tmp_path) is None
    assert ksds._tool_run(tools["CUSTMAST"]["dump"], back, kf, tmp_path) is None
    assert back.read_bytes() == seq.read_bytes()


# --- the sample and the deliberately wrong variants -------------------------------------------------------------

def java_with(tmp_path, edit):
    java = tmp_path / "java"
    shutil.copytree(SAMPLE / "java-conversion", java)
    src = (java / "Custupd.java").read_text()
    new = edit(src)
    assert new != src
    (java / "Custupd.java").write_text(new)
    return java


@needs_engine
def test_sample_certifies_and_reports_the_keyed_file():
    report = verify_sample(SAMPLE, seed=11, random_count=200)
    validate_report(report)
    assert passes(report), [r for r in report["results"] if not r["match"]][:2]
    k = report["runs"]["keyed"]
    assert k["engine"] == "gnucobol-indexed" and k["subset"] == "ksds-subset-1" and "BDB" in k["engineVersion"]
    f = k["files"][0]
    assert f["dd"] == "CUSTMAST" and f["match"] and f["recordsOriginal"] == f["recordsConverted"] and f["recordsSeeded"] >= 12
    assert f["changedFromSeed"] == {"original": True, "converted": True}
    assert any(r["inputId"] == "keyed:CUSTMAST" and r["inputSource"] == "keyed" for r in report["results"])
    reasons = {r["originalOutput"][13:25].strip() for r in report["results"] if r["inputSource"] == "files"}
    assert {"DUPLICATE", "NOT FOUND"} <= reasons  # the generated transactions hit and miss the seeded keys


@needs_engine
@pytest.mark.parametrize("name, edit", [
    ("off-by-one START (> for >=)", lambda s: s.replace('cust.start(">=", "999999")', 'cust.start(">", "999999")')),
    ("missing REWRITE", lambda s: s.replace('cust.rewrite(r.substring(0, 8) + name + display(balance) + "C");', "")),
    ("wrong FILE STATUS in a reject", lambda s: s.replace('reject(rej, id, code, "NOT FOUND   ", cust.status());\n                    } else if',
                                                          'reject(rej, id, code, "NOT FOUND   ", "21");\n                    } else if', 1)),
    ("DELETE that removes nothing", lambda s: s.replace("cust.delete(id);", "cust.read(id);")),
])
def test_wrong_java_is_caught_by_the_keyed_file_diff_or_the_outputs(tmp_path, name, edit):
    report = verify_sample(SAMPLE, java_dir=java_with(tmp_path, edit), seed=11, random_count=200)
    assert not passes(report), name
    if name in ("missing REWRITE", "DELETE that removes nothing"):  # START and the reject text show only in the reject report
        keyed = [r for r in report["results"] if r["inputSource"] == "keyed" and not r["match"]]
        assert keyed and "keyed file CUSTMAST" in keyed[0]["diff"], name
        assert report["runs"]["keyed"]["files"][0]["firstMismatch"]["key"]


@needs_engine
@pytest.mark.parametrize("snippet", [
    'Files.write(Path.of(System.getenv("DD_CUSTMAST")), new byte[0]);',
    'Files.walk(Path.of("/tmp/diocle-verify-x/ksds-tools"));',
    'Files.copy(Path.of("../CUSTMAST.kf"), Path.of("x"));',
    'Class.forName("java.lang.Runtime");',
])
def test_java_that_reaches_the_keyed_files_outside_dioksds_is_refused_before_it_runs(tmp_path, snippet):
    java = java_with(tmp_path, lambda s: s.replace("cust.open(\"I-O\");", snippet + "\n        cust.open(\"I-O\");", 1))
    report = verify_sample(SAMPLE, java_dir=java, seed=3, random_count=30)
    assert not report["runs"]["converted"]["compiled"] and "refused before running" in report["runs"]["converted"]["stderr"]
    assert not passes(report)


@needs_engine
def test_the_conversion_cannot_replace_dioksds(tmp_path):
    java = java_with(tmp_path, lambda s: s + "\n// unchanged logic\n")
    (java / "DioKsds.java").write_text("public final class DioKsds { public static DioKsds select(String a, int b, int c, int d, String e) { return null; } }")
    assert passes(verify_sample(SAMPLE, java_dir=java, seed=3, random_count=40))  # the verifier's own copy was compiled over it


@needs_engine
def test_java_that_overwrites_a_seed_the_original_reads_fails_closed(tmp_path):
    """A file the original will read is rewritten by the Java through a path no static check could name: caught by the hashes."""
    java = java_with(tmp_path, lambda s: s.replace(
        'cust.open("I-O");',
        'try (var st = Files.walk(Path.of(System.getenv("DD_TRANIN")).getParent())) { '
        'for (var p : (Iterable<Path>) st.filter(x -> x.toString().endsWith(String.valueOf((char) 107) + "seed"))::iterator) Files.write(p, new byte[0]); } '
        'cust.open("I-O");', 1))
    report = verify_sample(SAMPLE, java_dir=java, seed=3, random_count=40)
    assert not passes(report)
    assert report["runs"]["converted"]["compiled"] and "fails closed" in report["runs"]["original"]["stderr"]
    assert "changed" in report["runs"]["original"]["stderr"]


@needs_engine
def test_a_java_that_applies_nothing_is_not_certified(tmp_path):
    """The Java reads no transactions: the original changed the keyed file, the Java did not."""
    java = java_with(tmp_path, lambda s: s.replace('lines = Files.readAllLines(Path.of(System.getenv("DD_TRANIN")), StandardCharsets.ISO_8859_1)',
                                                    'lines = new java.util.ArrayList<String>()'))
    report = verify_sample(SAMPLE, java_dir=java, seed=3, random_count=40)
    assert not passes(report)
    assert any(r["inputSource"] == "keyed" and not r["match"] for r in report["results"])


@needs_engine
def test_sandbox_path_equals_local_path(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
        remote = verify_sample(SAMPLE, seed=9, random_count=60)
        monkeypatch.delenv("DIOCLE_SANDBOX_URL")
        local = verify_sample(SAMPLE, seed=9, random_count=60)
    finally:
        httpd.shutdown()
    assert remote["summary"] == local["summary"] and passes(remote)
    assert remote["runs"]["keyed"]["files"] == local["runs"]["keyed"]["files"]


@needs_engine
def test_nothing_is_left_in_the_temp_dir():
    before = set(Path(tempfile.gettempdir()).glob("diocle-verify-*"))
    verify_sample(SAMPLE, seed=2, random_count=30)
    assert set(Path(tempfile.gettempdir()).glob("diocle-verify-*")) == before


# --- the contract -----------------------------------------------------------------------------------------------

def test_contract_old_valid_and_invalid_keyed_blocks():
    old = {"version": "0.9", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}
    validate_report(old)  # reports without runs.keyed stay valid
    good = {"version": "0.10", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0},
            "runs": {"keyed": {"engine": "gnucobol-indexed", "engineVersion": "x", "subset": "ksds-subset-1", "seededFrom": "y",
                               "files": [{"dd": "K", "recordsSeeded": 1, "recordsOriginal": 1, "recordsConverted": 1, "match": True}]}}}
    validate_report(good)
    bad = json.loads(json.dumps(good))
    del bad["runs"]["keyed"]["files"][0]["recordsConverted"]
    with pytest.raises(Exception):
        validate_report(bad)
    bad2 = json.loads(json.dumps(good))
    bad2["runs"]["keyed"].pop("subset")
    with pytest.raises(Exception):
        validate_report(bad2)
