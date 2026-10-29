"""Migrate a legacy GitHub repository and deliver certified Java as a pull request on a target repository.

  python -m diocle_api.deliver LEGACY_URL TARGET_URL [--programs INTACCR,TXNPOST] [--runs RUN_ID ...] [--dry-run]
  python -m diocle_api.deliver LEGACY_URL --public     # a visitor's import: sandboxed, capped, results stay on the site

1. services/analyzer clones LEGACY_URL (allowed owners only), derives layouts and writes one sample per program.
2. services/converter translates, repairs and certifies each program (Meta models, fix memory on).
   With --runs, existing certified runs are delivered instead of converting again.
3. For each certified program, programs/<PROGRAM>/ gets java/, sample.json and certificate.json
   (contracts/certificate.schema.json), on a new branch of TARGET_URL, and a pull request is opened.
   The target repository's CI re-verifies on fresh inputs with diocle_verifier.reverify.
Uncertified programs are listed in the pull request but never delivered.
Without TARGET_URL there is no step 3: the converted, verified Java stays in runs/ and on the dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .runs import REPO_ROOT, get_run

DIOCLE_URL = "https://github.com/Nivetha200111/Diocle"
SERVICES = REPO_ROOT / "services"
CERT_SEED = 4242  # services/converter/repair.py: certification uses CERT_SEED + round


def _sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def analyze(legacy_url: str, delivery_id: str) -> tuple[dict, Path]:
    """Analyze into runs/deliveries/<id>/ so concurrent deliveries never share files."""
    out = REPO_ROOT / "runs" / "deliveries" / delivery_id
    _sh([str(SERVICES / "analyzer/.venv/bin/python"), "-m", "diocle_analyzer", legacy_url,
         "--out", str(out / "analysis-report.json"), "--samples-dir", str(out / "samples")], cwd=SERVICES / "analyzer")
    return json.loads((out / "analysis-report.json").read_text()), out / "samples"


GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def target_repo(url: str) -> str:
    """owner/repo of an allowed GitHub target (same owner allowlist as imports)."""
    m = GITHUB_URL.match(url.strip())
    if not m:
        raise SystemExit("target must be https://github.com/<owner>/<repo>")
    allowed = {o.strip().lower() for o in os.environ.get("DIOCLE_IMPORT_OWNERS", "Nivetha200111").split(",") if o.strip()}
    if m.group(1).lower() not in allowed:
        raise SystemExit(f"delivering to {m.group(1)!r} is not allowed (DIOCLE_IMPORT_OWNERS)")
    return f"{m.group(1)}/{m.group(2)}"


class Progress:
    """runs/deliveries/<id>/delivery.json (contracts/delivery.schema.json), rewritten at every step."""

    def __init__(self, legacy_url: str, target_url: str | None, delivery_id: str | None = None, public: bool = False):
        self.id = delivery_id or f"delivery-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.path = REPO_ROOT / "runs" / "deliveries" / self.id / "delivery.json"
        self.state = {"id": self.id, "legacy": {"repository": legacy_url, "commit": None}, "target": target_url, "public": public,
                      "stage": "analyzing", "startedAt": _now(), "finishedAt": None, "error": None,
                      "programs": [], "pullRequest": None}
        self.save()
        (self.path.parent / "pid").write_text(str(os.getpid()))  # lets the api tell a live job from a dead one

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2) + "\n")
        tmp.replace(self.path)

    def program(self, name: str) -> dict:
        return next(p for p in self.state["programs"] if p["name"] == name)

    def update(self, **fields) -> None:
        self.state.update(fields)
        self.save()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def convert(sample_dir: Path, on_start=lambda run_id: None, flags: list[str] | None = None) -> str | None:
    """Run the converter's translate + repair + certify, streaming its output; returns the run id."""
    proc = subprocess.Popen([str(SERVICES / "converter/.venv/bin/python"), "-m", "diocle_converter", "run", str(sample_dir),
                             *(flags or [])],
                            cwd=SERVICES / "converter", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})
    run_id = None
    for line in proc.stdout:
        sys.stdout.write(f"[{sample_dir.name}] {line}")
        m = re.match(r"run started runs/(\S+)", line)
        if m:
            run_id = m.group(1)
            on_start(run_id)
    proc.wait()
    return run_id


