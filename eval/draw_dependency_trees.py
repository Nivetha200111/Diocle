"""Dependency trees: the analyzer finds the edges, Muse Image draws them, Muse Wonder reads the picture back, and code compares the two.

  eval/draw_dependency_trees.py SPEC.json --out-dir apps/web/public/trees --results eval/results-dependency-trees.json

SPEC is a list of {"slug", "title", "report" (an analyzer report), and "kinds", or "edges" to draw one part of that report}. No model sees the expected graph at the reading step, and only an
exact match is marked verified. Every attempt is recorded, including failures. Reads the Meta key from the environment (never printed).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

IMAGE_MODEL, READ_MODEL = "muse-image-1.0", "muse-wonder-1.0"
MAX_ATTEMPTS = 3
READ_PRICE = (4.00, 20.00)  # USD per million tokens, input and output, as services/converter/diocle_converter/config.py PRICES


def edges_of(report: dict, kinds: list[str]) -> list[tuple[str, str]]:
    """The drawn graph: distinct (from, to) pairs of the given kinds, exactly as the analyzer reports them."""
    return sorted({(e["from"], e["to"]) for e in report["dependencies"] if e["kind"] in kinds})


def compare(expected: list[tuple[str, str]], read: dict) -> dict:
    """Exact comparison, ignoring only case and spaces around a label. Boxes are checked as well as arrows."""
    norm = lambda s: str(s).strip().upper()  # noqa: E731
    want = {(norm(a), norm(b)) for a, b in expected}
    got = {(norm(e.get("from")), norm(e.get("to"))) for e in read.get("edges", []) if isinstance(e, dict)}
    want_nodes = {n for pair in want for n in pair}
    got_nodes = {norm(n) for n in read.get("nodes", [])} | {n for pair in got for n in pair}
    return {"match": want == got and want_nodes == got_nodes, "missingEdges": sorted(want - got), "inventedEdges": sorted(got - want),
            "missingNodes": sorted(want_nodes - got_nodes), "inventedNodes": sorted(got_nodes - want_nodes)}


def _post(path: str, body: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(os.environ["META_MODEL_BASE_URL"].rstrip("/") + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + os.environ["META_MODEL_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def draw(edges: list[tuple[str, str]]) -> tuple[bytes, dict]:
    lines = "; ".join(f"{a} -> {b}" for a, b in edges)
    prompt = ("A clean technical dependency tree diagram on a plain white background, black text in a monospaced font, thin black arrows, laid out "
              "top to bottom. Exactly these boxes and arrows and no others, with every label spelled exactly as written: " + lines + ". No title and no other text.")
    d = _post("/images/generations", {"model": IMAGE_MODEL, "prompt": prompt, "n": 1, "size": "1024x1024"})
    return base64.b64decode(d["data"][0]["b64_json"]), d.get("usage") or {}


def read_back(image: bytes) -> tuple[dict, float]:
    """Muse Wonder sees only the picture. It is not told the expected graph."""
    with tempfile.TemporaryDirectory() as tmp:
        src, png = Path(tmp) / "t.webp", Path(tmp) / "t.png"
        src.write_bytes(image)
        subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(png)], check=True, capture_output=True)
        url = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
    d = _post("/chat/completions", {"model": READ_MODEL, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": [
        {"type": "text", "text": 'This picture is a dependency diagram. Read it exactly as drawn. Answer only with JSON: {"nodes": ["label", ...], '
         '"edges": [{"from": "label", "to": "label"}, ...]}, where an edge follows the direction of an arrow. Spell labels exactly as drawn, even if they look wrong.'},
        {"type": "image_url", "image_url": {"url": url}}]}]})
    u = d.get("usage") or {}
    return json.loads(d["choices"][0]["message"]["content"]), round((u.get("prompt_tokens", 0) * READ_PRICE[0] + u.get("completion_tokens", 0) * READ_PRICE[1]) / 1e6, 6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--max-images", type=int, default=16, help="hard limit on images drawn in this run")
    args = ap.parse_args()
    if args.results.exists():
        raise SystemExit(f"{args.results} exists: results are never overwritten")
    out = {"drawnBy": IMAGE_MODEL, "readBackBy": READ_MODEL, "decidedBy": "exact comparison with the analyzer's report", "maxAttempts": MAX_ATTEMPTS, "maxImages": args.max_images, "trees": []}
    drawn = 0
    for item in json.loads(args.spec.read_text()):
        report = json.loads(Path(item["report"]).read_text())
        edges = [tuple(e) for e in item["edges"]] if "edges" in item else edges_of(report, item["kinds"])
        tree = {**{k: item[k] for k in ("slug", "title")}, "repository": report["source"]["location"], "commit": report["source"]["commit"],
                "edges": edges, "attempts": [], "verified": False, "image": None}
        for n in range(1, MAX_ATTEMPTS + 1):
            if drawn >= args.max_images:
                tree["attempts"].append({"attempt": n, "error": "not drawn: the image limit was reached"})
                break
            drawn += 1
            started = time.time()
            try:
                image, usage = draw(edges)
                read, read_usd = read_back(image)
            except (urllib.error.URLError, KeyError, ValueError, subprocess.CalledProcessError) as e:
                tree["attempts"].append({"attempt": n, "error": type(e).__name__})
                print(item["slug"], n, "error", type(e).__name__, flush=True)
                continue
            result = compare(edges, read)
            name = f"{item['slug']}-{n}.webp"
            args.out_dir.mkdir(parents=True, exist_ok=True)
            (args.out_dir / name).write_bytes(image)
            tree["attempts"].append({"attempt": n, "image": name, "imageTokens": usage, "readUsd": read_usd, "seconds": round(time.time() - started, 1), **result})
            print(item["slug"], n, "match" if result["match"] else "no match", {k: len(v) for k, v in result.items() if k != "match"}, flush=True)
            if result["match"]:
                tree.update(verified=True, image=name)
                break
        out["trees"].append(tree)
        args.results.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
