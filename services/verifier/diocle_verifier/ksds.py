"""Keyed (INDEXED / VSAM KSDS-style) files: seeding, the two sides, and the final-contents comparison.

The ORIGINAL runs on GnuCOBOL's real indexed-file handler (Berkeley DB), in its own per-job directory. The CONVERTED
Java runs on DioKsds (dbsupport/DioKsds.java), the verifier's own class that reproduces that handler's observable
behaviour (FILE STATUS codes, byte-wise key order, START / READ NEXT positioning) for the subset ksds-subset-1; the
class is itself checked against the real handler with randomised operation sequences (tests/test_ksds.py).
Both sides start from the same seed records. The Java keeps a keyed file as plain fixed-length records in key order;
the original's file is read back by a small COBOL program the verifier generates (the Python side never parses the
Berkeley DB format). Final contents are compared record by record in key order.

What this proves: equivalence on GnuCOBOL's INDEXED handler, for this subset of operations, on the inputs tried.
Not IBM VSAM (no CI/CA splits, no alternate indexes, no locking, no IDCAMS).
"""

from __future__ import annotations

import hashlib
import random
import re
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .layout import Field, format_record, load_fields, parse_record, record_length
from .runners import IBM_FLAGS, Run, _exec, build_cobol, run_files

SUBSET = "ksds-subset-1"
SUPPORT = Path(__file__).resolve().parent / "dbsupport"
MAX_SEED_RECORDS = 500
MAX_FILE_BYTES = 16 << 20  # a keyed file bigger than this on either side is a failure, not something to read

_PREFIXES = "AZaz09 Kk"  # first characters that order differently under ASCII and EBCDIC


def indexed_handler() -> str | None:
    """The indexed-file handler of the cobc on this machine ('BDB', 'VBISAM', ...), None when it has none."""
    try:
        out = _exec(["cobc", "--info"], timeout=30).stdout
    except Exception:
        return None
    m = re.search(r"indexed file handler\s*:\s*(\S+)", out)
    return m.group(1) if m and m.group(1).lower() != "disabled" and m.group(1).lower() != "none" else None


def engine_version() -> str:
    try:
        first = _exec(["cobc", "--version"], timeout=30).stdout.splitlines()[0]
    except Exception:
        first = "cobc"
    return f"{first}; indexed handler {indexed_handler() or 'none'}"


def keyed_specs(meta: dict) -> list[dict]:
    return [f for f in meta.get("files", []) if f.get("keyed")]


# --- seeding ----------------------------------------------------------------------------------------------------

def _key_text(f: Field, rng: random.Random, n: int) -> str:
    if f.kind == "numeric":
        return str(rng.randrange(10 ** f.stored_digits)).zfill(f.stored_digits)
    if f.length == 1:
        return rng.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ")
    return rng.choice(_PREFIXES) + f"{rng.randrange(10 ** min(f.length - 1, 9)):0{f.length - 1}d}"[-(f.length - 1):]


def make_keys(f: Field, rng: random.Random, count: int) -> tuple[list[str], list[str]]:
    """(keys present in the seed, keys absent from it), all distinct. Boundary keys on both sides; alphanumeric keys
    start with characters that sort differently in ASCII and EBCDIC."""
    L = f.length
    if f.kind == "numeric":
        top = 10 ** f.stored_digits - 1
        boundary = [str(v).zfill(f.stored_digits) for v in (0, 1, 9, top, top - 1) if 0 <= v <= top]
    else:
        boundary = list(dict.fromkeys(c * L for c in " 09AZaz"))
    pool = list(dict.fromkeys(boundary))
    attempts = 0
    while len(pool) < count * 2 and attempts < count * 40:
        attempts += 1
        k = _key_text(f, rng, len(pool))
        if k not in pool:
            pool.append(k)
    seed_keys, miss = [], []
    for i, k in enumerate(pool):
        (seed_keys if (i < len(boundary) and i % 2 == 0) or (i >= len(boundary) and len(seed_keys) < count and rng.random() < 0.6)
         else miss).append(k)
    seed_keys = seed_keys[:count]
    miss = [k for k in pool if k not in set(seed_keys)]
    return seed_keys, miss


