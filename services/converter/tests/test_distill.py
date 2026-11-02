"""Verified distillation gates (docs/DISTILLATION.md). No model or host is called: the fakes below are labelled as such."""

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest

from diocle_converter import distill
from diocle_converter.sources import Program
from diocle_converter.translate import translation_messages

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "loyalty-waiver"
HELD = ROOT / "eval" / "samples" / "chqclr"


@dataclass
class FakeCall:
    model: str


def report(*, compiled=True, exit_match=True, total=1000, failed=0, stdout=True, exit_code=0):
    return {"runs": {"original": {"compiled": True, "exitCode": exit_code}, "converted": {"compiled": compiled},
                     "exitCodeMatch": exit_match, "stdoutMatch": stdout},
            "summary": {"total": total, "failed": failed}}


def test_hosted_muse_spark_output_is_refused():
    with pytest.raises(distill.NotOpenWeights):
        distill.check_teacher_calls([FakeCall("accounts/fireworks/models/muse-spark-open"), FakeCall("muse-spark-1.3-contributor")])


def test_an_example_with_no_recorded_call_is_refused():
    with pytest.raises(distill.NotOpenWeights):
        distill.check_teacher_calls([])


def test_both_open_weights_hosts_are_accepted():
    distill.check_teacher_calls([FakeCall("accounts/fireworks/models/muse-spark-open"), FakeCall("meta-models/muse-spark-open-1026")])


def test_flat_record_is_invisible_to_the_oracle(tmp_path):
    fields = [{"name": "IN-RECORD", "kind": "alnum", "length": 160}]
    (tmp_path / "sample.json").write_text(json.dumps({"files": [{"dd": "IN", "direction": "input", "layout": {"fields": fields}}]}))
    assert distill.oracle_can_see(tmp_path) is False


def test_structured_record_is_visible_to_the_oracle():
    assert distill.oracle_can_see(SAMPLE) is True


def test_no_input_file_is_invisible_to_the_oracle(tmp_path):
    (tmp_path / "sample.json").write_text(json.dumps({"files": [{"dd": "OUT", "direction": "output", "layout": {"fields": []}}]}))
    assert distill.oracle_can_see(tmp_path) is False


def test_similarity_bounds():
    text = "PERFORM COMPUTE-FEE THRU COMPUTE-EXIT UNTIL END-OF-FILE MOVE FEE-AMOUNT TO OUT-FEE"
    assert distill.similarity(text, text) == 1.0
    assert distill.similarity(text, "OPEN INPUT TELLER-FILE READ TELLER-FILE INTO WS-RECORD") == 0.0
    assert distill.similarity("", "") == 0.0


@pytest.mark.parametrize("kwargs,gate", [
    ({"compiled": False}, "differential-failed"), ({"failed": 1}, "differential-failed"), ({"stdout": False}, "differential-failed"),
    ({"exit_match": False}, "differential-failed"), ({"total": 0}, "differential-failed"), ({"total": 99}, "too-few-records"),
    ({"exit_code": 16}, "differential-failed"),
])
def test_oracle_refusals(kwargs, gate):
    assert distill.passes_oracle(report(**kwargs)) == (False, gate)


def test_oracle_accepts_a_clean_pass():
    assert distill.passes_oracle(report()) == (True, None)


def test_training_prompt_is_the_translators_prompt():
    program = Program.load(SAMPLE)
    line = distill.training_line(program, {"mainClass": program.main_class, "notes": "n"}, "class Loywaive {}")
    assert line["messages"][:2] == translation_messages(program)
    assert json.loads(line["messages"][2]["content"]) == {"mainClass": program.main_class, "javaSource": "class Loywaive {}", "notes": "n"}


def test_held_out_program_cannot_enter_the_dataset():
    held = {"CHQCLR": Program.load(HELD).as_text()}
    program = Program.load(HELD)
    line = distill.training_line(program, {"mainClass": program.main_class, "notes": ""}, "class X {}")
    with pytest.raises(ValueError, match="CHQCLR"):
        distill.check_no_leak([line], held)


def test_a_near_copy_of_a_held_out_program_cannot_enter_the_dataset():
    text = Program.load(HELD).as_text()
    renamed = text.replace("CHQCLR", "OTHERPGM")
    line = {"messages": [{"role": "user", "content": renamed}]}
    with pytest.raises(ValueError, match="similar to held-out"):
        distill.check_no_leak([line], {"CHQCLR": text})


def test_unrelated_program_passes_the_leak_check():
    program = Program.load(SAMPLE)
    line = distill.training_line(program, {"mainClass": program.main_class, "notes": ""}, "class X {}")
    distill.check_no_leak([line], {"CHQCLR": Program.load(HELD).as_text()})


COBOL = """      * SYNTHETIC. Fictional.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GEN0001.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT A ASSIGN TO INFILE ORGANIZATION IS LINE SEQUENTIAL.
           SELECT B ASSIGN TO OUTFILE ORGANIZATION IS LINE SEQUENTIAL.
       PROCEDURE DIVISION.
           STOP RUN.
"""


