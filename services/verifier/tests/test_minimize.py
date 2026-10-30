"""Counterexample minimization (minimize.py): ddmin, field simplification, caps, schema, replay.

Unit tests use synthetic oracles (labelled test doubles: functions that decide "still failing" from the data).
The end-to-end tests run the real harness (GnuCOBOL + JDK) on samples/interest-accrual, whose naive translation
(samples/interest-accrual/java-conversion) really differs from the COBOL and whose reference translation
(tests/fixtures/reference) does not.
"""

import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from diocle_verifier import minimize as mz
from diocle_verifier.layout import load_fields, record_length
from diocle_verifier.__main__ import main as cli

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
NAIVE = SAMPLE / "java-conversion"
_REFERENCE_ALL = Path(__file__).parent / "fixtures" / "reference"
# only this program's reference Java: the folder also holds other programs' Java, which the static policy rightly
# refuses to run for interest-accrual's DD names
REFERENCE = Path(tempfile.mkdtemp(prefix="diocle-ref-"))
shutil.copy(_REFERENCE_ALL / "IntAccr.java", REFERENCE / "IntAccr.java")
toolchain = pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac")), reason="needs GnuCOBOL and a JDK")

LAYOUT = {"record": "R", "format": "line", "fields": [
    {"name": "ID", "kind": "alnum", "length": 6},
    {"name": "AMT", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "sign": "trailing"},
    {"name": "PK", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "usage": "packed"},
    {"name": "BODY", "kind": "alnum", "length": 8},
    {"name": "B-A", "kind": "alnum", "length": 3, "redefines": "BODY"},
    {"name": "B-N", "kind": "numeric", "digits": 5, "scale": 0, "signed": False, "redefines": "BODY"},
    {"name": "B-Z", "kind": "alnum", "length": 8, "redefines": "BODY"},
]}


# --- ddmin ---------------------------------------------------------------------------------------------------

def test_ddmin_finds_a_one_minimal_pair_and_keeps_order():
    items = [str(i) for i in range(500)]
    need = {"17", "403"}
    calls = []

    def test(sub):
        calls.append(len(sub))
        return need <= set(sub)

    assert mz.ddmin(items, test) == ["17", "403"]
    assert len(calls) < 200  # far fewer than 500 singles


def test_ddmin_single_culprit_and_empty_input_case():
    assert mz.ddmin(list("abcdefgh"), lambda s: "e" in s) == ["e"]
    assert mz.ddmin(list("abc"), lambda s: True) == []  # fails even on empty input: nothing needed


def test_ddmin_result_is_one_minimal_for_a_state_dependent_oracle():
    # fails when a "set" record precedes a "use" record with anything but ONE reset between them
    items = ["x", "set", "y", "z", "use", "w", "reset", "set", "q"]

    def test(sub):
        if "set" not in sub:
            return False
        after = sub[sub.index("set") + 1 :]
        return "use" in after and "reset" not in after[: after.index("use")]

    best = mz.ddmin(items, test)
    assert test(best)
    assert all(not test(best[:i] + best[i + 1 :]) for i in range(len(best)))  # 1-minimal
    assert best == ["set", "use"]


def test_ddmin_is_deterministic():
    items = list(range(64))
    t = lambda s: 5 in s and 40 in s and 41 in s
    assert mz.ddmin(items, t) == mz.ddmin(items, t) == [5, 40, 41]


def test_ddmin_cap_keeps_the_best_so_far():
    state, n = {}, {"calls": 0}

    def test(sub):
        n["calls"] += 1
        if n["calls"] > 4:
            raise mz.CapReached("run-cap")
        return 3 in sub

    with pytest.raises(mz.CapReached):
        mz.ddmin(list(range(64)), test, state)
    assert 3 in state["best"] and len(state["best"]) < 64


# --- layout and field simplification -------------------------------------------------------------------------

