import io
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import diocle_labels as L  # noqa: E402
import diocle_summarize as S  # noqa: E402

ROOT = HERE.parents[1]
CORE_TS = (ROOT / "editors" / "vscode" / "src" / "core.ts").read_text()


def ts_text(label_case):
    """The wording literal of one `case` in core.ts badgeFor, template placeholders left in."""
    m = re.search(r'case "%s":.*?text: [`"](.*?)[`"] \}' % re.escape(label_case), CORE_TS, re.S)
    return m.group(1)


def check_result(diags, ok=True):
    return {"version": "0.1", "command": "check", "ok": ok, "diagnostics": diags}


# ---- label parity with the VS Code extension ----
def test_label_parity_with_vscode_core():
    assert L.badge_for({"assurance": "certified"})[1] == ts_text("certified")
    n_text = ts_text("certified-against-repaired-cobol").replace("${n}", "3").replace('${n === 1 ? "" : "s"}', "s")
    assert L.badge_for({"assurance": "certified-against-repaired-cobol", "repairedLines": 3})[1] == n_text
    assert "1 line (" in L.badge_for({"assurance": "certified-against-repaired-cobol", "repairedLines": 1})[1]
    for a, key in (("compiled-unverified", "compiled-unverified"), ("skipped", "skipped")):
        want = ts_text(key).replace("${reason}", " Reason: why")
        assert L.badge_for({"assurance": a, "assuranceReason": "why"})[1] == want
    assert L.badge_for({"assurance": "failed", "assuranceReason": "why"})[1] == "No Java was shown to match. Reason: why"
    labels = re.findall(r'label: "([A-Z ,]+)"', CORE_TS)
    for want in ("CERTIFIED", "CERTIFIED AGAINST REPAIRED COBOL", "COMPILED, NOT VERIFIED", "SKIPPED", "FAILED"):
        assert want in labels
    assert L.badge_for({"assurance": "certified-against-repaired-cobol"})[0] == "CERTIFIED AGAINST REPAIRED COBOL"
    assert L.badge_for({"assurance": "compiled-unverified"})[0] == "COMPILED, NOT VERIFIED"


def test_only_certified_says_certified_without_qualifier():
    for a in L.ASSURANCES:
        label = L.badge_for({"assurance": a})[0]
        assert (label == "CERTIFIED") == (a == "certified")


# ---- command-line builder ----
def test_build_args_check_and_convert():
    assert L.build_args("check", "C:\\My Code\\A B.cbl") == ["-P", "-m", "diocle_converter", "editor", "check", "C:\\My Code\\A B.cbl"]
    a = L.build_args("convert", "x.cbl", max_usd=0.25, copybooks=["C:\\cp books"])
    assert a == ["-P", "-m", "diocle_converter", "editor", "convert", "x.cbl", "--copybooks", "C:\\cp books", "--max-usd", "0.25"]
    assert "--convert-anyway" not in a
    assert L.build_args("convert", "x.cbl", convert_anyway=True)[-1] == "--convert-anyway"


def test_max_usd_clamped_and_never_shell_string():
    assert L.build_args("convert", "x", max_usd=50)[-1 - 0 if False else 6 + 0] == "1.00" or "1.00" in L.build_args("convert", "x", max_usd=50)
    assert "0.01" in L.build_args("convert", "x", max_usd=-3)
    assert "0.25" in L.build_args("convert", "x", max_usd=float("nan"))
    assert "0.25" in L.build_args("convert", "x", max_usd="abc")
    cmd = L.build_command("py", "check", 'a "quoted"; rm -rf.cbl')
    assert isinstance(cmd, list) and cmd[-1] == 'a "quoted"; rm -rf.cbl'
    with pytest.raises(ValueError):
        L.build_args("rm", "x")


# ---- parsing and validation ----
GOOD_CHECK = json.dumps(check_result([{"file": "NOPERIOD.cbl", "line": 5, "severity": "error", "message": "syntax error"}], ok=False))


def test_parse_result_accepts_last_line_and_rejects_bad():
    ok, v = L.parse_result("noise\n" + GOOD_CHECK + "\n", "check")
    assert ok and v["diagnostics"][0]["line"] == 5
    assert not L.parse_result("", "check")[0]
    assert not L.parse_result("not json", "check")[0]
    assert not L.parse_result(GOOD_CHECK, "convert")[0]
    for mutate in (lambda d: d.update(version="9"), lambda d: d["diagnostics"][0].update(line=0),
                   lambda d: d["diagnostics"][0].update(severity="fatal"), lambda d: d["diagnostics"][0].update(line=True),
                   lambda d: d.pop("diagnostics"), lambda d: d.update(ok="yes")):
        d = json.loads(GOOD_CHECK)
        mutate(d)
        assert not L.parse_result(json.dumps(d), "check")[0]


