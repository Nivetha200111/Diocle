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


def test_signed_display_defaults_to_trailing_overpunch_and_unknown_signs_are_rejected():
    [f] = load_fields({"fields": [{"name": "X", "kind": "numeric", "digits": 3, "scale": 0, "signed": True}]})
    assert f.sign == "trailing" and f.length == 3
    with pytest.raises(ValueError):
        load_fields({"fields": [{"name": "X", "kind": "numeric", "digits": 3, "scale": 0, "signed": True, "sign": "odd"}]})


def test_encodings_match_the_bytes_gnucobol_writes():
    """Expected bytes captured from GnuCOBOL 3.2 -std=ibm writing +123 / -123 (and +/-12345.67 packed)."""
    from decimal import Decimal as D
    from diocle_verifier.layout import format_value, parse_record
    spec = {"fields": [
        {"name": "OVP", "kind": "numeric", "digits": 3, "scale": 0, "signed": True},
        {"name": "TSEP", "kind": "numeric", "digits": 3, "scale": 0, "signed": True, "sign": "trailing-separate"},
        {"name": "PK", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "usage": "packed"},
        {"name": "PKU", "kind": "numeric", "digits": 4, "scale": 0, "signed": False, "usage": "packed"},
        {"name": "BIN", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary"},
        {"name": "BIN9", "kind": "numeric", "digits": 9, "scale": 0, "signed": True, "usage": "binary"},
        {"name": "C5", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary-native"},
        {"name": "F2", "kind": "numeric", "digits": 7, "scale": 2, "signed": True, "usage": "float", "bytes": 8},
        {"name": "P", "kind": "numeric", "digits": 5, "scale": -2, "signed": False}]}
    fields = load_fields(spec)
    gnucobol = [bytes.fromhex("313233" "3132332b" "1234567c" "00042f" "007b" "00011170" "7b00" "000000000000f83f" "313233"),
                bytes.fromhex("313273" "3132332d" "1234567d" "00042f" "ff85" "00011170" "85ff" "000000000000f83f" "313233")]
    for sign, expected in zip((1, -1), gnucobol):
        values = [D(123 * sign), D(123 * sign), D("12345.67") * sign, D(42), D(123 * sign), D(70000), D(123 * sign),
                  D("1.5"), D(12300)]
        encoded = "".join(format_value(f, v) for f, v in zip(fields, values)).encode("latin-1")
        assert encoded == expected
        parsed = parse_record(expected.decode("latin-1"), fields)
        assert [parsed[f.name] for f in fields] == values


def test_generation_is_deterministic_and_covers_boundaries():
    fields = load_fields(SPEC)
    a = generate_cases(fields, seed=7, random_count=50)
    assert a == generate_cases(fields, seed=7, random_count=50)
    assert all(len(c.record) == record_length(fields) for c in a)
    amounts = {parse_record(c.record, fields)["AMT"] for c in a if c.source == "boundary"}
    assert {Decimal("99999.99"), Decimal("-99999.99"), Decimal("0.01"), Decimal("-0.01"), Decimal(0)} <= amounts
    assert len({c.id for c in a}) == len(a)
