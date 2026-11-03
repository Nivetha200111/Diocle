"""Run the external estate exactly as docs/EXTERNAL_ESTATE.md pins it, before any tuning.

  services/verifier/.venv/bin/python eval/run_external_estate.py --plan                   # no model calls
  services/verifier/.venv/bin/python eval/run_external_estate.py --max-total-usd 2.00     # spends model credits

Imports openmainframeproject/cobol-programming-course once (analyzer, pinned commit in the report), then accounts
for every program in the report: refused (analyzer reason, quoted), certified, not certified, or not converted
because another source holds its PROGRAM-ID. Convertible programs run as a user would: `diocle_converter run
<sample> --breaker --no-memory` under the normal caps and a $0.40 limit per program, up to --workers at a time, then
five fresh seeds if certified. Each result says what was really exercised (input files, the fields a new seed changes, breaker run or skipped), because certifying a
program whose inputs never vary shows much less than certifying one that was attacked.

Results are saved after every program to runs/external-estate/results.partial.json, and a killed run resumes from
it under the same settings and Diocle commit; the finished file, eval/results-external-estate.json, is never
overwritten. A program starts only if everything spent so far, read from the run records, plus its limit for each
running program stays within --max-total-usd; the rest are reported as not run. A model provider failure stops the
run without recording a verdict, because an outage says nothing about the program. Full converter output goes to the
git-ignored runs/external-estate/logs/, not the public results: provider messages can echo account details.
Nothing here changes the product. The clone and derived samples stay in git-ignored runs/external-estate/ (no
estate source is committed). Needs GnuCOBOL, a JDK and .env keys, like every real conversion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "verifier"))
from diocle_verifier.inputs import generate_for_layout  # noqa: E402
from diocle_verifier.layout import load_fields  # noqa: E402
from diocle_verifier.multi import _input_records, file_specs, is_multi  # noqa: E402
from diocle_verifier.verify import passes, verify_sample  # noqa: E402

ESTATE_URL = "https://github.com/openmainframeproject/cobol-programming-course"
PINNED_COMMIT = "780b1c9624e066b9d784a738896e493282c5fbf4"
WORK = ROOT / "runs" / "external-estate"
REPORT = WORK / "report.json"
SAMPLES = WORK / "samples"
OUT = ROOT / "eval" / "results-external-estate.json"
PARTIAL = WORK / "results.partial.json"  # git-ignored: a partial result is published only if it is labelled as one
FRESH_SEEDS = [9001, 9002, 9003, 9004, 9005]
CONVERTER = [str(ROOT / "services/converter/.venv/bin/python"), "-m", "diocle_converter"]
CONVERTER_CWD = ROOT / "services" / "converter"
TIMEOUT_MINUTES = 150  # longer than the longest conversion on record (125.6 minutes, BRNCHSUM, eval-freeze-1)
LOGS = WORK / "logs"
PREFLIGHT = [CONVERTER[0], "-c", "from diocle_converter.config import Settings\nassert Settings.from_env().api_key\nSettings.guard_from_env()"]
REQUIRED_TOOLS = ["cobc", "javac", "java"]
TAIL_CHARS = 2000
PROGRAM_CAP_USD = 0.40  # hard, per program (--max-usd fails closed); dearest in the evaluations $0.1642, private-mode runs $0.18-0.23
RUN_DIR = re.compile(r"^(.+)-(\d{8}-\d{6})$")
# Not 400, 413 or 422: a request the provider rejects says something about this program, and would only repeat on resume.
PROVIDER_FAILURE = re.compile(r"APIConnectionError|APITimeoutError|AuthenticationError|PermissionDeniedError|RateLimitError|InternalServerError|\bHTTP (?:401|402|403|408|429|5\d\d)\b")
SECOND_PASS = False
EXTRA_FLAGS: list[str] = []
NOT_COMPILING_IN_FIRST_PASS = {"CBL0001", "CBL0002", "CBL0004", "CBL0005", "CBL0006", "CBL0007", "CBL0008", "CBL0009", "CBL0010", "CBL0011",
                               "CBL0012", "CBL0033", "CBL006A", "CBL0106", "CBL0106C", "PAYROL0X"}
THIRD_PASS = False
BLIND = False
NOT_CERTIFIED_IN_EARLIER_PASSES = {"CBL0004", "CBL0005", "CBL0006", "CBL0008", "CBL0010", "CBL0011", "CBL0012", "CBL0015", "CBL0033",
                                   "CBL006A", "CBL0106", "CBL0106C", "COBOL"}
THIRD_PASS_LABEL = ("third, after a product fix made in response to this same course's failures: "
                    "not a blind test, and it must say so wherever it is quoted")
REPAIRED = "certified against repaired COBOL"
_procs: set[subprocess.Popen] = set()
_procs_lock = threading.Lock()


def import_estate() -> dict:
    """Analyze the estate once, as found. Returns the analyzer report."""
    if REPORT.exists():
        return json.loads(REPORT.read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DIOCLE_IMPORT_OWNERS": ESTATE_URL.rsplit("/", 2)[1]}
    proc = subprocess.run([str(ROOT / "services/analyzer/.venv/bin/python"), "-m", "diocle_analyzer", ESTATE_URL,
                           "--out", str(REPORT), "--samples-dir", str(SAMPLES)],
                          cwd=ROOT / "services" / "analyzer", env=env, capture_output=True, text=True)
    if proc.returncode != 0 or not REPORT.exists():
        sys.exit(f"analyzer import failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(REPORT.read_text())


def check_pin(commit: str | None) -> None:
    """The result is about one commit. A report without one (a local path import) cannot be shown to be that commit."""
    if not commit:
        sys.exit("the report pins no commit (a local import?); delete runs/external-estate and import from GitHub")
    if not commit.startswith(PINNED_COMMIT):
        sys.exit(f"estate moved: report pins {commit}, protocol pins {PINNED_COMMIT}; "
                 "re-pin docs/EXTERNAL_ESTATE.md before running, do not silently follow the move")


def _clean(text: str | None) -> str | None:
    """Text bound for a public results file: no local paths, nothing that looks like a key, only the tail."""
    if not text:
        return text
    text = text.replace(str(ROOT), "<repo>").replace(str(ROOT.resolve()), "<repo>").replace(str(Path.home()), "~")
    text = re.sub(r"(?i)(authorization[\"':= ]+(?:bearer\s+)?|bearer\s+|(?:api[_-]?)?(?:key|token|secret)[\"':= ]+)\S+", r"\1<redacted>", text)
    return text[-TAIL_CHARS:]


def _records(sample: Path, meta: dict, seed: int) -> tuple[dict[str, list], dict[str, list[str]]]:
    """(the fields of each seeded file, its generated records) for a seed, the way verify_sample generates them."""
    specs = [s for s in file_specs(meta) if s["direction"] in ("input", "io") and not s.get("keyed")]
    fields = {s["dd"]: load_fields(s["layout"]) for s in specs}
    if not is_multi(meta):
        return fields, {s["dd"]: [c.record for c in generate_for_layout(s["layout"], seed=seed, random_count=1000)
                                  if c.source == "random"] for s in specs}
    plan = None
    if meta.get("ksds"):
        from diocle_verifier import ksds
        plan = ksds.plan_seeds(meta, seed, 1000)
    return fields, _input_records(meta, sample, specs, seed, 1000, plan)


def exercise(sample: Path) -> dict:
    """What a run of this sample can exercise, measured with the verifier's own generator. No model, no compiler.
    A field counts as varied only if a new seed changes it: alphanumeric fields get placeholders that number the
    record (C00000000000001), so they differ between records but are the same under every seed."""
    meta = json.loads((sample / "sample.json").read_text())
    fields, first = _records(sample, meta, FRESH_SEEDS[0])
    _, second = _records(sample, meta, FRESH_SEEDS[1])
    varied, total = [], 0
    for dd, layout in fields.items():
        offset = 0
        for f in layout:
            total += 1
            if [r[offset:offset + f.length] for r in first[dd]] != [r[offset:offset + f.length] for r in second[dd]]:
                varied.append(f"{dd}.{f.name}" if len(fields) > 1 else f.name)
            offset += f.length
    return {"shape": "display-only" if meta.get("displayOnly") else "multi-file" if is_multi(meta) else "single-file",
            "inputFiles": sorted(fields), "seedsChangeInputs": first != second,
            "fieldsTotal": total, "fieldsVaried": varied, "breakerCanRun": "layouts" in meta}


def level(entry: dict) -> str:
    """The one line a results table needs: a certification only shows what its run exercised."""
    label = entry["outcome"]
    if label not in ("certified", REPAIRED):
        return label
    if not all(s.get("passed") for s in entry["freshSeeds"]):
        return f"{label}, then failed a fresh seed"
    if "error" in entry["exercised"]:
        return f"{label}, what it exercised is unknown"
    if not entry["exercised"]["seedsChangeInputs"]:
        return f"{label}, inputs never vary"
    tried = (entry.get("breaker") or {}).get("tried", 0)
    return f"{label}, inputs vary, attacked" if tried else f"{label}, inputs vary, not attacked"


def _kill_running() -> None:
    with _procs_lock:
        for proc in _procs:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def _run_converter(sample: Path) -> tuple[int | None, str, str]:
    """Runs one conversion in its own process group, so a timeout or Ctrl-C also stops the compilers and JVMs under it.
    The exit code is None after a timeout."""
    proc = subprocess.Popen([*CONVERTER, "run", str(sample), "--breaker", "--no-memory", "--max-usd", str(PROGRAM_CAP_USD), *EXTRA_FLAGS],
                            cwd=CONVERTER_CWD, text=True, errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    with _procs_lock:
        _procs.add(proc)
    try:
        out, err = proc.communicate(timeout=TIMEOUT_MINUTES * 60)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        return None, out, err
    finally:
        with _procs_lock:
            _procs.discard(proc)


def _last_events(run_id: str) -> list | None:
    path = ROOT / "runs" / run_id / "events.jsonl"
    if not path.exists():
        return None
    events = [json.loads(line) for line in path.read_text(errors="replace").splitlines()]
    said = [e.get("message") or str(e.get("result") or "")[:300] for e in events]
    return [_clean(text) for text in said if text][-3:]


def _fresh_seed(sample: Path, java: Path, seed: int) -> dict:
    try:  # one broken re-check must not lose a night's results or a program's certification record
        report = verify_sample(sample, java, seed=seed, random_count=1000)
        failing = [r for r in report["results"] if not r["match"]]
        return {"seed": seed, "passed": passes(report), "compiled": {side: report["runs"][side]["compiled"] for side in ("original", "converted")},
                "cases": report["summary"]["total"], "failed": report["summary"]["failed"], "exitCodeMatch": report["runs"]["exitCodeMatch"],
                "stdoutMatch": report["runs"]["stdoutMatch"], "firstMismatch": failing[0].get("diff") if failing else None}
    except Exception as e:
        return {"seed": seed, "passed": False, "error": _clean(f"{type(e).__name__}: {e}")}


def convert(sample: Path, program: str) -> dict:
    started = time.time()
    code, out, err = _run_converter(sample)
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{sample.name}-{time.strftime('%Y%m%d-%H%M%S')}.log").write_text(f"{out}\n--- stderr ---\n{err}")
    m = re.search(r"run saved to runs/(\S+)", out) or re.search(r"run started runs/(\S+)", out)
    run_id = m.group(1) if m else None
    run_file = ROOT / "runs" / run_id / "run.json" if run_id else None
    meta = json.loads(run_file.read_text()) if run_file and run_file.exists() else {}
    settings = re.search(r"^model: (\S+) \((\w+)\), reasoning_effort=(\S+), caps: (.+)$", out, re.M)
    certified = meta.get("certified", False) is True and code is not None
    assurance = meta.get("assurance") if code is not None else None  # --convert-anyway only; `certified` stays false on all but plain
    repaired = assurance == "certified-against-repaired-cobol"
    error = meta.get("error") or (f"timed out after {TIMEOUT_MINUTES} minutes" if code is None else None)
    if not certified and not repaired and not error and meta.get("status", "running") == "running":  # the type only: a provider's message can echo account details
        last = (err.strip().splitlines() or [""])[-1]
        kind = re.match(r"[\w.]*(?:Error|Exception|Exceeded)\b", last)
        error = f"the converter exited with {code} and left {'an unfinished' if meta else 'no'} run record" + (f" ({kind.group(0)})" if kind else "")
    guard = meta.get("guard") or {}
    review = guard.get("review") or {}
    outcome = "certified" if certified else REPAIRED if repaired else "compiled, not verified" if assurance == "compiled-unverified" else "not certified"
    repair = meta.get("cobolRepair") or {}
    result = {"program": program, "outcome": outcome, "runId": run_id,
              "exitCode": code, "certified": certified, "error": _clean(error),
              "model": settings.group(1) if settings else None, "modelMode": settings.group(2) if settings else None,
              "reasoningEffort": settings.group(3) if settings else None, "caps": settings.group(4) if settings else None,
              "rounds": len(meta.get("rounds", [])), "usage": {k: v for k, v in meta.get("usage", {}).items() if k != "modelCalls"},
              "breaker": meta.get("breaker"), "status": meta.get("status"), "assurance": meta.get("assurance"), "assuranceReason": _clean(meta.get("assuranceReason")),
              "cobolRepair": {"method": repair.get("method"), "outcome": repair.get("outcome"), "changedLines": repair.get("changedLines"), "diff": _clean(repair.get("diff"))} if repair else None,
              "guard": {"blocked": guard.get("blocked"), "stopped": guard.get("stopped"), "reviewVerdict": review.get("verdict"),
                        "reviewSummary": _clean(review.get("summary"))} if guard else None,
              "minutes": round((time.time() - started) / 60, 1), "freshSeeds": []}
    if certified or repaired:  # a repair is compared in the sample's patched copy, next to it
        compared = sample.with_name(f"{sample.name}.repaired") if repaired else sample
        result["freshSeeds"] = [_fresh_seed(compared, ROOT / "runs" / run_id / "java", seed) for seed in FRESH_SEEDS]
    else:
        result["lastEvents"] = _last_events(run_id) if run_id else None
    return result


def _spend(names: set[str], since: str) -> dict:
    """Everything this run has spent, read from the run records (live ones too), so a killed or running conversion
    counts. A run with calls and no known price makes the total unknown, which stops new programs (fails closed)."""
    total, unknown, runs = 0.0, False, {}
    for path in (ROOT / "runs").glob("*/run.json"):
        m = RUN_DIR.match(path.parent.name)
        if not m or m.group(1) not in names or m.group(2) < since:
            continue
        runs[m.group(1)] = runs.get(m.group(1), 0) + 1
        try:
            usage = json.loads(path.read_text()).get("usage") or {}
        except (OSError, ValueError):
            unknown = True
            continue
        cost = usage.get("estimatedCostUsd")
        if cost is None and usage.get("calls"):
            unknown = True
        total += cost or 0
    return {"usd": total, "unknown": unknown, "restarted": sorted(n for n, count in runs.items() if count > 1)}


def _version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return "not found"
    return ((proc.stdout or proc.stderr).strip().splitlines() or ["unknown"])[0]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _save(path: Path, header: dict, results: list[dict], spend: dict, complete: bool) -> None:
    tally: dict[str, int] = {}
    for r in results:
        tally[level(r)] = tally.get(level(r), 0) + 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**header, "complete": complete, "programsAccounted": len(results), "tally": tally,
                               "recordedCostUsd": round(spend["usd"], 6), "costComplete": not spend["unknown"],
                               "restartedPrograms": spend["restarted"],
                               "certifiedWithoutGuardPass": [r["program"] for r in results if r.get("outcome") in ("certified", REPAIRED) and (r.get("guard") or {}).get("reviewVerdict") != "pass"],
                               "results": results}, indent=2) + "\n")
    tmp.replace(path)


def use_second_pass() -> None:
    """The dated re-run docs/EXTERNAL_ESTATE.md pins: its own import and files, and only the programs whose original did
    not compile, through the product's existing --convert-anyway, whose results are never labelled plain certified."""
    global WORK, REPORT, SAMPLES, OUT, PARTIAL, LOGS, SECOND_PASS, EXTRA_FLAGS
    WORK = ROOT / "runs" / "external-estate-second-pass"
    REPORT, SAMPLES, PARTIAL, LOGS = WORK / "report.json", WORK / "samples", WORK / "results.partial.json", WORK / "logs"
    OUT, SECOND_PASS, EXTRA_FLAGS = ROOT / "eval" / "results-external-estate-second-pass.json", True, ["--convert-anyway"]