def test_contained_program_is_accepted():
    assert distill.contained(COBOL)


@pytest.mark.parametrize("change", [
    ("ASSIGN TO OUTFILE", 'ASSIGN TO "/etc/hosts"'), ("STOP RUN", 'CALL "SYSTEM" USING X'), ("STOP RUN", "ACCEPT WS-DATE FROM DATE"),
    ("STOP RUN", "EXEC SQL COMMIT END-EXEC"), ("ASSIGN TO OUTFILE", "ASSIGN TO OTHER"),
])
def test_a_generated_program_may_only_touch_its_two_files(change):
    assert not distill.contained(COBOL.replace(*change))


def test_a_third_file_is_refused():
    extra = COBOL.replace("       PROCEDURE", "           SELECT C ASSIGN TO INFILE.\n       PROCEDURE")
    assert not distill.contained(extra)


def test_a_comment_mentioning_call_is_not_a_refusal():
    assert distill.contained(COBOL.replace("       PROCEDURE", "      * CALL NOTHING HERE\n       PROCEDURE"))


def test_a_data_name_containing_call_is_not_a_refusal():
    assert distill.contained(COBOL.replace("STOP RUN", "MOVE 1 TO WS-CALL-COUNT ACCEPT-FLAG\n           STOP RUN"))


def test_generator_asks_for_the_copy_form_the_analyzer_reads():
    assert 'COPY GEN0001I.' in distill.GENERATOR_SYSTEM


def test_topics_are_stable_and_unique_and_avoid_the_held_out_domains():
    first = distill.topics(120)
    assert first == distill.topics(120) and len({t[0] for t in first}) == 120 and len({t[1:] for t in first}) == 120
    assert not [t for t in first if any(w in t[1].lower() for w in ("cheque", "branch", "exchange", "amortiz"))]


def test_dataset_bytes_are_deterministic():
    a = distill.dataset_bytes([{"messages": [{"role": "user", "content": "é"}]}])
    assert a == distill.dataset_bytes([{"messages": [{"content": "é", "role": "user"}]}]) and a.endswith(b"\n")
    assert distill.estimate_training_tokens(b"x" * 300, 3) == 300


def test_wait_for_gives_up_at_the_limit():
    now = [0.0]

    def tick(seconds):
        now[0] += seconds

    with pytest.raises(TimeoutError):
        distill.wait_for(lambda: {"state": "PENDING"}, lambda v: False, every=10, limit=30, sleep=tick, clock=lambda: now[0])
    assert distill.wait_for(lambda: 1, lambda v: v == 1, sleep=tick, clock=lambda: now[0]) == 1


def test_report_contract_refuses_a_hosted_teacher():
    schema = json.loads((ROOT / "contracts" / "distillation-report.schema.json").read_text())
    good = {"version": "0.1", "teacher": {"model": "accounts/fireworks/models/muse-spark-open", "host": "fireworks", "reasoningEffort": "low"},
            "student": {"baseModel": "accounts/fireworks/models/muse-glimmer-30b"},
            "dataset": {"examples": 0, "sha256": "x", "heldOut": [], "oracle": {"seed": 1, "cases": 1}, "rejected": {}},
            "training": {"status": "not-run"}, "evaluation": {"status": "not-run"}, "spend": {"teacherUsd": 0}, "limits": ["small"]}
    jsonschema.validate(good, schema)
    bad = {**good, "teacher": {**good["teacher"], "model": "muse-spark-1.3-contributor"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


class FakeResponse:
    """A stand-in for the host's reply. Nothing here reaches Fireworks."""
    def __init__(self, status=200, body=None):
        self.status_code, self.content, self.text = status, json.dumps(body or {}).encode(), json.dumps(body or {})
        self.request = type("R", (), {"method": "POST", "url": type("U", (), {"path": "/x"})})
        self._body = body or {}

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, response=None):
        self.requests, self.response = [], response or FakeResponse()

    def post(self, path, **kw):
        self.requests.append(("POST", path, kw))
        return self.response

    def delete(self, path, **kw):
        self.requests.append(("DELETE", path, kw))
        return self.response


def test_deployment_scales_to_zero_and_never_past_one_replica():
    http = FakeHttp()
    distill.Fireworks("acct", "key", http).create_deployment("base", "NVIDIA_H100_80GB", 1)
    body = http.requests[0][2]["json"]
    assert (body["minReplicaCount"], body["maxReplicaCount"], body["enableAddons"]) == (0, 1, True)
    assert body["scaleToZeroWindow"] == "300s"


def test_a_host_error_is_raised_with_its_status_and_not_the_key():
    http = FakeHttp(FakeResponse(403, {"error": "denied"}))
    with pytest.raises(RuntimeError, match="403") as e:
        distill.Fireworks("acct", "secret-key", http).create_job("j", "b", "d", "o", 3, 8)
    assert "secret-key" not in str(e.value)
