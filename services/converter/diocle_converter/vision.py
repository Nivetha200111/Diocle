"""Printout intake: an image of a COBOL listing becomes COBOL source, and the ORIGINAL gate decides whether it is right.

A vision model (Muse Wonder, VISION_MODEL_ID; empty = feature off) reads a PNG/JPG of a fixed-format listing and writes
COBOL. Nothing the model says is trusted:

  1. compile gate: `cobc -fsyntax-only -std=ibm` with the verifier's IBM flags. A failure sends the compiler errors back
     for one more attempt (hard cap VISION_MAX_CALLS, default 3, plus a dollar cap VISION_MAX_USD and a per-call
     output-token cap VISION_MAX_OUTPUT_TOKENS: rule 10);
  2. differential gate (only with an original to compare to): the transcription and the original are both compiled with
     GnuCOBOL and run on the same generated inputs (the verifier's generator and comparator); the output records, stdout
     and exit code must be identical. A mismatch is reported, never hidden, and never "fixed" by the model.

Without an original the best possible result is `compiled-unchecked`: it compiles, but nothing proves it is what the
paper said. The record shape is contracts/transcription.schema.json.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .client import BudgetExceeded, ModelClient, _call_cost, usage_of
from .config import PRICES, Settings

VERSION = "0.1"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
DIFF_INPUTS = 1000  # random inputs on top of the verifier's fixture and boundary cases
DIFF_SEED = 1026

PROMPT = """This is a photograph or scan of a COBOL program listing printed on fixed-format paper.
Transcribe it into COBOL source, exactly as printed.

Rules:
- Fixed format: columns 1-6 are the sequence area, column 7 is the indicator (* for a comment, - for a continuation),
  columns 8-72 hold the code. Keep every character in the column it is printed in; do not re-indent, tidy or "fix" anything.
- If the page has a gutter of printer line numbers on the left (separated by a vertical rule), it is NOT part of the
  source: leave it out. If the sequence area (columns 1-6) is blank on paper, write six spaces.
- Copy comments, literals and spacing exactly. Distinguish the digit 0 from the letter O and the digit 1 from the letter I
  and l by the context of the COBOL.
- Do not add, remove, reorder or correct any line. Do not explain.
Reply with the COBOL source only, in one ```cobol block."""

RETRY = """The compiler (cobc -std=ibm, fixed format) rejected your transcription:

{errors}

Look at the image again. Fix only the lines where you mis-read the paper; do not invent code to make it compile.
Reply with the complete corrected COBOL source only, in one ```cobol block."""


@dataclass
class Image:
    name: str
    media_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def data_url(self) -> str:
        return f"data:{self.media_type};base64,{base64.b64encode(self.data).decode()}"


class ImageRejected(ValueError):
    pass


def load_image(path: Path) -> Image:
    """PNG or JPEG only (judged by the bytes, not the file name), at most 2 MB."""
    path = Path(path)
    if not path.is_file():
        raise ImageRejected(f"not a file: {path}")
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ImageRejected(f"image is {size} bytes; the limit is {MAX_IMAGE_BYTES} (2 MB)")
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        media = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        media = "image/jpeg"
    else:
        raise ImageRejected("only PNG and JPEG images are accepted")
    return Image(path.name, media, data)


def clean_transcription(text: str) -> str:
    """The COBOL from a model reply: the fenced block if there is one; trailing blanks off; one final newline.
    Nothing else is touched (columns are the point)."""
    m = re.search(r"```[A-Za-z]*\n(.*?)```", text, re.S) or re.search(r"```[A-Za-z]*\n(.*)\Z", text, re.S)
    body = m.group(1) if m else text
    lines = [ln.rstrip() for ln in body.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def program_id(source: str) -> str | None:
    m = re.search(r"^.{6}[ \-]?\s*PROGRAM-ID\.\s+([A-Za-z0-9\-]+)", source, re.M | re.I)
    return m.group(1).upper() if m else None


def compile_check(source: Path, copybook_dir: Path | None) -> dict:
    """cobc -fsyntax-only with the verifier's flags. {"ok": bool, "errors": str}"""
    try:
        from diocle_verifier.runners import IBM_FLAGS, _exec
    except ImportError:
        raise SystemExit("diocle-verifier is not installed: pip install -e ../verifier")
    cmd = ["cobc", "-fsyntax-only", "-std=ibm", *IBM_FLAGS]
    if copybook_dir and copybook_dir.is_dir():
        cmd += ["-I", str(copybook_dir)]
    try:
        proc = _exec(cmd + [str(source)])
    except FileNotFoundError:
        return {"ok": False, "errors": "cobc (GnuCOBOL) is not installed"}
    text = (proc.stderr + proc.stdout).replace(str(source.parent) + "/", "")
    return {"ok": proc.returncode == 0, "errors": text.strip()[:3000]}


