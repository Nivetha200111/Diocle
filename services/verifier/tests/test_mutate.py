import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest

from diocle_verifier import mutate
from diocle_verifier.mutate import _edits, extra_cases, generate_mutants, mask, mutate_local

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]
TOOLS = shutil.which("cobc") and shutil.which("javac") and shutil.which("javap")
needs_tools = pytest.mark.skipif(not TOOLS, reason="needs GnuCOBOL and a JDK")


def ops(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in _edits(text):
        out.setdefault(e.operator, []).append(text[:e.start] + e.replacement + text[e.end:])
    return out


# --- operators ------------------------------------------------------------------------------------------------

def test_relational_and_arithmetic_swaps_keep_the_rest_of_the_line():
    found = ops("class A { void f(int a, int b) {\n if (a >= b && a != 3) { a = a + b; }\n} }\n")
    assert any("if (a > b && a != 3)" in m for m in found["relational-swap"])
    assert any("a != 3" not in m and "a == 3" in m for m in found["relational-swap"])
    assert any("a = a - b;" in m for m in found["arithmetic-swap"])


def test_strings_comments_and_generics_are_never_mutated():
    text = 'class A { java.util.List<String> l; String s = "a > b + c"; // x > y\n /* p < q */ }\n'
    assert "relational-swap" not in ops(text) and "arithmetic-swap" not in ops(text)
    assert mask(text).count("_") > 10 and len(mask(text)) == len(text)


def test_rounding_mode_scale_and_truncation_operators():
    found = ops("class A { void f() {\n x = y.setScale(2, RoundingMode.HALF_UP);\n z = w.remainder(M);\n q = a % 1000;\n} }\n")
    assert any("RoundingMode.HALF_EVEN" in m for m in found["rounding-mode"])
    assert any("RoundingMode.DOWN" in m for m in found["rounding-mode"])
    assert any("setScale(3," in m for m in found["scale-off-by-one"]) and any("setScale(1," in m for m in found["scale-off-by-one"])
    assert any("z = w;" in m for m in found["remove-truncation"])
    assert any("q = a;" in m for m in found["remove-truncation"])


def test_branch_loop_else_and_pad_operators():
    found = ops("class A { void f() {\n for (int i = 0; i < n; i++) { }\n if (a) { } else { b = (byte) 0x20; c = ' '; }\n} }\n")
    assert any("i < (n) - 1" in m for m in found["loop-bound"])
    assert any("if (!(a))" in m for m in found["negate-condition"])
    assert any("else if (false) {" in m for m in found["remove-else"])
    assert any("0x30" in m for m in found["pad-char"]) and any("c = '0'" in m for m in found["pad-char"])


def test_boundary_constants_only_on_comparison_like_lines():
    found = ops("class A { void f() {\n if (n > 10) { }\n int k = 7;\n s.substring(0, 4);\n} }\n")
    changed = {m for m in found["boundary-constant"]}
    assert any("n > 11" in m for m in changed) and any("n > 9" in m for m in changed)
    assert not any("k = 8" in m or "k = 6" in m for m in changed)
    assert any("substring(0, 5)" in m for m in changed)


# --- selection ------------------------------------------------------------------------------------------------

def test_selection_is_deterministic_per_seed_and_capped(tmp_path):
    java = tmp_path / "j"
    java.mkdir()
    shutil.copy(HERE / "fixtures" / "reference" / "IntAccr.java", java)
    a, total = generate_mutants(java, seed=7, max_mutants=12)
    b, _ = generate_mutants(java, seed=7, max_mutants=12)
    c, _ = generate_mutants(java, seed=8, max_mutants=12)
    assert a == b and len(a) == 12 and total > 12
    assert [m.id for m in a] == [f"m{i:03d}" for i in range(1, 13)]
    assert [(m.line, m.replacement) for m in a] != [(m.line, m.replacement) for m in c]
    assert len({m.operator for m in a}) >= 5  # round-robin over operators, not one operator crowding the rest


def test_extra_inputs_are_deterministic_and_include_the_midpoint():
    from diocle_verifier.layout import load_fields
    fields = load_fields({"fields": [{"name": "ID", "kind": "alnum", "length": 4},
                                     {"name": "AMT", "kind": "numeric", "digits": 3, "scale": 2, "signed": False}]})
    a, b = extra_cases(fields, 1, 60), extra_cases(fields, 1, 60)
    assert a == b and all(c.id.startswith("extra-") for c in a)
    assert any(c.record.endswith("50000") for c in a)  # 500.00 exactly: max/2 on a 999.99 field


@needs_tools
def test_equivalent_bytecode_is_recognised_and_a_real_change_is_not(tmp_path):
    def build(name: str, src: str) -> dict:
        d = tmp_path / name
        (d / "c").mkdir(parents=True)
        (d / "A.java").write_text(src)
        subprocess.run(["javac", "-d", str(d / "c"), str(d / "A.java")], check=True)
        return mutate._bytecode(d / "c")
    base = build("a", "class A { int f() { return 4 + 0; } }\n")
    assert build("b", "class A {\n\n  // comment\n int f() { return 4 - 0; } }\n") == base
    assert build("c", "class A { int f() { return 5; } }\n") != base


# --- end to end on a weak translation (test double) ------------------------------------------------------------

def _weak_sample(tmp: Path) -> tuple[Path, Path]:
    sample = tmp / "weak"
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    shutil.copy(HERE / "fixtures" / "mutation" / "weak" / "WEAK.cbl", sample / "src" / "WEAK.cbl")
    in_layout = {"record": "IN-REC", "fields": [{"name": "IN-ID", "kind": "alnum", "length": 4},
                                                {"name": "IN-AMT", "kind": "numeric", "digits": 3, "scale": 2, "signed": False}]}
    out_layout = {"record": "OUT-REC", "fields": [{"name": "OUT-ID", "kind": "alnum", "length": 4},
                                                  {"name": "OUT-FEE", "kind": "numeric", "digits": 3, "scale": 2, "signed": False}]}
    (sample / "sample.json").write_text(json.dumps({
        "name": "weak", "program": "WEAK", "source": "src/WEAK.cbl", "copybookDir": "copybooks", "modules": [],
        "dd": {"input": "WKIN", "output": "WKOUT"}, "javaConversion": {"dir": "x", "mainClass": "Weak"},
        "layouts": {"input": in_layout, "output": out_layout}}))
    java = tmp / "java"
    java.mkdir()
    shutil.copy(HERE / "fixtures" / "mutation" / "weak-java" / "Weak.java", java)
    return sample, java


def _digest(d: Path) -> str:
    return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file())).hexdigest()


