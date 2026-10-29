"""Render a synthetic fixed-format COBOL source as a greenbar-style printer listing PNG (demo asset for the printout
intake: `python -m diocle_converter transcribe`).

  pip install pillow
  python demo/render-listing.py samples/loyalty-waiver/src/LOYWAIVE.cbl demo/out/loywaive-listing.png

Deterministic: the same source and font give the same bytes. The font must be monospaced; the default is Menlo (macOS),
override with --font. Only synthetic samples are rendered. The left gutter holds printer line numbers behind a vertical
rule; they are not part of the source (the transcription prompt says so).
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GREEN, WHITE, INK, GUTTER_INK, RULE = (214, 236, 214), (252, 252, 248), (20, 20, 20), (120, 120, 120), (90, 90, 90)


def render(source: Path, out: Path, font_path: str, size: int) -> None:
    font = ImageFont.truetype(font_path, size, index=0)
    lines = source.read_text().expandtabs(8).splitlines()
    char_w = font.getlength("M")
    line_h = size + 8
    gutter_w = int(char_w * 6) + 14
    margin, header_h = 24, 54
    width = int(margin * 2 + gutter_w + char_w * 80)
    height = header_h + line_h * len(lines) + margin
    img = Image.new("RGB", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    d.text((margin, 18), f"SOURCE LISTING   {source.name}   (SYNTHETIC SAMPLE)", fill=INK, font=font)
    for i, line in enumerate(lines):
        y = header_h + i * line_h
        if (i // 3) % 2 == 0:  # greenbar: bands of three lines
            d.rectangle([0, y - 2, width, y + line_h - 3], fill=GREEN)
        d.text((margin, y), f"{i + 1:>5}", fill=GUTTER_INK, font=font)
        d.text((margin + gutter_w, y), line, fill=INK, font=font)
    d.line([margin + gutter_w - 8, header_h - 4, margin + gutter_w - 8, height - margin + 6], fill=RULE, width=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--font", default="/System/Library/Fonts/Menlo.ttc")
    p.add_argument("--size", type=int, default=16)
    a = p.parse_args()
    render(a.source, a.out, a.font, a.size)
    print(f"wrote {a.out} ({a.out.stat().st_size} bytes)")
