"""Verification for programs with several input or output files (match-merge, split, SORT USING/GIVING).

Each input file gets its own generated records. Key fields shared between input files (sample "sharedKeys")
draw from one pool of values, and each file can be sorted by its key ("sortedBy") in the program's collating
sequence, so matched, unmatched and end-of-file paths are all exercised. Both programs run once with every DD
bound; each output file is compared record by record.
"""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

from .diff import compare
from .inputs import Case, generate_cases
from .layout import Field, format_record, load_fields, parse_record, record_format, record_length
from .runners import CLOCK, build_cobol, build_java, read_records, run_files, write_records


def file_specs(meta: dict) -> list[dict]:
    """The sample's files as [{dd, direction, layout}], whichever way sample.json states them."""
    if "files" in meta:
        return meta["files"]
    return [{"dd": meta["dd"]["input"], "direction": "input", "layout": meta["layouts"]["input"]},
            {"dd": meta["dd"]["output"], "direction": "output", "layout": meta["layouts"]["output"]}]


def is_multi(meta: dict) -> bool:
    specs = file_specs(meta)
    return sum(f["direction"] == "input" for f in specs) != 1 or sum(f["direction"] == "output" for f in specs) != 1


def _sort_key(value: str, collation: str) -> bytes:
    return value.encode("cp037" if collation == "ebcdic" else "latin-1", errors="replace")


def _key_slice(fields: list[Field], name: str) -> slice:
    start = 0
    for f in fields:
        if f.name == name:
            return slice(start, start + f.length)
        start += f.length
    raise KeyError(name)


def _input_records(meta: dict, sample_dir: Path, inputs: list[dict], seed: int, random_count: int) -> dict[str, list[str]]:
    rng = random.Random(seed)
    collation = meta.get("collation", "ascii")
    fields = {s["dd"]: load_fields(s["layout"]) for s in inputs}
    rows: dict[str, list[dict]] = {}
    for i, spec in enumerate(inputs):
        generated = generate_cases(fields[spec["dd"]], seed=seed + i, random_count=random_count)
        rows[spec["dd"]] = [parse_record(c.record, fields[spec["dd"]]) for c in generated]
    for group in meta.get("sharedKeys", []):  # e.g. [["MSTIN", "MS-ACCT-ID"], ["TXNIN", "TX-ACCT-ID"]]
        length = next(f.length for dd, name in group for f in fields[dd] if f.name == name)
        span = 10 ** min(length - 1, 6)
        pool = [f"K{n:0{length - 1}d}"[-length:] for n in rng.sample(range(span), min(span, max(10, random_count)))]
        for position, (dd, name) in enumerate(group):
            for k, row in enumerate(rows[dd]):
                if position == 0:  # the first file (the master) gets distinct keys
                    row[name] = pool[k % len(pool)]
                elif rng.random() < 0.15:  # some keys the master does not have: the unmatched path
                    row[name] = f"Z{rng.randrange(span):0{length - 1}d}"[-length:]
                else:
                    row[name] = rng.choice(pool)
    out: dict[str, list[str]] = {}
    for spec in inputs:
        dd = spec["dd"]
        corpus_paths = meta.get("corpus", {}).get(dd, []) if isinstance(meta.get("corpus"), dict) else []
        corpus = [r for path in corpus_paths
                  for r in read_records(sample_dir / path, record_format(spec["layout"]), record_length(fields[dd]))]
        records = meta.get("fixtureFiles", {}).get(dd, []) + corpus + [format_record(r, fields[dd]) for r in rows[dd]]
        key = meta.get("sortedBy", {}).get(dd)
        if key:
            cut = _key_slice(fields[dd], key)
            records.sort(key=lambda r: _sort_key(r[cut], collation))
        out[dd] = records
    return out


def verify_multi(sample_dir: Path, meta: dict, java_dir: Path, seed: int, random_count: int) -> dict:
    from . import REPORT_VERSION

    specs = file_specs(meta)
    inputs = [s for s in specs if s["direction"] == "input"]
    outputs = [s for s in specs if s["direction"] == "output"]
    out_fields = {s["dd"]: load_fields(s["layout"]) for s in outputs}
    data = _input_records(meta, sample_dir, inputs, seed, random_count)
    collation = meta.get("collation", "ascii")
    with tempfile.TemporaryDirectory(prefix="diocle-verify-") as tmp:
        work = Path(tmp)
        paths = {}
        for s in inputs:
            paths[s["dd"]] = work / f"{s['dd']}.in"
            write_records(paths[s["dd"]], data[s["dd"]], record_format(s["layout"]))
        out_spec = {s["dd"]: (record_format(s["layout"]), record_length(out_fields[s["dd"]])) for s in outputs}
        cobol_cmd, original = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                          [sample_dir / m for m in meta.get("modules", [])], collation)
        java_cmd, converted = build_java(java_dir, meta["javaConversion"]["mainClass"], work)
        if cobol_cmd:
            original = run_files(cobol_cmd, paths, out_spec, work, "original")
        if java_cmd:
            converted = run_files(java_cmd, paths, out_spec, work, "converted", {"DIOCLE_COLLATION": collation.upper()})

    results: list[dict] = []
    if original.compiled and converted.compiled:
        for s in outputs:
            dd = s["dd"]
            o, c = original.output_files.get(dd, []), converted.output_files.get(dd, [])
            cases = [Case(f"{dd}#{i + 1:04d}", "files", "") for i in range(len(o))]  # extras show as extra output
            for r in compare(cases, o, c, out_fields[dd], record_format(s["layout"])):
                r.update({"program": meta["program"], "outputDd": dd})
                r.pop("input", None)
                results.append(r)
    passed = sum(r["match"] for r in results)
    meta_run = lambda r: {"compiled": r.compiled, "exitCode": r.exit_code, "stdout": r.stdout, "stderr": r.stderr}
    return {
        "version": REPORT_VERSION,
        "results": results,
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
        "runs": {
            "original": meta_run(original),
            "converted": meta_run(converted),
            "stdoutMatch": original.stdout == converted.stdout,
            "exitCodeMatch": original.compiled and converted.compiled and original.exit_code == converted.exit_code,
            "clock": CLOCK,
            "collation": collation,
            "golden": None,
            "files": {"inputs": {dd: len(r) for dd, r in data.items()},
                      "outputs": {s["dd"]: {"original": len(original.output_files.get(s["dd"], [])),
                                            "converted": len(converted.output_files.get(s["dd"], []))} for s in outputs}},
        },
    }