def use_third_pass() -> None:
    """The dated re-run docs/EXTERNAL_ESTATE.md pins, after the WRITE ... ADVANCING fix: its own import and files, and only
    the 13 programs that were not certified. --convert-anyway, because 11 of them need the repaired copy again; the two whose
    original compiles (CBL0015, COBOL) pass through it unpatched. Never a blind test: the fix was made in response to them."""
    global WORK, REPORT, SAMPLES, OUT, PARTIAL, LOGS, THIRD_PASS, EXTRA_FLAGS
    WORK = ROOT / "runs" / "external-estate-third-pass"
    REPORT, SAMPLES, PARTIAL, LOGS = WORK / "report.json", WORK / "samples", WORK / "results.partial.json", WORK / "logs"
    OUT, THIRD_PASS, EXTRA_FLAGS = ROOT / "eval" / "results-external-estate-third-pass.json", True, ["--convert-anyway"]


BLIND_REPOS = {  # pinned in docs/BLIND_TEST.md before any model call
    "navikt/DSF": "faade4961e316c89e8c312456bae411c63f1c482",
    "fzn0x/core-banking-system": "770860d4a11f1d203b0369456d867108097a550f",
    "ibmdbbdev/Samples": "61a1a20f495203bdb16d4c74a5a076f4fbfc379b",
}


