from decimal import Decimal

import pytest

from diocle_verifier.inputs import generate_cases
from diocle_verifier.layout import format_record, load_fields, parse_record, record_length

SPEC = {
    "fields": [
        {"name": "ID", "kind": "alnum", "length": 4},
        {"name": "AMT", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "sign": "leading-separate"},
        {"name": "QTY", "kind": "numeric", "digits": 3, "scale": 0, "signed": False},
        {"name": "TIER", "kind": "alnum", "length": 1, "values": ["P", "S"]},
    ]
}


def test_lengths_follow_pic_clauses():
    fields = load_fields(SPEC)
    assert [f.length for f in fields] == [4, 8, 3, 1]
    assert record_length(fields) == 16


def test_format_and_parse_round_trip():
    fields = load_fields(SPEC)
    values = {"ID": "AB", "AMT": Decimal("-123.45"), "QTY": Decimal(7), "TIER": "P"}
    record = format_record(values, fields)
    assert record == "AB  -0012345007P"
    parsed = parse_record(record, fields)
    assert parsed["AMT"] == Decimal("-123.45") and parsed["QTY"] == 7 and parsed["TIER"] == "P"


def test_values_that_do_not_fit_are_rejected():
    fields = load_fields(SPEC)
    with pytest.raises(ValueError):
        format_record({"ID": "A", "AMT": Decimal("100000.00"), "QTY": Decimal(0), "TIER": "S"}, fields)
    with pytest.raises(ValueError):
        format_record({"ID": "A", "AMT": Decimal(0), "QTY": Decimal(-1), "TIER": "S"}, fields)


def test_unsupported_sign_is_rejected():
    with pytest.raises(ValueError):
        load_fields({"fields": [{"name": "X", "kind": "numeric", "digits": 3, "scale": 0, "signed": True}]})


def test_generation_is_deterministic_and_covers_boundaries():
    fields = load_fields(SPEC)
    a = generate_cases(fields, seed=7, random_count=50)
    assert a == generate_cases(fields, seed=7, random_count=50)
    assert all(len(c.record) == record_length(fields) for c in a)
    amounts = {parse_record(c.record, fields)["AMT"] for c in a if c.source == "boundary"}
    assert {Decimal("99999.99"), Decimal("-99999.99"), Decimal("0.01"), Decimal("-0.01"), Decimal(0)} <= amounts
    assert len({c.id for c in a}) == len(a)