def test_overlay_places_redefines_views_on_the_redefined_bytes():
    views = {v.name: v for v in mz.overlay(LAYOUT)}
    assert (views["BODY"].offset, views["BODY"].length) == (6 + 7 + 4, 8)
    assert views["B-A"].offset == views["B-N"].offset - 3 == views["BODY"].offset
    assert views["B-Z"].offset == views["BODY"].offset  # 3 + 5 = 8 fills the body, so the next view starts over


def test_candidates_keep_the_field_length_and_never_break_the_line():
    views = mz.overlay(LAYOUT)
    from diocle_verifier.layout import format_record

    rec = format_record({"ID": "AB12", "AMT": Decimal("-123.45"), "PK": Decimal("99999.99"), "BODY": "ZZ12345Z"},
                        load_fields(LAYOUT))
    for v in views:
        raw = rec[v.offset : v.offset + v.length]
        for c in mz.candidates(v, raw, line_format=True):
            assert len(c) == v.length and c != raw and "\n" not in c and "\r" not in c
    amt = next(v for v in views if v.name == "AMT")
    shown = {mz._numeric_value(amt, c) for c in mz.candidates(amt, rec[amt.offset : amt.offset + amt.length], True)}
    assert Decimal("0.00") in shown and Decimal("-0.01") in shown and Decimal("-100.00") in shown


def test_simplify_fields_neutralizes_all_but_the_needed_field_and_preserves_length():
    fields = load_fields(LAYOUT)
    from diocle_verifier.layout import format_record

    rec = format_record({"ID": "AB12", "AMT": Decimal("-123.45"), "PK": Decimal("99999.99"), "BODY": "ZZ12345Z"}, fields)
    views = mz.overlay(LAYOUT)
    pk = next(v for v in views if v.name == "PK")
    needed = rec[pk.offset : pk.offset + pk.length]
    state = {}
    out = mz.simplify_fields([rec], views, fields, True, lambda recs: recs[0][pk.offset : pk.offset + pk.length] == needed, state)
    assert len(out[0]) == len(rec) == record_length(fields)
    assert out[0][pk.offset : pk.offset + pk.length] == needed
    assert out[0][:6].strip() == "" and out[0][-8:].strip(" 0") == ""
    assert state["simplified"] >= 3 and (0, "PK", pk.offset) not in {k for k in state["tried"] if mz._is_neutral(pk, needed)}


def test_simplify_fields_never_creates_a_new_invalid_number():
    fields = load_fields(LAYOUT)
    from diocle_verifier.layout import format_record, parse_record

    rec = format_record({"ID": "A", "AMT": Decimal("1.00"), "PK": Decimal("1.00"), "BODY": "x"}, fields)
    seen = []
    mz.simplify_fields([rec], mz.overlay(LAYOUT), fields, True, lambda recs: seen.append(recs[0]) or True)
    for r in seen:
        values = parse_record(r, fields)
        assert not isinstance(values["AMT"], str) and not isinstance(values["PK"], str)


# --- signatures ------------------------------------------------------------------------------------------------

def _run(exit_code=0, stdout=""):
    return mz.Run(True, exit_code, stdout, "", [])


def test_signature_kinds_and_strictness():
    fd = [{"field": "F", "original": "1", "converted": "2"}]
    bad = [{"match": False, "fieldDiffs": fd, "diff": "x"}]
    assert mz.signature(_run(), _run(), [{"match": True}]) is None
    assert mz.signature(_run(0), _run(1), bad) == ("exit-code",)
    assert mz.signature(_run(), _run(), bad) == ("output-record", ("F",))
    assert mz.signature(_run(), _run(), bad, strict=True)[2] == (("F", "1", "2"),)
    assert mz.signature(_run(), _run(), [{"match": False, "fieldDiffs": [], "diff": "the converted program wrote 1 records, the other wrote more"}]) == ("output-count",)
    assert mz.signature(_run(stdout="a"), _run(stdout="b"), [{"match": True}]) == ("stdout",)


# --- real harness: interest-accrual's naive translation -------------------------------------------------------

