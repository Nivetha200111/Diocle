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
import sys
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
    if len(data) > MAX_IMAGE_BYTES:  # the file may have grown between stat and read
        raise ImageRejected(f"image is {len(data)} bytes; the limit is {MAX_IMAGE_BYTES} (2 MB)")
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


def compile_check(source: Path, copybook_dir: Path | None, timeout: int = 60) -> dict:
    """cobc -fsyntax-only with the verifier's flags. {"ok": bool, "errors": str}"""
    try:
        from diocle_verifier.runners import IBM_FLAGS, _exec
    except ImportError:
        raise SystemExit("diocle-verifier is not installed: pip install -e ../verifier")
    cmd = ["cobc", "-fsyntax-only", "-std=ibm", *IBM_FLAGS]
    if copybook_dir and copybook_dir.is_dir():
        cmd += ["-I", str(copybook_dir)]
    try:
        proc = _exec(cmd + [str(source)], timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "errors": "cobc (GnuCOBOL) is not installed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": f"cobc did not finish within {timeout} s"}
    text = (proc.stderr + proc.stdout).replace(str(source.parent) + "/", "")
    return {"ok": proc.returncode == 0, "errors": text.strip()[:3000]}


def sandbox_profile(work: Path, exe: Path) -> str:
    """macOS sandbox-exec profile for the transcription's executable: no network, no file writes outside its own work
    directory (plus /dev/null and the tty), no exec of anything but the executable itself. Reads stay open (the GnuCOBOL
    runtime libraries live all over the disk). Defense in depth only; see the README for what it does not cover."""
    for path in (work, exe):
        if '"' in str(path) or "\\" in str(path):
            raise ValueError("unsafe path for a sandbox profile")
    return ("(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
            f'(allow file-write* (subpath "{work}") (literal "/dev/null") (literal "/dev/dtracehelper") (literal "/dev/tty"))\n'
            f'(deny process-exec*)\n(allow process-exec (literal "{exe}"))\n')


def sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def differential(against: Path, source: Path, *, random_count: int = DIFF_INPUTS, seed: int = DIFF_SEED,
                 timeout: int = 120, sandbox: bool = True) -> dict:
    """Run the original (against/sample.json's source) and the transcription on the same generated inputs; compare the
    whole output sequence, stdout and exit code. Uses the verifier's generator, builder and comparator.
    WARNING: this builds and RUNS the transcription (model-written COBOL) on this machine with plain subprocesses. On
    macOS the transcription's executable additionally runs under sandbox-exec (`sandbox`), elsewhere there is no sandbox.
    Only for our own synthetic printouts on a dev machine, and only when the caller opted in (transcribe's run_model_code).
    Each program run is limited to `timeout` seconds. A single-file program with no output layout is compared on stdout
    and exit code."""
    from diocle_verifier.diff import compare
    from diocle_verifier.inputs import Case, generate_cases
    from diocle_verifier.layout import load_fields, record_format, record_length
    from diocle_verifier.multi import is_multi
    from diocle_verifier.runners import CLOCK_ENV, Run, _exec, build_cobol, read_records, write_records

    rec = {"against": str(against), "ran": False, "seed": seed, "inputs": 0, "matched": 0, "mismatched": 0}
    meta = json.loads((against / "sample.json").read_text())
    if "files" in meta:  # the analyzer's file list: one input and no output file is a DISPLAY-only program
        ins = [f for f in meta["files"] if f["direction"] == "input"]
        if len(ins) != 1 or len(ins) != len(meta["files"]):
            return {**rec, "reason": "only programs with one input file (and at most DISPLAY output) are supported"}
        layouts, dd = {"input": ins[0]["layout"]}, {"input": ins[0]["dd"]}
    elif is_multi(meta):
        return {**rec, "reason": "multi-file programs are not supported by the transcription differential"}
    else:
        layouts, dd = meta["layouts"], meta["dd"]
    has_out = "output" in layouts and "output" in dd
    in_fields = load_fields(layouts["input"])
    out_fields = load_fields(layouts["output"]) if has_out else []
    fixtures = [Case(f"fixture-{c['id']}", "fixture", c["record"]) for c in meta.get("fixtureCases", [])]
    cases = fixtures + generate_cases(in_fields, seed=seed, random_count=random_count)
    in_fmt = record_format(layouts["input"])
    out_fmt = (record_format(layouts["output"]), record_length(out_fields)) if has_out else ("line", 0)
    copybooks = against / meta["copybookDir"]
    modules = [against / m for m in meta.get("modules", [])]
    collation = meta.get("collation", "ascii")
    use_sandbox = sandbox and sandbox_available()
    rec["sandbox"] = "sandbox-exec" if use_sandbox else "none"
    with tempfile.TemporaryDirectory(prefix="diocle-transcribe-") as tmp:
        tmp = Path(tmp).resolve()
        work_o, work_t = tmp / "original", tmp / "transcribed"
        work_o.mkdir(), work_t.mkdir()
        input_path = tmp / "input.dat"
        write_records(input_path, [c.record for c in cases], in_fmt)

        def run(src: Path, work: Path, label: str, sandboxed: bool) -> Run:
            cmd, failed = build_cobol(src, copybooks, work, modules, collation)
            if failed:
                return failed
            out = work / f"{label}.out"
            env = {**CLOCK_ENV, f"DD_{dd['input']}": str(input_path)}
            if has_out:
                env[f"DD_{dd['output']}"] = str(out)
            if sandboxed:
                profile = tmp / f"{label}.sb"
                profile.write_text(sandbox_profile(work, Path(cmd[0]).resolve()))
                cmd = ["sandbox-exec", "-f", str(profile), *cmd]
            proc = _exec(cmd, env=env, cwd=work, timeout=timeout)
            return Run(True, proc.returncode, proc.stdout, proc.stderr, read_records(out, *out_fmt))

        try:
            orig = run(against / meta["source"], work_o, "original", False)  # our own sample, not model output
            trans = run(source, work_t, "transcribed", use_sandbox)
        except subprocess.TimeoutExpired:
            return {**rec, "inputs": len(cases), "reason": f"a program did not finish within {timeout} s (timed out)"}
    rec["inputs"] = len(cases)
    if not orig.compiled:
        return {**rec, "reason": "the original does not compile with GnuCOBOL: " + orig.stderr.strip()[:300]}
    if not trans.compiled:
        return {**rec, "reason": "the transcription does not build: " + trans.stderr.strip()[:300]}
    stdout_compared = bool(orig.stdout.strip())
    if not orig.output_lines and not stdout_compared:
        return {**rec, "reason": "the original wrote no output records and no stdout: nothing to compare, so no proof"}
    stdout_match, exit_match = orig.stdout == trans.stdout, orig.exit_code == trans.exit_code
    identical = orig.output_lines == trans.output_lines and stdout_match and exit_match
    if has_out:
        results = compare(cases, orig.output_lines, trans.output_lines, out_fields, out_fmt[0])
        bad = [r for r in results if not r["match"]]
        matched, mismatched = len(results) - len(bad), len(bad) + (0 if stdout_match else 1) + (0 if exit_match else 1)
    else:  # no output file: the whole run is one comparison of stdout and exit code
        bad, matched, mismatched = [], (len(cases) if identical else 0), (0 if identical else 1)
    if not identical and not mismatched:  # same values, differing only in trailing blanks
        mismatched = 1
    return {**rec, "ran": True, "outputRecords": len(orig.output_lines), "stdoutCompared": stdout_compared,
            "matched": matched, "mismatched": mismatched, "stdoutMatch": stdout_match, "exitCodeMatch": exit_match,
            "firstMismatches": [{k: r.get(k) for k in ("inputId", "input", "originalOutput", "convertedOutput", "fieldDiffs")
                                 if k in r} for r in bad[:5]]}


_DENY_ANYWHERE = re.compile(r"CBL_|C[$]|[\"']\s*SYSTEM\s*[\"']", re.I)
_DIRECTIVE = re.compile(r">>|^\s*[$]\s*SET\b|SOURCE\s*-?\s*FORMAT", re.I | re.M)