def use_blind_repo(repo: str) -> None:
    """A repository the WRITE ... ADVANCING fix never saw, run once as found on the product as it stands. --convert-anyway only
    patches an original that does not compile, and that result is never labelled plain certified."""
    global WORK, REPORT, SAMPLES, OUT, PARTIAL, LOGS, BLIND, EXTRA_FLAGS, ESTATE_URL, PINNED_COMMIT
    slug = repo.replace("/", "-").lower()
    ESTATE_URL, PINNED_COMMIT = f"https://github.com/{repo}", BLIND_REPOS[repo]
    WORK = ROOT / "runs" / f"blind-{slug}"
    REPORT, SAMPLES, PARTIAL, LOGS = WORK / "report.json", WORK / "samples", WORK / "results.partial.json", WORK / "logs"
    OUT, BLIND, EXTRA_FLAGS = ROOT / "eval" / f"results-blind-{slug}.json", True, ["--convert-anyway"]


def _outside_this_pass(name: str) -> str | None:
    """Why a convertible program is not converted in this pass, or None if it is."""
    if SECOND_PASS and name not in NOT_COMPILING_IN_FIRST_PASS:
        return "its original compiled in the first pass; see that result"
    if THIRD_PASS and name not in NOT_CERTIFIED_IN_EARLIER_PASSES:
        return "certified, or never compared, in an earlier pass; see those results"
    return None


