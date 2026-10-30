#!/usr/bin/env python3
"""Render timed transcripts (from timed_run.py) into a terminal-style mp4. Needs Pillow and ffmpeg (dev tools only).

  python3 render_capture.py OUT.mp4 [--max-seconds N] [--idle-cap 1.2] TRANSCRIPT.jsonl [TRANSCRIPT.jsonl ...]

Text and timings come from the transcripts. The only edit is idle compression: a gap longer than --idle-cap seconds between
two lines is shown as --idle-cap seconds, and a visible "[... N s idle skipped]" line says so. Long lines are wrapped, not cut.
A caption on screen states that it is a real recording.
"""
import json, subprocess, sys, tempfile, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 15
BG, FG, DIM, ACC, GOOD, BAD = (16, 18, 24), (225, 228, 235), (130, 138, 155), (120, 180, 255), (120, 220, 150), (255, 130, 120)
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 17)
CAP = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
COLS, ROWS = 121, 33

def color(text, stream):
    if stream in ("cmd",): return ACC
    if stream == "title": return GOOD
    if text.startswith("[... "): return DIM
    low = text.lower()
    if "isError".lower() in low or "error" in low[:30]: return BAD
    return FG

def events(paths, idle_cap):
    evs, offset = [], 0.0
    for p in paths:
        rows = [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
        end = next((r for r in rows if r.get("kind") == "end"), {"seconds": 0})
        last_t = 0.0
        for r in rows:
            if r.get("kind") == "end": continue
            gap = r["t"] - last_t
            if gap > idle_cap and r["stream"] not in ("cmd", "title"):
                evs.append((offset + last_t + idle_cap * 0.0, f"[... {gap:.0f} s idle skipped]", "note", gap - idle_cap))
            last_t = r["t"]
            evs.append((offset + r["t"], r["text"], r["stream"], 0.0))
        offset += end["seconds"] + 0.8
    # compress: running subtraction of skipped time
    out, skipped = [], 0.0
    for t, text, stream, skip in evs:
        out.append((t - skipped, text, stream)); skipped += skip
    return out

def wrap(text):
    return textwrap.wrap(text.expandtabs(4), COLS, replace_whitespace=False, drop_whitespace=False, subsequent_indent="    ") or [""]

def frame(lines, caption, shown_t):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 34], fill=(28, 31, 40))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))): d.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=c)
    d.text((100, 9), caption, font=CAP, fill=DIM)
    d.text((W - 150, 9), f"real time {shown_t:5.1f}s", font=CAP, fill=DIM)
    y = 46
    for text, col in lines[-ROWS:]:
        d.text((16, y), text, font=FONT, fill=col); y += 20
    return im

def main():
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    out, rest = a[0], a[1:]
    idle, maxs, paths = 1.2, None, []
    while rest:
        x = rest.pop(0)
        if x == "--idle-cap": idle = float(rest.pop(0))
        elif x == "--max-seconds": maxs = float(rest.pop(0))
        else: paths.append(x)
    evs = events(paths, idle)
    total = evs[-1][0] + 2.0
    if maxs and total > maxs: print(f"warning: {total:.1f}s exceeds --max-seconds {maxs}", file=sys.stderr)
    caption = "Muse Code 1.4.14 + local Diocle plugin | real recording, idle waits shortened where marked"
    with tempfile.TemporaryDirectory() as tmp:
        shown, ei, n, lines = 0.0, 0, int(total * FPS), []
        for k in range(n):
            t = k / FPS
            while ei < len(evs) and evs[ei][0] <= t:
                _, text, stream = evs[ei]
                for w in wrap(text): lines.append((w, color(text, stream)))
                ei += 1
            frame(lines, caption, t).save(f"{tmp}/f{k:05d}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/f%05d.png",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out], check=True)
    print(f"wrote {out} ({total:.1f}s of video from {len(paths)} transcript(s))")

if __name__ == "__main__":
    main()
