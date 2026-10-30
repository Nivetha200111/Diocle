"""Whole-repository build check: the contract, the real checks on small synthetic repositories (javac is real), and one
deliberately broken fixture per finding. No model is called. Domain-class tests use tiny synthetic classes written here."""
import json
import shutil
import zipfile
from pathlib import Path

import jsonschema
import pytest

from diocle_verifier import buildcheck as bc

pytestmark = pytest.mark.skipif(shutil.which("javac") is None, reason="javac not installed")
SCHEMA = json.loads((Path(bc.__file__).resolve().parents[3] / "contracts" / "build-report.schema.json").read_text())


def cobol(name, body="           GOBACK.\n", ws="", linkage="", using="", copy=""):
    return (f"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. {name}.\n       DATA DIVISION.\n"
            f"       WORKING-STORAGE SECTION.\n{copy}{ws}"
            + (f"       LINKAGE SECTION.\n{linkage}" if linkage else "")
            + f"       PROCEDURE DIVISION{(' USING ' + using) if using else ''}.\n{body}")


def program(root, name, src, java=None, copybooks=None, jname=None):
    """A delivered program: sample dir (COBOL + copybooks + sample.json) and a Java dir."""
    sample, jdir = root / "samples" / name.lower(), root / "java" / name.lower()
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    (sample / "src" / f"{name}.cbl").write_text(src)
    for member, text in (copybooks or {}).items():
        (sample / "copybooks" / f"{member}.cpy").write_text(text)
    (sample / "sample.json").write_text(json.dumps({"source": f"src/{name}.cbl", "modules": [], "copybookDir": "copybooks",
                                                     "javaConversion": {"mainClass": name.capitalize()}}))
    jdir.mkdir(parents=True)
    cls = name.capitalize()
    (jdir / (jname or f"{cls}.java")).write_text(java if java is not None else f"public class {cls} {{ public static void main(String[] a) {{}} }}\n")
    return {"name": name, "javaDir": jdir, "sampleDir": sample}


def check(programs, **kw):
    report = bc.build_check(programs, **kw)
    jsonschema.validate(report, SCHEMA)
    return report