def test_convert_result_validation():
    base = {"version": "0.1", "command": "convert", "ok": True, "assurance": "certified", "maxUsd": 0.25, "costUsd": 0.0033,
            "files": {"java": ["/w/A.java"]}}
    assert L.parse_result(json.dumps(base), "convert")[0]
    assert not L.parse_result(json.dumps({**base, "assurance": "great"}), "convert")[0]
    assert not L.parse_result(json.dumps({**base, "maxUsd": "x"}), "convert")[0]
    assert not L.parse_result(json.dumps({**base, "files": {"java": "A.java"}}), "convert")[0]
    assert L.parse_result(json.dumps({"version": "0.1", "command": "convert", "ok": False, "error": "no key"}), "convert")[0]


# ---- diagnostic to line mapping ----
def test_diagnostics_by_line_zero_based_and_basename_match():
    diags = [{"file": "/w/NOPERIOD.cbl", "line": 5, "severity": "error", "message": "a"},
             {"file": "NOPERIOD.cbl", "line": 5, "severity": "warning", "message": "b"},
             {"file": "REC.cpy", "line": 2, "severity": "error", "message": "copybook"}]
    m = L.diagnostics_by_line(diags, "C:\\code\\noperiod.cbl" if os.name == "nt" else "/x/NOPERIOD.cbl")
    assert m == {4: [("error", "a"), ("warning", "b")]}


# ---- summarizer and hostile text ----
def test_summarize_check_and_convert():
    ok, v = L.parse_result(GOOD_CHECK, "check")
    lines = L.summarize(v)
    assert lines[0].startswith("NOT OK") and lines[1] == "NOPERIOD.cbl:5: error: syntax error"
    conv = {"version": "0.1", "command": "convert", "ok": True, "assurance": "compiled-unverified", "assuranceReason": "no output file",
            "maxUsd": 0.25, "costUsd": None, "model": "m", "files": {"java": ["/w/A.java"]}}
    out = "\n".join(L.summarize(conv))
    assert "COMPILED, NOT VERIFIED" in out and "never run against the original COBOL" in out and "Cost: unknown" in out


def test_hostile_text_is_stripped():
    evil = "ok\x1b[2J\x00\x07\r\u0085boom\u2028x"
    d = {"file": "A.cbl\x1b[31m", "line": 1, "severity": "error", "message": evil}
    line = L.format_diagnostic(d)
    assert not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028]", line) and "\n" not in line
    r = {"version": "0.1", "command": "convert", "ok": True, "assurance": "failed", "assuranceReason": evil, "maxUsd": 0.1, "model": evil,
         "notes": [evil]}
    assert not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028]", "".join(L.summarize(r)).replace("\n", ""))


def test_summarize_cli_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(GOOD_CHECK + "\n"))
    assert S.main(["check"]) == 1  # exit 1: the file does not compile
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("{") and "NOPERIOD.cbl:5: error: syntax error" in out
    monkeypatch.setattr(sys, "stdin", io.StringIO("garbage\x1b[0m"))
    assert S.main(["check"]) == 2
    assert "\x1b" not in capsys.readouterr().out