def _classify(program: dict, samples: dict[str, Path], holders: dict[Path, str]) -> dict | None:
    """The outcome of a program that needs no conversion, or None if it is to be converted (and now holds its sample)."""
    name, path = program["name"], program["path"]
    if not program["convertible"]:
        return {"program": name, "path": path, "outcome": "refused", "reason": program["notConvertibleReason"]}
    if name not in samples:
        return {"program": name, "path": path, "outcome": "not run", "reason": "the analyzer marked it convertible but wrote no sample"}
    if samples[name] in holders:
        # The analyzer writes one sample per PROGRAM-ID and keeps the first file. This source can be a different
        # program under the same ID (CBLC1.cobol is PROGRAM-ID CBL0006 but counts New York, not Virginia).
        return {"program": name, "path": path, "outcome": "not converted",
                "reason": f"PROGRAM-ID {name} is already held by {holders[samples[name]]}; the analyzer writes one sample per PROGRAM-ID, so this source was never converted"}
    holders[samples[name]] = path
    outside = _outside_this_pass(name)
    return {"program": name, "path": path, "outcome": "not in this pass", "reason": outside} if outside else None


def _convert_entry(program: dict, sample: Path) -> dict:
    name, path = program["name"], program["path"]
    try:  # measured first, so a program this cannot read is reported before anything is spent on it
        exercised = exercise(sample)
    except Exception as e:
        exercised = {"error": _clean(f"{type(e).__name__}: {e}")}
    try:
        return {"path": path, **convert(sample, name), "exercised": exercised}
    except Exception as e:  # one broken program must not lose the night: it is reported, and the run goes on
        return {"program": name, "path": path, "outcome": "not certified", "certified": False, "exercised": exercised,
                "error": _clean(f"the runner failed on this program: {type(e).__name__}: {e}")}