@pytest.fixture(scope="module")
def failing_batch():
    from diocle_verifier.verify import verify_sample

    report = verify_sample(SAMPLE, random_count=60)
    return [r["input"] for r in report["results"]], [r["input"] for r in report["results"] if not r["match"]]


@toolchain
def test_real_batch_shrinks_to_one_record_with_named_fields_and_a_valid_contract(failing_batch, tmp_path):
    batch, _ = failing_batch
    rec = mz.minimize(SAMPLE, NAIVE, "naive-1", [batch], source="initial-test", out_dir=tmp_path)
    mz.validate(rec)
    red = rec["reduction"]
    assert rec["status"] == "minimized" and red["recordsBefore"] == len(batch) and red["recordsAfter"] == 1
    assert red["recordMinimal"] and red["stoppedBy"] == "complete" and red["oracleRuns"] <= red["maxOracleRuns"]
    assert red["bytesAfter"] < red["bytesBefore"]
    fields = {f["name"]: f for f in rec["inputs"][0]["records"][0]["fields"]}
    assert fields["ACCT-ID"]["role"] == "neutral" and "ACCT-BALANCE" in fields
    assert len(rec["inputs"][0]["records"][0]["hex"]) // 2 == rec["inputs"][0]["recordLength"]
    assert rec["output"]["firstDifference"]["field"] in rec["discrepancy"]["fields"]
    assert "explanation" not in rec  # the minimizer invents no cause


@toolchain
def test_real_reduction_is_deterministic(failing_batch):
    batch, _ = failing_batch
    a = mz.minimize(SAMPLE, NAIVE, "d", [batch])
    b = mz.minimize(SAMPLE, NAIVE, "d", [batch])
    for r in (a, b):
        r["reduction"].pop("wallClockSeconds")
    assert a == b


@toolchain
def test_regression_case_fails_on_the_buggy_java_and_passes_on_the_fixed_one(failing_batch, tmp_path):
    batch, _ = failing_batch
    rec = mz.minimize(SAMPLE, NAIVE, "naive-2", [batch], out_dir=tmp_path)
    case = tmp_path / "regression" / "naive-2"
    assert sorted(p.name for p in case.iterdir()) == ["case.json", "expected-output.dat", "expected-stdout.txt", "input.dat"]
    mz.validate_case(json.loads((case / "case.json").read_text()))
    assert rec["regression"]["dir"] == "regression/naive-2"
    bad = mz.replay(case, NAIVE)
    good = mz.replay(case, REFERENCE)
    assert not bad["passed"] and bad["firstDifference"]["field"]
    assert good["passed"], good
    assert [r["passed"] for r in mz.replay_all(tmp_path, REFERENCE)] == [True]
    # the CLI replays the same way and says so with its exit code
    assert cli(["replay", str(case), "--java-dir", str(NAIVE)]) == 1
    assert cli(["replay", str(tmp_path), "--java-dir", str(REFERENCE)]) == 0


@toolchain
def test_run_cap_stops_early_and_says_so(failing_batch):
    batch, _ = failing_batch
    rec = mz.minimize(SAMPLE, NAIVE, "cap", [batch], max_runs=3)
    mz.validate(rec)
    assert rec["reduction"]["stoppedBy"] == "run-cap" and rec["reduction"]["oracleRuns"] <= 3 + 1
    assert rec["reduction"]["recordsAfter"] <= len(batch) and not rec["reduction"]["recordMinimal"]


@toolchain
def test_time_cap_with_a_fake_clock(failing_batch):
    batch, _ = failing_batch
    ticks = iter(range(0, 1000, 10))  # 10 "seconds" per clock read
    rec = mz.minimize(SAMPLE, NAIVE, "t", [batch], max_seconds=25, now=lambda: float(next(ticks)))
    assert rec["reduction"]["stoppedBy"] == "time-cap" or rec["status"] == "not-reproduced"
    mz.validate(rec)


