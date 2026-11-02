"""Checks that span the services: contracts, recorded results and the rules every checkout must keep (CLAUDE.md rule 4)."""

import hashlib
import json
import re
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
SCHEMAS = sorted(CONTRACTS.glob("*.schema.json"))
SECRET = re.compile(r"^\s*#?\s*([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSCODE))=(.+)$")


def schema(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.schema.json").read_text())


def errors(name: str, document: dict) -> list:
    checker = jsonschema.validators.validator_for(schema(name))(schema(name))
    return list(checker.iter_errors(document))


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_every_contract_is_a_valid_schema(path):
    document = json.loads(path.read_text())
    jsonschema.validators.validator_for(document).check_schema(document)


def test_contract_examples_are_accepted_and_the_invalid_one_refused():
    examples = CONTRACTS / "examples"
    assert not errors("mutation-report", json.loads((examples / "mutation-report.valid.json").read_text()))
    assert errors("mutation-report", json.loads((examples / "mutation-report.invalid.json").read_text()))
    assert not errors("minimal-reproducer", json.loads((examples / "minimal-reproducer.chqclr-nsf-fee.json").read_text()))


def test_distillation_report_matches_its_contract_and_its_dataset():
    report = json.loads((ROOT / "eval/results-distillation.json").read_text())
    assert not errors("distillation-report", report)
    data = (ROOT / "eval/distill/train.jsonl").read_bytes()
    assert hashlib.sha256(data).hexdigest() == report["dataset"]["sha256"]
    assert len(data.splitlines()) == report["dataset"]["examples"]


@pytest.mark.parametrize("name", [".env.example", "deploy/diocle.env.example"])
def test_example_env_files_hold_no_secret_values(name):
    for line in (ROOT / name).read_text().splitlines():
        match = SECRET.match(line)
        assert not match, f"{name}: {match.group(1)} has a value"


def test_docker_entry_points_build_the_engine_image():
    assert (ROOT / "Dockerfile").resolve() == (ROOT / "deploy/Dockerfile.api").resolve()
    assert "dockerfile: deploy/Dockerfile.api" in (ROOT / "compose.yaml").read_text()