def preflight() -> None:
    """A missing key or compiler must stop the run here, not be published as a program that failed."""
    missing = [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]
    if missing:
        sys.exit(f"missing {', '.join(missing)}: nothing was run")
    proc = subprocess.run(PREFLIGHT, cwd=CONVERTER_CWD, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["unknown"])[-1].split(":")[0]
        sys.exit(f"the converter's settings do not load ({last}): check .env; nothing was run")


def run_estate(max_total: float, workers: int = 1) -> dict[str, int]:
    if OUT.exists():
        sys.exit(f"{OUT.name} exists; results are never overwritten (a re-run is a separate, dated file)")
    preflight()
    if _git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("the working tree has changes: the result must name the commit that produced it")
    report = import_estate()
    commit = (report.get("source") or {}).get("commit")
    check_pin(commit)
    samples = {json.loads((s / "sample.json").read_text())["program"]: s
               for s in sorted(SAMPLES.iterdir()) if (s / "sample.json").exists() and not s.name.endswith(".repaired")}
    names = {s.name for s in samples.values()}
    header = {"pass": "blind: a repository the fix never saw, one run as found" if BLIND else THIRD_PASS_LABEL if THIRD_PASS else "second, --convert-anyway on what did not compile" if SECOND_PASS else "first, as found",
              **({"blindTest": False} if THIRD_PASS else {"blindTest": True} if BLIND else {}), "estate": ESTATE_URL, "pinnedCommit": PINNED_COMMIT, "analyzedCommit": commit, "memory": False,
              "converterFlags": ["--breaker", "--no-memory", "--max-usd", str(PROGRAM_CAP_USD), *EXTRA_FLAGS], "freshSeeds": FRESH_SEEDS,
              "maxTotalUsd": max_total, "programCapUsd": PROGRAM_CAP_USD, "workers": workers, "timeoutMinutes": TIMEOUT_MINUTES,
              "diocleCommit": _git("rev-parse", "HEAD"), "startedAt": time.strftime("%Y%m%d-%H%M%S"),
              "cobc": _version(["cobc", "--version"]), "java": _version(["java", "-version"]), "resumes": 0,
              **({"ranIn": os.environ["DIOCLE_RAN_IN"]} if os.environ.get("DIOCLE_RAN_IN") else {})}
    results: list[dict] = []
    if PARTIAL.exists():  # same settings, the rest of the same pass; the file says how often this happened
        earlier = json.loads(PARTIAL.read_text())
        if earlier["maxTotalUsd"] != max_total:
            sys.exit(f"{PARTIAL.name} was started with a ${earlier['maxTotalUsd']:.2f} ceiling; a resume keeps the settings")
        if earlier["diocleCommit"] != header["diocleCommit"]:
            sys.exit(f"{PARTIAL.name} was started on {earlier['diocleCommit']}; changing Diocle partway would be tuning")
        results, header["resumes"], header["startedAt"] = earlier["results"], earlier["resumes"] + 1, earlier["startedAt"]
        print(f"resuming: {len(results)} of {len(report['programs'])} programs already accounted for", flush=True)
    done = {r["path"] for r in results}
    cond = threading.Condition()
    stop = threading.Event()
    provider_failure: list[str] = []
    running = 0

    def record(entry: dict) -> None:
        with cond:
            results.append(entry)
            spend = _spend(names, header["startedAt"])
            _save(PARTIAL, header, results, spend, complete=False)
            print(json.dumps({"program": entry["program"], "level": level(entry), "spentUsd": round(spend["usd"], 4),
                              **({"minutes": entry["minutes"]} if "minutes" in entry else {})}), flush=True)

    def work(program: dict) -> None:
        nonlocal running
        with cond:
            while True:  # a program waits for room while others run; it is only given up on when nothing is left to wait for
                if stop.is_set():
                    return
                spend = _spend(names, header["startedAt"])
                if not spend["unknown"] and spend["usd"] + (running + 1) * PROGRAM_CAP_USD <= max_total:
                    running += 1
                    break
                if running == 0:
                    why = "the spend so far is unknown" if spend["unknown"] else f"the ${max_total:.2f} ceiling left no room for its ${PROGRAM_CAP_USD:.2f} limit"
                    record({"program": program["name"], "path": program["path"], "outcome": "not run", "reason": why})
                    return
                cond.wait(timeout=5)
        try:
            entry = _convert_entry(program, samples[program["name"]])
        except BaseException:  # stop starting programs; what has finished is saved
            stop.set()
            raise
        finally:
            with cond:
                running -= 1
                cond.notify_all()
        if stop.is_set() and (entry.get("exitCode") or 0) < 0:  # killed by the stop: no verdict. A finished conversion is kept
            return
        if entry["outcome"] != "certified" and PROVIDER_FAILURE.search(entry.get("error") or ""):
            provider_failure.append(f"{entry['program']}: {entry['error']}")
            stop.set()
            _kill_running()
            with cond:
                cond.notify_all()
            return
        record(entry)

    holders: dict[Path, str] = {}
    todo = []
    for program in report["programs"]:
        immediate = _classify(program, samples, holders)
        if program["path"] in done:
            continue
        if immediate:
            record(immediate)
        else:
            todo.append(program)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        for future in [pool.submit(work, program) for program in todo]:
            future.result()
    except BaseException:
        stop.set()
        _kill_running()
        with cond:
            cond.notify_all()
        pool.shutdown(cancel_futures=True)
        raise
    pool.shutdown()
    if provider_failure:
        sys.exit(f"stopped by a model provider failure, recorded as no verdict ({provider_failure[0]}). "
                 "Fix it and run the same command to resume; the spend so far stays counted")
    order = {program["path"]: i for i, program in enumerate(report["programs"])}
    results.sort(key=lambda r: order[r["path"]])
    spend = _spend(names, header["startedAt"])
    _save(OUT, header, results, spend, complete=True)
    PARTIAL.unlink()
    tally: dict[str, int] = {}
    for r in results:
        tally[level(r)] = tally.get(level(r), 0) + 1
    print(json.dumps({"programs": len(results), **tally, "recordedCostUsd": round(spend["usd"], 4)}))
    return tally


