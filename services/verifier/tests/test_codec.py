import json
from decimal import Decimal
from pathlib import Path

import pytest

from diocle_verifier.codec import convert_record, decimal_from_hfp, float_to_hfp, hfp_to_float
from diocle_verifier.layout import format_record, load_fields, parse_record

ROOT = Path(__file__).resolve().parents[3]


def test_ibm_hexadecimal_float_known_values():
    assert hfp_to_float(bytes.fromhex("C276A000")) == -118.625  # IBM's documented example
    assert hfp_to_float(bytes.fromhex("41100000")) == 1.0
    assert float_to_hfp(-118.625, 4) == bytes.fromhex("C276A000")
    assert float_to_hfp(1.0, 8) == bytes.fromhex("4110000000000000")
    tenth = float_to_hfp(0.1, 8)
    assert tenth == bytes.fromhex("401999999999999A")
    assert decimal_from_hfp(tenth) != Decimal("0.1")  # not exact in base 16 either, just differently wrong
    assert hfp_to_float(bytes(8)) == 0.0


def test_zoned_text_and_packed_fields_convert_field_by_field():
    fields = load_fields({"fields": [
        {"name": "ID", "kind": "alnum", "length": 3},
        {"name": "Z", "kind": "numeric", "digits": 3, "scale": 0, "signed": True},
        {"name": "S", "kind": "numeric", "digits": 3, "scale": 0, "signed": True, "sign": "leading-separate"},
        {"name": "P", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "usage": "packed"},
        {"name": "B", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary"},
        {"name": "N", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary-native"}]})
    ebcdic = bytes.fromhex("C1C2C3" "F1F2D3" "60F1F2F3" "1234567D" "FF85" "FF85")
    gnucobol = convert_record(ebcdic, fields)
    values = parse_record(gnucobol.decode("latin-1"), fields)
    assert values == {"ID": "ABC", "Z": Decimal(-123), "S": Decimal(-123), "P": Decimal("-12345.67"),
                      "B": Decimal(-123), "N": Decimal(-123)}
    assert convert_record(gnucobol, fields, to_mainframe=True) == ebcdic


def test_a_packed_extract_round_trips_through_ebcdic():
    meta = json.loads((ROOT / "samples" / "packed-posting" / "sample.json").read_text())
    fields = load_fields(meta["layouts"]["input"])
    record = format_record({"PK-ACCT": "Q-00001", "PK-BAL": Decimal("-1234567.89"), "PK-RATE": Decimal("0.0500"),
                            "PK-DAYS": Decimal(-30), "PK-ADJ": Decimal("-0.07"), "PK-LIMIT": Decimal(12300),
                            "PK-ITEMS": Decimal(-2)}, fields).encode("latin-1")
    mainframe = convert_record(record, fields, to_mainframe=True)
    assert mainframe[:7] == "Q-00001".encode("cp037") and mainframe != record
    assert convert_record(mainframe, fields) == record


def test_codec_refuses_what_it_cannot_represent():
    for bad in (float("inf"), float("-inf"), float("nan"), 1e80, 1e-80):
        with pytest.raises(ValueError):
            float_to_hfp(bad)
    fields = load_fields({"fields": [{"name": "Z", "kind": "numeric", "digits": 3, "scale": 0, "signed": True}]})
    with pytest.raises(ValueError):
        convert_record(bytes.fromhex("404040"), fields)  # spaces are not zoned digits