def differential(against: Path, source: Path, *, random_count: int = DIFF_INPUTS, seed: int = DIFF_SEED) -> dict:
    """Run the original (against/sample.json's source) and the transcription on the same generated inputs; compare the
    whole output sequence, stdout and exit code. Uses the verifier's generator, runner and comparator."""
    from diocle_verifier.diff import compare
    from diocle_verifier.inputs import Case, generate_cases
    from diocle_verifier.layout import load_fields, record_format, record_length
    from diocle_verifier.multi import is_multi
    from diocle_verifier.runners import run_cobol, write_records

    rec = {"against": str(against), "ran": False, "seed": seed, "inputs": 0, "matched": 0, "mismatched": 0}
    meta = json.loads((against / "sample.json").read_text())
    if is_multi(meta):
        return {**rec, "reason": "multi-file programs are not supported by the transcription differential"}
    in_fields = load_fields(meta["layouts"]["input"])
    out_fields = load_fields(meta["layouts"]["output"])
    fixtures = [Case(f"fixture-{c['id']}", "fixture", c["record"]) for c in meta.get("fixtureCases", [])]
    cases = fixtures + generate_cases(in_fields, seed=seed, random_count=random_count)
    in_fmt = record_format(meta["layouts"]["input"])
    out_fmt = (record_format(meta["layouts"]["output"]), record_length(out_fields))
    copybooks = against / meta["copybookDir"]
    modules = [against / m for m in meta.get("modules", [])]
    collation = meta.get("collation", "ascii")
    with tempfile.TemporaryDirectory(prefix="diocle-transcribe-") as tmp:
        work_o, work_t = Path(tmp) / "original", Path(tmp) / "transcribed"
        work_o.mkdir(), work_t.mkdir()
        input_path = Path(tmp) / "input.dat"
        write_records(input_path, [c.record for c in cases], in_fmt)
        orig = run_cobol(against / meta["source"], copybooks, meta["dd"], input_path, work_o, out_fmt, modules, collation)
        trans = run_cobol(source, copybooks, meta["dd"], input_path, work_t, out_fmt, modules, collation)
    rec["inputs"] = len(cases)
    if not orig.compiled:
        return {**rec, "reason": "the original does not compile with GnuCOBOL: " + orig.stderr.strip()[:300]}
    if not trans.compiled:
        return {**rec, "reason": "the transcription does not build: " + trans.stderr.strip()[:300]}
    results = compare(cases, orig.output_lines, trans.output_lines, out_fields, out_fmt[0])
    bad = [r for r in results if not r["match"]]
    stdout_match, exit_match = orig.stdout == trans.stdout, orig.exit_code == trans.exit_code
    identical = orig.output_lines == trans.output_lines and stdout_match and exit_match
    mismatched = len(bad) + (0 if stdout_match else 1) + (0 if exit_match else 1)
    if not identical and not mismatched:  # same values, differing only in trailing blanks
        mismatched = 1
    return {**rec, "ran": True, "matched": len(results) - len(bad), "mismatched": mismatched,
            "stdoutMatch": stdout_match, "exitCodeMatch": exit_match,
            "firstMismatches": [{k: r.get(k) for k in ("inputId", "input", "originalOutput", "convertedOutput", "fieldDiffs")
                                 if k in r} for r in bad[:5]]}


