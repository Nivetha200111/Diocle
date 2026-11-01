#!/usr/bin/env python3
"""build.py V12.mp4 OVERLAY_DIR OUT.mp4: the v13 candidate, made only from the v12 picture and the owner's recorded narration.
It adds captions and corrected stamps, and cuts two spoken overclaims. No voice is synthesized and v12 is left as it is."""
import subprocess, sys
src, ov, out = sys.argv[1:4]
# name, from, to, on the v12 timeline
SHOWN = [("patch-passed", 0.0, 4.95), ("patch-broken", 4.95, 9.07), ("hook-stamp-slam", 6.55, 6.8), ("hook-stamp", 6.8, 9.07), ("hook-bar", 6.8, 9.07),
         ("hood-malformed", 98.3, 112.8), ("hood-stamp-slam", 110.4, 110.65), ("hood-stamp", 110.65, 111.87), ("hood-weak", 112.8, 119.03), ("ci", 124.2, 129.9),
         ("measured", 146.2, 156.53), ("limits", 156.53, 168.5), ("end", 174.0, 177.6)]
# (from, to) of v12 kept, in order; HOLD seconds of the limits card with no voice sit between the 2nd and 3rd.
KEEP = [(0.0, 32.2), (33.9, 156.55), (164.2, 177.6)]
HOLD = 0.8
inputs = ["-i", src]
for name, *_ in SHOWN:
    inputs += ["-loop", "1", "-t", "178", "-framerate", "30", "-i", f"{ov}/{name}.png"]
inputs += ["-loop", "1", "-t", str(HOLD), "-framerate", "30", "-i", f"{ov}/limits.png"]
hold_in = len(SHOWN) + 1
f, last = [], "0:v"
for i, (name, a, b) in enumerate(SHOWN):
    f.append(f"[{last}][{i + 1}:v]overlay=enable='between(t,{a},{b})':eof_action=pass[o{i}]")
    last = f"o{i}"
f.append(f"[{last}]split=3[p0][p1][p2]")
fade = 0.025
for i, (a, b) in enumerate(KEEP):
    f.append(f"[p{i}]trim={a}:{b},setpts=PTS-STARTPTS[v{i}]")
    f.append(f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS,afade=t=in:d={fade},afade=t=out:st={b - a - fade}:d={fade}[a{i}]")
f.append(f"[{hold_in}:v]format=yuv420p,fps=30,setpts=PTS-STARTPTS[vh]")
f.append(f"anullsrc=r=48000:cl=mono,atrim=0:{HOLD},asetpts=PTS-STARTPTS[ah]")
f.append("[v0][a0][v1][a1][vh][ah][v2][a2]concat=n=4:v=1:a=1[v][a]")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", out], check=True)
