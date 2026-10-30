"""EXPERIMENTAL --domain-classes: only public signatures reach the translator; nothing is compiled, loaded or run here.
The model is a scripted test double (no network)."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from openai.types.chat import ChatCompletionMessage

from diocle_converter import domain
from diocle_converter.client import ModelClient
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace
from test_converter import ScriptedSDK, settings

ADDFEE = Path(__file__).resolve().parents[3] / "samples" / "addfee"
POJO = """package com.acme;
/** SECRET-BODY-COMMENT */
public class AcctInRecord {
    public static final int WIDTH = 42;
    private String id = "hidden-initializer";
    public String acctId = "x";
    public AcctInRecord(String id) { this.id = "BODY-STATEMENT"; }
    public String getId() { return id.trim(); }
    public void setId(String id) { this.id = id; }
    private void internal() {}
    static class Inner { public int nested; }
}
"""


def domain_dir(tmp_path):
    d = tmp_path / "customer"
    d.mkdir()
    (d / "AcctInRecord.java").write_text(POJO)
    return d


def test_the_signature_has_public_members_and_no_bodies_comments_or_initializers(tmp_path):
    sigs = domain.load_signatures(domain_dir(tmp_path))
    sig = sigs["AcctInRecord"]
    assert sig.splitlines()[0] == "public class AcctInRecord"
    for member in ("public static final int WIDTH", "public String acctId", "public AcctInRecord(String id)",
                   "public String getId()", "public void setId(String id)"):
        assert member in sig
    for secret in ("SECRET-BODY-COMMENT", "BODY-STATEMENT", "hidden-initializer", "internal", "nested", '"x"', "= 42"):
        assert secret not in sig


def test_class_names_match_cobol_records_after_dropping_punctuation_case_and_rec(tmp_path):
    program = Program.load(ADDFEE)
    found = domain.matches(program, domain.load_signatures(domain_dir(tmp_path)))
    assert set(found) == {"ACCT-IN-REC", "ACCTIN"} and found["ACCT-IN-REC"][0] == "AcctInRecord"  # record name and copybook name
    assert domain.matches(program, {"Unrelated": "public class Unrelated"}) == {} and domain.hint({}) == ""


def test_the_translator_prompt_gets_the_signature_and_the_not_a_dependency_rule(tmp_path):
    program = Program.load(ADDFEE)
    hint = domain.hint(domain.matches(program, domain.load_signatures(domain_dir(tmp_path))))
    answer = json.dumps({"mainClass": program.main_class, "javaSource": f"public class {program.main_class} {{}}", "notes": "n"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    translate(program, ModelClient(settings(), _sdk=sdk), Workspace(tmp_path / "j"), domain_hint=hint)
    system = sdk.requests[0]["messages"][0]["content"]
    assert "COBOL record ACCT-IN-REC / ACCTIN <-> Java class AcctInRecord" in system and "public String getId()" in system
    assert "do NOT reference, import or extend these classes" in system and "BODY-STATEMENT" not in system
    assert "BODY-STATEMENT" not in sdk.requests[0]["messages"][1]["content"]


def test_without_the_option_the_prompt_is_unchanged(tmp_path):
    program = Program.load(ADDFEE)
    answer = json.dumps({"mainClass": program.main_class, "javaSource": "public class X {}", "notes": "n"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    translate(program, ModelClient(settings(), _sdk=sdk), Workspace(tmp_path / "j"))
    assert "domain classes" not in sdk.requests[0]["messages"][0]["content"].lower()


@pytest.mark.skipif(shutil.which("javap") is None or shutil.which("javac") is None, reason="needs a JDK")
def test_a_jar_is_read_with_javap_only(tmp_path):
    src = tmp_path / "s"
    src.mkdir()
    (src / "AcctInRecord.java").write_text("public class AcctInRecord { public String getId() { throw new Error(\"static code must never run\"); } static { if (System.nanoTime() > 0) throw new Error(\"x\"); } }\n")
    out = tmp_path / "o"
    out.mkdir()
    subprocess.run(["javac", "-proc:none", "-d", str(out), str(src / "AcctInRecord.java")], check=True)
    jar = tmp_path / "c.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.write(out / "AcctInRecord.class", "AcctInRecord.class")
    sigs = domain.load_signatures(jar)
    assert "public java.lang.String getId();" in sigs["AcctInRecord"]  # javap listing; the static initializer never ran


def test_unsafe_inputs_are_refused(tmp_path):
    for bad in (tmp_path / "missing", ):
        with pytest.raises(ValueError):
            domain.load_signatures(bad)
    notjar = tmp_path / "x.jar"
    notjar.write_text("x")
    with pytest.raises(ValueError):
        domain.load_signatures(notjar)
    link = tmp_path / "link"
    link.symlink_to(domain_dir(tmp_path))
    with pytest.raises(ValueError):
        domain.load_signatures(link)
    evil = tmp_path / "evil.jar"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../x.class", b"x")
    with pytest.raises(ValueError):
        domain.load_signatures(evil)