def layout_problem(source: str) -> str | None:
    """Only plain fixed-format text is accepted, so comment indicators can be read reliably: no tabs, no compiler
    directives (>>SOURCE FORMAT IS FREE, $ SET, ...), nothing in columns 1-6 but blanks or digits, an indicator in
    column 7 of blank, *, / or -, and nothing after column 72."""
    if "\t" in source:
        return "tabs are not accepted (columns would be uncertain)"
    if _DIRECTIVE.search(source):
        return "compiler directives (>>, $ SET, SOURCE FORMAT) are not accepted"
    for n, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        if len(line) < 7 or not (line[:6].strip().isdigit() or not line[:6].strip()):
            return f"line {n} is not fixed format (columns 1-6 must be blank or digits, code starts in column 7 or later)"
        if line[6] not in " */-":
            return f"line {n}: column 7 must be blank, *, / or - (found {line[6]!r})"
        if line[72:].strip():
            return f"line {n} has text after column 72"
    return None


def unsafe_calls(source: str, allowed_programs=frozenset()) -> str | None:
    """A reason when the transcription could do more than read and write the program's files: CALL "SYSTEM", any CBL_*
    or C$* routine, a CALL to an identifier (dynamic) or to a program that is not listed. Comment lines are skipped
    (call layout_problem first: it makes the comment rule reliable). A best-effort scan, NOT a security boundary."""
    code = "\n".join(ln for ln in source.splitlines() if not (len(ln) > 6 and ln[6] in "*/"))
    m = _DENY_ANYWHERE.search(code)
    if m:
        return f"the transcription mentions {m.group(0).strip()!r} (system or CBL_/C$ routines are not allowed)"
    for call in re.finditer(r"\bCALL\s+(\S+)", code, re.I):
        target = call.group(1).rstrip(".")
        if not (target[:1] in ("'", '"') and len(target) > 2):
            return f"CALL {target}: only CALLs to quoted program names listed with the original are allowed"
        if target.strip("\"'").upper() not in allowed_programs:
            return f"CALL {target}: not a program listed with the original"
    return None


def file_problem(source: str, dd_names: set[str], copybooks: set[str]) -> str | None:
    """ASSIGN TO only the original's DD names (no paths, no literals) and COPY only the original's copybooks."""
    code = "\n".join(ln for ln in source.splitlines() if not (len(ln) > 6 and ln[6] in "*/"))
    for m in re.finditer(r"\bASSIGN\s+(?:TO\s+)?(\S+)", code, re.I):
        target = m.group(1).rstrip(".")
        if target.upper() not in {d.upper() for d in dd_names}:
            return f"ASSIGN TO {target}: only the original's DD names {sorted(dd_names)} are allowed"
    for m in re.finditer(r"\bCOPY\s+(\S+)", code, re.I):
        target = m.group(1).rstrip(".")
        if target.upper() not in {c.upper() for c in copybooks}:
            return f"COPY {target}: only the original's own copybooks {sorted(copybooks)} are allowed"
    return None


def scan_transcription(source: str, *, programs=frozenset(), dd_names: set[str] | None = None,
                       copybooks: set[str] | None = None) -> str | None:
    """Best-effort refusal scan of model text before it is compiled or run: NOT a security boundary (a model can build
    names at run time, and no deny-list is airtight). Running it stays opt-in (transcribe's run_model_code)."""
    return (layout_problem(source) or unsafe_calls(source, programs)
            or (file_problem(source, dd_names, copybooks or set()) if dd_names is not None else None))


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


def _out_dir_problem(out_dir: Path, against: Path | None) -> str | None:
    """--out must be a new or empty directory that does not overlap the original: nothing is overwritten silently, and the
    transcription can never replace the original it is about to be compared with."""
    if out_dir.is_symlink():
        return f"--out ({out_dir}) is a symbolic link: refusing"
    if against is not None:
        o, a = out_dir.resolve(), Path(against).resolve()
        if o == a or a in o.parents or o in a.parents:
            return f"--out ({out_dir}) overlaps --against ({against}): refusing, the original must not be touched"
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        return f"--out ({out_dir}) exists and is not an empty directory: refusing to overwrite"
    return None


