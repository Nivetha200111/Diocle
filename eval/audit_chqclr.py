"""SYNTHETIC evidence audit of the showcased CHQCLR run. No model call: GnuCOBOL and the JDK only, deterministic seeds.

Why it exists: CHQCLR's record is a type byte plus one 39-byte body shared by two REDEFINES views, and until Nov 1, 2026
the verifier's generator filled only that body with a placeholder (see docs/SHOWCASE_CHQCLR.md). The stored run's
"1,004 held-out inputs" are real but near-identical. This script asks what that Java does on the inputs they could not be.

    services/verifier/.venv/bin/python eval/audit_chqclr.py [--java DIR ...] [--mutants] [--out FILE]

1. Replays the stored breaker counterexamples on the original and on the repaired Java.
2. Runs well-formed cheques and returns with real amounts and fees (seed below, written before any result was seen).
3. Reports malformed records on which the certified Java still differs and no attack tried.
4. With --mutants, re-tests the 40 seeded faults of the live mutation report on the stored run's generated records, on
   those of the fixed generator, on the well-formed records above and on the breaker's.
"""
import argparse
import hashlib
import json
import random
import shutil
import string
import tempfile
from pathlib import Path

from diocle_verifier.inputs import Case, generate_cases
from diocle_verifier.layout import load_fields
from diocle_verifier.mutate import generate_mutants
from diocle_verifier.runners import ProgramTimeout
from diocle_verifier.verify import passes, verify_sample

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "samples" / "chqclr"
RUN = ROOT / "eval" / "showcase" / "chqclr-20261028-214355"
AUDIT_SEED, AUDIT_RECORDS = 20261101, 1000
CERT_SEED, MUTANT_SEED = 4243, 1026  # the stored run's certification seed and the live report's mutant seed


def digits(rng: random.Random, width: int) -> str:
    """Width digits with a log-uniform size, so small, ordinary and maximum values all appear."""
    size = rng.randint(1, width)
    value = rng.randint(0, 10 ** size - 1)
    return f"{value:0{width}d}"


def well_formed(seed: int = AUDIT_SEED, count: int = AUDIT_RECORDS) -> list[Case]:
    """Every record obeys the copybook: digits in PIC 9 fields, a sign byte in the separate sign, 40 bytes."""
    rng, cases = random.Random(seed), []
    alnum = string.ascii_uppercase + string.digits
    for i in range(count):
        acct = "".join(rng.choices(alnum, k=10))
        number = f"{rng.randint(0, 99_999_999):08d}"
        kind = rng.random()
        if kind < 0.45:
            date = f"{rng.randint(2000, 2030)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
            record = f"C{acct}{number}{rng.choice('+-')}{digits(rng, 9)}{date}   "
        elif kind < 0.9:
            fee = rng.choice([digits(rng, 5), digits(rng, 5), "00000", "49999", "50000", "50001", "99999"])
            record = f"R{acct}{number}{rng.choice(['NS', 'NS', 'SP', 'XX'])}{fee}{' ' * 14}"
        else:  # any other type byte takes the reject path
            record = rng.choice("XZ ") + "".join(rng.choices(alnum, k=39))
        cases.append(Case(f"audit-{i + 1:04d}", "audit", record))
    return cases


def breaker_cases() -> list[Case]:
    """Every distinct record the stored run's breaker designed (well-formed and malformed)."""
    attempts = json.loads((RUN / "breaker.json").read_text())["attempts"]
    records = list(dict.fromkeys(a["input"] for a in attempts))
    return [Case(f"breaker-{i + 1:02d}", "model", r) for i, r in enumerate(records)]


def large_cheques(count: int) -> list[Case]:
    """Credits of 9,999,999.99 each, the largest the field holds."""
    return [Case(f"large-{i + 1:03d}", "audit", f"CACCT{i:06d}{i:08d}-99999999920240101   ") for i in range(count)]


def is_malformed(record: str) -> bool:
    """Does a cheque or return record break its own copybook? (The other type bytes never read the body.)"""
    if record[0] == "C":
        return not (record[11:19].isdigit() and record[19] in "+-" and record[20:29].isdigit() and record[29:37].isdigit())
    if record[0] == "R":
        return not (record[11:19].isdigit() and record[21:26].isdigit())
    return False


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(java: Path) -> dict:
    report = verify_sample(SAMPLE, java, seed=AUDIT_SEED, random_count=0, extra_cases=well_formed())
    rows = [r for r in report["results"] if r.get("inputSource") == "audit"]
    outputs = [r.get("originalOutput", "") for r in rows]
    return {"java": str(java.relative_to(ROOT)) if java.is_relative_to(ROOT) else f"run folder {java.parent.name}",
            "javaSha256": sha(next(java.glob("*.java"))),
            "recordsCompared": report["summary"]["total"], "failed": report["summary"]["failed"],
            "auditRecords": len(rows), "distinctOutputs": len(set(outputs)),
            "nonZeroDebits": sum(o[19:28].strip("0") != "" for o in outputs),
            "nonZeroFees": sum(o[28:33].strip("0") != "" for o in outputs),
            "stdoutMatch": report["runs"]["stdoutMatch"], "exitCodeMatch": report["runs"]["exitCodeMatch"],
            "passes": passes(report),
            "firstFailures": [{"input": r.get("input"), "diff": r.get("diff")} for r in report["results"] if not r["match"]][:5]}


