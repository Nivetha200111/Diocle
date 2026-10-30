"""Verification for programs with several input or output files (match-merge, split, SORT USING/GIVING).

Each input file gets its own generated records. Key fields shared between input files (sample "sharedKeys")
draw from one pool of values, and each file can be sorted by its key ("sortedBy") in the program's collating
sequence, so matched, unmatched and end-of-file paths are all exercised. Both programs run once with every DD
bound; each output file is compared record by record.
"""

from __future__ import annotations

import os
import random
import tempfile
from pathlib import Path

from .diff import compare
from .inputs import Case, generate_cases
from .layout import Field, format_record, load_fields, parse_record, record_format, record_length
from .runners import CLOCK, Run, build_cobol, build_java, read_records, run_files, write_records


def file_specs(meta: dict) -> list[dict]:
    """The sample's files as [{dd, direction, layout}], whichever way sample.json states them."""
    if "files" in meta:
        return meta["files"]
    return [{"dd": meta["dd"]["input"], "direction": "input", "layout": meta["layouts"]["input"]},
            {"dd": meta["dd"]["output"], "direction": "output", "layout": meta["layouts"]["output"]}]


def is_multi(meta: dict) -> bool:
    """False only for the classic shape: exactly one input, one output, nothing opened I-O, files compared."""
    specs = file_specs(meta)
    return (bool(meta.get("sql")) or bool(meta.get("ksds")) or sum(f["direction"] == "input" for f in specs) != 1 or sum(f["direction"] == "output" for f in specs) != 1
            or any(f["direction"] == "io" for f in specs) or bool(meta.get("displayOnly")))


def _sort_key(value: str, collation: str) -> bytes:
    return value.encode("cp037" if collation == "ebcdic" else "latin-1", errors="replace")


def _key_slice(fields: list[Field], name: str) -> slice:
    start = 0
    for f in fields:
        if f.name == name:
            return slice(start, start + f.length)
        start += f.length
    raise KeyError(name)