@dataclass
class Plan:
    specs: list[dict]
    fields: dict[str, list[Field]]
    seeds: dict[str, list[str]] = field(default_factory=dict)   # DD -> seed records in key order (input and I-O files)
    hits: dict[str, list[str]] = field(default_factory=dict)    # DD -> keys the seed has
    misses: dict[str, list[str]] = field(default_factory=dict)  # DD -> keys it does not
    links: list[dict] = field(default_factory=list)             # sample.json ksds.keyLinks


def _key_slice(spec: dict) -> tuple[int, int]:
    return spec["keyed"]["recordKey"]["offset"], spec["keyed"]["recordKey"]["length"]


def plan_seeds(meta: dict, seed: int, random_count: int) -> Plan:
    from .inputs import generate_cases

    specs = keyed_specs(meta)
    plan = Plan(specs, {s["dd"]: load_fields(s["layout"]) for s in specs}, links=meta.get("ksds", {}).get("keyLinks", []))
    count = max(12, min(random_count // 4, MAX_SEED_RECORDS))
    for i, spec in enumerate(specs):
        dd = spec["dd"]
        fields = plan.fields[dd]
        key_name = spec["keyed"]["recordKey"]["field"]
        off, length = _key_slice(spec)
        names = [f.name for f in fields]
        # the analyzer's offset must be the one the verifier's layout gives (they compute it separately): fail closed
        start = sum(f.length for f in fields[: names.index(key_name)]) if key_name in names else -1
        if start != off or fields[names.index(key_name)].length != length:
            raise ValueError(f"{dd}: the RECORD KEY offset/length in sample.json does not match the record layout")
        kf = fields[names.index(key_name)]
        rng = random.Random(seed * 104729 + 31 * i + 7)
        hits, misses = make_keys(kf, rng, count)
        plan.hits[dd], plan.misses[dd] = hits, misses
        if spec["direction"] in ("output",):
            continue  # the program creates the file
        cases = generate_cases(fields, seed=seed + 50 + i, random_count=len(hits))
        records = {}
        for key, case in zip(hits, cases):
            row = parse_record(case.record, fields)
            row[key_name] = key if kf.kind == "alnum" else Decimal(int(key)).scaleb(-kf.scale)
            rec = format_record(row, fields)
            records[rec[off: off + length]] = rec
        plan.seeds[dd] = [records[k] for k in sorted(records)]  # byte order, the order of the file
        plan.hits[dd] = sorted(records)
    return plan


def link_values(plan: Plan, dd: str, field_name: str, f: Field, rng: random.Random):
    """A value for a transaction field linked to a keyed file's RECORD KEY: mostly seeded keys, some absent ones."""
    for link in plan.links:
        if link["dd"] == dd and link["field"] == field_name:
            r = rng.random()
            pool = plan.hits.get(link["keyedDd"], []) if r < 0.5 else plan.misses.get(link["keyedDd"], []) if r < 0.9 else []
            if not pool:
                return None
            key = rng.choice(pool)
            return key if f.kind == "alnum" else Decimal(int(key)).scaleb(-f.scale)
    return None


# --- the original's side: generated COBOL that moves between flat files and the real indexed file ---------------

def _copy_program(kind: str, spec: dict, fields: list[Field]) -> str:
    n = record_length(fields)
    off, length = _key_slice(spec)
    rest = n - off - length
    pre = f"           05  K-PRE   PIC X({off}).\n" if off else ""
    post = f"           05  K-POST  PIC X({rest}).\n" if rest else ""
    load = kind == "load"
    return f"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. DIOKCOPY.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SEQF ASSIGN TO DIOSEQ ORGANIZATION IS SEQUENTIAL.
           SELECT KF ASSIGN TO DIOKEY ORGANIZATION IS INDEXED
               ACCESS MODE IS {"RANDOM" if load else "SEQUENTIAL"}
               RECORD KEY IS K-KEY
               FILE STATUS IS FS.
       DATA DIVISION.
       FILE SECTION.
       FD  SEQF.
       01  S-REC PIC X({n}).
       FD  KF.
       01  K-REC.
{pre}           05  K-KEY   PIC X({length}).
{post}       WORKING-STORAGE SECTION.
       01  FS  PIC XX.
       01  EOF-FLAG PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN.
           OPEN {"INPUT SEQF" if load else "INPUT KF"}
           OPEN {"OUTPUT KF" if load else "OUTPUT SEQF"}
           PERFORM UNTIL EOF-FLAG = 'Y'
{"               READ SEQF AT END MOVE 'Y' TO EOF-FLAG END-READ" if load else "               READ KF NEXT AT END MOVE 'Y' TO EOF-FLAG END-READ"}
               IF EOF-FLAG NOT = 'Y'
{"                   MOVE S-REC TO K-REC" + chr(10) + "                   WRITE K-REC" + chr(10) + "                   IF FS NOT = '00'" + chr(10) + "                       DISPLAY 'LOAD FAILED ' FS" + chr(10) + "                       MOVE 9 TO RETURN-CODE" + chr(10) + "                       STOP RUN" + chr(10) + "                   END-IF" if load else "                   MOVE K-REC TO S-REC" + chr(10) + "                   WRITE S-REC"}
               END-IF
           END-PERFORM
           CLOSE SEQF KF
           STOP RUN.
"""


def _build_tools(plan: Plan, work: Path) -> tuple[dict[str, dict[str, Path]] | None, Run | None]:
    tools = work / "ksds-tools"
    tools.mkdir(exist_ok=True)
    out: dict[str, dict[str, Path]] = {}
    for spec in plan.specs:
        dd = spec["dd"]
        for kind in ("load", "dump"):
            if kind == "load" and dd not in plan.seeds:
                continue
            src, exe = tools / f"{dd}-{kind}.cbl", tools / f"{dd}-{kind}"
            src.write_text(_copy_program(kind, spec, plan.fields[dd]))
            build = _exec(["cobc", "-x", "-std=ibm", *IBM_FLAGS, "-o", str(exe), str(src)], timeout=120)
            if build.returncode != 0:
                return None, Run(False, build.returncode, build.stdout, build.stderr)
            out.setdefault(dd, {})[kind] = exe
    return out, None


def _tool_run(exe: Path, seq: Path, key: Path, cwd: Path) -> str | None:
    proc = _exec([str(exe)], env={"DD_DIOSEQ": str(seq), "DD_DIOKEY": str(key)}, cwd=cwd, timeout=120)
    return None if proc.returncode == 0 else f"{exe.name} failed ({proc.returncode}): {(proc.stdout + proc.stderr)[:200]}"


# --- the converted side ------------------------------------------------------------------------------------------

FORBIDDEN = (r"processbuilder", r"runtime\s*\.\s*(?:getruntime|exec)", r"system\s*\.\s*load", r"loadlibrary", r"methodhandle",
             r"serviceloader", r"classloader", r"\bgetmethod\b", r"\bsetaccessible\b", r"java\.lang\.reflect", r"java\.net",
             r"\bsocket\b", r"forname", r"\.kf\b", r"kseed", r"diocle-verify", r"ksds-tools", r"\.final\b")


class JavaRefused(ValueError):
    pass


def check_java_source(name: str, text: str, keyed_dds: list[str]) -> None:
    """Static check of one converted source file (every file except the verifier's own DioKsds.java): keyed files are
    reached only through DioKsds. A speed bump (a determined author can still build names at run time), backed by the
    sandbox and by the verifier's hashes of everything the original reads."""
    if re.search(r"[^\x00-\x7f]", text) or "\\u" in text:
        raise JavaRefused(f"{name}: non-ASCII characters and unicode escapes are refused in converted keyed-file programs")
    joined = re.sub(r'"\s*\+\s*"', "", text)
    for m in re.finditer(r"getenv\s*\(", joined):
        rest = joined[m.end():]
        lit = re.match(r'\s*"([A-Za-z0-9_-]+)"\s*\)', rest)
        ok = lit and (lit.group(1) in ("DIOCLE_COLLATION", "DIOCLE_CLOCK")
                      or (lit.group(1).startswith("DD_") and lit.group(1)[3:] not in keyed_dds))
        if not ok:
            raise JavaRefused(f"{name}: System.getenv may only name a literal DD_ variable of an ordinary file, DIOCLE_COLLATION "
                              "or DIOCLE_CLOCK (keyed files are opened through DioKsds.select only)")
    for view in (text, joined):
        low = view.lower()
        for pattern in FORBIDDEN:
            m = re.search(pattern, low)
            if m:
                raise JavaRefused(f"{name}: '{m.group(0)}' is refused: converted programs reach keyed files only through "
                                  "DioKsds objects (DioKsds.select(...) then open/read/write/...)")


def stage_java(java_dir: Path, workdir: Path, keyed_dds: list[str]) -> Path:
    for path in sorted(java_dir.rglob("*.java")):
        if path.name != "DioKsds.java":
            check_java_source(path.name, path.read_text(errors="replace"), keyed_dds)
    dest = workdir / "java-src"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(java_dir, dest, ignore=shutil.ignore_patterns("DioKsds.java"))
    shutil.copy2(SUPPORT / "DioKsds.java", dest / "DioKsds.java")
    return dest


def build_java(java_dir: Path, main_class: str, workdir: Path, keyed_dds: list[str]) -> tuple[list[str] | None, Run | None]:
    try:
        src = stage_java(java_dir, workdir, keyed_dds)
    except JavaRefused as e:
        return None, Run(False, 1, "", f"refused before running: {e}")
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    build = _exec(["javac", "-proc:none", "-d", str(classes), *sorted(str(p) for p in src.rglob("*.java"))])
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return ["java", "-cp", str(classes), main_class], None


# --- both sides, then the comparison ---------------------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _records(path: Path | None, n: int) -> list[str] | None:
    """Fixed-length records of a flat keyed-file dump; [] when the file does not exist; None when it is not whole records."""
    if path is None or not path.is_file():
        return []
    if path.stat().st_size > MAX_FILE_BYTES:
        return None
    data = path.read_bytes().decode("latin-1")
    if len(data) % n:
        return None
    return [data[i:i + n] for i in range(0, len(data), n)]


def _esc(s: str, limit: int = 120) -> str:
    out = "".join(c if 32 <= ord(c) < 127 else f"\\x{ord(c):02x}" for c in s)
    return out if len(out) <= limit else out[:limit] + "..."


def compare_files(spec: dict, original: list[str] | None, converted: list[str] | None, seeded: list[str],
                  program: str) -> tuple[dict, dict]:
    """(result, report entry) for one keyed file: records in key order, the first difference by position."""
    dd, (off, length) = spec["dd"], _key_slice(spec)
    if original is None or converted is None:
        bad = "original" if original is None else "converted"
        first = {"position": 0, "key": "", "kind": "value", "original": "(unreadable)" if original is None else "",
                 "converted": "(unreadable)" if converted is None else ""}
        a, b = original or [], converted or []
        note = f"{bad} keyed file is not a whole number of records or is over the {MAX_FILE_BYTES >> 20} MB cap"
    else:
        a, b, note = original, converted, ""
        first = None
        for i in range(max(len(a), len(b))):
            ra, rb = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
            if ra == rb:
                continue
            ka = ra[off: off + length] if ra is not None else None
            kb = rb[off: off + length] if rb is not None else None
            kind = ("value" if ka == kb else "extra-in-converted" if ka is None or (kb is not None and kb < ka)
                    else "missing-in-converted")
            first = {"position": i + 1, "key": _esc(ka if ka is not None else kb or ""), "kind": kind,
                     "original": "(no record)" if ra is None else _esc(ra), "converted": "(no record)" if rb is None else _esc(rb)}
            break
    match = first is None
    entry = {"dd": dd, "keyField": spec["keyed"]["recordKey"]["field"], "recordsSeeded": len(seeded),
             "recordsOriginal": len(a), "recordsConverted": len(b), "match": match, "firstMismatch": first,
             "changedFromSeed": {"original": a != seeded, "converted": b != seeded}}
    result = {"program": program, "inputId": f"keyed:{dd}", "inputSource": "keyed", "outputDd": f"keyed:{dd}",
              "match": match, "fieldDiffs": []}
    if not match:
        result["originalOutput"], result["convertedOutput"] = first["original"], first["converted"]
        result["diff"] = (note or (f"keyed file {dd} (key {spec['keyed']['recordKey']['field']}): position {first['position']} "
                                   f"key {first['key']!r} {first['kind']}: original {first['original']!r} converted "
                                   f"{first['converted']!r}; records: original {len(a)} converted {len(b)} (seeded {len(seeded)})"))
        result["fieldDiffs"] = [{"field": f"{dd}[{first['key']}]", "original": first["original"], "converted": first["converted"]}]
    return result, entry


def run_both(plan: Plan, meta: dict, sample_dir: Path, java_dir: Path, work: Path, paths: dict, out_spec: dict, seeds: dict,
             inputs_dd: list[str], updated_dd: list[str], collation: str, seed: int):
    """Java first (own directory, own copy of the seeds), then the original; returns (original, converted, results, report,
    tamper). Everything the original reads or is built from is hashed before the Java runs and checked after."""
    dds = [s["dd"] for s in plan.specs]
    handler = indexed_handler()
    jrun = work / "jrun"
    jrun.mkdir()
    for dd, records in plan.seeds.items():
        (work / f"{dd}.kseed").write_bytes("".join(records).encode("latin-1"))
        shutil.copyfile(work / f"{dd}.kseed", jrun / f"{dd}.kf")
    genv = {"DIOCLE_COLLATION": collation.upper()}
    jenv = {**genv, **{f"DD_{dd}": str(jrun / f"{dd}.kf") for dd in dds}}
    java_cmd, converted = build_java(java_dir, meta["javaConversion"]["mainClass"], work, dds)
    guarded = [work / f"{n}.in" for n in inputs_dd] + [work / f"{n}.seed" for n in updated_dd] + [work / f"{n}.kseed" for n in plan.seeds]
    guarded += [sample_dir / meta["source"]] + [sample_dir / m for m in meta.get("modules", [])]
    guarded += sorted(p for p in (sample_dir / meta["copybookDir"]).rglob("*") if p.is_file())
    before = {str(p): _sha(p) for p in guarded if p.is_file()}
    if java_cmd:
        converted = run_files(java_cmd, paths, out_spec, jrun, "converted", jenv, seeds=seeds)
    tamper = [f"the converted program changed {Path(p).name}" for p, h in before.items() if not Path(p).is_file() or _sha(Path(p)) != h]
    for stray in ["original", "ksds-tools", *[f"{dd}.kf" for dd in dds], *[f"{dd}.final" for dd in dds]]:
        if (work / stray).exists():
            tamper.append(f"the converted program created {stray}")
    if handler is None:
        original = Run(False, None, "", "this GnuCOBOL has no indexed-file handler (cobc --info), so keyed files cannot be verified here")
    elif tamper:
        original = Run(False, None, "", "not run, verification fails closed: " + "; ".join(tamper))
    else:
        tools, original = _build_tools(plan, work)
        if tools is not None:
            cobol_cmd, original = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], work,
                                              [sample_dir / m for m in meta.get("modules", [])], collation)
            problem = None
            if cobol_cmd:
                for dd in plan.seeds:
                    problem = problem or _tool_run(tools[dd]["load"], work / f"{dd}.kseed", work / f"{dd}.kf", work)
                if problem:
                    original = Run(False, None, "", f"verifier error seeding the keyed file: {problem}")
                else:
                    original = run_files(cobol_cmd, paths, out_spec, work, "original", {f"DD_{dd}": str(work / f"{dd}.kf") for dd in dds},
                                         seeds=seeds)
    results, files = [], []
    if original.compiled and converted.compiled:
        for spec in plan.specs:
            dd, n = spec["dd"], record_length(plan.fields[spec["dd"]])
            a = None
            kf = work / f"{dd}.kf"
            if kf.is_file():
                if kf.stat().st_size > MAX_FILE_BYTES * 4:
                    a = None
                else:
                    err = _tool_run(tools[dd]["dump"], work / f"{dd}.final", kf, work)
                    a = None if err else _records(work / f"{dd}.final", n)
            else:
                a = []
            b = _records(jrun / f"{dd}.kf", n)
            res, entry = compare_files(spec, a, b, plan.seeds.get(dd, []), meta["program"])
            results.append(res)
            files.append(entry)
        extra = list(tamper)
        wrote = [s for s in plan.specs if s["direction"] in ("io", "output")]
        if wrote and not any(f["changedFromSeed"]["original"] or f["changedFromSeed"]["converted"] for f in files):
            extra.append("no keyed-file update took effect on the inputs tried: the files equal their seeds on both sides, "
                         "so equal files prove nothing")
        for why in extra:
            results.append({"program": meta["program"], "inputId": "keyed-check", "inputSource": "keyed", "outputDd": "keyed",
                            "match": False, "fieldDiffs": [], "diff": why})
    report = ({"engine": "gnucobol-indexed", "engineVersion": engine_version(), "subset": SUBSET,
               "seededFrom": f"generated records (seed {seed})", "files": files} if files else None)
    return original, converted, results, report
