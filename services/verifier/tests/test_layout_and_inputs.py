import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from diocle_verifier.inputs import generate_cases, generate_for_layout
from diocle_verifier.layout import format_record, load_fields, parse_record, record_length, redefine_views
from diocle_verifier import verify as verify_module
from diocle_verifier.verify import passes, verify_sample

ROOT = Path(__file__).resolve().parents[3]

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


# ---- REDEFINES views: the generator fills a shared body with real values ----------------------------------------------

CHQCLR = ROOT / "eval" / "samples" / "chqclr"


def _chqclr_layout():
    return json.loads((CHQCLR / "sample.json").read_text())["layouts"]["input"]


def test_views_are_grouped_by_the_length_of_the_body_they_fill():
    views = redefine_views(_chqclr_layout())
    assert [[f.name for f in v] for v in views["CQ-BODY"]] == [
        ["CQ-ACCT", "CQ-NUMBER", "CQ-AMOUNT", "CQ-DATE", "FILLER"], ["RT-ACCT", "RT-NUMBER", "RT-REASON", "RT-FEE", "FILLER"]]


def test_a_view_that_does_not_fill_the_body_is_not_guessed():
    base = {"name": "BODY", "kind": "alnum", "length": 10}
    short = {"name": "A", "kind": "alnum", "length": 4, "redefines": "BODY"}
    over = {"name": "B", "kind": "alnum", "length": 12, "redefines": "BODY"}
    assert redefine_views({"fields": [base, short]}) == {}
    assert redefine_views({"fields": [base, over]}) == {}
    assert redefine_views({"fields": [{**base, "kind": "numeric", "digits": 10, "scale": 0}, short]}) == {}


def test_generated_chqclr_records_are_valid_and_carry_real_values():
    cases = generate_for_layout(_chqclr_layout(), seed=4243, random_count=1000)
    records = [c.record for c in cases if c.source == "random"]
    assert len(records) == 1000 and all(len(r) == 40 for r in records)
    boundary = [c.record for c in cases if c.source == "boundary"]
    assert all(r[19] in "+-" for r in boundary if r[0] == "C")  # boundary records carry a real body too
    cheques = [r for r in records if r[0] == "C"]
    returns = [r for r in records if r[0] == "R"]
    assert len(cheques) > 400 and len(returns) > 400 and len(cheques) + len(returns) == 1000
    assert all(r[11:19].isdigit() and r[19] in "+-" and r[20:29].isdigit() and r[29:37].isdigit() and r[37:] == "   " for r in cheques)
    assert all(r[11:19].isdigit() and r[19:21] in ("NS", "SP") and r[21:26].isdigit() and r[26:] == " " * 14 for r in returns)
    assert len({r[20:29] for r in cheques}) > 200 and len({r[21:26] for r in returns}) > 200


def test_records_without_views_are_exactly_what_they_always_were():
    # Hashes of the records from the generator before views existed (commit 785bf3f): a layout without a redefined
    # alphanumeric body keeps its records, seed for seed.
    pinned = {"samples/interest-accrual": "636558dc611442c793843453f43c4484df8f881593af81b9f9450384206302cd",
              "samples/txn-posting": "e827a5c6f071ee15caaa1c1811f38460925fa8302e7fee9d059dec303c8fdbf1",
              "eval/samples/loanamrt": "3f21abd890d207c514d39f87beedaaee8937d289dee9c3068c22733a89b303e3"}
    for sample, sha in pinned.items():
        layout = json.loads((ROOT / sample / "sample.json").read_text())["layouts"]["input"]
        records = [c.record for c in generate_for_layout(layout, seed=8801, random_count=50)]
        assert hashlib.sha256("\n".join(records).encode("latin-1")).hexdigest() == sha


def test_a_numeric_filler_in_a_view_gets_a_number():
    spec = {"fields": [{"name": "BODY", "kind": "alnum", "length": 8},
                       {"name": "A", "kind": "alnum", "length": 4, "redefines": "BODY"},
                       {"name": "FILLER", "kind": "numeric", "digits": 4, "scale": 0, "signed": False, "redefines": "BODY"}]}
    records = [c.record for c in generate_for_layout(spec, seed=1, random_count=20)]
    assert all(len(r) == 8 and r[4:].isdigit() for r in records)


def test_two_fields_with_the_same_name_keep_the_record_length():
    spec = {"fields": [{"name": "BODY", "kind": "alnum", "length": 5}, {"name": "BODY", "kind": "alnum", "length": 11},
                       {"name": "A", "kind": "alnum", "length": 11, "redefines": "BODY"}]}
    assert redefine_views(spec) == {}
    assert all(len(c.record) == 16 for c in generate_for_layout(spec, seed=1, random_count=5))


@pytest.mark.toolchain
def test_a_fee_fault_on_ordinary_returns_is_caught_only_with_real_values(tmp_path, monkeypatch):
    """The failure this fix exists for: Java that charges no NSF fee at all. Without views every generated fee is zero and it
    passes 1,004 of 1,004; with views the same check fails. GnuCOBOL and the JDK are real; the fault is planted here."""
    java = tmp_path / "java"
    shutil.copytree(ROOT / "eval" / "showcase" / "chqclr-20261028-214355" / "java", java)
    source = java / "Chqclr.java"
    text = source.read_text()
    good = "outFee = truncUnsigned(fee.multiply(BigDecimal.valueOf(2)), 3, 2);"
    assert good in text
    source.write_text(text.replace(good, "outFee = BigDecimal.ZERO.setScale(2);"))
    with monkeypatch.context() as old:  # the generator as it was: placeholder bodies miss the fault
        old.setattr(verify_module, "generate_for_layout", lambda spec, *, seed, random_count: generate_cases(
            load_fields(spec), seed=seed, random_count=random_count))
        assert passes(verify_sample(CHQCLR, java, seed=4243, random_count=200))
    caught = verify_sample(CHQCLR, java, seed=4243, random_count=200)
    assert not passes(caught) and any("CL-FEE" in (r.get("diff") or "") for r in caught["results"])
    source.write_text(text)
    assert passes(verify_sample(CHQCLR, java, seed=4243, random_count=200))