def test_contract_rejects_invalid_reports(tmp_path):
    good = check([program(tmp_path, "AAA", cobol("AAA"))])
    jsonschema.validate(good, SCHEMA)
    for broken in ({**good, "verdict": "maybe"}, {**good, "extra": 1}, {k: v for k, v in good.items() if k != "scope"},
                   {**good, "whole": {**good["whole"], "compile": {"status": "ok", "diagnostics": ["rm -rf / ; not a diagnostic"]}}},
                   {**good, "version": "0.2"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(broken, SCHEMA)


def test_a_clean_repository_passes_and_says_what_it_did_not_check(tmp_path):
    ws = "       01  WS-A   PIC X(10).\n"
    lk = "       01  LK-A   PIC X(10).\n"
    a = program(tmp_path, "CALLER", cobol("CALLER", "           CALL 'CALLEE' USING WS-A.\n           GOBACK.\n", ws=ws))
    b = program(tmp_path, "CALLEE", cobol("CALLEE", linkage=lk, using="LK-A"))
    r = check([a, b])
    assert r["verdict"] == "pass" and r["reasons"] == []
    assert r["whole"]["compile"]["status"] == "ok" and r["whole"]["sources"] == 2
    assert r["calls"]["checked"] == 1 and r["calls"]["findings"] == []
    assert [p["mainClass"] for p in r["programs"]] == ["Caller", "Callee"]
    assert {"id": "CALLEE", "kind": "program"} in r["graph"]["nodes"]
    assert {"from": "CALLER", "to": "CALLEE", "kind": "call"} in r["graph"]["edges"]
    assert r["scope"]["notChecked"]


def test_two_programs_defining_the_same_class_are_a_collision(tmp_path):
    a = program(tmp_path, "AAA", cobol("AAA"), java="public class Shared { int a() { return 1; } }\n", jname="Shared.java")
    b = program(tmp_path, "BBB", cobol("BBB"), java="public class Shared { int a() { return 2; } }\n", jname="Shared.java")
    r = check([a, b])
    assert r["verdict"] == "fail"
    assert r["classCollisions"] == [{"class": "Shared", "between": ["AAA", "BBB"]}]
    assert r["whole"]["compile"]["status"] == "fail"
    assert any("duplicate class: Shared" in d for d in r["whole"]["compile"]["diagnostics"])
    assert [p["compile"]["status"] for p in r["programs"]] == ["ok", "ok"]  # each alone compiles: only together it breaks


def test_byte_identical_copies_of_a_class_are_not_a_collision(tmp_path):
    same = "public class Shared { int a() { return 1; } }\n"
    r = check([program(tmp_path, "AAA", cobol("AAA"), java=same, jname="Shared.java"), program(tmp_path, "BBB", cobol("BBB"), java=same, jname="Shared.java")])
    assert r["classCollisions"] == [] and r["whole"]["compile"]["status"] == "ok" and r["verdict"] == "pass"


def test_a_missing_symbol_is_flagged_with_file_and_line(tmp_path):
    a = program(tmp_path, "AAA", cobol("AAA"), java="public class Aaa {\n  void f() {\n    Bbb.run();\n  }\n}\n")
    r = check([a])
    assert r["verdict"] == "fail"
    assert r["whole"]["compile"]["diagnostics"] == ["AAA/Aaa.java:3: error: cannot find symbol [symbol: variable Bbb]"]
    assert r["programs"][0]["compile"]["status"] == "fail"


def test_a_symbol_defined_by_another_program_resolves_in_the_whole_compile_only(tmp_path):
    a = program(tmp_path, "AAA", cobol("AAA"), java="public class Aaa { void f() { Bbb.run(); } }\n")
    b = program(tmp_path, "BBB", cobol("BBB"), java="public class Bbb { static void run() {} }\n")
    r = check([a, b])
    assert r["whole"]["compile"]["status"] == "ok"  # together they compile; alone, Aaa does not
    assert r["programs"][0]["compile"]["status"] == "fail" and r["verdict"] == "fail"


CALLEE = cobol("SUBPGM", linkage="       01  LK-AMT  PIC S9(9)V99 COMP-3.\n       01  LK-NAME PIC X(10).\n", using="LK-AMT LK-NAME")
WS = "       01  WS-AMT  PIC S9(7)V99 COMP-3.\n       01  WS-NAME PIC X(20).\n"


def test_call_with_a_too_short_argument_is_flagged_on_its_exact_line(tmp_path):
    caller = cobol("MAINPGM", "           CALL 'SUBPGM' USING WS-AMT WS-NAME.\n           GOBACK.\n", ws=WS)
    r = check([program(tmp_path, "MAINPGM", caller), program(tmp_path, "SUBPGM", CALLEE)])
    fails = [f for f in r["calls"]["findings"] if f["severity"] == "fail"]
    assert [(f["kind"], f["line"], f["caller"], f["callee"]) for f in fails] == [("length", 8, "MAINPGM", "SUBPGM")]
    assert "5 bytes" in fails[0]["message"] and "is 6" in fails[0]["message"]
    warns = [f for f in r["calls"]["findings"] if f["severity"] == "warn"]
    assert [(f["kind"], f["line"]) for f in warns] == [("length", 8)]  # WS-NAME 20 into X(10): the callee sees a prefix
    assert r["verdict"] == "fail"


def test_call_arity_and_unresolved_targets(tmp_path):
    caller = cobol("MAINPGM", "           CALL 'SUBPGM' USING WS-AMT.\n           CALL 'NOPGM' USING WS-AMT.\n"
                              "           CALL 'CEE3ABD' USING WS-AMT.\n           GOBACK.\n", ws=WS)
    r = check([program(tmp_path, "MAINPGM", caller), program(tmp_path, "SUBPGM", CALLEE)])
    got = {(f["kind"], f["severity"], f["line"]) for f in r["calls"]["findings"]}
    assert ("arity", "fail", 8) in got and ("unresolved", "fail", 9) in got and ("runtime-routine", "info", 10) in got
    assert r["calls"]["checked"] == 3


def test_dynamic_call_is_a_warning_not_a_pass(tmp_path):
    caller = cobol("MAINPGM", "           ACCEPT WS-PGM.\n           CALL WS-PGM USING WS-AMT.\n           GOBACK.\n",
                   ws=WS + "       01  WS-PGM  PIC X(8).\n")
    r = check([program(tmp_path, "MAINPGM", caller)])
    assert r["verdict"] == "warn" and r["calls"]["findings"][0]["kind"] == "dynamic"


BOOK_A = "       01  ACCT-REC.\n           05  ACCT-ID   PIC X(10).\n           05  ACCT-BAL  PIC S9(7)V99.\n"
BOOK_B = "       01  ACCT-REC.\n           05  ACCT-ID   PIC X(12).\n           05  ACCT-BAL  PIC S9(7)V99.\n"


def test_copybook_with_a_different_layout_between_two_files_is_drift(tmp_path):
    cp = "       COPY ACCT.\n"
    r = check([program(tmp_path, "AAA", cobol("AAA", copy=cp), copybooks={"ACCT": BOOK_A}),
               program(tmp_path, "BBB", cobol("BBB", copy=cp), copybooks={"ACCT": BOOK_B})])
    [d] = r["copybooks"]["drift"]
    assert d["copybook"] == "ACCT" and d["kind"] == "layout" and d["severity"] == "fail" and r["verdict"] == "fail"
    assert "ACCT-ID" in d["message"] and "X(10)" in d["message"] and "X(12)" in d["message"]
    assert sorted(p for v in d["versions"] for p in v["programs"]) == ["AAA", "BBB"]


def test_copybook_that_differs_only_in_comments_and_spacing_is_not_drift_but_a_value_change_is_a_warning(tmp_path):
    cp = "       COPY ACCT.\n"
    commented = "      * the account record\n" + BOOK_A.replace("PIC X(10)", "PIC  X(10)")
    r = check([program(tmp_path, "AAA", cobol("AAA", copy=cp), copybooks={"ACCT": BOOK_A}),
               program(tmp_path, "BBB", cobol("BBB", copy=cp), copybooks={"ACCT": commented})])
    assert r["copybooks"]["drift"] == [] and r["verdict"] == "pass"
    valued = BOOK_A.replace("PIC X(10).", "PIC X(10) VALUE 'A'.")
    r = check([program(tmp_path / "w", "AAA", cobol("AAA", copy=cp), copybooks={"ACCT": BOOK_A}),
               program(tmp_path / "w", "BBB", cobol("BBB", copy=cp), copybooks={"ACCT": valued})])
    assert [(d["kind"], d["severity"]) for d in r["copybooks"]["drift"]] == [("content", "warn")] and r["verdict"] == "warn"


def test_dioSql_is_added_for_the_compile_and_reported_not_hidden(tmp_path):
    java = "public class Aaa { void f() throws Exception { DioSql.connect(); } }\n"
    r = check([program(tmp_path, "AAA", cobol("AAA"), java=java)])
    assert r["whole"]["supportClasses"] == ["DioSql.java"] and r["whole"]["compile"]["status"] == "ok"
    assert r["verdict"] == "warn" and "DioSql" in r["reasons"][0]


def test_scanner_ignores_comments_strings_and_nested_types():
    src = 'package p.q;\n// class Fake\n/* class Fake2 */\npublic class A { String s = "class Fake3"; static class Inner {} }\nclass B {}\ninterface C {}\n'
    assert bc.top_level_types(src) == ("p.q", ["A", "B", "C"])


# ---- EXPERIMENTAL: the customer's own classes on the classpath ------------------------------------------------------

def domain_dir(root):
    d = root / "customer"
    (d / "com" / "acme").mkdir(parents=True)
    (d / "com" / "acme" / "Account.java").write_text("package com.acme;\npublic class Account { public String id() { return \"x\"; } }\n")
    return d


def test_programs_compile_beside_the_customers_classes_and_a_missing_class_is_flagged(tmp_path):
    uses = "public class Aaa { String f() { return new com.acme.Account().id(); } }\n"
    without = check([program(tmp_path, "AAA", cobol("AAA"), java=uses)])
    assert without["verdict"] == "fail" and "package com.acme does not exist" in without["whole"]["compile"]["diagnostics"][0]
    r = check([program(tmp_path / "w", "AAA", cobol("AAA"), java=uses)], domain_classes=domain_dir(tmp_path))
    assert r["verdict"] == "pass" and r["whole"]["domainClasses"] == {
        "kind": "source", "entries": 1, "ownCompile": {"status": "ok", "javacExit": 0, "diagnostics": []}}


def test_a_class_with_the_name_of_a_domain_class_is_reported(tmp_path):
    java = "package com.acme;\npublic class Account { }\n"
    r = check([program(tmp_path, "AAA", cobol("AAA"), java=java, jname="Account.java")], domain_classes=domain_dir(tmp_path))
    assert r["classCollisions"] == [{"class": "com.acme.Account", "between": ["AAA", "domain classes"]}] and r["verdict"] == "fail"


def test_domain_classes_that_do_not_compile_alone_are_the_customers_problem_and_a_warning(tmp_path):
    d = tmp_path / "customer"
    d.mkdir()
    (d / "Broken.java").write_text("public class Broken { void f() { missing(); } }\n")
    r = check([program(tmp_path, "AAA", cobol("AAA"))], domain_classes=d)
    assert r["whole"]["domainClasses"]["ownCompile"]["status"] == "fail" and r["verdict"] == "warn"


def make_jar(root, entries=None):
    src = root / "jarsrc"
    src.mkdir()
    (src / "Money.java").write_text("public class Money { public static long cents() { return 1; } }\n")
    out = root / "jarout"
    out.mkdir()
    import subprocess

    subprocess.run(["javac", "-proc:none", "-d", str(out), str(src / "Money.java")], check=True)
    jar = root / "customer.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.write(out / "Money.class", "Money.class")
        for name in entries or []:
            z.writestr(name, b"x")
    return jar


def test_a_jar_is_put_on_the_classpath_and_listed_but_never_extracted_or_run(tmp_path):
    jar = make_jar(tmp_path)
    uses = "public class Aaa { long f() { return Money.cents(); } }\n"
    r = check([program(tmp_path, "AAA", cobol("AAA"), java=uses)], domain_classes=jar)
    assert r["verdict"] == "pass" and r["whole"]["domainClasses"]["kind"] == "jar" and r["whole"]["domainClasses"]["entries"] == 1
    clash = check([program(tmp_path / "w", "AAA", cobol("AAA"), java="public class Money { }\n", jname="Money.java")], domain_classes=jar)
    assert clash["classCollisions"] == [{"class": "Money", "between": ["AAA", "domain classes"]}]


def test_unsafe_domain_inputs_are_refused(tmp_path):
    progs = [program(tmp_path, "AAA", cobol("AAA"))]
    with pytest.raises(ValueError):
        bc.build_check(progs, domain_classes=tmp_path / "missing")
    notjar = tmp_path / "x.jar"
    notjar.write_text("not a zip")
    with pytest.raises(ValueError):
        bc.build_check(progs, domain_classes=notjar)
    (tmp_path / "t").mkdir()
    with pytest.raises(ValueError):  # an entry that leaves the archive
        bc.build_check(progs, domain_classes=make_jar(tmp_path / "t", ["../evil.class"]))
    link = tmp_path / "link"
    link.symlink_to(domain_dir(tmp_path))
    with pytest.raises(ValueError):
        bc.build_check(progs, domain_classes=link)


def test_symlinked_java_files_in_a_domain_directory_are_not_followed(tmp_path):
    d = domain_dir(tmp_path)
    secret = tmp_path / "secret.java"
    secret.write_text("public class Secret { }\n")
    (d / "Link.java").symlink_to(secret)
    r = check([program(tmp_path, "AAA", cobol("AAA"))], domain_classes=d)
    assert r["whole"]["domainClasses"]["entries"] == 1


def test_markdown_keeps_only_a_conservative_character_set(tmp_path):
    r = check([program(tmp_path, "AAA", cobol("AAA"))])
    r["reasons"] = ["[click](http://evil) <script>|`x`"]
    md = bc.render_markdown({**r, "verdict": "warn"})
    assert "<script>" not in md and "](http" not in md and "`x`" not in md and "# Build report: WARN" in md