def _caps() -> tuple[float, int]:
    import os
    def num(name, default, cast):
        try:
            return cast(os.environ.get(name, "") or default)
        except ValueError:
            return cast(default)
    return num("VISION_MAX_USD", "0.20", float), max(500, num("VISION_MAX_OUTPUT_TOKENS", "5000", int))


def _refused(image_info: dict, reason: str, settings: Settings | None, caps: dict) -> dict:
    return {"version": VERSION, "status": "refused", "reason": reason, "image": image_info,
            "model": settings.model if settings else None, "program": None, "source": None, "attempts": [],
            "usage": {"calls": 0, "inputTokens": 0, "outputTokens": 0, "estimatedCostUsd": 0.0, "modelCalls": []},
            "caps": caps, "compile": None, "differential": None}


def transcribe(image_path: Path, out_dir: Path, *, settings: Settings | None, client: ModelClient | None = None,
               against: Path | None = None, max_usd: float | None = None, max_output_tokens: int | None = None,
               check: Callable[[Path, Path | None], dict] = compile_check,
               diff: Callable[..., dict] = differential, log: Callable[[str], None] = print) -> dict:
    """Run the intake. Always returns a record (contracts/transcription.schema.json); writes it, and the COBOL when one
    compiled or was the best attempt, under out_dir. Raises nothing for a model or gate failure: the status says what happened."""
    usd_cap, tok_cap = _caps()
    usd_cap = usd_cap if max_usd is None else max_usd
    tok_cap = tok_cap if max_output_tokens is None else max_output_tokens
    caps = {"maxCalls": settings.max_calls_per_run if settings else 0, "maxUsd": usd_cap, "maxOutputTokens": tok_cap}
    out_dir = Path(out_dir)
    try:
        image = load_image(image_path)
    except ImageRejected as e:
        name = Path(image_path).name
        record = _refused({"name": name, "mediaType": None, "bytes": 0, "sha256": ""}, str(e), settings, caps)
        return _finish(record, out_dir)
    info = {"name": image.name, "mediaType": image.media_type, "bytes": len(image.data), "sha256": image.sha256}
    if settings is None:
        return _finish(_refused(info, "image transcription is off: set VISION_MODEL_ID (and a Meta key) in .env", None, caps), out_dir)
    if PRICES.get(settings.model) is None:
        return _finish(_refused(info, f"{settings.model} has no price in PRICES; the cost cap fails closed", settings, caps), out_dir)
    client = client or ModelClient(settings)

    copybooks = None
    if against:
        meta_path = Path(against) / "sample.json"
        if not meta_path.is_file():
            return _finish(_refused(info, f"--against: no sample.json in {against}", settings, caps), out_dir)
        copybooks = Path(against) / json.loads(meta_path.read_text())["copybookDir"]

    messages: list[dict] = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": image.data_url()}}]}]
    attempts, source, compiled, reason = [], "", None, None
    price = PRICES[settings.model]
    while True:
        n = len(attempts) + 1
        spent = usage_of(client.calls)["estimatedCostUsd"] or 0.0
        # worst case for the next call: a generous flat input estimate (a 1000x1100 page is about 1.5k image tokens; the
        # bytes of the file say nothing about tokens) plus the whole output-token cap
        worst = 12000 * price[0] / 1e6 + tok_cap * price[2] / 1e6
        if n > settings.max_calls_per_run:
            reason = f"call cap reached ({settings.max_calls_per_run})"
            break
        if spent + worst > usd_cap:
            reason = f"cost cap would be exceeded (spent ${spent:.4f}, next call up to ${worst:.4f}, cap ${usd_cap:.2f})"
            break
        try:
            choice = client.chat(role="vision-transcribe", round=n, messages=messages, max_tokens=tok_cap)
        except BudgetExceeded as e:
            reason = str(e)
            break
        except Exception as e:  # a provider error: record type and status only, never the body
            reason = f"model call failed: {type(e).__name__} {getattr(e, 'status_code', '')}".strip()
            break
        text = choice.message.content or ""
        source = clean_transcription(text)
        call_cost = _call_cost(client.calls[-1])
        log(f"call {n}: {client.calls[-1].inputTokens} in / {client.calls[-1].outputTokens} out"
            f" (reasoning {client.calls[-1].reasoningTokens}), ${call_cost or 0:.4f}, finish={choice.finish_reason}")
        if not source:
            attempts.append({"n": n, "finishReason": choice.finish_reason, "lines": 0,
                             "compile": {"ok": False, "errors": "the model returned no COBOL"
                                         + (" (output token cap reached before an answer)" if choice.finish_reason == "length" else "")}})
            reason = attempts[-1]["compile"]["errors"]
            break
        with tempfile.TemporaryDirectory(prefix="diocle-vision-") as tmp:
            src_path = Path(tmp) / "TRANSCRIBED.cbl"
            src_path.write_text(source)
            compiled = check(src_path, copybooks)
        attempts.append({"n": n, "finishReason": choice.finish_reason, "lines": source.count("\n"), "compile": compiled})
        log(f"attempt {n}: compile {'OK' if compiled['ok'] else 'FAILED'}")
        if compiled["ok"]:
            break
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": RETRY.format(errors=compiled["errors"])}]

    record = {"version": VERSION, "status": "no-transcription", "reason": reason, "image": info, "model": settings.model,
              "program": program_id(source) if source else None, "source": None, "attempts": attempts,
              "usage": usage_of(client.calls), "caps": caps, "compile": compiled, "differential": None}
    if source:
        name = record["program"] or re.sub(r"[^A-Za-z0-9]", "", Path(image.name).stem).upper() or "PROGRAM"
        record["source"] = f"src/{name}.cbl"
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        (out_dir / record["source"]).write_text(source)
    if compiled and compiled["ok"]:
        record["reason"] = None
        if against:
            record["differential"] = diff(Path(against), out_dir / record["source"])
            d = record["differential"]
            if not d["ran"]:
                record["status"], record["reason"] = "compiled-unchecked", "differential could not run: " + d.get("reason", "")
            else:
                record["status"] = "verified-identical" if d["mismatched"] == 0 and d["inputs"] > 0 else "differs"
            _copy_sample_files(Path(against), out_dir, record)
        else:
            record["status"] = "compiled-unchecked"
            record["reason"] = "no original supplied (--against), so the transcription is NOT checked against anything"
    elif source:
        record["status"] = "compile-failed"
        record["reason"] = reason or "still not valid COBOL after the last attempt"
    return _finish(record, out_dir)


def _copy_sample_files(against: Path, out_dir: Path, record: dict) -> None:
    """Make out_dir a usable sample: the original's copybooks (they are not on the printout) and a sample.json that
    says where the source came from. No Java is claimed."""
    meta = json.loads((against / "sample.json").read_text())
    dest = out_dir / meta["copybookDir"]
    if (against / meta["copybookDir"]).is_dir() and not dest.exists():
        shutil.copytree(against / meta["copybookDir"], dest)
    meta["description"] = (f"SYNTHETIC. Transcribed from the image {record['image']['name']} by {record['model']}; "
                           f"status {record['status']} (see transcription.json). Copybooks copied from {against.name}.")
    meta["source"] = record["source"]
    meta.pop("javaConversion", None)
    (out_dir / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")


def _finish(record: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcription.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