def transcribe(image_path: Path, out_dir: Path, *, settings: Settings | None, client: ModelClient | None = None,
               against: Path | None = None, max_usd: float | None = None, max_output_tokens: int | None = None,
               check: Callable[..., dict] = compile_check, diff: Callable[..., dict] = differential,
               timeout: int | None = None, run_model_code: bool = False,
               log: Callable[[str], None] = print) -> dict:
    """Run the intake. Always returns a record (contracts/transcription.schema.json); writes it, and the COBOL when one
    was produced, under out_dir (never into an existing non-empty directory, never over the original). Raises nothing for
    a model or gate failure: the status says what happened. With `against`, the original is snapshotted into a temp
    directory first and every comparison uses the snapshot. `timeout` (seconds) limits each cobc or program run.
    The differential BUILDS AND RUNS the model-written COBOL on this machine, so it only happens with run_model_code=True;
    otherwise the best status is compiled-unchecked."""
    usd_cap, tok_cap = _caps()
    usd_cap = usd_cap if max_usd is None else max_usd
    tok_cap = tok_cap if max_output_tokens is None else max_output_tokens
    caps = {"maxCalls": settings.max_calls_per_run if settings else 0, "maxUsd": usd_cap, "maxOutputTokens": tok_cap}
    out_dir = Path(out_dir)
    problem = _out_dir_problem(out_dir, against)
    if problem:  # nothing is written anywhere: not even the record
        placeholder = {"name": Path(image_path).name, "mediaType": None, "bytes": 0, "sha256": ""}
        return _refused(placeholder, problem, settings, caps)
    if against is None:
        return _transcribe(image_path, out_dir, settings, client, None, None, caps, check, diff, timeout, run_model_code, log)
    against = Path(against)
    if not (against / "sample.json").is_file():
        placeholder = {"name": Path(image_path).name, "mediaType": None, "bytes": 0, "sha256": ""}
        return _finish(_refused(placeholder, f"--against: no sample.json in {against}", settings, caps), out_dir)
    with tempfile.TemporaryDirectory(prefix="diocle-original-") as tmp:
        snapshot = Path(tmp) / "original"
        shutil.copytree(against, snapshot)
        return _transcribe(image_path, out_dir, settings, client, snapshot, str(against), caps, check, diff, timeout,
                           run_model_code, log)