def fixed_generator(java: Path, seeds=(4243, 8801, 9001, 9002, 9003)) -> list[dict]:
    """The verifier's own check as it now is: fills the REDEFINES body, from several seeds."""
    rows = []
    for seed in seeds:
        report = verify_sample(SAMPLE, java, seed=seed, random_count=1000)
        outputs = [r.get("originalOutput", "") for r in report["results"]]
        rows.append({"seed": seed, "passes": passes(report), **report["summary"], "distinctOutputs": len(set(outputs)),
                     "nonZeroDebits": sum(o[19:28].strip("0") != "" for o in outputs), "nonZeroFees": sum(o[28:33].strip("0") != "" for o in outputs)})
    return rows


def replay_breaks(java: Path) -> list[dict]:
    """One program run per record, so a record cannot hide behind another's output."""
    rows = []
    stored = {c["input"]: c["diff"] for c in json.loads((RUN / "breaker.json").read_text())["counterexamples"]}
    for record, diff in stored.items():
        report = verify_sample(SAMPLE, java, seed=AUDIT_SEED, random_count=0, extra_cases=[Case("break", "model", record)])
        row = next(r for r in report["results"] if r.get("inputId") == "break")
        rows.append({"input": record, "malformed": is_malformed(record), "storedDiffOnPreRepairJava": diff,
                     "originalOutputToday": row["originalOutput"], "repairedJavaOutputToday": row["convertedOutput"],
                     "repairedMatches": row["match"]})
    return rows


def residual(java: Path) -> list[dict]:
    """Malformed records no attack tried, from the mutation tool's extra inputs. Differences here stay reported: the Java
    is certified on the inputs it was tried on, not on these."""
    rows = []
    for name, record in (("return with a blank body", "R" + " " * 39), ("cheque with a blank body", "C" + " " * 39)):
        report = verify_sample(SAMPLE, java, seed=AUDIT_SEED, random_count=0, extra_cases=[Case("blank", "audit", record)])
        row = next(r for r in report["results"] if r.get("inputId") == "blank")
        rows.append({"record": name, "input": record, "malformed": is_malformed(record), "matches": row["match"],
                     "original": row["originalOutput"], "java": row["convertedOutput"], "diff": row.get("diff")})
    return rows


def mutants(java: Path) -> dict:
    """Same 40 faults as the live report: which does each input set detect? Compile failures are not detections."""
    selected, generated = generate_mutants(java, seed=MUTANT_SEED, max_mutants=40)
    layout = json.loads((SAMPLE / "sample.json").read_text())["layouts"]["input"]
    placeholders = generate_cases(load_fields(layout), seed=CERT_SEED, random_count=1000)  # the generator the stored run used
    sets = {"storedRunInputs": dict(seed=AUDIT_SEED, random_count=0, extra_cases=placeholders),
            "fixedGenerator": dict(seed=CERT_SEED, random_count=1000, extra_cases=[]),
            "wellFormedAudit": dict(seed=AUDIT_SEED, random_count=0, extra_cases=well_formed()),
            "breakerRecords": dict(seed=AUDIT_SEED, random_count=0, extra_cases=breaker_cases()),
            # Well-formed, and only a long file of large cheques gets the running total this high: 9 integer digits, then past them.
            "largeTotal": dict(seed=AUDIT_SEED, random_count=0, extra_cases=large_cheques(11)),
            "overflowingTotal": dict(seed=AUDIT_SEED, random_count=0, extra_cases=large_cheques(120)),
            # And one small cheque: a net total with a single integer digit, so the edited total's leading spaces all show.
            "smallTotal": dict(seed=AUDIT_SEED, random_count=0, extra_cases=[Case("small-001", "audit", f"CACCT000001{1:08d}+00000050020240101   ")])}
    rows = []
    for m in selected:
        with tempfile.TemporaryDirectory(prefix="diocle-audit-") as tmp:
            work = Path(tmp) / "java"
            shutil.copytree(java, work)
            target = work / m.file
            text = target.read_text(encoding="utf-8", errors="surrogateescape")
            target.write_text(text[: m.start] + m.replacement + text[m.end :], encoding="utf-8", errors="surrogateescape")
            row = {"id": m.id, "operator": m.operator, "line": m.line, "original": m.original, "mutated": m.mutated,
                   "compiled": True, "detectedBy": []}
            for name, args in sets.items():
                try:
                    report = verify_sample(SAMPLE, work, **args)
                except ProgramTimeout:  # never finishes where the original does: detected, as in the mutation report
                    row["detectedBy"].append(name)
                    continue
                if not report["runs"]["converted"]["compiled"]:
                    row["compiled"] = False
                    break
                if not passes(report):
                    row["detectedBy"].append(name)
            rows.append(row)
        print(m.id, row["compiled"], row["detectedBy"], flush=True)
    compiled = [r for r in rows if r["compiled"]]
    return {"generatedCandidates": generated, "selected": len(rows), "compiled": len(compiled),
            "detected": {name: sum(name in r["detectedBy"] for r in compiled) for name in sets},
            "detectedByAny": sum(bool(r["detectedBy"]) for r in compiled), "mutants": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--java", action="append", type=Path, help="other stored Java folders to run on the well-formed records")
    ap.add_argument("--mutants", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    java = RUN / "java"
    result = {"synthetic": True, "modelCalls": 0, "auditSeed": AUDIT_SEED, "cobolSha256": sha(SAMPLE / "src" / "CHQCLR.cbl"),
              "runId": RUN.name, "breaks": replay_breaks(java), "residual": residual(java), "fixedGenerator": fixed_generator(java), "wellFormed": [summarize(j) for j in [java, *(a.java or [])]]}
    designed = breaker_cases()
    result["breakerDesigned"] = {"distinctRecords": len(designed), "malformed": sum(is_malformed(c.record) for c in designed)}
    if a.mutants:
        result["mutation"] = mutants(java)
    text = json.dumps(result, indent=1)
    if a.out:
        a.out.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
