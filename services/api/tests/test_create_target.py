"""Create-the-target-repository option: contract (delivery v0.5), validation, owner allowlist, admin-only path,
and the delivery flow against a TEST DOUBLE for `gh` (see the fake_gh fixture). No real GitHub repository is ever created."""
import json

import jsonschema
import pytest

from diocle_api import deliver

CONTRACTS = deliver.REPO_ROOT / "contracts"
DELIVERY = json.loads((CONTRACTS / "delivery.schema.json").read_text())
REQUEST = {"$ref": "#/$defs/request", "$defs": DELIVERY["$defs"]}
BASE = {"id": "d", "legacy": {"repository": "https://github.com/o/r"}, "target": None, "stage": "analyzing",
        "programs": [], "startedAt": "2026-10-30T00:00:00+00:00"}


def test_contract_accepts_valid_and_old_records_and_rejects_invalid_ones():
    jsonschema.validate(BASE, DELIVERY)  # an old record: no createTarget
    jsonschema.validate({**BASE, "target": "https://github.com/me/x-java", "targetCreated": True,
                         "createTarget": {"name": "x-java", "owner": "me", "visibility": "private"}}, DELIVERY)
    jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": {"name": "x_1.2-java"}}, REQUEST)
    jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": {"name": "x", "owner": None, "visibility": "public"}}, REQUEST)
    bad = [{"name": ""}, {"name": ".."}, {"name": "."}, {"name": "a/b"}, {"name": "a b"}, {"name": "x" * 101}, {"name": "répo"},
           {"name": "x.git"}, {"name": "x", "visibility": "internal"}, {"name": "x", "owner": "a/b"}, {"name": "x", "extra": 1}, {}]
    for create in bad:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": create}, REQUEST)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**BASE, "targetCreated": "yes"}, DELIVERY)