def _input_records(meta: dict, sample_dir: Path, inputs: list[dict], seed: int, random_count: int, plan=None) -> dict[str, list[str]]:
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
    if plan:  # transaction fields that carry a keyed file's RECORD KEY: mostly keys the seed has, some it does not
        from . import ksds
        lrng = random.Random(seed * 31 + 5)
        for spec in inputs:
            for f in fields[spec["dd"]]:
                for row in rows[spec["dd"]]:
                    value = ksds.link_values(plan, spec["dd"], f.name, f, lrng)
                    if value is not None:
                        row[f.name] = value
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
    plan = None
    if meta.get("ksds"):
        from . import ksds
        plan = ksds.plan_seeds(meta, seed, random_count)
    specs = [s for s in specs if not s.get("keyed")]  # keyed files are seeded and compared by ksds.py
    inputs = [s for s in specs if s["direction"] == "input"]
    updated = [s for s in specs if s["direction"] == "io"]  # opened I-O: seeded from generated records, compared at the end
    outputs = [s for s in specs if s["direction"] in ("output", "io")]
    stdout_only = not outputs and bool(meta.get("displayOnly"))  # nothing but DISPLAY and RETURN-CODE to compare
    out_fields = {s["dd"]: load_fields(s["layout"]) for s in outputs}
    data = _input_records(meta, sample_dir, inputs + updated, seed, random_count, plan)
    collation = meta.get("collation", "ascii")
    sql = meta.get("sql")
    with tempfile.TemporaryDirectory(prefix="diocle-verify-") as tmp:
        work = Path(tmp)
        paths = {}
        for s in inputs:
            paths[s["dd"]] = work / f"{s['dd']}.in"
            write_records(paths[s["dd"]], data[s["dd"]], record_format(s["layout"]))
        seeds = {}
        for s in updated:
            seeds[s["dd"]] = work / f"{s['dd']}.seed"
            write_records(seeds[s["dd"]], data[s["dd"]], record_format(s["layout"]))
        out_spec = {s["dd"]: (record_format(s["layout"]), record_length(out_fields[s["dd"]])) for s in outputs}
        db_env = {"original": {}, "converted": {}}
        keyed_results, keyed_report = [], None
        jrun = work
        tamper: list[str] = []
        if sql:
            import hashlib
            import shutil

            from . import sqlrun
            from .sqlseed import seed_for_meta
            seeded = seed_for_meta(meta, sample_dir, work, data, seed, {s["dd"]: s for s in inputs + updated})
            sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            seed_hash = sha(work / "seed.db")
            cap = {"DIOCLE_SQL_MAX_STMTS": os.environ["DIOCLE_SQL_MAX_STMTS"]} if os.environ.get("DIOCLE_SQL_MAX_STMTS") else {}
            # The Java gets its own directory and its own database, and runs BEFORE the original's database exists, so
            # it can neither read nor overwrite the answer it is compared with.
            jrun = work / "jrun"
            jrun.mkdir()
            shutil.copyfile(work / "seed.db", jrun / "converted.db")
            db_env = {"original": {"DIOCLE_DB": str(work / "original.db"), **cap},
                      "converted": {"DIOCLE_DB": str(jrun / "converted.db"), **cap}}
            java_cmd, converted = sqlrun.build_java_sql(java_dir, meta["javaConversion"]["mainClass"], work)
            # Everything the original is built from or reads is hashed before the Java runs and checked after: the Java
            # runs as the same user, so it could otherwise rewrite them. The COBOL executable does not exist yet.
            guarded = [work / f"{n}.in" for n in (x["dd"] for x in inputs)] + [work / f"{n}.seed" for n in (x["dd"] for x in updated)]
            guarded += [work / "seed.db", sample_dir / meta["source"]] + [sample_dir / m for m in meta.get("modules", [])]
            guarded += sorted(p for p in (sample_dir / meta["copybookDir"]).rglob("*") if p.is_file())
            before = {str(p): sha(p) for p in guarded if p.is_file()}
            if java_cmd:
                converted = run_files(java_cmd, paths, out_spec, jrun, "converted",
                                      {"DIOCLE_COLLATION": collation.upper(), **db_env["converted"]}, seeds=seeds)
            tamper += [f"the converted program changed {Path(p).name}" for p, h in before.items()
                       if not Path(p).is_file() or sha(Path(p)) != h]
            for stray in ("original", "original.db", "sqlpre"):
                if (work / stray).exists():
                    tamper.append(f"the converted program created {stray}")
            if tamper:
                original = Run(False, None, "", "not run, verification fails closed: " + "; ".join(tamper))
            else:
                cobol_cmd, original = sqlrun.build_cobol_sql(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                                             sql["tables"], [sample_dir / m for m in meta.get("modules", [])],
                                                             collation)
                if cobol_cmd:
                    shutil.copyfile(work / "seed.db", work / "original.db")
                    original = run_files(cobol_cmd, paths, out_spec, work, "original", db_env["original"], seeds=seeds)
        elif plan:
            original, converted, keyed_results, keyed_report = ksds.run_both(
                plan, meta, sample_dir, java_dir, work, paths, out_spec, seeds, [s["dd"] for s in inputs],
                [s["dd"] for s in updated], collation, seed)
        else:
            cobol_cmd, original = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                              [sample_dir / m for m in meta.get("modules", [])], collation)
            java_cmd, converted = build_java(java_dir, meta["javaConversion"]["mainClass"], work)
            if cobol_cmd:
                original = run_files(cobol_cmd, paths, out_spec, work, "original", db_env["original"], seeds=seeds)
            if java_cmd:
                converted = run_files(java_cmd, paths, out_spec, work, "converted",
                                      {"DIOCLE_COLLATION": collation.upper(), **db_env["converted"]}, seeds=seeds)
        db_results, db_report = [], None
        if sql and original.compiled and converted.compiled:
            from . import sqldb
            db_results, tables_report = sqldb.compare_tables(work / "original.db", jrun / "converted.db", sql["tables"],
                                                             seeded, meta["program"], seed_db=work / "seed.db",
                                                             writes=bool(sql.get("writes")), tamper=tamper)
            db_report = {"engine": "sqlite", "engineVersion": sqldb.engine_version(), "subset": sql.get("subset", ""),
                         "seededFrom": ", ".join(sorted({t.get("path") or "DECLARE TABLE in the program" for t in sql["tables"]}))
                                       + f"; generated rows (seed {seed})",
                         "tables": tables_report}

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
    results += db_results + keyed_results
    if stdout_only and original.compiled and converted.compiled:
        results.append(stdout_result(meta["program"], original, converted))
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
            **({"stdoutCompared": True} if stdout_only else {}),
            **({"database": db_report} if db_report else {}),
            **({"keyed": keyed_report} if keyed_report else {}),
            "files": {"inputs": {s["dd"]: len(data[s["dd"]]) for s in inputs},
                      **({"updated": {s["dd"]: {"seeded": len(data[s["dd"]]),
                                                "original": len(original.output_files.get(s["dd"], [])),
                                                "converted": len(converted.output_files.get(s["dd"], []))}
                                      for s in updated}} if updated else {}),
                      "outputs": {s["dd"]: {"original": len(original.output_files.get(s["dd"], [])),
                                            "converted": len(converted.output_files.get(s["dd"], []))} for s in outputs}},
        },
    }


STDOUT_LIMIT = 2000


def stdout_result(program: str, original: Run, converted: Run) -> dict:
    """The one result of a DISPLAY-only program: stdout and exit code, byte for byte.

    A program whose original printed nothing has nothing observable to compare, so it cannot pass."""
    o, c = original.stdout, converted.stdout
    problems = []
    if not o:
        problems.append("the original printed nothing to stdout: no output file and no DISPLAY text to compare")
    if o != c:
        o_lines, c_lines = o.splitlines(), c.splitlines()
        n = next((i for i in range(max(len(o_lines), len(c_lines)))
                  if (o_lines[i] if i < len(o_lines) else None) != (c_lines[i] if i < len(c_lines) else None)), 0)
        problems.append(f"stdout line {n + 1}: original {o_lines[n] if n < len(o_lines) else '(none)'!r} "
                        f"converted {c_lines[n] if n < len(c_lines) else '(none)'!r}"
                        if o.rstrip("\n") != c.rstrip("\n") else "stdout differs only in the final newline")
    if original.exit_code != converted.exit_code:
        problems.append(f"exit code: original {original.exit_code} converted {converted.exit_code}")
    result = {"program": program, "inputId": "stdout", "inputSource": "stdout", "outputDd": "stdout",
              "originalOutput": o[:STDOUT_LIMIT], "convertedOutput": c[:STDOUT_LIMIT],
              "match": not problems, "fieldDiffs": []}
    if problems:
        result["diff"] = "; ".join(problems)
    return result