def plan() -> list[dict]:
    """What the run would cover, with no model call and no compiler."""
    report = import_estate()
    check_pin((report.get("source") or {}).get("commit"))
    rows, seen = [], set()
    for program in report["programs"]:
        name, row = program["name"], {"program": program["name"], "path": program["path"]}
        if not program["convertible"]:
            rows.append({**row, "outcome": "refused", "reason": program["notConvertibleReason"]})
        elif name in seen:
            rows.append({**row, "outcome": "not converted", "reason": f"PROGRAM-ID {name} is already held by an earlier source"})
        elif _outside_this_pass(name):
            seen.add(name)
            rows.append({**row, "outcome": "not in this pass"})
        else:
            seen.add(name)
            rows.append({**row, "outcome": "to convert", "exercised": exercise(SAMPLES / name.lower())})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", action="store_true", help="print what would be exercised; no model calls")
    parser.add_argument("--max-total-usd", type=float, help="the approved ceiling for the whole run (required for a run)")
    parser.add_argument("--workers", type=int, default=1, help="conversions at a time (default 1)")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--second-pass", action="store_true", help="the dated re-run, with --convert-anyway, of the programs whose original did not compile")
    which.add_argument("--third-pass", action="store_true", help="the dated re-run, after the WRITE ... ADVANCING fix, of the 13 not certified; not a blind test")
    which.add_argument("--blind", choices=sorted(BLIND_REPOS), help="one repository the fix never saw, as docs/BLIND_TEST.md pins")
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):  # a kill or a closed terminal stops the conversions too
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.second_pass:
        use_second_pass()
    if args.third_pass:
        use_third_pass()
    if args.blind:
        use_blind_repo(args.blind)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    elif args.max_total_usd is None:
        parser.error("a real run spends model credits: pass the approved --max-total-usd, or --plan")
    else:
        run_estate(args.max_total_usd, args.workers)
