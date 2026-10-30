#!/usr/bin/env python3
"""Run a command (argv, no shell) and record every output line with its real elapsed time.

  python3 timed_run.py OUT.jsonl [--title "text"] -- COMMAND ARG...

Writes one JSON object per line: {"t": seconds_since_start, "text": "...", "stream": "out"|"err"}, plus a first
{"t":0,"text":"$ <command>","stream":"cmd"} line and a last {"kind":"end","exit":N,"seconds":S}. The child inherits the
environment unchanged (so a Muse login or META_API_KEY in YOUR shell works); this script never reads, stores or prints a key.
"""
import json, subprocess, sys, threading, time

def main():
    argv = sys.argv[1:]
    if "--" not in argv or len(argv) < 3:
        sys.exit(__doc__)
    i = argv.index("--")
    out_path, opts, cmd = argv[0], argv[1:i], argv[i + 1:]
    title = opts[opts.index("--title") + 1] if "--title" in opts else None
    t0 = time.monotonic()
    lock = threading.Lock()
    with open(out_path, "w") as f:
        def emit(obj):
            with lock:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n"); f.flush()
        if title:
            emit({"t": 0.0, "text": title, "stream": "title"})
        emit({"t": 0.0, "text": "$ " + " ".join(cmd), "stream": "cmd"})
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        def pump(stream, name):
            for line in stream:
                emit({"t": round(time.monotonic() - t0, 3), "text": line.rstrip("\n"), "stream": name})
        th = [threading.Thread(target=pump, args=(p.stdout, "out")), threading.Thread(target=pump, args=(p.stderr, "err"))]
        [t.start() for t in th]; [t.join() for t in th]
        rc = p.wait()
        emit({"kind": "end", "exit": rc, "seconds": round(time.monotonic() - t0, 3)})
    return rc

if __name__ == "__main__":
    sys.exit(main())
