# -*- coding: utf-8 -*-
"""Shared, pure logic for the Notepad++ integration (Python 3, standard library only; no Npp import).

ONE place for: the honest assurance wording (kept identical to editors/vscode/src/core.ts badgeFor), the command-line
builder, result validation (contracts/editor-result.schema.json v0.1), diagnostic-to-line mapping and console-safe text.
Used by diocle_npp.py (PythonScript) and diocle_summarize.py (NppExec).
"""
import json
import os
import re

HARD_MAX_USD = 1.0      # the converter enforces the same cap; this only keeps the prompt honest
DEFAULT_MAX_USD = 0.25
ASSURANCES = ("certified", "certified-against-repaired-cobol", "compiled-unverified", "failed", "skipped")
SEVERITIES = ("error", "warning", "note")

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f  ]")


def clean(text, limit=1000):
    """Text from a model, a compiler or a file, made safe for a console or message box: control characters (ESC, CR,
    NUL, C1) are dropped, tabs become spaces, newlines are kept only where `clean_lines` splits them."""
    s = "" if text is None else str(text)
    s = s.replace("\t", " ").replace("\r\n", "\n").replace("\r", " ")
    s = _CTRL.sub("", s)
    return s[:limit]


def clean_line(text, limit=500):
    return clean(text, limit).replace("\n", " ")


def clamp_max_usd(value, fallback=DEFAULT_MAX_USD):
    try:
        n = float(value)
        if n != n or n in (float("inf"), float("-inf")):
            n = fallback
    except (TypeError, ValueError):
        n = fallback
    return min(HARD_MAX_USD, max(0.01, n))


def safe_env():
    """The converter's environment plus PYTHONSAFEPATH=1 (same effect as -P, for a wrapper that drops the flag)."""
    env = dict(os.environ)
    env["PYTHONSAFEPATH"] = "1"
    return env


def build_args(command, path, max_usd=DEFAULT_MAX_USD, convert_anyway=False, copybooks=()):
    """Arguments after the Python executable. A list, never a shell string, so spaces and quotes in paths are safe."""
    if command not in ("check", "convert"):
        raise ValueError("command must be check or convert")
    # -P (Python 3.11+): do not put the current folder first on sys.path. The converter is started from the user's open folder, and
    # `python -m` would otherwise import a diocle_converter/ package planted in that folder before the installed one.
    args = ["-P", "-m", "diocle_converter", "editor", command, path]
    for c in copybooks:
        args += ["--copybooks", c]
    if command == "convert":
        args += ["--max-usd", "%.2f" % clamp_max_usd(max_usd)]
        if convert_anyway:
            args.append("--convert-anyway")
    return args


def build_command(python, command, path, **kw):
    return [python] + build_args(command, path, **kw)


def _is_str(v):
    return isinstance(v, str)


def parse_result(stdout, expected):
    """Validate the converter's stdout (the last non-empty line is the JSON document).
    Returns (True, dict) or (False, error text). The child's output is never trusted blindly."""
    lines = [l for l in (stdout or "").strip().split("\n") if l.strip()]
    try:
        v = json.loads(lines[-1]) if lines else None
    except ValueError:
        return False, "the converter did not print a JSON result"
    if v is None:
        return False, "the converter did not print a JSON result"

    def bad(why):
        return False, "unexpected converter output: " + why
    if not isinstance(v, dict):
        return bad("not an object")
    if v.get("version") != "0.1":
        return bad("version")
    if v.get("command") != expected:
        return bad("command")
    if not isinstance(v.get("ok"), bool):
        return bad("ok")
    if "error" in v and not _is_str(v["error"]):
        return bad("error")
    if "diagnostics" in v:
        if not isinstance(v["diagnostics"], list):
            return bad("diagnostics")
        for d in v["diagnostics"]:
            if (not isinstance(d, dict) or not _is_str(d.get("file")) or isinstance(d.get("line"), bool)
                    or not isinstance(d.get("line"), int) or d["line"] < 1 or d.get("severity") not in SEVERITIES
                    or not _is_str(d.get("message"))):
                return bad("diagnostic")
    if expected == "check" and not isinstance(v.get("diagnostics"), list):
        return bad("diagnostics missing")
    if expected == "convert" and v["ok"]:
        if v.get("assurance") not in ASSURANCES:
            return bad("assurance")
        if isinstance(v.get("maxUsd"), bool) or not isinstance(v.get("maxUsd"), (int, float)):
            return bad("maxUsd")
    if "files" in v:
        f = v["files"]
        if not isinstance(f, dict):
            return bad("files")
        for k in ("sqlSchema", "repairedCobol", "diff", "behaviorMd"):
            if k in f and not _is_str(f[k]):
                return bad("files." + k)
        if "java" in f and not (isinstance(f["java"], list) and all(_is_str(x) for x in f["java"])):
            return bad("files.java")
    for k in ("assuranceReason", "runDir", "file"):
        if k in v and not _is_str(v[k]):
            return bad(k)
    if v.get("costUsd") is not None and (isinstance(v.get("costUsd"), bool) or not isinstance(v.get("costUsd"), (int, float))):
        if "costUsd" in v:
            return bad("costUsd")
    if "notes" in v and not (isinstance(v["notes"], list) and all(_is_str(x) for x in v["notes"])):
        return bad("notes")
    return True, v


