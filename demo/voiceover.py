"""Synthetic narration for the submission cut, placed line by line at its timecodes.

  ~/.cache/diocle-voice/.venv/bin/python demo/voiceover.py [voice]
Writes demo/promo/public/voiceover.wav (played by the Submission composition) and demo/promo/src/captions.json
(caption chunks timed from the generated audio, so spelling is exactly the script's).

Kokoro (Apache 2.0, runs offline). Each line starts at its time in the video; a line too long for its slot is
regenerated slightly faster (at most 1.15x) rather than overlapping the next. The end card says the voice is synthetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

RATE = 24000
TOTAL = 138.6  # seconds: the Submission composition
HERE = Path(__file__).resolve().parent
OUT = HERE / "promo" / "public" / "voiceover.wav"
CAPTIONS = HERE / "promo" / "src" / "captions.json"

# (start in seconds, text). Timed to demo/promo/src/Submission.tsx; the cold open (0-5.5 s) is silent on purpose.
LINES = [
    (5.6, "Banks still run on COBOL. People re-check converted code by hand. AI writes Java in minutes. So who checks the AI?"),
    (14.6, "This is Diocle."),
    (18.2, "Three Muse Spark agents. One writes the Java, one attacks it, one repairs it. The judge isn't a model. It's the original program."),
    (27.6, "GNU COBOL runs the original next to the Java, on the same inputs. Every byte must match, or the repair agent fixes the Java."),
    (40.0, "So we let AI rewrite a bank's programs, and tried to break them."),
    (45.4, "This is the live product. A cheque-clearing program passed one thousand and four tests it had never seen."),
    (56.0, "Then the breaker attacked it. Two of its inputs broke the Java. The COBOL charges a twenty dollar fee. The Java charges nothing. The repair agent fixed it, and it re-certified."),
    (68.8, "Don't trust us. Press re-verify, and both programs run again on a fresh seed."),
    (75.4, "Certified code ships as a pull request, and the target repository's own CI checks it again."),
    (85.6, "Or paste any public COBOL repository, and watch it convert."),
    (91.6, "Banks keep code private, so the agents also run on Muse Spark Open, Meta's open weights."),
    (99.0, "We test ourselves too. Our evaluation publishes its failures, including a bug our own stricter check caught."),
    (108.4, "Few developers know COBOL, so teams retrain Java developers for months. Diocle checks the Java."),
    (115.4, "A wrong cent repeats on every account."),
    (119.0, "With Diocle, every program arrives with proof you can re-run."),
    (124.3, "Today: batch COBOL with files. Next: real mainframe output, and a pilot with a bank team."),
    (131.0, "Diocle. Try it now, at diocle dot vercel dot app. Built during the hackathon, with Meta Muse Spark."),
]


def speak(pipe: KPipeline, voice: str, text: str, speed: float) -> np.ndarray:
    return np.concatenate([np.asarray(audio) for _, _, audio in pipe(text, voice=voice, speed=speed)])


def chunks(text: str, max_words: int = 7) -> list[str]:
    """Caption-sized pieces: split at sentence and clause ends, then by length."""
    import re
    out = []
    for part in re.split(r"(?<=[.?!,:])\s+", text):
        words = part.split()
        while words:
            out.append(" ".join(words[:max_words]))
            words = words[max_words:]
    return out


def main() -> int:
    voice = sys.argv[1] if len(sys.argv) > 1 else "af_heart"
    pipe = KPipeline(lang_code="a")
    track = np.zeros(int(TOTAL * RATE), dtype=np.float32)
    captions = []
    for i, (start, text) in enumerate(LINES):
        slot = (LINES[i + 1][0] if i + 1 < len(LINES) else TOTAL) - start - 0.25
        speed = 1.0
        audio = speak(pipe, voice, text, speed)
        for _ in range(3):  # speed is not linear in duration: retry a few times, never past 1.15x
            if len(audio) / RATE <= slot or speed >= 1.15:
                break
            speed = min(1.15, speed * (len(audio) / RATE) / slot * 1.03)
            audio = speak(pipe, voice, text, speed)
        dur = len(audio) / RATE
        flag = "  TOO LONG, shorten the line" if dur > slot else ""
        print(f"{start:6.1f}s  {dur:4.1f}s of {slot:4.1f}s  x{speed:.2f}{flag}  {text[:60]}")
        pieces = chunks(text)
        weights = [len(p) + 6 for p in pieces]  # time spread by length, with a little per-chunk pause
        t = start
        for piece, w in zip(pieces, weights):
            d = dur * w / sum(weights)
            captions.append({"from": round(t, 2), "to": round(t + d, 2), "text": piece})
            t += d
        at = int(start * RATE)
        end = min(len(track), at + len(audio))
        track[at:end] += audio[: end - at]
    peak = float(np.max(np.abs(track))) or 1.0
    sf.write(OUT, track / peak * 0.89, RATE)
    print(f"wrote {OUT}")
    import json
    CAPTIONS.write_text(json.dumps({"voice": voice, "captions": captions}, indent=1) + "\n")
    print(f"wrote {CAPTIONS} ({len(captions)} captions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
