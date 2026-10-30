"""CLI: python -m diocle_verifier SAMPLE_DIR [--java-dir DIR] [--out report.json]"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .verify import passes, validate_report, verify_sample


def _minimize_main(argv: list[str]) -> int:
    """python -m diocle_verifier minimize RUN_DIR --case ID [--java-dir D] [--max-runs N] [--max-seconds S]"""
    from .minimize import DEFAULT_MAX_RUNS, DEFAULT_MAX_SECONDS, minimize_run

    parser = argparse.ArgumentParser(prog="diocle_verifier minimize", description=_minimize_main.__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--case", required=True, help="a breaker input id or a verification-report inputId of that run")
    parser.add_argument("--java-dir", type=Path, help="the Java that shows the discrepancy (default: RUN_DIR/java; a "
                        "repaired run needs the pre-fix Java here)")
    parser.add_argument("--sample-dir", type=Path)
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    parser.add_argument("--from-report", action="store_true",
                        help="start from the whole input list of the run's verification report (a batch), not a lone breaker record")
    parser.add_argument("--strict", action="store_true",
                        help="also keep the exact differing values (no drift to a different manifestation)")
    args = parser.parse_args(argv)
    from .minimize import Refused
    try:
        r = minimize_run(args.run_dir, args.case, sample_dir=args.sample_dir, java_dir=args.java_dir,
                         max_runs=args.max_runs, max_seconds=args.max_seconds, strict=args.strict, from_report=args.from_report)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    red = r["reduction"]
    if r["status"] != "minimized":
        print(f"{r['status'].upper()}: {r.get('reason', '')}  ({red['oracleRuns']} oracle runs)")
        return 1
    print(f"MINIMIZED {r['id']}: {red['recordsBefore']} -> {red['recordsAfter']} records, {red['bytesBefore']} -> "
          f"{red['bytesAfter']} bytes, {red['oracleRuns']}/{red['maxOracleRuns']} oracle runs, {red['wallClockSeconds']} s, "
          f"stopped by {red['stoppedBy']}; {r['discrepancy']['summary']}")
    print(f"saved {args.run_dir}/reproducers/{r['id']}.json and {r['regression']['dir']}/")
    return 0


def _replay_main(argv: list[str]) -> int:
    """python -m diocle_verifier replay CASE_DIR --java-dir DIR   (CASE_DIR may also be a run's regression/ folder)"""
    from .minimize import replay, replay_all

    parser = argparse.ArgumentParser(prog="diocle_verifier replay", description=_replay_main.__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--java-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    from .minimize import Refused
    try:
        if (args.case_dir / "case.json").is_file():
            results = [replay(args.case_dir, args.java_dir)]
        elif (args.case_dir / "regression").is_dir():
            results = replay_all(args.case_dir, args.java_dir)
        else:
            results = [replay(d, args.java_dir) for d in sorted(args.case_dir.iterdir()) if (d / "case.json").is_file()]
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    for r in results:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']}: {r['detail']}")
    if not results:
        print("no regression cases found", file=sys.stderr)
        return 2
    return 0 if all(r["passed"] for r in results) else 1


def mutate_main(argv: list[str]) -> int:
    from .mutate import DEFAULT_MAX_EXTRA, DEFAULT_MAX_MUTANTS, mutate_run

    parser = argparse.ArgumentParser(prog="diocle_verifier mutate", description="Mutation testing of a certified run's Java.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--max-mutants", type=int, default=DEFAULT_MAX_MUTANTS)
    parser.add_argument("--max-extra", type=int, default=DEFAULT_MAX_EXTRA, help="extra inputs for survivors (default 60)")
    parser.add_argument("--seed", type=int, default=1026, help="selects the mutants; same seed, same mutants")
    parser.add_argument("--random", type=int, default=1000, help="random inputs besides fixtures and boundaries")
    args = parser.parse_args(argv)
    report = mutate_run(args.run_dir, seed=args.seed, max_mutants=args.max_mutants, max_extra=args.max_extra,
                        random_count=args.random)
    (args.run_dir / "mutation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    c, a = report["counts"], report["augmented"]
    print(f"{report['status']}: {c['killed']} killed, {c['survived']} survived, {c['notCompiled']} not compiled, "
          f"{c['equivalentSuspected']} suspected equivalent, {c['timeout']} timeout, {c['error']} error "
          f"(score {c['score']}); extra inputs killed {a['extraKills']} of {a['survivorsRerun']} survivors")
    return 0 if report["status"] == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["minimize"]:
        return _minimize_main(argv[1:])
    if argv[:1] == ["replay"]:
        return _replay_main(argv[1:])
    if argv[:1] == ["mutate"]:
        return mutate_main(argv[1:])
    parser = argparse.ArgumentParser(prog="diocle_verifier", description=__doc__)
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("--java-dir", type=Path, help="converted Java sources (default: the sample's javaConversion dir)")
    parser.add_argument("--random", type=int, default=200, help="number of random cases (default 200)")
    parser.add_argument("--seed", type=int, default=1026)
    parser.add_argument("--out", type=Path, help="write the verification report JSON here")
    parser.add_argument("--show", type=int, default=5, help="failing cases to print (default 5)")
    args = parser.parse_args(argv)

    report = verify_sample(args.sample_dir, args.java_dir, seed=args.seed, random_count=args.random)
    validate_report(report)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")

    runs = report["runs"]
    for side in ("original", "converted"):
        if not runs[side]["compiled"]:
            print(f"BUILD FAILED ({side}):\n{runs[side]['stderr']}", file=sys.stderr)
            return 2

    if not runs["exitCodeMatch"]:
        print(f"EXIT CODES DIFFER: original {runs['original']['exitCode']}, converted {runs['converted']['exitCode']}",
              file=sys.stderr)
        for side in ("original", "converted"):
            if runs[side]["stderr"].strip():
                print(f"  {side} stderr: {runs[side]['stderr'].strip()[-2000:]}", file=sys.stderr)

    s = report["summary"]
    status = "PASS" if passes(report) else "FAIL"
    print(f"{status}  {s['passed']}/{s['total']} cases match  (stdout {'matches' if runs['stdoutMatch'] else 'DIFFERS'})")
    failing = [r for r in report["results"] if not r["match"]]
    if failing:
        by_field = Counter(d["field"] for r in failing for d in r.get("fieldDiffs", []))
        print("Mismatched fields: " + ", ".join(f"{name} x{n}" for name, n in by_field.most_common()))
        for r in failing[: args.show]:
            print(f"  {r['inputId']} [{r.get('inputSource', '?')}] input={r.get('input', '')!r}\n      {r.get('diff', '')}")
    if not runs["stdoutMatch"]:
        print(f"  stdout original : {runs['original']['stdout'].strip()}\n  stdout converted: {runs['converted']['stdout'].strip()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