def _copybook_paths(report: dict, program: dict) -> list[str]:
    """Where the analyzer found each copybook (library members have no extension, so never guess by suffix)."""
    return [program["copybookPaths"][c] for c in program["copybooks"]]


def certificate(run: dict, sample: dict, report: dict, program: dict, diocle_commit: str) -> dict:
    after = run["after"]
    eff = run["efficiency"]
    return {
        "version": "0.1",
        "program": program["name"],
        "legacy": {"repository": report["source"]["location"], "commit": report["source"]["commit"],
                   "path": program["path"], "copybooks": _copybook_paths(report, program),
                   "modules": program.get("modules", []),
                   "job": program.get("job")},
        "java": {"mainClass": sample["javaConversion"]["mainClass"],
                 "files": sorted(p.name for p in (REPO_ROOT / "runs" / run["id"] / "java").glob("*.java"))},
        "verification": {"passed": after["passed"], "total": after["total"], "stdoutMatch": after["stdoutMatch"],
                         "seed": run.get("certificationSeed") or CERT_SEED + len(run["rounds"]),
                         "verifier": {"repository": DIOCLE_URL, "commit": diocle_commit,
                                      "gnucobol": _sh(["cobc", "--version"]).stdout.splitlines()[0]}},
        "agent": {"runId": run["id"], "model": run["model"], "mode": "translate" if run["command"] == "run" else "repair",
                  "rounds": len(run["rounds"]), "modelCalls": eff["modelCalls"], "totalTokens": eff["totalTokens"],
                  "estimatedCostUsd": eff["estimatedCostUsd"],
                  "memoryLessonsUsed": (run.get("memory") or {}).get("used", 0)},
        "issuedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _usd(cost: float | None) -> str:
    """A cost for the PR table; n/a when a call was on a model without a known price (the run's cost is then None)."""
    return "n/a" if cost is None else f"${cost:.4f}"


def _pr_body(report: dict, delivered: list[tuple[dict, dict]], skipped: list[str]) -> str:
    src = report["source"]
    lines = [
        f"Diocle migrated [{src['location'].split('github.com/')[-1]}@{src['commit'][:12]}]({src['location']}/tree/{src['commit']}) "
        "and certified each program below against the original COBOL compiled with GnuCOBOL.", "",
        "| Program | Before | Held-out certification | Agent | Est. cost |", "|---|---|---|---|---|",
    ]
    for run, cert in delivered:
        before = f"{run['before']['passed']}/{run['before']['total']}" if run.get("before") else "n/a"
        v, a = cert["verification"], cert["agent"]
        lines.append(f"| `{cert['program']}` | {before} | **{v['passed']}/{v['total']}** match, stdout "
                     f"{'matches' if v['stdoutMatch'] else 'differs'} | {a['modelCalls']} calls, {a['rounds']} round(s), "
                     f"{a['memoryLessonsUsed']} lessons from memory | {_usd(a['estimatedCostUsd'])} |")
    if skipped:
        lines += ["", "**Not delivered** (not certified or not convertible): " + ", ".join(f"`{s}`" for s in skipped)]
    lines += ["", "Each `programs/<PROGRAM>/certificate.json` pins the legacy commit and the verifier. "
              "The **reverify** check re-runs both sides on fresh inputs from a seed Diocle never used, "
              "so this PR does not ask you to trust Diocle's own result.", "",
              "Converted by Meta Muse Spark and certified by [Diocle](https://github.com/Nivetha200111/Diocle). "
              "Estimated costs use list prices."]
    return "\n".join(lines)


def deliver(report: dict, samples: Path, run_ids: dict[str, str], target_url: str, dry_run: bool,
            progress: Progress | None = None, onto: str | None = None) -> str:
    diocle_commit = _sh(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"]).stdout.strip()
    pushed = _sh(["git", "-C", str(REPO_ROOT), "branch", "-r", "--contains", diocle_commit]).stdout.strip()
    if not pushed and not dry_run:
        raise SystemExit("Push Diocle first: CI installs the verifier from the commit named in each certificate.")
    delivered, skipped = [], []
    with tempfile.TemporaryDirectory(prefix="diocle-deliver-") as tmp:
        repo = Path(tmp) / "target"
        if onto and not re.fullmatch(r"[A-Za-z0-9._/-]+", onto):
            raise SystemExit(f"bad branch name {onto!r}")
        _sh(["git", "clone", "-q", "--depth", "1", *(["--branch", onto] if onto else []), "--",
             f"https://github.com/{target_repo(target_url)}.git", str(repo)])
        branch = onto or f"diocle/{report['source']['commit'][:12]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        if not onto:
            _sh(["git", "-C", str(repo), "checkout", "-q", "-b", branch])
        for program in report["programs"]:
            run = get_run(run_ids[program["name"]]) if program["name"] in run_ids else None
            if not run or not run["certified"] or not run.get("after"):
                skipped.append(program["name"])
                if progress:
                    progress.program(program["name"])["status"] = "not-certified" if run else "skipped"
                    progress.save()
                continue
            sample = json.loads((samples / program["name"].lower() / "sample.json").read_text())
            dest = repo / "programs" / program["name"]
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(REPO_ROOT / "runs" / run["id"] / "java", dest / "java")
            (dest / "sample.json").write_text(json.dumps(sample, indent=2) + "\n")
            cert = certificate(run, sample, report, program, diocle_commit)
            (dest / "certificate.json").write_text(json.dumps(cert, indent=2) + "\n")
            delivered.append((run, cert))
        if not delivered:
            raise SystemExit(f"Nothing certified to deliver (skipped: {', '.join(skipped)})")
        body = _pr_body(report, delivered, skipped)
        if dry_run:
            print(body)
            return str(repo)
        git = ["git", "-C", str(repo), "-c", "user.name=Diocle", "-c", "user.email=diocle@users.noreply.github.com"]
        _sh(git + ["add", "-A"])
        models = sorted({c["agent"]["model"] or "unknown model" for _, c in delivered})
        _sh(git + ["commit", "-q", "-m", f"Deliver {len(delivered)} certified program(s) from {report['source']['commit'][:12]}",
                   "-m", f"Converted by {', '.join(models)} and certified against GnuCOBOL by Diocle."])
        _sh(git + ["push", "-q", "-u", "origin", branch])
        if onto:  # an existing branch: its pull request (if any) picks up the new commit
            return f"pushed to {branch}"
        title = f"Diocle: {', '.join(c['program'] for _, c in delivered)} converted and certified"
        url = _sh(["gh", "pr", "create", "--repo", target_repo(target_url), "--head", branch,
                   "--title", title, "--body", body]).stdout.strip()
        if progress:
            progress.update(pullRequest={"url": url})
        return url


# The only strings that reach delivery.json `precheck.notes`: fixed phrases, never output of a child, the sandbox or a program.
NOTE_UNREADABLE = "the pre-check subprocess output could not be read"
NOTE_NOT_RUN = "the pre-check subprocess could not run"
NOTE_UNKNOWN = "the sandbox could not check a program (busy, unreachable or returned an error)"


class CompilePrecheck:
    """Before any model call: can GnuCOBOL build the original? Asks the verifier's compile-only job, which runs in the
    sandbox (never in this process). Bounded: at most DIOCLE_PUBLIC_MAX_PRECHECK programs and
    DIOCLE_PUBLIC_PRECHECK_SECONDS in total per import; an unavailable or busy sandbox means "no answer" and the
    program proceeds as before. Two answers of "no answer" end the pre-check for this import."""

    def __init__(self, samples: Path, max_checks: int, seconds: float):
        self.samples, self.left, self.deadline, self.unknown = samples, max_checks, time.time() + seconds, 0
        self.checked, self.stopped, self.notes = 0, None, []

    def record(self) -> dict:
        """For delivery.json (`precheck`): how many were asked and why the check ended early, if it did."""
        return {"checked": self.checked, "stopped": self.stopped, "notes": self.notes[-5:]}

    def failure(self, name: str) -> str | None:
        """The compiler's reason when the original does not compile, else None (compiles, or could not be checked)."""
        remaining = self.deadline - time.time()
        if self.left <= 0 or remaining <= 0 or self.unknown >= 2:
            self.stopped = self.stopped or ("the sandbox did not answer twice (busy, unreachable or failed)" if self.unknown >= 2
                                            else "the time bound was used up" if remaining <= 0 else "the program count bound was reached")
            return None
        self.left -= 1
        self.checked += 1
        wait = min(30.0, remaining)
        answer, noted = {"status": "unknown"}, len(self.notes)
        try:
            proc = subprocess.run(
                [str(SERVICES / "verifier/.venv/bin/python"), "-I", "-m", "diocle_verifier.precheck",
                 str(self.samples / name.lower()), "--wait", str(wait)],
                capture_output=True, text=True, timeout=wait + 120, cwd=SERVICES / "verifier",
                env={k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "DIOCLE_SANDBOX_URL")})
            try:
                answer = json.loads(proc.stdout.strip().splitlines()[-1])
                if not isinstance(answer, dict):
                    raise ValueError("not an object")
            except (ValueError, IndexError):
                answer = {"status": "unknown"}
                # Visible to the operator in deliver.log (server side) only; the delivery record gets a fixed phrase.
                print(f"precheck {name}: unreadable output (exit {proc.returncode}); stderr tail: "
                      f"{(proc.stderr or '')[-300:].strip()!r}", flush=True)
                self.notes.append(NOTE_UNREADABLE)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"precheck {name}: could not run: {type(e).__name__}", flush=True)
            self.notes.append(NOTE_NOT_RUN)
        if answer.get("status") == "fail":
            found = [d[:200] for d in (answer.get("diagnostics") or []) if isinstance(d, str)][:4]
            return " | ".join(found) if found else None  # a failure without a diagnostic is not believed
        if answer.get("status") != "ok":
            self.unknown += 1
            if len(self.notes) == noted and NOTE_UNKNOWN not in self.notes[-1:]:
                self.notes.append(NOTE_UNKNOWN)
            if self.unknown >= 2:
                self.stopped = "the sandbox did not answer twice (busy, unreachable or failed); the rest proceed unchecked"
                print(f"precheck stopped: {self.stopped}", flush=True)
        return None