def _transcribe(image_path, out_dir, settings, client, against, against_label, caps, check, diff, timeout,
                run_model_code, log) -> dict:
    usd_cap, tok_cap = caps["maxUsd"], caps["maxOutputTokens"]
    extra = {"timeout": timeout} if timeout else {}
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

    copybooks, allowed, dd_names, copy_names = None, set(), None, None
    if against:
        try:
            meta = json.loads((against / "sample.json").read_text())
            copybooks = against / meta["copybookDir"]
            allowed = {Path(m).stem.upper() for m in meta.get("modules", [])}
            dd_names = ({str(v) for v in meta["dd"].values()} if isinstance(meta.get("dd"), dict) else set()) \
                | {str(f["dd"]) for f in meta.get("files", [])}
            if not dd_names:
                raise KeyError("dd")
            copy_names = {f.stem for f in copybooks.iterdir() if f.is_file()} if copybooks.is_dir() else set()
        except (ValueError, KeyError, AttributeError, OSError) as e:
            return _finish(_refused(info, f"--against: unusable sample.json ({type(e).__name__}: {e})", settings, caps), out_dir)

    messages: list[dict] = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": image.data_url()}}]}]
    attempts, source, compiled, reason, refusal = [], "", None, None, None
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
        refusal = scan_transcription(source, programs=allowed, dd_names=dd_names, copybooks=copy_names)
        if refusal:  # never compiled, never run, never written
            attempts.append({"n": n, "finishReason": choice.finish_reason, "lines": source.count("\n"),
                             "compile": {"ok": False, "errors": "not compiled: " + refusal}})
            break
        with tempfile.TemporaryDirectory(prefix="diocle-vision-") as tmp:
            src_path = Path(tmp) / "TRANSCRIBED.cbl"
            src_path.write_text(source)
            compiled = check(src_path, copybooks, **extra)
        attempts.append({"n": n, "finishReason": choice.finish_reason, "lines": source.count("\n"), "compile": compiled})
        log(f"attempt {n}: compile {'OK' if compiled['ok'] else 'FAILED'}")
        if compiled["ok"]:
            break
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": RETRY.format(errors=compiled["errors"])}]

    record = {"version": VERSION, "status": "no-transcription", "reason": reason, "image": info, "model": settings.model,
              "program": program_id(source) if source and not refusal else None, "source": None, "attempts": attempts,
              "usage": usage_of(client.calls), "caps": caps, "compile": compiled, "differential": None}
    if refusal:
        record["status"], record["reason"] = "refused", refusal
        return _finish(record, out_dir)
    if source:
        name = record["program"] or re.sub(r"[^A-Za-z0-9]", "", Path(image.name).stem).upper() or "PROGRAM"
        record["source"] = f"src/{name}.cbl"
        (out_dir / "src").mkdir(parents=True, exist_ok=True)
        (out_dir / record["source"]).write_text(source)
    if compiled and compiled["ok"]:
        record["reason"] = None
        if against and not run_model_code:
            record["status"] = "compiled-unchecked"
            record["reason"] = "running model-written COBOL on this machine needs --run-model-code"
            _copy_sample_files(against, Path(against_label).name, out_dir, record)
        elif against:
            log("WARNING: --run-model-code: the transcription is built and EXECUTED on this machine"
                + (" under sandbox-exec (no network, writes only in its temp dir)." if sandbox_available()
                   else ", UNSANDBOXED (no sandbox-exec here)."))
            try:
                d = diff(against, out_dir / record["source"], **extra)
            except subprocess.TimeoutExpired:
                d = {"against": str(against), "ran": False, "inputs": 0, "matched": 0, "mismatched": 0,
                     "reason": "timed out"}
            except (OSError, KeyError, ValueError) as e:  # cobc missing, malformed sample.json, ...
                d = {"against": str(against), "ran": False, "inputs": 0, "matched": 0, "mismatched": 0,
                     "reason": f"{type(e).__name__}: {e}"}
            d["against"] = against_label  # the snapshot is a temp directory; name the original
            record["differential"] = d
            if not d["ran"]:
                record["status"], record["reason"] = "compiled-unchecked", "differential could not run: " + (d.get("reason") or "")
            else:
                # a pass needs something actually compared: at least one output record (or stdout, checked in differential())
                record["status"] = ("verified-identical" if d["mismatched"] == 0 and d["inputs"] > 0
                                    and (d.get("outputRecords", 1) > 0 or d.get("stdoutCompared", False)) else "differs")
            _copy_sample_files(against, Path(against_label).name, out_dir, record)
        else:
            record["status"] = "compiled-unchecked"
            record["reason"] = "no original supplied (--against), so the transcription is NOT checked against anything"
    elif source:
        record["status"] = "compile-failed"
        record["reason"] = reason or "still not valid COBOL after the last attempt"
    return _finish(record, out_dir)


def _copy_sample_files(against: Path, against_name: str, out_dir: Path, record: dict) -> None:
    """Make out_dir a usable sample: the original's copybooks (they are not on the printout) and a sample.json that
    says where the source came from. No Java is claimed."""
    meta = json.loads((against / "sample.json").read_text())
    # copybooks always go to out_dir/copybooks: a copybookDir such as "src" could collide with the transcription itself
    if (against / meta["copybookDir"]).is_dir():
        shutil.copytree(against / meta["copybookDir"], out_dir / "copybooks")
    meta["copybookDir"] = "copybooks"
    meta["description"] = (f"SYNTHETIC. Transcribed from the image {record['image']['name']} by {record['model']}; "
                           f"status {record['status']} (see transcription.json). Copybooks copied from {against_name}.")
    meta["source"] = record["source"]
    meta.pop("javaConversion", None)
    (out_dir / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")


def _finish(record: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcription.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