@pytest.fixture(scope="module")
def weak(tmp_path_factory):
    if not TOOLS:
        pytest.skip("needs GnuCOBOL and a JDK")
    tmp = tmp_path_factory.mktemp("weak")
    sample, java = _weak_sample(tmp)
    before = _digest(java)
    report = mutate_local(sample, java, seed=5, max_mutants=60, random_count=0, mutant_timeout=3)
    return report, before == _digest(java)


def by(report: dict, text: str) -> dict:
    return next(m for m in report["mutants"] if text in m["description"])


@needs_tools
def test_weak_translation_has_survivors_that_extra_inputs_kill(weak):
    report, untouched = weak
    assert untouched, "the certified Java must not be modified"
    assert report["status"] == "ok" and report["counts"]["notRun"] == 0
    gt = next(m for m in report["mutants"] if m["operator"] == "relational-swap" and "`>` changed to `>=`" in m["description"])
    assert gt["outcome"] == "survived" and gt["augmentedOutcome"] == "killed" and gt["augmentedKilledBy"].startswith("extra-")
    assert report["augmented"]["extraKills"] >= 1 and report["augmented"]["modelCalls"] == 0
    assert report["augmented"]["survivorsRerun"] == report["counts"]["survived"]
    assert any(m["outcome"] == "killed" and m["killedBy"] for m in report["mutants"])


@needs_tools
def test_not_compiled_equivalent_and_timeout_are_reported(weak):
    report, _ = weak
    assert by(report, "`equals` changed to `equalsIgnoreCase`")["outcome"] == "not-compiled"
    assert by(report, "`equals` changed to `equalsIgnoreCase`")["note"]
    folded = next(m for m in report["mutants"] if m["original"] == "int pad = 4 + 0;" and "`+` changed to `-`" in m["description"])
    assert folded["outcome"] == "equivalent-suspected" and "bytecode" in folded["note"]
    assert any(m["outcome"] == "timeout" for m in report["mutants"])  # tries += 1 -> tries -= 1 never ends


@needs_tools
def test_score_counts_only_compiled_non_equivalent_mutants_and_report_validates(weak):
    report, _ = weak
    c = report["counts"]
    scored = c["killed"] + c["timeout"] + c["survived"]
    assert c["score"] == round((c["killed"] + c["timeout"]) / scored, 3)
    assert c["run"] == c["killed"] + c["survived"] + c["notCompiled"] + c["equivalentSuspected"] + c["timeout"] + c["error"]
    mutate.validate_report(report)
    assert any("coverage question" in n for n in report["notes"])


@needs_tools
def test_a_translation_that_does_not_match_is_not_judged(tmp_path):
    sample, java = _weak_sample(tmp_path)
    (java / "Weak.java").write_text((java / "Weak.java").read_text().replace("5000 : 500", "5000 : 400"))
    report = mutate_local(sample, java, random_count=0)
    assert report["status"] == "baseline-failed" and report["mutants"] == []
    mutate.validate_report(report)


@needs_tools
def test_wall_clock_cap_leaves_the_rest_not_run(tmp_path):
    sample, java = _weak_sample(tmp_path)
    report = mutate_local(sample, java, random_count=0, wall_clock=10)  # the job keeps 30 s in reserve, so nothing runs
    assert report["caps"]["budgetExhausted"] and report["counts"]["notRun"] > 0 and report["counts"]["run"] == 0
    mutate.validate_report(report)


def test_multi_file_samples_are_reported_unsupported(tmp_path):
    sample = tmp_path / "s"
    sample.mkdir()
    (sample / "sample.json").write_text(json.dumps({"program": "P", "displayOnly": True, "files": []}))
    java = tmp_path / "j"
    java.mkdir()
    report = mutate_local(sample, java)
    assert report["status"] == "unsupported" and "DISPLAY" in report["reason"]
    mutate.validate_report(report)


def test_contract_examples():
    schema = json.loads((ROOT / "contracts" / "mutation-report.schema.json").read_text())
    jsonschema.validate(json.loads((ROOT / "contracts" / "examples" / "mutation-report.valid.json").read_text()), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(json.loads((ROOT / "contracts" / "examples" / "mutation-report.invalid.json").read_text()), schema)


def test_sandbox_clamps_what_a_caller_asks_for(monkeypatch, tmp_path):
    sample = tmp_path / "s"
    sample.mkdir()
    (sample / "sample.json").write_text(json.dumps({"program": "P", "displayOnly": True, "files": []}))
    report = mutate_local(sample, tmp_path, max_mutants=10**6, max_extra=10**6, wall_clock=10**6)
    assert report["caps"] == {"maxMutants": mutate.HARD_MAX_MUTANTS, "maxExtraInputs": mutate.HARD_MAX_EXTRA,
                              "wallClockSeconds": mutate.HARD_MAX_WALL_CLOCK, "mutantTimeoutSeconds": 10,
                              "budgetExhausted": False}
