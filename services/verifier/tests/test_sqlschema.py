import json
from pathlib import Path

from decimal import Decimal

from diocle_verifier.layout import format_record, load_fields
from diocle_verifier.sqlschema import build_table, main, round_trip, schema_report, validate_report

ROOT = Path(__file__).resolve().parents[3]

EVERY_KIND = {
    "record": "ALL-REC",
    "fields": [
        {"name": "ID", "kind": "alnum", "length": 4},
        {"name": "BODY", "kind": "alnum", "length": 6},
        {"name": "BODY-NUM", "kind": "numeric", "digits": 6, "scale": 0, "signed": False, "redefines": "BODY"},
        {"name": "FILLER", "kind": "alnum", "length": 1},
        {"name": "AMT", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "sign": "trailing"},
        {"name": "LEAD", "kind": "numeric", "digits": 3, "scale": 0, "signed": True, "sign": "leading"},
        {"name": "SEP", "kind": "numeric", "digits": 4, "scale": 1, "signed": True, "sign": "trailing-separate"},
        {"name": "BAL", "kind": "numeric", "digits": 9, "scale": 2, "signed": True, "usage": "packed"},
        {"name": "UPK", "kind": "numeric", "digits": 3, "scale": 0, "signed": False, "usage": "packed"},
        {"name": "DAYS", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary"},
        {"name": "ITEMS", "kind": "numeric", "digits": 9, "scale": 0, "signed": False, "usage": "binary-native"},
        {"name": "LIMIT", "kind": "numeric", "digits": 5, "scale": -2, "signed": False},
        {"name": "WIDE", "kind": "numeric", "digits": 16, "scale": 2, "signed": True, "usage": "packed"},
        {"name": "RATE", "kind": "numeric", "digits": 7, "scale": 2, "signed": True, "usage": "float", "bytes": 8},
        {"name": "RATE4", "kind": "numeric", "digits": 7, "scale": 2, "signed": True, "usage": "float", "bytes": 4},
        {"name": "MON(1)", "kind": "numeric", "digits": 3, "scale": 0, "signed": False},
        {"name": "MON(2)", "kind": "numeric", "digits": 3, "scale": 0, "signed": False},
        {"name": "EDIT", "kind": "alnum", "length": 7, "edited": "ZZZ9.99"},
        {"name": "FILLER", "kind": "alnum", "length": 2},
    ],
    "format": "fixed",
}


def _columns(table):
    return {c["field"]: c for c in table.columns}


def test_every_usage_maps_to_a_column_type():
    table = build_table(EVERY_KIND, dd="ALLIN", direction="input")
    cols = _columns(table)
    assert cols["ID"]["sqlType"] == "CHAR(4)"
    assert cols["AMT"]["sqlType"] == "DECIMAL(7,2)"
    assert cols["BAL"]["sqlType"] == "DECIMAL(11,2)" and cols["BAL"]["cobol"] == "PIC S9(9)V9(2) COMP-3"
    assert cols["DAYS"]["sqlType"] == "DECIMAL(4,0)" and cols["DAYS"]["length"] == 2
    assert cols["LIMIT"]["sqlType"] == "DECIMAL(5,0)" and cols["LIMIT"]["cobol"] == "PIC 9(3)P(2)"
    assert cols["RATE"]["sqlType"] == "DOUBLE PRECISION" and cols["RATE4"]["sqlType"] == "REAL"
    assert cols["EDIT"]["sqlType"] == "CHAR(7)" and "(edited)" in cols["EDIT"]["cobol"]
    assert [c["column"] for c in table.columns if c["field"] == "FILLER"] == ["filler", "filler_2"]
    assert cols["MON(2)"]["column"] == "mon_2"
    # every stored byte has exactly one column
    assert sum(c["length"] for c in table.columns) == table.length
    assert [c["offset"] for c in table.columns][:3] == [1, 5, 11]


def test_redefines_and_occurs_are_stated_not_stored_twice():
    table = build_table(EVERY_KIND)
    assert "BODY-NUM" not in _columns(table)
    assert _columns(table)["BODY"]["redefinedBy"] == ["BODY-NUM"]
    assert any(n.startswith("REDEFINES: BODY-NUM") for n in table.notes)
    assert "OCCURS: MON(1) .. MON(2) (2 entries) stored as columns mon_1 .. mon_2." in table.notes
    assert "also read as BODY-NUM (REDEFINES)" in table.ddl


def test_unsigned_numerics_get_a_check_and_wide_decimals_stay_exact_in_sqlite():
    table = build_table(EVERY_KIND)
    assert 'CHECK ("upk" >= 0)' in table.ddl and 'CHECK ("amt" >= 0)' not in table.ddl
    assert '"wide" DECIMAL(18,2)' in table.ddl  # the portable DDL keeps the PIC's precision
    assert '"wide" TEXT' in table.sqlite_ddl  # SQLite NUMERIC would keep only 15 digits


def test_generated_records_of_every_usage_come_back_byte_for_byte():
    report = schema_report({"program": "ALL", "files": [{"dd": "ALLIN", "direction": "input", "layout": EVERY_KIND}]},
                           random_count=300)
    rt = report["tables"][0]["roundTrip"]
    assert rt["records"] > 300 and rt["identical"] == rt["records"] and rt["failures"] == []
    assert report["summary"]["passed"]
    validate_report(report)


def test_a_non_canonical_sign_nibble_is_caught():
    # Unsigned packed written with sign C (as some producers do); a DECIMAL holds the value but not the nibble.
    spec = {"record": "R", "fields": [{"name": "UPK", "kind": "numeric", "digits": 3, "scale": 0, "signed": False,
                                       "usage": "packed"}], "format": "fixed"}
    table = build_table(spec)
    canonical = format_record({"UPK": 123}, table.fields)
    odd = bytes.fromhex("123C").decode("latin-1")
    rt = round_trip(table, [("file", [canonical, odd])])
    assert rt["records"] == 2 and rt["identical"] == 1
    assert rt["failures"][0]["record"] == 2 and rt["failures"][0]["field"] == "UPK"
    assert "x'123C'" in rt["failures"][0]["detail"] and "x'123F'" in rt["failures"][0]["detail"]


def test_bad_numeric_content_and_values_beyond_the_pic_are_reported():
    spec = {"record": "R", "fields": [
        {"name": "AMT", "kind": "numeric", "digits": 3, "scale": 2, "signed": False},
        {"name": "DAYS", "kind": "numeric", "digits": 4, "scale": 0, "signed": True, "usage": "binary"}],
        "format": "fixed"}
    table = build_table(spec)
    good = format_record({"AMT": 1, "DAYS": 9999}, table.fields)
    letters = "12A45" + good[5:]
    too_big = good[:5] + (32767).to_bytes(2, "big").decode("latin-1")  # fits two bytes, not PIC S9(4)
    rt = round_trip(table, [("file", [good, letters, too_big])])
    assert rt["identical"] == 1
    details = {f["record"]: f["detail"] for f in rt["failures"]}
    assert "not a valid number" in details[2]
    assert "does not fit DECIMAL(4,0)" in details[3]


def test_short_records_are_reported_not_padded_for_fixed_files():
    table = build_table({"record": "R", "fields": [{"name": "ID", "kind": "alnum", "length": 4}], "format": "fixed"})
    rt = round_trip(table, [("file", ["ABCD", "AB"])])
    assert rt["identical"] == 1 and "2 bytes" in rt["failures"][0]["detail"]


def test_line_records_compare_with_trailing_spaces_like_the_verifier():
    table = build_table({"record": "R", "fields": [{"name": "ID", "kind": "alnum", "length": 4},
                                                    {"name": "N", "kind": "alnum", "length": 3}]})
    assert round_trip(table, [("file", ["ABCDXY\n"])])["identical"] == 1


def test_table_names_do_not_collide_when_layouts_share_a_record_name():
    meta = {"files": [{"dd": "IN", "direction": "input", "layout": {"record": "R", "fields": EVERY_KIND["fields"][:1]}},
                      {"dd": "OUT", "direction": "output", "layout": {"record": "R", "fields": EVERY_KIND["fields"][:1]}}]}
    report = schema_report(meta, random_count=5)
    assert [t["table"] for t in report["tables"]] == ["r", "r_out"]


def test_every_sample_in_the_repository_round_trips(tmp_path):
    samples = sorted(ROOT.glob("samples/*/sample.json")) + sorted(ROOT.glob("eval/samples/*/sample.json"))
    assert len(samples) >= 10
    for sample in samples:
        report = schema_report(json.loads(sample.read_text()), random_count=50)
        assert report["summary"]["passed"], (sample, report["tables"])


def test_cli_writes_the_schema_and_a_valid_report_including_ebcdic_golden_files(tmp_path):
    sample = ROOT / "samples" / "packed-posting"
    code = main([str(sample), "--out", str(tmp_path), "--ebcdic",
                 "--data", f"PKIN={sample / 'golden' / 'input.ebcdic'}",
                 "--data", f"PKOUT={sample / 'golden' / 'expected.ebcdic'}"])
    assert code == 0
    assert 'CREATE TABLE "pk_rec"' in (tmp_path / "schema.sql").read_text()
    report = json.loads((tmp_path / "sql-schema.json").read_text())
    validate_report(report)
    assert any("input.ebcdic (EBCDIC)" in t["roundTrip"]["sources"] for t in report["tables"])


def _fixed(fields):
    return {"record": "R", "fields": fields, "format": "fixed"}


def test_a_ddl_type_that_cannot_hold_the_data_fails_the_proof():
    # SQLite ignores declared sizes, so the proof checks values against the type as published.
    table = build_table(_fixed([{"name": "AMT", "kind": "numeric", "digits": 5, "scale": 2, "signed": True,
                                 "usage": "packed"}, {"name": "ID", "kind": "alnum", "length": 3}]))
    record = format_record({"AMT": Decimal("123.45"), "ID": "ABC"}, table.fields)
    assert round_trip(table, [("file", [record])])["identical"] == 1
    table.columns[0]["sqlType"] = "DECIMAL(7,0)"  # a wrong scale
    rt = round_trip(table, [("file", [record])])
    assert rt["identical"] == 0 and "more decimal places than DECIMAL(7,0)" in rt["failures"][0]["detail"]
    table.columns[0]["sqlType"], table.columns[1]["sqlType"] = "DECIMAL(7,2)", "CHAR(2)"  # too short
    rt = round_trip(table, [("file", [record])])
    assert rt["identical"] == 0 and "longer than CHAR(2)" in rt["failures"][0]["detail"]


def test_fields_with_the_same_name_keep_their_own_bytes():
    table = build_table(_fixed([{"name": "FILLER", "kind": "alnum", "length": 1},
                                {"name": "ID", "kind": "alnum", "length": 2},
                                {"name": "FILLER", "kind": "alnum", "length": 3}]))
    rt = round_trip(table, [("file", ["AXYBCD", "BXYBCD"])])
    assert rt["identical"] == 2 and rt["failures"] == []


def test_comp5_holds_its_full_byte_range():
    table = build_table(_fixed([{"name": "N", "kind": "numeric", "digits": 4, "scale": 0, "signed": False,
                                 "usage": "binary-native"}]))
    assert table.columns[0]["sqlType"] == "DECIMAL(5,0)"
    rt = round_trip(table, [("file", [(65535).to_bytes(2, "little").decode("latin-1")])])
    assert rt["identical"] == 1


def test_a_float_nan_is_reported_not_a_crash():
    import struct

    table = build_table(_fixed([{"name": "RATE", "kind": "numeric", "digits": 7, "scale": 2, "signed": True,
                                 "usage": "float", "bytes": 8}]))
    nan = struct.pack("<d", float("nan")).decode("latin-1")
    rt = round_trip(table, [("file", [nan, struct.pack("<d", 1.5).decode("latin-1")])])
    assert rt["identical"] == 1 and rt["failures"][0]["record"] == 1


def test_a_group_redefines_and_long_line_records_are_handled():
    table = build_table({"record": "R", "fields": [
        {"name": "A", "kind": "alnum", "length": 2}, {"name": "B", "kind": "alnum", "length": 2},
        {"name": "C", "kind": "numeric", "digits": 4, "scale": 0, "signed": False, "redefines": "GRP"}]})
    assert any("group GRP" in n for n in table.notes)
    rt = round_trip(table, [("file", ["ABCD", "ABCDEF"])])
    assert rt["identical"] == 1 and "6 bytes" in rt["failures"][0]["detail"]


def test_wide_alphanumerics_use_varchar_and_comments_cannot_break_out():
    table = build_table({"record": "R\nDROP TABLE x", "fields": [{"name": "TXT", "kind": "alnum", "length": 300}]})
    assert table.columns[0]["sqlType"] == "VARCHAR(300)"
    assert all(line.startswith(("--", "CREATE", "  ", ")")) for line in table.ddl.splitlines())


def test_bad_data_arguments_are_refused(tmp_path):
    import pytest

    with pytest.raises(SystemExit):
        main([str(ROOT / "samples" / "packed-posting"), "--data", "NOPE=x"])
