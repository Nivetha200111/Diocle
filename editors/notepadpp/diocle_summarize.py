# -*- coding: utf-8 -*-
"""NppExec helper: reads one editor-result JSON document on stdin (or runs the CLI itself with --run) and prints a short,
console-safe summary. Standard library only (Python 3). The JSON is printed first, then the summary.

  python diocle_summarize.py check            < result.json
  python diocle_summarize.py --run check FILE [--max-usd 0.25] [--convert-anyway] [--python PYTHON]

`--run` exists because NppExec has no portable pipe; it starts the converter with an argument list (no shell)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diocle_labels as L  # noqa: E402


def report(stdout, command):
    ok, v = L.parse_result(stdout, command)
    if not ok:
        print("Diocle: " + L.clean_line(v))
        return 2
    for line in L.summarize(v):
        print(line)
    return 0 if v["ok"] else 1


def main(argv):
    if argv and argv[0] == "--run":
        import argparse
        p = argparse.ArgumentParser(prog="diocle_summarize --run")
        p.add_argument("command", choices=["check", "convert"])
        p.add_argument("file")
        p.add_argument("--max-usd", type=float, default=L.DEFAULT_MAX_USD)
        p.add_argument("--convert-anyway", action="store_true")
        p.add_argument("--python", default=sys.executable or "python")
        a = p.parse_args(argv[1:])
        cmd = L.build_command(a.python, a.command, a.file, max_usd=a.max_usd, convert_anyway=a.convert_anyway)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                              errors="replace", cwd=L.find_workspace(a.file), env=L.safe_env())
        for line in proc.stderr.splitlines():  # PROGRESS lines
            print(L.clean_line(line, 300))
        stdout, command = proc.stdout, a.command
    else:
        command = argv[0] if argv and argv[0] in ("check", "convert") else "check"
        stdout = sys.stdin.read()
    last = [l for l in stdout.strip().split("\n") if l.strip()]
    if last:
        print(L.clean_line(last[-1], 20000))
    return report(stdout, command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
