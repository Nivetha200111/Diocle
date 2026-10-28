"""Migrate a legacy GitHub repository and deliver certified Java as a pull request on a target repository.

  python -m diocle_api.deliver LEGACY_URL TARGET_URL [--programs INTACCR,TXNPOST] [--runs RUN_ID ...] [--dry-run]

1. services/analyzer clones LEGACY_URL (allowed owners only), derives layouts and writes one sample per program.
2. services/converter translates, repairs and certifies each program (Meta models, fix memory on).
   With --runs, existing certified runs are delivered instead of converting again.
3. For each certified program, programs/<PROGRAM>/ gets java/, sample.json and certificate.json
   (contracts/certificate.schema.json), on a new branch of TARGET_URL, and a pull request is opened.
   The target repository's CI re-verifies on fresh inputs with diocle_verifier.reverify.
Uncertified programs are listed in the pull request but never delivered.
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .runs import REPO_ROOT, get_run

DIOCLE_URL = "https://github.com/Nivetha200111/Diocle"
SERVICES = REPO_ROOT / "services"
CERT_SEED = 4242  # services/converter/repair.py: certification uses CERT_SEED + round


def _sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def analyze(legacy_url: str) -> tuple[dict, Path]:
    out = REPO_ROOT / "runs" / "imports"
    report_path = out / "latest-report.json"
    _sh([str(SERVICES / "analyzer/.venv/bin/python"), "-m", "diocle_analyzer", legacy_url,
         "--out", str(report_path), "--samples-dir", str(out / "latest-samples")], cwd=SERVICES / "analyzer")
    report = json.loads(report_path.read_text())
    samples = out / f"samples-{report['source']['commit'][:12]}"
    if samples.exists():
        shutil.rmtree(samples)
    (out / "latest-samples").rename(samples)
    return report, samples


class Progress:
    """runs/deliveries/<id>/delivery.json (contracts/delivery.schema.json), rewritten at every step."""

    def __init__(self, legacy_url: str, target_url: str):
        self.id = f"delivery-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.path = REPO_ROOT / "runs" / "deliveries" / self.id / "delivery.json"
        self.state = {"id": self.id, "legacy": {"repository": legacy_url, "commit": None}, "target": target_url,
                      "stage": "analyzing", "startedAt": _now(), "finishedAt": None, "error": None,
                      "programs": [], "pullRequest": None}
        self.save()

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


def _legacy_root(report: dict) -> Path:
    owner_repo = report["source"]["location"].split("github.com/")[1].replace("/", "-")
    return REPO_ROOT / "runs" / "imports" / f"{owner_repo}-{report['source']['commit'][:12]}"


def _copybook_paths(report: dict, program: dict) -> list[str]:
    root = _legacy_root(report)
    found = {p.stem.upper(): p.relative_to(root).as_posix() for p in root.rglob("*")
             if p.suffix.lower() in (".cpy", ".copy") and ".git" not in p.parts}
    return [found[c] for c in program["copybooks"]]


def certificate(run: dict, sample: dict, report: dict, program: dict, diocle_commit: str) -> dict:
    after = run["after"]
    eff = run["efficiency"]
    return {
        "version": "0.1",
        "program": program["name"],
        "legacy": {"repository": report["source"]["location"], "commit": report["source"]["commit"],
                   "path": program["path"], "copybooks": _copybook_paths(report, program),
                   "job": program.get("job")},
        "java": {"mainClass": sample["javaConversion"]["mainClass"],
                 "files": sorted(p.name for p in (REPO_ROOT / "runs" / run["id"] / "java").glob("*.java"))},
        "verification": {"passed": after["passed"], "total": after["total"], "stdoutMatch": after["stdoutMatch"],
                         "seed": CERT_SEED + len(run["rounds"]),
                         "verifier": {"repository": DIOCLE_URL, "commit": diocle_commit,
                                      "gnucobol": _sh(["cobc", "--version"]).stdout.splitlines()[0]}},
        "agent": {"runId": run["id"], "model": run["model"], "mode": "translate" if run["command"] == "run" else "repair",
                  "rounds": len(run["rounds"]), "modelCalls": eff["modelCalls"], "totalTokens": eff["totalTokens"],
                  "estimatedCostUsd": eff["estimatedCostUsd"],
                  "memoryLessonsUsed": (run.get("memory") or {}).get("used", 0)},
        "issuedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


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
                     f"{a['memoryLessonsUsed']} lessons from memory | ${a['estimatedCostUsd']:.4f} |")
    if skipped:
        lines += ["", "**Not delivered** (not certified or not convertible): " + ", ".join(f"`{s}`" for s in skipped)]
    lines += ["", "Each `programs/<PROGRAM>/certificate.json` pins the legacy commit and the verifier. "
              "The **reverify** check re-runs both sides on fresh inputs from a seed Diocle never used, "
              "so this PR does not ask you to trust Diocle's own result.", "",
              "Model: Meta Muse Spark. Estimated costs use list prices.", "",
              "🤖 Generated with [Claude Code](https://claude.com/claude-code) and Diocle"]
    return "\n".join(lines)


def deliver(report: dict, samples: Path, run_ids: dict[str, str], target_url: str, dry_run: bool,
            progress: Progress | None = None) -> str:
    diocle_commit = _sh(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"]).stdout.strip()
    pushed = _sh(["git", "-C", str(REPO_ROOT), "branch", "-r", "--contains", diocle_commit]).stdout.strip()
    if not pushed and not dry_run:
        raise SystemExit("Push Diocle first: CI installs the verifier from the commit named in each certificate.")
    delivered, skipped = [], []
    with tempfile.TemporaryDirectory(prefix="diocle-deliver-") as tmp:
        repo = Path(tmp) / "target"
        _sh(["git", "clone", "-q", "--depth", "1", f"{target_url}.git", str(repo)])
        branch = f"diocle/{report['source']['commit'][:12]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        _sh(["git", "-C", str(repo), "checkout", "-q", "-b", branch])
        for program in report["programs"]:
            run = get_run(run_ids[program["name"]]) if program["name"] in run_ids else None
            if not run or not run["certified"] or not run.get("after"):
                skipped.append(program["name"])
                if progress:
                    progress.program(program["name"])["status"] = "not-certified" if run else "skipped"
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
        _sh(git + ["commit", "-q", "-m", f"Deliver {len(delivered)} certified program(s) from {report['source']['commit'][:12]}",
                   "-m", "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"])
        _sh(git + ["push", "-q", "-u", "origin", branch])
        title = f"Diocle: {', '.join(c['program'] for _, c in delivered)} converted and certified"
        url = _sh(["gh", "pr", "create", "--repo", target_url.split("github.com/")[1], "--head", branch,
                   "--title", title, "--body", body]).stdout.strip()
        if progress:
            progress.update(pullRequest={"url": url})
        return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_api.deliver", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("legacy_url")
    parser.add_argument("target_url")
    parser.add_argument("--programs", help="comma-separated PROGRAM-IDs (default: all convertible)")
    parser.add_argument("--runs", nargs="*", default=[], help="deliver these existing run ids instead of converting")
    parser.add_argument("--dry-run", action="store_true", help="build the delivery and print the PR body; push nothing")
    parser.add_argument("--parallel", action="store_true",
                        help="swarm: convert all programs at once; agents share lessons as each one certifies")
    parser.add_argument("--breaker", action="store_true", help="after certification, a breaker agent attacks each program")
    args = parser.parse_args(argv)

    progress = Progress(args.legacy_url, args.target_url.rstrip("/").removesuffix(".git"))
    print(f"delivery {progress.id}", flush=True)
    try:
        report, samples = analyze(args.legacy_url)
        wanted = set(args.programs.split(",")) if args.programs else None
        report["programs"] = [p for p in report["programs"] if p["convertible"] and (wanted is None or p["name"] in wanted)]
        progress.state["legacy"]["commit"] = report["source"]["commit"]
        progress.update(stage="converting", programs=[
            {"name": p["name"], "path": p["path"], "status": "queued", "runId": None} for p in report["programs"]])
        run_ids = {}
        for run_id in args.runs:
            run = get_run(run_id)
            if run:
                run_ids[run["program"]] = run_id
        flags = (["--swarm"] if args.parallel else []) + (["--breaker"] if args.breaker else [])
        lock = threading.Lock()

        def work(program: dict) -> None:
            entry = progress.program(program["name"])
            with lock:
                entry["status"] = "converting"
                progress.save()

            def started(run_id: str) -> None:
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
            with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
                list(pool.map(work, todo))
        else:
            for program in todo:
                print(f"converting {program['name']} ...", flush=True)
                work(program)
        progress.update(stage="delivering")
        print(deliver(report, samples, run_ids, progress.state["target"], args.dry_run, progress))
        progress.update(stage="done", finishedAt=_now())
    except BaseException as e:
        progress.update(stage="failed", error=str(e)[:500] or type(e).__name__, finishedAt=_now())
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