def test_find_workspace(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    f = tmp_path / "a" / "b" / "X.cbl"
    f.write_text("")
    assert L.find_workspace(str(f)) == str(tmp_path)


# ---- the PythonScript with a stubbed Npp module ----
class FakeEditor:
    def __init__(self, text="A\nB\nC\n", dirty=False):
        self.lines = text.split("\n")
        self.dirty, self.notes, self.fills = dirty, {}, []
    def getModify(self): return self.dirty
    def annotationClearAll(self): self.notes.clear()
    def setIndicatorCurrent(self, n): pass
    def indicatorClearRange(self, a, b): pass
    def getLength(self): return 10
    def indicSetStyle(self, *a): pass
    def indicSetFore(self, *a): pass
    def annotationSetVisible(self, *a): pass
    def getLineCount(self): return len(self.lines)
    def positionFromLine(self, l): return l * 2
    def lineLength(self, l): return 2
    def indicatorFillRange(self, s, n): self.fills.append((s, n))
    def annotationSetText(self, l, t): self.notes[l] = t
    def annotationSetStyle(self, *a): pass


def load_npp(path, answers, editor):
    flags = types.SimpleNamespace(YESNO=1, OKCANCEL=2, RESULTYES=6, RESULTOK=1)
    boxes, opened, written = [], [], []
    notepad = types.SimpleNamespace(getCurrentFilename=lambda: path, save=lambda: written.append("saved"),
                                    messageBox=lambda m, t, f=0: (boxes.append(m), answers.pop(0))[1], open=opened.append)
    console = types.SimpleNamespace(write=lambda s: written.append(s))
    mod = types.ModuleType("Npp")
    mod.__dict__.update(notepad=notepad, editor=editor, console=console, MESSAGEBOXFLAGS=flags,
                        INDICATORSTYLE=types.SimpleNamespace(SQUIGGLE=1), ANNOTATIONVISIBLE=types.SimpleNamespace(STANDARD=1))
    sys.modules["Npp"] = mod
    sys.modules.pop("diocle_npp", None)
    import diocle_npp
    return diocle_npp, boxes, opened, written


def test_script_check_annotates_reported_line(tmp_path, monkeypatch):
    f = tmp_path / "NOPERIOD.cbl"
    f.write_text("x")
    ed = FakeEditor(dirty=True)
    npp, boxes, opened, out = load_npp(str(f), [6], ed)  # 6 = YES to save
    monkeypatch.setattr(npp, "_run", lambda c, p, cb: (GOOD_CHECK, 1))
    npp.diocle_check()
    assert "saved" in out and ed.notes == {}  # asked to save; line 5 is outside this 3-line fake buffer, so nothing is marked
    ed2 = FakeEditor(text="\n".join("L%d" % i for i in range(10)))
    npp, boxes, opened, out = load_npp(str(f), [], ed2)
    monkeypatch.setattr(npp, "_run", lambda c, p, cb: (GOOD_CHECK, 1))
    npp.diocle_check()
    assert ed2.notes == {4: "error: syntax error"}
    assert any("NOPERIOD.cbl:5: error: syntax error" in w for w in out)


def test_script_convert_declined_and_confirmed(tmp_path, monkeypatch):
    f = tmp_path / "A.cbl"
    f.write_text("x")
    java = tmp_path / "A.java"
    java.write_text("class A{}")
    npp, boxes, opened, out = load_npp(str(f), [2], FakeEditor())  # 2 is not RESULTOK(1): declined
    called = []
    monkeypatch.setattr(npp, "_run", lambda *a: called.append(a) or ("", 0))
    npp.diocle_convert()
    assert not called and "$0.25" in boxes[0] and "$1.00" in boxes[0]
    res = json.dumps({"version": "0.1", "command": "convert", "ok": True, "assurance": "certified", "maxUsd": 0.25, "costUsd": 0.003,
                      "files": {"java": [str(java)]}})
    npp, boxes, opened, out = load_npp(str(f), [1, 1], FakeEditor())
    monkeypatch.setattr(npp, "_run", lambda *a: (res, 0))
    npp.diocle_convert()
    assert opened == [str(java)] and boxes[-1].startswith("CERTIFIED\n\nThe generated Java matched")


# ---- the real CLI (free `editor check`), skipped when the converter or cobc is unavailable ----
def _cli_python():
    p = Path(os.environ.get("DIOCLE_TEST_CONVERTER_PYTHON") or ROOT / "services" / "converter" / ".venv" / "bin" / "python")
    return str(p) if p.exists() else None


@pytest.mark.skipif(not _cli_python() or subprocess.run(["which", "cobc"], capture_output=True).returncode != 0, reason="needs a converter Python (venv or DIOCLE_TEST_CONVERTER_PYTHON) and cobc")
def test_real_check_on_noperiod():
    f = ROOT / "samples" / "convert-anyway-repo" / "cobol" / "NOPERIOD.cbl"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "services" / "converter")}
    p = subprocess.run(L.build_command(_cli_python(), "check", str(f)), capture_output=True, text=True, env=env, cwd=str(ROOT))
    ok, v = L.parse_result(p.stdout, "check")
    assert ok and not v["ok"] and 5 in {d["line"] for d in v["diagnostics"]}



# ---- a package planted in the opened folder must not be imported ----
def test_planted_package_in_the_open_folder_is_not_imported(tmp_path):
    """The converter is started with the user's open folder as its working directory. `python -P` keeps that folder off sys.path."""
    import subprocess
    import sys
    if sys.version_info < (3, 11):
        pytest.skip("-P needs Python 3.11+")
    pkg = tmp_path / "diocle_converter"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text("open('PLANTED_RAN', 'w').write('x')\n")
    args = L.build_args("check", "a.cbl")
    assert args[0] == "-P"
    subprocess.run([sys.executable] + args, cwd=str(tmp_path), capture_output=True, timeout=60)
    assert not (tmp_path / "PLANTED_RAN").exists(), "the planted package ran: -P is not protecting"
    subprocess.run([sys.executable] + args[1:], cwd=str(tmp_path), capture_output=True, timeout=60)  # control, without -P
    assert (tmp_path / "PLANTED_RAN").exists(), "control failed: the test cannot detect the problem"