@toolchain
def test_the_fixed_java_is_not_reproduced_and_nothing_is_saved(failing_batch, tmp_path):
    batch, _ = failing_batch
    rec = mz.minimize(SAMPLE, REFERENCE, "ok", [batch], out_dir=tmp_path)
    mz.validate(rec)
    assert rec["status"] == "not-reproduced" and rec["reduction"]["oracleRuns"] == 1
    assert not (tmp_path / "regression").exists()


@toolchain
def test_programs_with_several_files_are_reported_unsupported():
    rec = mz.minimize(ROOT / "samples" / "account-match", REFERENCE, "m", [["x"]])
    mz.validate(rec)
    assert rec["status"] == "unsupported" and "several files" in rec["reason"]


# --- run directories and the CLI -----------------------------------------------------------------------------

def _run_dir(tmp_path, batch, failing):
    run = tmp_path / "run"
    (run / "java").mkdir(parents=True)
    for f in NAIVE.glob("*.java"):
        shutil.copy(f, run / "java" / f.name)
    (run / "run.json").write_text(json.dumps({"sample": "samples/interest-accrual", "program": "INTACCR"}))
    (run / "breaker.json").write_text(json.dumps({"attempts": [
        {"id": "breaker-attack-r1-01", "input": failing[0], "why": "Tie rounding on a negative balance.", "broke": True, "diff": "x"}]}))
    (run / "verification-report.json").write_text(json.dumps({"results": [
        {"inputId": f"case-{i:04d}", "input": r, "match": r not in failing} for i, r in enumerate(batch)]}))
    return run


@toolchain
def test_cli_minimizes_a_breaker_case_with_the_breakers_reason_as_a_labelled_opinion(failing_batch, tmp_path, capsys):
    batch, failing = failing_batch
    run = _run_dir(tmp_path, batch, failing)
    assert cli(["minimize", str(run), "--case", "breaker-attack-r1-01"]) == 0
    saved = json.loads((run / "reproducers" / "breaker-attack-r1-01.json").read_text())
    mz.validate(saved)
    assert saved["source"] == "breaker" and saved["reduction"]["recordsAfter"] == 1
    assert saved["explanation"] == {"text": "Tie rounding on a negative balance.", "label": "explanation, not proof",
                                    "source": "breaker"}
    assert (run / "regression" / "breaker-attack-r1-01" / "case.json").is_file()
    assert "MINIMIZED" in capsys.readouterr().out
    # a whole-batch start from the report, by the id of one failing row
    first_bad = next(i for i, r in enumerate(batch) if r in failing)
    assert cli(["minimize", str(run), "--case", f"case-{first_bad:04d}", "--from-report", "--strict"]) == 0
    big = json.loads((run / "reproducers" / f"case-{first_bad:04d}.json").read_text())
    assert big["reduction"]["recordsBefore"] == len(batch) and big["reduction"]["recordsAfter"] == 1
    assert cli(["minimize", str(run), "--case", "no-such-case"]) == 2


def test_locate_case_prefers_the_breaker_record_and_falls_back_to_the_report(tmp_path):
    meta = json.loads((SAMPLE / "sample.json").read_text())
    (tmp_path / "breaker.json").write_text(json.dumps({"attempts": [{"id": "b1", "input": "REC"}]}))
    (tmp_path / "verification-report.json").write_text(json.dumps({"results": [
        {"inputId": "c1", "input": "A", "match": True}, {"inputId": "c2", "input": "B", "match": False}]}))
    contexts, hint, source = mz.locate_case(tmp_path, "b1", SAMPLE, meta)
    assert contexts[0] == ["REC"] and contexts[1][-1] == "REC" and source == "breaker"
    contexts, hint, source = mz.locate_case(tmp_path, "c2", SAMPLE, meta)
    assert contexts == [["A", "B"]] and hint[0] == "B" and source == "held-out"
    with pytest.raises(KeyError):
        mz.locate_case(tmp_path, "zzz", SAMPLE, meta)