def _visitor_caps(programs: list[dict], samples: Path, precheck: CompilePrecheck | None = None
                  ) -> tuple[list[dict], list[dict]]:
    """Visitor imports convert at most DIOCLE_PUBLIC_MAX_PROGRAMS programs of DIOCLE_PUBLIC_MAX_LINES lines each.
    With a precheck, a program whose original does not compile is skipped (with the compiler's reason) before any
    model call and does not use up one of the program slots: the next compilable program takes its place."""
    max_programs = int(os.environ.get("DIOCLE_PUBLIC_MAX_PROGRAMS", "3"))
    max_lines = int(os.environ.get("DIOCLE_PUBLIC_MAX_LINES", "1500"))
    keep, skipped = [], []
    for p in programs:
        meta = json.loads((samples / p["name"].lower() / "sample.json").read_text())
        lines = len((samples / p["name"].lower() / meta["source"]).read_bytes().splitlines())
        reason = (f"{lines} lines; visitor imports take up to {max_lines}" if lines > max_lines else
                  f"visitor imports convert up to {max_programs} programs" if len(keep) >= max_programs else None)
        if reason is None and precheck is not None:
            why = precheck.failure(p["name"])
            if why:
                reason = f"the original does not compile under GnuCOBOL -std=ibm: {why}"
                print(f"precheck {p['name']}: {reason}", flush=True)
        if reason:
            skipped.append({"name": p["name"], "path": p["path"], "status": "skipped", "runId": None, "reason": reason})
        else:
            keep.append(p)
    return keep, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_api.deliver", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("legacy_url")
    parser.add_argument("target_url", nargs="?", help="repository for the pull request (omit to keep results on the site)")
    parser.add_argument("--programs", help="comma-separated PROGRAM-IDs (default: all convertible)")
    parser.add_argument("--runs", nargs="*", default=[], help="deliver these existing run ids instead of converting")
    parser.add_argument("--dry-run", action="store_true", help="build the delivery and print the PR body; push nothing")
    parser.add_argument("--parallel", action="store_true",
                        help="swarm: convert all programs at once; agents share lessons as each one certifies")
    parser.add_argument("--breaker", action="store_true", help="after certification, a breaker agent attacks each program")
    parser.add_argument("--onto", help="commit onto this existing target branch instead of opening a new pull request")
    parser.add_argument("--id", help="delivery id to use (the API passes one so the dashboard can follow it)")
    parser.add_argument("--public", action="store_true",
                        help="a visitor's import: needs the sandbox, visitor caps, no pull request, no swarm or breaker")
    args = parser.parse_args(argv)
    if args.public:
        if not os.environ.get("DIOCLE_SANDBOX_URL"):
            parser.error("--public needs DIOCLE_SANDBOX_URL: imported code must never run beside the secrets")
        args.target_url, args.parallel, args.breaker, args.runs = None, False, False, []

    target = args.target_url.rstrip("/").removesuffix(".git") if args.target_url else None
    progress = Progress(args.legacy_url, target, args.id, args.public)
    print(f"delivery {progress.id}", flush=True)
    try:
        if target:
            target_repo(target)  # fail fast on a bad or disallowed target
        report, samples = analyze(args.legacy_url, progress.id)
        wanted = set(args.programs.split(",")) if args.programs else None
        report["programs"] = [p for p in report["programs"] if p["convertible"] and (wanted is None or p["name"] in wanted)]
        skipped, seen = [], {}
        for p in list(report["programs"]):  # samples are keyed by PROGRAM-ID, so a second file with the same one is skipped
            if p["name"] in seen:
                report["programs"].remove(p)
                skipped.append({"name": f"{p['name']} ({p['path'].rsplit('/', 1)[-1]})", "path": p["path"], "status": "skipped",
                                "runId": None, "reason": f"same PROGRAM-ID as {seen[p['name']]}"})
            else:
                seen[p["name"]] = p["path"]
        if args.public:
            from . import public

            lim = public.limits()
            pre = CompilePrecheck(samples, lim["maxPrecheck"], lim["precheckSeconds"])
            report["programs"], skipped = _visitor_caps(report["programs"], samples, pre)
            progress.state["precheck"] = pre.record()
        max_programs = int(os.environ.get("DIOCLE_MAX_PROGRAMS", "10"))  # rule 10: bound spend per delivery
        if len(report["programs"]) > max_programs:
            raise SystemExit(f"{len(report['programs'])} programs exceed DIOCLE_MAX_PROGRAMS={max_programs}; "
                             "pass --programs or raise the cap")
        progress.state["legacy"]["commit"] = report["source"]["commit"]
        if not report["programs"]:
            raise SystemExit("no convertible programs" + (f" within the visitor limits ({skipped[0]['reason']})" if skipped else ""))
        progress.update(stage="converting", programs=[
            {"name": p["name"], "path": p["path"], "status": "queued", "runId": None} for p in report["programs"]] + skipped)
        run_ids = {}
        for run_id in args.runs:
            run = get_run(run_id)
            if run and run["certified"]:
                run_ids[run["program"]] = run_id
            else:
                print(f"ignoring --runs {run_id}: {'not certified' if run else 'not found'}", flush=True)
        flags = ((["--swarm"] if args.parallel else []) + (["--breaker"] if args.breaker else [])
                 + (["--memory-read-only"] if args.public else []))  # strangers' code never shapes later runs
        lock = threading.Lock()

        def work(program: dict) -> None:
            entry = progress.program(program["name"])
            with lock:
                entry["status"] = "converting"
                progress.save()

            def started(run_id: str) -> None:
                if args.public:  # a visitor's run: labelled, and never offered for public re-verification
                    (REPO_ROOT / "runs" / run_id).mkdir(parents=True, exist_ok=True)
                    (REPO_ROOT / "runs" / run_id / "visitor").write_text(progress.id + "\n")
                with lock:
                    entry["runId"] = run_id
                    progress.save()

            run_id = convert(samples / program["name"].lower(), started, flags)
            run = get_run(run_id) if run_id else None
            with lock:
                entry.update(runId=run_id, status="certified" if run and run["certified"] else "not-certified")
                progress.save()
                if run_id:
                    run_ids[program["name"]] = run_id

        todo = []
        for program in report["programs"]:
            if program["name"] in run_ids:
                progress.program(program["name"]).update(runId=run_ids[program["name"]], status="certified")
                progress.save()
            else:
                todo.append(program)
        if args.parallel:
            print(f"swarm: converting {len(todo)} programs in parallel", flush=True)
            workers = max(1, min(len(todo), int(os.environ.get("DIOCLE_MAX_PARALLEL", "4"))))  # rule 10
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(work, todo))
        else:
            for program in todo:
                print(f"converting {program['name']} ...", flush=True)
                work(program)
        if target:
            progress.update(stage="delivering")
            print(deliver(report, samples, run_ids, target, args.dry_run, progress, args.onto))
        progress.update(stage="done", finishedAt=_now())
    except BaseException as e:
        progress.update(stage="failed", error=str(e)[:500] or type(e).__name__, finishedAt=_now())
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
