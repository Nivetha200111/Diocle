"""Check behaviour claims against the ORIGINAL COBOL (contracts/behavior-claims.schema.json).

A model proposes claims with examples; this module is the only authority on whether they hold. It only ever
compiles and runs the original program (GnuCOBOL, -std=ibm, the verification flags), never any model-written code,
and with DIOCLE_SANDBOX_URL set the compile-and-run happens in the sandbox container like every other job.

  run_original(sample_dir, examples)  -> one run record per example (output records, stdout, return code)
  judge(expected, run, out_fields)    -> matched / differed / unchecked for one example, with the actual values
  claim_status(example_statuses)      -> confirmed / refuted / unchecked for one claim
  summarize(claims)                   -> the contract's `summary`
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .layout import Field, load_fields, parse_record, record_format, record_length
from .runners import CLOCK_ENV, _exec, build_cobol, read_records, write_records

CHECKED_WITH = "GnuCOBOL -std=ibm"
MAX_EXAMPLES = 60  # one cobc build, then one short run per example
RUN_TIMEOUT = 10  # seconds per example
TOTAL_BUDGET = 90  # seconds for all runs of one call; no run starts after TOTAL_BUDGET - RUN_TIMEOUT, so the loop ends within it
MAX_STDOUT = 2000  # what the report shows of stdout
CAPTURE_STDOUT = 32 * 1024  # what is captured, so stdoutContains is judged on the real output, not the displayed part
MAX_RECORDS = 20  # output records returned per example; the true count travels beside them
MAX_RECORD_LEN = 4096


def unsupported(meta: dict) -> str | None:
    """Why this sample cannot have its claims checked here, else None. Claims address single-file record programs."""
    from .multi import is_multi

    if is_multi(meta):
        return "several files, or a program that writes no file: claims are checked for single-file programs"
    if "layouts" not in meta:
        return "the sample has no file layouts"
    return None


def run_original(sample_dir: Path, examples: list[dict]) -> list[dict]:
    """examples: [{"id", "records": [input record strings, already formatted for the input layout]}].
    Returns one dict per example: {"id", "ran", "records" (output lines), "stdout", "returnCode", "error"}.
    In the sandbox (DIOCLE_SANDBOX_URL) when set; the original is compiled once."""
    import os

    if len(examples) > MAX_EXAMPLES:
        raise ValueError(f"at most {MAX_EXAMPLES} examples per call")
    if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
        from .sandbox import remote_claims

        return remote_claims(Path(sample_dir).resolve(), examples)
    return run_local(Path(sample_dir).resolve(), examples)


def run_local(sample_dir: Path, examples: list[dict]) -> list[dict]:
    meta = json.loads((sample_dir / "sample.json").read_text())
    why = unsupported(meta)
    if why:
        return [_failed(e, why) for e in examples]
    in_format = record_format(meta["layouts"]["input"])
    out_spec = meta["layouts"]["output"]
    out_fields = load_fields(out_spec)
    out_format = (record_format(out_spec), record_length(out_fields))
    dd = meta["dd"]
    with tempfile.TemporaryDirectory(prefix="diocle-claims-") as tmp:
        work = Path(tmp)
        cmd, failed = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                  [sample_dir / m for m in meta.get("modules", [])], meta.get("collation", "ascii"),
                                  timeout=60)
        if cmd is None:
            return [_failed(e, "the original COBOL did not compile under GnuCOBOL") for e in examples]
        started, results = time.monotonic(), []
        for n, example in enumerate(examples):
            if time.monotonic() - started > TOTAL_BUDGET - RUN_TIMEOUT:
                results.append(_failed(example, "time budget for running examples was used up"))
                continue
            bad = next((r for r in example["records"] if len(r) > MAX_RECORD_LEN or (in_format == "line" and ("\n" in r or "\r" in r))), None)
            if bad is not None:
                results.append(_failed(example, "an input record is too long or breaks the line framing"))
                continue
            input_path, output_path = work / f"in-{n}.dat", work / f"out-{n}.dat"
            write_records(input_path, list(example["records"]), in_format)
            env = {**CLOCK_ENV, f"DD_{dd['input']}": str(input_path), f"DD_{dd['output']}": str(output_path)}
            try:
                proc = _exec(cmd, env=env, cwd=work, timeout=RUN_TIMEOUT)
            except subprocess.TimeoutExpired:
                results.append(_failed(example, f"the program did not finish within {RUN_TIMEOUT} seconds"))
                continue
            lines = read_records(output_path, *out_format)
            results.append({"id": example["id"], "ran": True, "records": [r[:MAX_RECORD_LEN] for r in lines[:MAX_RECORDS]],
                            "recordCount": len(lines), "stdout": proc.stdout[:CAPTURE_STDOUT],
                            "stderr": proc.stderr[:300], "returnCode": proc.returncode, "error": ""})
    return results


def _failed(example: dict, why: str) -> dict:
    return {"id": example["id"], "ran": False, "records": [], "recordCount": 0, "stdout": "", "stderr": "",
            "returnCode": None, "error": why}


def output_fields(meta: dict) -> list[Field]:
    return load_fields(meta["layouts"]["output"])


def _plain(f: Field, value: Decimal | str) -> str:
    """A field value as the plain string the contract carries."""
    if f.kind == "alnum":
        return str(value).rstrip()
    if isinstance(value, Decimal):
        return f"{value:.{max(f.scale, 0)}f}"
    return str(value)  # an unparseable numeric stays the raw text


def actual_records(lines: list[str], fields: list[Field]) -> list[dict[str, str]]:
    return [{f.name: _plain(f, v) for f, v in zip(fields, parse_record(line, fields).values())} for line in lines]


def _same(f: Field, expected: str, actual: str) -> bool:
    if f.kind == "alnum":
        return expected.rstrip() == actual.rstrip()
    try:
        return Decimal(expected.strip().replace("+", "")) == Decimal(actual)
    except InvalidOperation:
        return False


def check_expected(expected: dict, fields: list[Field]) -> str | None:
    """Why the expectations cannot be judged against the output layout (unknown field, a value that is not a number)."""
    by_name = {f.name: f for f in fields}
    for i, rec in enumerate(expected.get("records", []), 1):
        if not isinstance(rec, dict) or not rec:
            return f"expected record {i} names no field"
        for name, value in rec.items():
            f = by_name.get(name)
            if f is None:
                return f"expected record {i}: {name} is not a field of the output layout"
            if not isinstance(value, str):
                return f"expected record {i}: {name} is not a string"
            if f.kind == "numeric":
                try:
                    if not Decimal(value.strip().replace("+", "")).is_finite():
                        raise InvalidOperation
                except InvalidOperation:
                    return f"expected record {i}: {name} is not a number"
    if not any(k in expected for k in ("records", "outputRecordCount", "stdoutContains", "returnCode")):
        return "the example states no expected output"
    return None


_CONTROLS = {c: " " for c in [*range(0, 32), *range(127, 160)]}


def flat(text: str, limit: int = 200) -> str:
    """One line: control characters (newlines, tabs, escapes) become spaces and runs of whitespace collapse, so no
    text can start a new line or a new section in a reader."""
    return " ".join(str(text).translate(_CONTROLS).split())[:limit]


def judge(expected: dict, run: dict, fields: list[Field]) -> dict:
    """Decide one example from the run of the original: {"status", "actual", "mismatches", "reason"}.
    `actual` is present whenever the program ran, even if the example cannot be judged.
    Matched needs a real comparison (an output field value or stdout) AND a clean run: a program that ended with a
    non-zero return code while the example says nothing about it, or an expectation that compares nothing but a
    return code or a record count, leaves the example unchecked instead of confirmed."""
    if not run["ran"]:
        return {"status": "unchecked", "actual": None, "mismatches": [], "reason": run["error"] or "the program did not run"}
    records = actual_records(run["records"], fields)
    count = run.get("recordCount", len(records))
    actual = {"records": records[:5], "outputRecordCount": count, "stdout": run["stdout"][:MAX_STDOUT],
              "returnCode": run["returnCode"]}
    bad = check_expected(expected, fields)
    if bad:
        return {"status": "unchecked", "actual": actual, "mismatches": [], "reason": bad}
    by_name, mismatches = {f.name: f for f in fields}, []
    for i, want in enumerate(expected.get("records", []), 1):
        if i > count:
            mismatches.append({"what": f"record {i}", "expected": "a record", "actual": f"no such record: the program wrote {count}"})
            continue
        if i > len(records):
            continue  # beyond the records kept; expectations cover at most 5
        for name, value in want.items():
            got = records[i - 1][name]
            if not _same(by_name[name], value, got):
                mismatches.append({"what": f"record {i} {name}", "expected": value, "actual": got})
    if "outputRecordCount" in expected and expected["outputRecordCount"] != count:
        mismatches.append({"what": "number of output records", "expected": str(expected["outputRecordCount"]), "actual": str(count)})
    if "stdoutContains" in expected and expected["stdoutContains"] not in run["stdout"]:
        mismatches.append({"what": "stdout", "expected": f"contains {flat(expected['stdoutContains'])!r}",
                           "actual": flat(run["stdout"], 200)})
    if "returnCode" in expected and expected["returnCode"] != run["returnCode"]:
        mismatches.append({"what": "return code", "expected": str(expected["returnCode"]), "actual": str(run["returnCode"])})
    if mismatches:
        return {"status": "differed", "actual": actual, "mismatches": mismatches[:20], "reason": ""}
    if run["returnCode"] != 0 and "returnCode" not in expected:
        err = flat(run.get("stderr", ""), 120)
        return {"status": "unchecked", "actual": actual, "mismatches": [], "reason": (
            f"the program ended with return code {run['returnCode']} and the example does not expect that"
            + (f" (it printed: {err})" if err else ""))}
    strong = any(v for rec in expected.get("records", []) for v in rec) or "stdoutContains" in expected
    if not strong:
        return {"status": "unchecked", "actual": actual, "mismatches": [],
                "reason": "weak expectation: it compares only a record count or return code, not an output field or stdout"}
    return {"status": "matched", "actual": actual, "mismatches": [], "reason": ""}


def claim_status(example_statuses: list[str]) -> str:
    """confirmed: every example matched; refuted: at least one differed; otherwise unchecked (no example, or one could not run)."""
    if "differed" in example_statuses:
        return "refuted"
    if example_statuses and all(s == "matched" for s in example_statuses):
        return "confirmed"
    return "unchecked"


def summarize(claims: list[dict]) -> dict:
    counts = {s: sum(c["status"] == s for c in claims) for s in ("confirmed", "refuted", "unchecked")}
    ran = sum(1 for c in claims for e in c["examples"] if e.get("actual") is not None)
    return {"claims": len(claims), **counts, "examplesRun": ran}
