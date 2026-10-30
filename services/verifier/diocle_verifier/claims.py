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
TOTAL_BUDGET = 90  # seconds for all runs of one call (a hung program must not hold a job)
MAX_STDOUT = 2000


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
            if time.monotonic() - started > TOTAL_BUDGET:
                results.append(_failed(example, "time budget for running examples was used up"))
                continue
            input_path, output_path = work / f"in-{n}.dat", work / f"out-{n}.dat"
            write_records(input_path, list(example["records"]), in_format)
            env = {**CLOCK_ENV, f"DD_{dd['input']}": str(input_path), f"DD_{dd['output']}": str(output_path)}
            try:
                proc = _exec(cmd, env=env, cwd=work, timeout=RUN_TIMEOUT)
            except subprocess.TimeoutExpired:
                results.append(_failed(example, f"the program did not finish within {RUN_TIMEOUT} seconds"))
                continue
            results.append({"id": example["id"], "ran": True, "records": read_records(output_path, *out_format),
                            "stdout": proc.stdout[:MAX_STDOUT], "returnCode": proc.returncode, "error": ""})
    return results


def _failed(example: dict, why: str) -> dict:
    return {"id": example["id"], "ran": False, "records": [], "stdout": "", "returnCode": None, "error": why}


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


def judge(expected: dict, run: dict, fields: list[Field]) -> dict:
    """Decide one example from the run of the original: {"status", "actual", "mismatches", "reason"}."""
    if not run["ran"]:
        return {"status": "unchecked", "actual": None, "mismatches": [], "reason": run["error"] or "the program did not run"}
    bad = check_expected(expected, fields)
    if bad:
        return {"status": "unchecked", "actual": None, "mismatches": [], "reason": bad}
    records = actual_records(run["records"], fields)
    actual = {"records": records[:5], "outputRecordCount": len(records), "stdout": run["stdout"],
              "returnCode": run["returnCode"]}
    by_name, mismatches = {f.name: f for f in fields}, []
    for i, want in enumerate(expected.get("records", []), 1):
        if i > len(records):
            mismatches.append({"what": f"record {i}", "expected": "a record", "actual": "no such record: the program wrote "
                               f"{len(records)}"})
            continue
        for name, value in want.items():
            got = records[i - 1][name]
            if not _same(by_name[name], value, got):
                mismatches.append({"what": f"record {i} {name}", "expected": value, "actual": got})
    if "outputRecordCount" in expected and expected["outputRecordCount"] != len(records):
        mismatches.append({"what": "number of output records", "expected": str(expected["outputRecordCount"]),
                           "actual": str(len(records))})
    if "stdoutContains" in expected and expected["stdoutContains"] not in run["stdout"]:
        mismatches.append({"what": "stdout", "expected": f"contains {expected['stdoutContains']!r}", "actual": run["stdout"][:200]})
    if "returnCode" in expected and expected["returnCode"] != run["returnCode"]:
        mismatches.append({"what": "return code", "expected": str(expected["returnCode"]), "actual": str(run["returnCode"])})
    return {"status": "differed" if mismatches else "matched", "actual": actual, "mismatches": mismatches[:20], "reason": ""}


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