def badge_for(result):
    """(LABEL, honest text). Same wording as editors/vscode/src/core.ts badgeFor; tests assert the parity."""
    reason = " Reason: %s" % clean_line(result["assuranceReason"], 1000) if result.get("assuranceReason") else ""
    a = result.get("assurance")
    if a == "certified":
        return ("CERTIFIED", "The generated Java matched the original COBOL byte for byte on the inputs tried. "
                "This is not a proof that the two behave the same on every input.")
    if a == "certified-against-repaired-cobol":
        n = result.get("repairedLines") or 0
        return ("CERTIFIED AGAINST REPAIRED COBOL",
                "Your original COBOL did not compile. A model patched %d line%s (the diff is shown) and the Java matched the "
                "PATCHED COBOL, not your file. A person must confirm the patch is what the author meant. "
                "This is not plain certified." % (n, "" if n == 1 else "s"))
    if a == "compiled-unverified":
        return ("COMPILED, NOT VERIFIED", "The Java compiles, but it was never run against the original COBOL.%s" % reason)
    if a == "skipped":
        return ("SKIPPED", "Nothing was converted.%s" % reason)
    return ("FAILED", "No Java was shown to match.%s" % reason)


def same_file(diag_file, current):
    """cobc prints the path as given; compare by normalised base name so relative/absolute spellings match."""
    return os.path.normcase(os.path.basename(clean_line(diag_file))) == os.path.normcase(os.path.basename(current or ""))


def diagnostics_by_line(diagnostics, current_file):
    """{zero_based_line: [(severity, message)]} for diagnostics in the open file (Scintilla lines are 0-based).
    Diagnostics in other files (copybooks) are not mapped; callers list them in the console."""
    out = {}
    for d in diagnostics or []:
        if same_file(d["file"], current_file):
            out.setdefault(d["line"] - 1, []).append((d["severity"], clean_line(d["message"])))
    return out


def format_diagnostic(d):
    """`file:line: severity: message`, the shape NppExec's console filter and most error parsers recognise."""
    return "%s:%d: %s: %s" % (clean_line(d["file"], 300), d["line"], d["severity"], clean_line(d["message"]))


def summarize(result):
    """Short human summary of a validated editor-result, console-safe (list of lines)."""
    lines = []
    if result["command"] == "check":
        diags = result.get("diagnostics") or []
        if result["ok"] and not diags:
            lines.append("OK: compiles under cobc -std=ibm.")
        else:
            errs = sum(1 for d in diags if d["severity"] == "error")
            lines.append("%s: %d diagnostic(s), %d error(s)." % ("OK with notes" if result["ok"] else "NOT OK", len(diags), errs))
        if result.get("error"):
            lines.append("Could not check: " + clean_line(result["error"]))
        lines += [format_diagnostic(d) for d in diags]
        return lines
    if not result["ok"]:
        return ["Could not convert: " + clean_line(result.get("error") or "unknown reason")]
    label, text = badge_for(result)
    cost = result.get("costUsd")
    lines.append(label)
    lines.append(text)
    lines.append("Cost: %s (cap $%.2f), your own Meta key. Model: %s" % (
        "unknown" if cost is None else "$%.4f" % cost, result.get("maxUsd") or 0, clean_line(result.get("model") or "unknown", 120)))
    for j in (result.get("files") or {}).get("java", []):
        lines.append("Java: " + clean_line(j, 400))
    if result.get("runDir"):
        lines.append("Run folder: " + clean_line(result["runDir"], 400))
    lines += ["Note: " + clean_line(n) for n in result.get("notes") or []]
    return lines


def find_workspace(path):
    """The folder the converter runs in (it reads a `.env` there and writes `.diocle/runs`): the nearest parent of the
    file holding `.env` or `.git`, else the file's own folder. Only existence is checked; `.env` is never opened."""
    here = os.path.dirname(os.path.abspath(path))
    d = here
    for _ in range(12):
        if os.path.exists(os.path.join(d, ".env")) or os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return here
