# -*- coding: utf-8 -*-
"""Diocle for Notepad++ (PythonScript plugin script). NOT TESTED INSIDE NOTEPAD++ (see README.md).

Requires the PythonScript 3 plugin (Python 3.x). Standard library only. Two entry points to bind to the menu:
    diocle_check()     compile-check the open COBOL file (free), diagnostics in the console + annotations
    diocle_convert()   convert and verify (spends your own Meta key, capped): Java opens in a new tab

The converter reads the Meta key from the environment or a `.env` in the workspace. This script never sees it.
"""
import os
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diocle_labels as L  # noqa: E402

try:
    from Npp import notepad, editor, console, MESSAGEBOXFLAGS, INDICATORSTYLE, ANNOTATIONVISIBLE  # type: ignore
except ImportError:  # imported headless (tests stub the module); the functions below need Notepad++
    notepad = editor = console = MESSAGEBOXFLAGS = INDICATORSTYLE = ANNOTATIONVISIBLE = None

# ---- settings: edit here (or set the environment variables before starting Notepad++) ----
# Python that has the converter installed (the repo's services/converter venv). Empty: `python` on PATH.
CONVERTER_PYTHON = os.environ.get("DIOCLE_NPP_PYTHON", "")
MAX_USD = L.clamp_max_usd(os.environ.get("DIOCLE_NPP_MAX_USD", L.DEFAULT_MAX_USD))  # hard-capped at 1.00 here and in the converter
CONVERT_ANYWAY = False        # True: also try programs that cannot be verified (labelled, never "certified")
COPYBOOK_DIRS = []            # extra copybook folders, passed as --copybooks
INDICATOR = 8                 # Scintilla indicator number used for the squiggles (8 to 11 are free for plugins)
TITLE = "Diocle"


def _say(text=""):
    console.write(L.clean(text, 4000) + "\n")


def _python():
    return CONVERTER_PYTHON or "python"


def _current_cobol_file():
    path = notepad.getCurrentFilename()
    if not path or not os.path.isabs(path) or not os.path.exists(path):
        notepad.messageBox("Save the file somewhere first; Diocle works on a file on disk.", TITLE)
        return None
    if editor.getModify():
        ans = notepad.messageBox("The file has unsaved changes. Save it before running Diocle?", TITLE, MESSAGEBOXFLAGS.YESNO)
        if ans != MESSAGEBOXFLAGS.RESULTYES:
            return None
        notepad.save()
    return path


def _run(command, path, on_progress):
    """Start the converter with an argument list (no shell). Returns (stdout, returncode or None on start failure)."""
    cmd = L.build_command(_python(), command, path, max_usd=MAX_USD, convert_anyway=CONVERT_ANYWAY, copybooks=COPYBOOK_DIRS)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=L.find_workspace(path),
                                universal_newlines=True, errors="replace", creationflags=flags, env=L.safe_env())
    except (OSError, ValueError) as e:
        _say("Diocle: could not start %r: %s. Set CONVERTER_PYTHON in diocle_npp.py." % (_python(), e))
        return "", None
    out = []
    t = threading.Thread(target=lambda: out.append(proc.stdout.read()))
    t.daemon = True
    t.start()
    for line in proc.stderr:  # PROGRESS lines; the Notepad++ UI is busy until the command ends
        on_progress(L.clean_line(line, 300))
    proc.wait()
    t.join(5)
    return (out[0] if out else ""), proc.returncode


def clear_annotations():
    editor.annotationClearAll()
    editor.setIndicatorCurrent(INDICATOR)
    editor.indicatorClearRange(0, editor.getLength())


def annotate(by_line):
    """Squiggle each reported line and show the message under it (Scintilla annotations)."""
    editor.indicSetStyle(INDICATOR, INDICATORSTYLE.SQUIGGLE)
    editor.indicSetFore(INDICATOR, (255, 0, 0))
    editor.setIndicatorCurrent(INDICATOR)
    editor.annotationSetVisible(ANNOTATIONVISIBLE.STANDARD)
    for line, items in by_line.items():
        if line >= editor.getLineCount():
            continue
        start = editor.positionFromLine(line)
        editor.indicatorFillRange(start, max(1, editor.lineLength(line) - 1))
        editor.annotationSetText(line, "\n".join("%s: %s" % (sev, msg) for sev, msg in items))
        editor.annotationSetStyle(line, 0)


def diocle_check():
    path = _current_cobol_file()
    if not path:
        return
    _say("Diocle check: %s" % path)
    stdout, rc = _run("check", path, _say)
    if rc is None:
        return
    ok, v = L.parse_result(stdout, "check")
    if not ok:
        _say("Diocle: " + v)
        return
    for line in L.summarize(v):
        _say(line)
    clear_annotations()
    by_line = L.diagnostics_by_line(v.get("diagnostics"), path)
    annotate(by_line)
    others = [d for d in v.get("diagnostics") or [] if not L.same_file(d["file"], path)]
    if others:
        _say("(%d diagnostic(s) are in other files, such as copybooks; listed above, not marked here)" % len(others))


def diocle_convert():
    path = _current_cobol_file()
    if not path:
        return
    msg = ("Convert %s to Java and verify it?\n\nThis sends your COBOL and the copybooks it COPYs to the Meta model endpoint set "
           "in your .env, with your own key, and spends your own money: at most $%.2f (hard cap $%.2f)."
           % (os.path.basename(path), MAX_USD, L.HARD_MAX_USD))
    if CONVERT_ANYWAY:
        msg += "\n\nConvert anyway is ON: programs that cannot be verified are still attempted and labelled."
    if notepad.messageBox(msg, TITLE, MESSAGEBOXFLAGS.OKCANCEL) != MESSAGEBOXFLAGS.RESULTOK:
        return
    _say("Diocle convert: %s (cap $%.2f)" % (path, MAX_USD))
    stdout, rc = _run("convert", path, lambda l: _say(l))
    if rc is None:
        return
    ok, v = L.parse_result(stdout, "convert")
    if not ok:
        _say("Diocle: " + v)
        notepad.messageBox("Diocle: " + v, TITLE)
        return
    for line in L.summarize(v):
        _say(line)
    if not v["ok"]:
        notepad.messageBox("\n".join(L.summarize(v)), TITLE)
        return
    label, text = L.badge_for(v)
    for j in (v.get("files") or {}).get("java", [])[:5]:
        if os.path.isfile(j):
            notepad.open(j)  # a new tab
    notepad.messageBox("%s\n\n%s" % (label, L.clean(text, 1500)), TITLE)