def test_explanation_prefers_the_repair_agents_patch_rationale_after_it_resumed(tmp_path):
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"type": "agent-step", "tool": "patch_java", "rationale": "before the break"},
        {"type": "stage", "stage": "repairing", "message": "Repair agent resumes with 2 counterexample(s)"},
        {"type": "agent-step", "tool": "patch_java", "rationale": "Use the low nibble of each byte."}]) + "\n")
    got = mz.explanation_from_run(tmp_path, "any")
    assert got == {"text": "Use the low nibble of each byte.", "source": "repair-agent"}
    assert mz.explanation_from_run(tmp_path / "nowhere", "any") is None


def test_the_schema_rejects_an_explanation_without_the_label_and_unknown_fields():
    import jsonschema

    base = {"version": "0.1", "id": "x", "program": "P", "status": "not-reproduced",
            "reduction": {"recordsBefore": 1, "recordsAfter": 0, "oracleRuns": 1, "maxOracleRuns": 150, "stoppedBy": "complete"}}
    mz.validate(base)
    with pytest.raises(jsonschema.ValidationError):
        mz.validate({**base, "explanation": {"text": "t", "label": "proof", "source": "breaker"}})
    with pytest.raises(jsonschema.ValidationError):
        mz.validate({**base, "surprise": 1})


def test_published_example_validates():
    for path in (ROOT / "contracts" / "examples").glob("minimal-reproducer*.json"):
        mz.validate(json.loads(path.read_text()))


# --- refusals: sandbox rule, static Java policy, shared-file tripwire ------------------------------------------

def test_nothing_is_built_or_run_when_a_sandbox_is_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.delenv("DIOCLE_IN_SANDBOX", raising=False)
    with pytest.raises(mz.Refused, match="sandbox"):
        mz.minimize(SAMPLE, NAIVE, "x", [["r"]])
    with pytest.raises(mz.Refused):
        mz.replay(tmp_path, NAIVE)
    with pytest.raises(mz.Refused):
        mz.replay_all(tmp_path, NAIVE)
    assert cli(["minimize", str(tmp_path), "--case", "x"]) == 2
    assert cli(["replay", str(tmp_path), "--java-dir", str(NAIVE)]) == 2
    monkeypatch.setenv("DIOCLE_IN_SANDBOX", "1")
    mz.refuse_if_sandboxed()  # inside the sandbox itself it is allowed


def _hostile_java(tmp_path):
    d = tmp_path / "hostile"
    d.mkdir()
    (d / "Intaccr.java").write_text('public class Intaccr { public static void main(String[] a) throws Exception '
                                    '{ Runtime.getRuntime().exec("ls"); } }\n')
    return d


def test_java_the_policy_blocks_is_refused_before_it_is_built_or_run(tmp_path):
    hostile = _hostile_java(tmp_path)
    with pytest.raises(mz.Refused, match="refused to run"):
        mz.minimize(SAMPLE, hostile, "x", [["r"]])
    case = tmp_path / "case"
    case.mkdir()
    (case / "case.json").write_text(json.dumps({"id": "x", "dd": {"input": "A", "output": "B"}}))
    with pytest.raises(mz.Refused, match="refused to run"):
        mz.replay(case, hostile)
    assert not list(hostile.glob("*.class"))


def test_without_the_policy_module_nothing_runs(monkeypatch, tmp_path):
    import sys
    monkeypatch.setitem(sys.modules, "diocle_converter.guard", None)  # makes the import fail
    with pytest.raises(mz.Refused, match="not importable"):
        mz.static_java_policy(NAIVE, ("A", "B"))


@toolchain
def test_signature_mode_is_recorded_and_strict_keeps_the_values(failing_batch):
    batch, _ = failing_batch
    loose = mz.minimize(SAMPLE, NAIVE, "m1", [batch])
    strict = mz.minimize(SAMPLE, NAIVE, "m2", [batch], strict=True, origin="test double origin")
    mz.validate(loose)
    mz.validate(strict)
    assert loose["signatureMode"] == "fields" and strict["signatureMode"] == "strict"
    assert "origin" not in loose and strict["origin"] == "test double origin"
