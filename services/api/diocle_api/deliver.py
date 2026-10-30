"""Migrate a legacy GitHub repository and deliver certified Java as a pull request on a target repository.

  python -m diocle_api.deliver LEGACY_URL TARGET_URL [--programs INTACCR,TXNPOST] [--runs RUN_ID ...] [--dry-run]
  python -m diocle_api.deliver LEGACY_URL --public     # a visitor's import: sandboxed, capped, results stay on the site

1. services/analyzer clones LEGACY_URL (allowed owners only), derives layouts and writes one sample per program.
2. services/converter translates, repairs and certifies each program (Meta models, fix memory on).
   With --runs, existing certified runs are delivered instead of converting again.
3. For each certified program, programs/<PROGRAM>/ gets java/, sample.json and certificate.json
   (contracts/certificate.schema.json), on a new branch of TARGET_URL, and a pull request is opened.
   The target repository's CI re-verifies on fresh inputs with diocle_verifier.reverify.
With --create-target NAME the target repository is created first (private unless --target-public), never reusing an
existing one, and the pull request is opened into it.
Uncertified programs are listed in the pull request but never delivered.
Without TARGET_URL there is no step 3: the converted, verified Java stays in runs/ and on the dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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


def analyze(legacy_url: str, delivery_id: str, convert_anyway: bool = False) -> tuple[dict, Path]:
    """Analyze into runs/deliveries/<id>/ so concurrent deliveries never share files."""
    out = REPO_ROOT / "runs" / "deliveries" / delivery_id
    _sh([str(SERVICES / "analyzer/.venv/bin/python"), "-m", "diocle_analyzer", legacy_url,
         "--out", str(out / "analysis-report.json"), "--samples-dir", str(out / "samples"),
         *(["--convert-anyway"] if convert_anyway else [])], cwd=SERVICES / "analyzer")
    return json.loads((out / "analysis-report.json").read_text()), out / "samples"


GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def target_repo(url: str) -> str:
    """owner/repo of an allowed GitHub target (same owner allowlist as imports)."""
    m = GITHUB_URL.match(url.strip())
    if not m:
        raise SystemExit("target must be https://github.com/<owner>/<repo>")
    check_owner(m.group(1))
    return f"{m.group(1)}/{m.group(2)}"


def check_owner(owner: str) -> None:
    """The one owner allowlist, for existing targets and for repositories this delivery creates."""
    allowed = {o.strip().lower() for o in os.environ.get("DIOCLE_IMPORT_OWNERS", "Nivetha200111").split(",") if o.strip()}
    if owner.lower() not in allowed:
        raise SystemExit(f"delivering to {owner!r} is not allowed (DIOCLE_IMPORT_OWNERS)")


REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")  # matched with fullmatch: no trailing newline, ASCII only
OWNER_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


def validate_create_target(name, owner=None, visibility="private") -> dict:
    """contracts/delivery.schema.json $defs.createTarget. Offline checks only (syntax and the owner allowlist for an
    explicit owner); the engine's own GitHub login is checked against the allowlist when the delivery runs."""
    if not isinstance(name, str) or not REPO_NAME.fullmatch(name) or name in (".", "..") or name.endswith(".git"):
        raise SystemExit("repository name: 1 to 100 letters, digits, '.', '-' or '_' (not '.', '..' or ending in .git)")
    if owner is not None and (not isinstance(owner, str) or not OWNER_NAME.fullmatch(owner)):
        raise SystemExit("owner must be a GitHub user or organisation name")
    if owner is not None:
        check_owner(owner)
    if visibility not in ("private", "public"):
        raise SystemExit("visibility must be private or public")
    return {"name": name, "owner": owner, "visibility": visibility}


def _gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """gh with a fixed argv (no shell). It authenticates itself (gh login or GH_TOKEN in its environment); the token is
    never read, printed or logged here."""
    return subprocess.run(["gh", *args], check=check, text=True, capture_output=True)


def _gh_error(e: subprocess.CalledProcessError) -> str:
    return ((e.stderr or "").strip().splitlines() or [f"exit status {e.returncode}"])[-1][:200]


def plan_create(create: dict, legacy_url: str, dry_run: bool = False) -> dict:
    """Resolve owner and name, apply the allowlist, refuse an existing repository. Creates nothing.
    In a dry run, a missing or logged-out gh only marks that check as skipped."""
    owner, notes = create.get("owner"), []
    if owner is None:
        try:
            owner = _gh(["api", "user", "--jq", ".login"]).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as e:
            if not dry_run:
                raise SystemExit("could not find your GitHub login with gh; run `gh auth login` or pass --target-owner")
            owner = "<your-github-login>"
            notes.append("the GitHub login could not be read (gh not logged in); owner and allowlist not checked")
        else:
            if not OWNER_NAME.fullmatch(owner):
                raise SystemExit("gh returned an unexpected login")
    if not notes:
        check_owner(owner)  # the authenticated user must be allowed as well
    full = f"{owner}/{create['name']}"
    if not notes:
        try:
            exists = _gh(["api", f"repos/{full}"], check=False)
        except OSError:
            if not dry_run:
                raise SystemExit("gh is not installed")
            exists, notes = None, ["gh not available; existence not checked"]
        if exists is not None:
            if exists.returncode == 0:
                raise SystemExit(f"{full} already exists. Diocle never reuses or overwrites an existing repository when "
                                 f"asked to create one; pass https://github.com/{full} as the target instead.")
            if "404" not in exists.stderr and "Not Found" not in exists.stderr:  # anything but a clear "does not exist"
                if not dry_run:
                    raise SystemExit(f"could not tell whether {full} exists ({exists.stderr.strip().splitlines()[-1][:120] if exists.stderr.strip() else 'no answer'}); nothing was created")
                notes.append("existence not checked")
    m = GITHUB_URL.match(legacy_url.strip())
    legacy = f"{m.group(1)}/{m.group(2)}" if m else "a legacy repository"
    command = ["gh", "repo", "create", full, "--private" if create["visibility"] == "private" else "--public",
               "--description", f"Java conversion of {legacy}, verified by Diocle", "--add-readme"]
    return {"owner": owner, "name": create["name"], "full": full, "visibility": create["visibility"],
            "url": f"https://github.com/{full}", "command": command, "notes": notes}


def create_repository(plan: dict) -> None:
    """The one place a repository is created. --add-readme gives it an initial commit, so a pull request base exists."""
    if plan["visibility"] == "public":
        print(f"NOTICE: {plan['full']} will be PUBLIC (--target-public).", flush=True)
    try:
        _gh(plan["command"][1:])
    except (OSError, subprocess.CalledProcessError) as e:
        raise SystemExit(f"gh repo create {plan['full']} failed ({_gh_error(e) if isinstance(e, subprocess.CalledProcessError) else 'gh not found'}); "
                         f"check with `gh repo view {plan['full']}` whether it exists. Nothing else was done.") from e
    print(f"created {plan['url']} ({plan['visibility']})", flush=True)


def reverify_workflow(legacy_url: str, diocle_commit: str) -> str:
    """CI for a repository Diocle created: a target that already existed brings its own. Pins the verifier commit the
    certificates name; the seed is one the converter never used."""
    # Both values end up in a shell line of the generated workflow: accept only what they must look like, and quote them anyway.
    if not GITHUB_URL.fullmatch(legacy_url.strip()):
        raise SystemExit(f"the legacy repository must be https://github.com/<owner>/<repo> to be written into CI, got {legacy_url[:60]!r}")
    if not re.fullmatch(r"[0-9a-f]{7,40}", diocle_commit):
        raise SystemExit("the pinned Diocle commit must be a hex commit id")
    legacy_url = shlex.quote(legacy_url.strip())
    return f"""name: reverify
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  reverify:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: {{distribution: temurin, java-version: '21'}}
      - uses: actions/setup-python@v5
        with: {{python-version: '3.12'}}
      # The verifier compiles with options only GnuCOBOL 3.2 knows (-fdefault-colseq=EBCDIC): the distribution package is older.
      - name: Cache GnuCOBOL 3.2
        id: gnucobol
        uses: actions/cache@v4
        with:
          path: ~/gnucobol
          key: gnucobol-3.2-ubuntu-24.04-v2-db
      - name: Build GnuCOBOL 3.2 (the version Diocle certifies with)
        if: steps.gnucobol.outputs.cache-hit != 'true'
        run: |
          sudo apt-get update -q && sudo apt-get install -y -q libgmp-dev libdb-dev
          curl -sSfL https://ftp.gnu.org/gnu/gnucobol/gnucobol-3.2.tar.xz | tar xJ
          cd gnucobol-3.2
          ./configure -q --prefix="$HOME/gnucobol" --with-db --with-curses=no --without-xml2 --without-json
          make -s -j"$(nproc)" && make -s install
      - name: Install the Berkeley DB runtime (needed by the cached build too)
        run: sudo apt-get update -q && sudo apt-get install -y -q libdb5.3t64
      - name: Put GnuCOBOL on the path
        run: |
          echo "$HOME/gnucobol/bin" >> "$GITHUB_PATH"
          echo "LD_LIBRARY_PATH=$HOME/gnucobol/lib" >> "$GITHUB_ENV"
      - name: Install the pinned verifier
        run: |
          git clone {DIOCLE_URL}.git "$RUNNER_TEMP/diocle"
          git -C "$RUNNER_TEMP/diocle" checkout {diocle_commit}
          pip install "$RUNNER_TEMP/diocle/services/analyzer" "$RUNNER_TEMP/diocle/services/verifier"
      - name: Compile every program together (whole-repository build)
        run: |
          set -eu
          [ -d programs ] || {{ echo "no programs/ directory: nothing to compile"; exit 0; }}
          extra=""
          # Programs with embedded SQL use the verifier's own DioSql.java, which is not delivered with them: take it from the pinned commit.
          if grep -rlqw DioSql programs && [ -z "$(find programs -name DioSql.java)" ]; then
            extra="$RUNNER_TEMP/diocle/services/verifier/diocle_verifier/dbsupport/DioSql.java"
          fi
          mkdir -p "$RUNNER_TEMP/out"
          # One quoted path per line in an @argfile: spaces in names are safe and the command line never hits ARG_MAX.
          find programs -name '*.java' -print | sort | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g' -e 's/^/"/' -e 's/$/"/' > "$RUNNER_TEMP/files.txt"
          if [ -n "$extra" ]; then printf '"%s"\\n' "$extra" >> "$RUNNER_TEMP/files.txt"; fi
          javac -proc:none -d "$RUNNER_TEMP/out" @"$RUNNER_TEMP/files.txt"
      - name: Re-verify on fresh inputs
        run: python -m diocle_verifier.reverify programs --seed 777777 --expect-legacy {legacy_url} --summary "$GITHUB_STEP_SUMMARY"
"""


def _clean_line(text: object, limit: int = 300) -> str:
    """Text from the build report into the PR body: a conservative character set (no links, HTML or code spans)."""
    return re.sub(r"[^A-Za-z0-9 _.,:;'/=+$()-]", "?", str(text))[:limit]


def run_build_check(repo: Path, delivered: list[tuple[dict, dict]], samples: Path, report: dict,
                    domain_classes: Path | None = None) -> dict | None:
    """Whole-repository build check of the certified programs as they sit in the delivery (programs/<NAME>/java), through
    the verifier's own CLI in a child with a minimal environment (it compiles model-written Java with javac -proc:none and
    runs nothing). Writes build/build-report.json and build/BUILD-REPORT.md into the delivery. Returns the report, or None
    when the check could not run: it never blocks a delivery, because every program is verified on its own."""
    py = SERVICES / "verifier/.venv/bin/python"
    args = []
    for _, cert in delivered:
        name = cert["program"]
        sample = samples / name.lower()
        if (repo / "programs" / name / "java").is_dir() and sample.is_dir():
            args += ["--program", name, str(repo / "programs" / name / "java"), str(sample)]
    if not args or not py.exists():
        return None
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "JAVA_HOME")}
    env["PYTHONPATH"] = os.pathsep.join([str(SERVICES / "verifier"), str(SERVICES / "analyzer")])
    with tempfile.TemporaryDirectory(prefix="diocle-build-") as tmp:
        report_file = Path(tmp) / "analysis-report.json"
        report_file.write_text(json.dumps(report))
        try:
            proc = subprocess.run([str(py), "-m", "diocle_verifier.buildcheck", *args, "--report", str(report_file),
                                   *(["--domain-classes", str(domain_classes)] if domain_classes else []), "--out", str(Path(tmp) / "out")],
                                  cwd=SERVICES / "verifier", env=env, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
            result = json.loads((Path(tmp) / "out" / "build-report.json").read_text())
            if proc.returncode not in (0, 1) or result.get("verdict") not in ("pass", "warn", "fail"):
                return None
        except (OSError, subprocess.SubprocessError, ValueError):
            print("build check: could not run (the delivery continues; programs are verified on their own)", flush=True)
            return None
        dest = repo / "build"
        dest.mkdir(exist_ok=True)
        shutil.copyfile(Path(tmp) / "out" / "build-report.json", dest / "build-report.json")
        shutil.copyfile(Path(tmp) / "out" / "BUILD-REPORT.md", dest / "BUILD-REPORT.md")
    return result


def build_summary(result: dict | None) -> dict | None:
    """The part of a build report kept in the delivery record (contracts/delivery.schema.json buildCheck)."""
    if not result:
        return None
    return {"verdict": result["verdict"], "reasons": [_clean_line(r) for r in result["reasons"]][:30],
            "programs": len(result["programs"]), "calls": result["calls"]["checked"],
            "copybookDrift": len(result["copybooks"]["drift"]), "classCollisions": len(result["classCollisions"])}


def build_section(result: dict | None, delivered_count: int) -> list[str]:
    """PR body lines about the whole-repository build. Says plainly when it did not pass or did not run."""
    if not delivered_count:
        return []
    if not result:
        return ["", "## Whole-repository build check", "",
                "**Not run.** The programs were not compiled together by Diocle for this pull request (the check could not run). "
                "Each program is still verified on its own; the generated CI compiles all of them together."]
    verdict, reasons = result["verdict"], [_clean_line(r) for r in result["reasons"]]
    head = {"pass": f"**Pass.** All {len(result['programs'])} certified programs compiled together with `javac -proc:none`, and the copybook "
                    "and CALL checks found no mismatch. This is a compile and interface check, not a behavioural one.",
            "warn": "**Warn.** The programs compiled together, but something could not be checked or looks suspicious:",
            "fail": "**FAIL: the whole-repository build did not pass.** The certified programs are delivered anyway, because each was verified "
                    "on its own against the original COBOL, but they do not build or fit together as a whole:"}[verdict]
    lines = ["", "## Whole-repository build check", "", head]
    if verdict != "pass":
        lines += [f"- {r}" for r in reasons[:8]]
        if len(reasons) > 8:
            lines.append(f"- and {len(reasons) - 8} more in `build/BUILD-REPORT.md`")
    lines += ["", "`build/BUILD-REPORT.md` and `build/build-report.json` list what was checked and what was not "
              "(behaviour of the programs together, JCL step order and dataset wiring are not checked)."]
    return lines


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


def child_env(convert_anyway: bool) -> dict:
    """Environment of converter children. Convert-anyway is never inherited by accident: a delivery that did not ask for it
    (every visitor import) strips DIOCLE_CONVERT_ANYWAY, so the engine's own environment cannot switch it on for strangers."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if not convert_anyway:
        env.pop("DIOCLE_CONVERT_ANYWAY", None)
    return env


def convert(sample_dir: Path, on_start=lambda run_id: None, flags: list[str] | None = None,
            convert_anyway: bool = False) -> str | None:
    """Run the converter's translate + repair + certify, streaming its output; returns the run id."""
    proc = subprocess.Popen([str(SERVICES / "converter/.venv/bin/python"), "-m", "diocle_converter", "run", str(sample_dir),
                             *(flags or [])],
                            cwd=SERVICES / "converter", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=child_env(convert_anyway))
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


def _pr_body(report: dict, delivered: list[tuple[dict, dict]], skipped: list[str], others: list[dict] | None = None,
             build: dict | None = None) -> str:
    """others: convert-anyway programs that are NOT certified, each {name, assurance, reason, run}. They are listed under their
    own headings, with a sentence saying what was and was not shown; nothing in this section says "certified" of them."""
    src = report["source"]
    others = others or []
    lines = [
        f"Diocle migrated [{src['location'].split('github.com/')[-1]}@{src['commit'][:12]}]({src['location']}/tree/{src['commit']}) "
        + ("and certified each program in the first table against the original COBOL compiled with GnuCOBOL."
           if delivered else "in convert-anyway mode. No program below is certified.")
        + ("" if not others else " Programs under the other headings are NOT certified; read their sections."), "",
    ]
    if delivered:
        lines += ["## Certified", "", "| Program | Before | Held-out certification | Agent | Est. cost |", "|---|---|---|---|---|"]
    for run, cert in delivered:
        before = f"{run['before']['passed']}/{run['before']['total']}" if run.get("before") else "n/a"
        v, a = cert["verification"], cert["agent"]
        lines.append(f"| `{cert['program']}` | {before} | **{v['passed']}/{v['total']}** match, stdout "
                     f"{'matches' if v['stdoutMatch'] else 'differs'} | {a['modelCalls']} calls, {a['rounds']} round(s), "
                     f"{a['memoryLessonsUsed']} lessons from memory | {_usd(a['estimatedCostUsd'])} |")
    repaired = [o for o in others if o["assurance"] == "certified-against-repaired-cobol"]
    unverified = [o for o in others if o["assurance"] == "compiled-unverified"]
    failed = [o for o in others if o["assurance"] == "failed"]
    if repaired:
        lines += ["", "## Verified against repaired COBOL (not certified against the original)", ""]
        lines += [f"- `{o['name']}`: {o['reason']}" for o in repaired]
        lines += ["", "The patch and the diagnostics it fixed are in `not-certified/<PROGRAM>/assurance.json`."]
    if unverified:
        lines += ["", "## Compiled, NOT verified", ""]
        lines += [f"- `{o['name']}`: {o['reason']}" for o in unverified]
        lines += ["", "These are under `not-certified/<PROGRAM>/`, with no certificate. They were compiled with javac and never run by Diocle."]
    if failed:
        lines += ["", "## Failed (not delivered)", ""] + [f"- `{o['name']}`: {o['reason']}" for o in failed]
    if skipped:
        lines += ["", "**Not delivered** (not certified or not convertible): " + ", ".join(f"`{s}`" for s in skipped)]
    lines += build_section(build, len(delivered))
    lines += ["", *(["Each `programs/<PROGRAM>/certificate.json` pins the legacy commit and the verifier. "
                    "The **reverify** check re-runs both sides on fresh inputs from a seed Diocle never used, "
                    "so this PR does not ask you to trust Diocle's own result."] if delivered else []), "",
              ("Converted by Meta Muse Spark and certified by [Diocle](https://github.com/Nivetha200111/Diocle). "
               if delivered else
               "Converted by Meta Muse models with [Diocle](https://github.com/Nivetha200111/Diocle); nothing here is certified. ")
              + "Estimated costs use list prices."]
    return "\n".join(lines)


def _other_programs(report: dict, run_ids: dict[str, str]) -> list[dict]:
    """Programs of a convert-anyway delivery that finished with a label other than certified (read from their run records)."""
    out = []
    for program in report["programs"]:
        run = get_run(run_ids[program["name"]]) if program["name"] in run_ids else None
        if run and not run["certified"] and run.get("assurance") in ("certified-against-repaired-cobol", "compiled-unverified", "failed"):
            out.append({"name": program["name"], "assurance": run["assurance"], "run": run, "program": program,
                        "reason": run.get("assuranceReason") or run.get("error") or "no reason recorded"})
    return out


def unverified_sentence(assurance: str, reason: str) -> str:
    """The one sentence shown for a program that is not certified; it never says certified of the program."""
    if assurance == "compiled-unverified":
        return f"Java compiles; a developer must review it; the differential test could not run because {reason}"
    return reason


def deliver(report: dict, samples: Path, run_ids: dict[str, str], target_url: str, dry_run: bool,
            progress: Progress | None = None, onto: str | None = None, create: dict | None = None,
            domain_classes: Path | None = None) -> str:
    """domain_classes: EXPERIMENTAL, local only: the customer's own classes, put on the classpath of the build check.
    create: a plan_create() result. The repository is created here, after everything is certified, so a delivery with
    nothing to deliver creates nothing. If a later step fails, the repository stays (never deleted automatically)."""
    created: list[str] = []
    try:
        return _deliver(report, samples, run_ids, target_url, dry_run, progress, onto, create, created, domain_classes)
    except BaseException as e:
        if not created:
            raise
        detail = _gh_error(e) if isinstance(e, subprocess.CalledProcessError) else (str(e) or type(e).__name__)
        raise SystemExit(f"{create['full']} was created ({create['visibility']}) and is still there; a later step failed "
                         f"after: {', '.join(created)}. Failure: {detail[:200]}. Nothing was deleted. "
                         f"To remove it yourself: gh repo delete {create['full']} --yes") from e


def _deliver(report: dict, samples: Path, run_ids: dict[str, str], target_url: str, dry_run: bool,
             progress: Progress | None, onto: str | None, create: dict | None, created: list[str],
             domain_classes: Path | None = None) -> str:
    diocle_commit = _sh(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"]).stdout.strip()
    pushed = _sh(["git", "-C", str(REPO_ROOT), "branch", "-r", "--contains", diocle_commit]).stdout.strip()
    if not pushed and not dry_run:
        raise SystemExit("Push Diocle first: CI installs the verifier from the commit named in each certificate.")
    delivered, skipped = [], []
    with tempfile.TemporaryDirectory(prefix="diocle-deliver-") as tmp:
        repo = Path(tmp) / "target"
        if onto and not re.fullmatch(r"[A-Za-z0-9._/-]+", onto):
            raise SystemExit(f"bad branch name {onto!r}")
        if create:  # decide before creating anything: a delivery with nothing to deliver must not leave an empty repository
            ready = [n for n in (p["name"] for p in report["programs"]) if n in run_ids
                     and (get_run(run_ids[n]) or {}).get("certified") and (get_run(run_ids[n]) or {}).get("after")]
            if not ready and not any(o["assurance"] != "failed" for o in _other_programs(report, run_ids)):
                raise SystemExit(f"Nothing certified to deliver (skipped: {', '.join(p['name'] for p in report['programs'])}); no repository was created")
        if create and dry_run:  # nothing exists yet: build the delivery in an empty local repository
            _sh(["git", "init", "-q", str(repo)])
        else:
            if create:
                create_repository(create)
                created.append("repository created")
                if progress:
                    progress.update(targetCreated=True)
            for attempt in range(4 if create else 1):  # a new repository can take a moment to be cloneable
                try:
                    _sh(["git", "clone", "-q", "--depth", "1", *(["--branch", onto] if onto else []), "--",
                         f"https://github.com/{target_repo(target_url)}.git", str(repo)])
                    break
                except subprocess.CalledProcessError:
                    if attempt == 3:
                        raise
                    shutil.rmtree(repo, ignore_errors=True)
                    time.sleep(2 * (attempt + 1))
            if create:
                created.append("cloned")
        branch = onto or f"diocle/{report['source']['commit'][:12]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        if not onto:
            _sh(["git", "-C", str(repo), "checkout", "-q", "-b", branch])
        others = _other_programs(report, run_ids)
        for o in others:
            if o["assurance"] == "failed":
                continue
            dest = repo / "not-certified" / o["name"]
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(REPO_ROOT / "runs" / o["run"]["id"] / "java", dest / "java")
            repair = o["run"].get("cobolRepair")
            (dest / "assurance.json").write_text(json.dumps({
                "program": o["name"], "assurance": o["assurance"], "reason": o["reason"],
                "statement": unverified_sentence(o["assurance"], o["reason"]),
                "legacy": {"repository": report["source"]["location"], "commit": report["source"]["commit"], "path": o["program"]["path"]},
                "cobolRepair": repair, "agent": {"runId": o["run"]["id"], "model": o["run"]["model"],
                                                 "estimatedCostUsd": o["run"]["efficiency"]["estimatedCostUsd"]},
                "issuedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2) + "\n")
            if repair:
                (dest / "cobol-repair.diff").write_text(repair["diff"])
        for program in report["programs"]:
            run = get_run(run_ids[program["name"]]) if program["name"] in run_ids else None
            if not run or not run["certified"] or not run.get("after"):
                if any(o["name"] == program["name"] for o in others):
                    continue  # listed under its own heading, never as "not certified" noise
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
        if not delivered and not any(o["assurance"] != "failed" for o in others):
            raise SystemExit(f"Nothing certified to deliver (skipped: {', '.join(skipped)})")
        build = run_build_check(repo, delivered, samples, report, domain_classes) if delivered else None
        if progress and delivered:
            progress.update(buildCheck=build_summary(build))
        body = _pr_body(report, delivered, skipped, others, build)
        if create:
            (repo / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (repo / ".github" / "workflows" / "reverify.yml").write_text(reverify_workflow(report["source"]["location"], diocle_commit))
            body += ("\n\nThis repository was created by Diocle for this migration. This pull request adds "
                     "`.github/workflows/reverify.yml`, the CI that re-verifies each program; the pushing token needs the "
                     "`workflow` scope for that file.")
        if dry_run:
            print(body)
            if create:
                print("\nDRY RUN: nothing was created, cloned or pushed. Planned:")
                print("  " + " ".join(shlex.quote(a) for a in create["command"]))
                print(f"  then: clone {create['url']}, branch diocle/<commit>-<time>, commit programs/ and .github/workflows/reverify.yml, "
                      f"push, and `gh pr create --repo {create['full']}` into its default branch")
                for note in create["notes"]:
                    print(f"  not checked: {note}")
            return str(repo)
        git = ["git", "-C", str(repo), "-c", "user.name=Diocle", "-c", "user.email=diocle@users.noreply.github.com"]
        _sh(git + ["add", "-A"])
        if (repo / "build").is_dir():  # a target's own .gitignore (the Node template ignores build/) must not drop the report
            _sh(git + ["add", "-f", "build"])
        models = sorted({c["agent"]["model"] or "unknown model" for _, c in delivered})
        extra = f" and {len([o for o in others if o['assurance'] != 'failed'])} NOT-certified program(s) under not-certified/" if others else ""
        _sh(git + ["commit", "-q", "-m", f"Deliver {len(delivered)} certified program(s){extra} from {report['source']['commit'][:12]}",
                   "-m", f"Converted by {', '.join(models) or 'Meta Muse models'}. "
                   + (f"{len(delivered)} program(s) certified against GnuCOBOL by Diocle. " if delivered else "Nothing is certified. ")
                   + ("Programs under not-certified/ are NOT certified (compiled only, or verified against repaired COBOL)." if others else "")])
        if create:
            created.append("committed")
        _sh(git + ["push", "-q", "-u", "origin", branch])
        if create:
            created.append("pushed")
        if onto:  # an existing branch: its pull request (if any) picks up the new commit
            return f"pushed to {branch}"
        title = (f"Diocle: {', '.join(c['program'] for _, c in delivered)} converted and certified"
                 + (f"; {len(others)} more NOT certified" if others else "")) if delivered else \
            f"Diocle: {len(others)} program(s) converted, NONE certified (convert anyway)"
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


class Spend:
    """REPO_MAX_USD: one hard dollar cap across all programs of a convert-anyway delivery (rule 10), on top of each run's
    own call caps. What is left is passed to every run as --max-usd, so even the program being converted cannot overshoot
    by more than one model call. A program whose cost is unknown (a model without a price) makes the total unknown, and
    an unknown total stops the delivery: fail closed."""

    def __init__(self, cap: float):
        self.cap, self.spent = cap, 0.0

    @classmethod
    def from_env(cls) -> "Spend":
        try:
            return cls(max(0.0, float(os.environ.get("REPO_MAX_USD", "") or "1.00")))
        except ValueError:
            return cls(1.00)

    def add(self, cost: float | None) -> None:
        self.spent = None if cost is None or self.spent is None else round(self.spent + cost, 6)

    def remaining(self) -> float | None:
        return None if self.spent is None else self.cap - self.spent

    def reason(self) -> str:
        return (f"repo spend cap reached (REPO_MAX_USD ${self.cap:.2f}; "
                + ("spend unknown, a model has no price" if self.spent is None else f"${self.spent:.4f} spent") + ")")


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
    parser.add_argument("--create-target", metavar="NAME", help="create this new repository for the result and open the pull "
                        "request into it (private unless --target-public; refused if it already exists; not with a target URL or --onto)")
    parser.add_argument("--target-owner", help="owner of the repository --create-target creates (default: your gh login); allowlisted")
    parser.add_argument("--target-public", action="store_true", help="make the created repository public (default private)")
    parser.add_argument("--domain-classes", type=Path, help="EXPERIMENTAL, local only: a directory of .java files or a .jar of your own "
                        "classes. The whole-repository build check compiles the programs beside them (compile-time classpath, never "
                        "run), and the translator sees matching classes' public signatures. Not with --public.")
    parser.add_argument("--id", help="delivery id to use (the API passes one so the dashboard can follow it)")
    parser.add_argument("--convert-anyway", action="store_true",
                        help="never refuse (local or admin only): refused, uncompilable or unverifiable programs are still "
                             "translated and compile-checked and labelled compiled-unverified / failed; an original that "
                             "does not compile is patched first. REPO_MAX_USD (default 1.00) caps the whole delivery.")
    parser.add_argument("--public", action="store_true",
                        help="a visitor's import: needs the sandbox, visitor caps, no pull request, no swarm or breaker")
    args = parser.parse_args(argv)
    if args.public and args.domain_classes:
        parser.error("--domain-classes is not available to visitor imports (--public)")
    if args.public and args.convert_anyway:
        parser.error("--convert-anyway is not available to visitor imports (--public)")
    if args.create_target is None and (args.target_owner or args.target_public):
        parser.error("--target-owner and --target-public need --create-target")
    if args.create_target is not None and (args.target_url or args.onto or args.public):
        parser.error("--create-target cannot be combined with a target URL, --onto or --public")
    create = plan = None
    if args.create_target is not None:
        create = validate_create_target(args.create_target, args.target_owner, "public" if args.target_public else "private")
        plan = plan_create(create, args.legacy_url, args.dry_run)  # fail fast; creates nothing
        args.target_url = plan["url"]
    # DIOCLE_CONVERT_ANYWAY=1 in the environment counts for local runs only; a visitor import never reads it.
    convert_anyway = args.convert_anyway or (not args.public and os.environ.get("DIOCLE_CONVERT_ANYWAY") == "1")
    if convert_anyway:
        args.parallel = False  # sequential, so REPO_MAX_USD is exact (no program starts while another may still spend)
    if args.public:
        if not os.environ.get("DIOCLE_SANDBOX_URL"):
            parser.error("--public needs DIOCLE_SANDBOX_URL: imported code must never run beside the secrets")
        args.target_url, args.parallel, args.breaker, args.runs = None, False, False, []

    target = args.target_url.rstrip("/").removesuffix(".git") if args.target_url else None
    progress = Progress(args.legacy_url, target, args.id, args.public)
    if create:
        progress.update(createTarget=create, targetCreated=False)
    spend = Spend.from_env() if convert_anyway else None
    if spend:
        progress.state.update(convertAnyway=True, repoMaxUsd=spend.cap, spentUsd=0.0)
        progress.save()
    print(f"delivery {progress.id}" + (f" (convert anyway, REPO_MAX_USD ${spend.cap:.2f})" if spend else ""), flush=True)
    try:
        if target:
            target_repo(target)  # fail fast on a bad or disallowed target (a planned one passes the same allowlist)
        report, samples = analyze(args.legacy_url, progress.id, convert_anyway)
        wanted = set(args.programs.split(",")) if args.programs else None
        report["programs"] = [p for p in report["programs"] if (p["convertible"] or convert_anyway) and (wanted is None or p["name"] in wanted)]
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
                 + (["--memory-read-only"] if args.public else [])  # strangers' code never shapes later runs
                 + (["--convert-anyway"] if convert_anyway else [])
                 + (["--domain-classes", str(args.domain_classes)] if args.domain_classes else []))
        lock = threading.Lock()

        def work(program: dict) -> None:
            entry = progress.program(program["name"])
            with lock:
                entry["status"] = "converting"
                progress.save()

            if spend:
                left = spend.remaining()
                if left is None or left <= 0:
                    with lock:
                        entry.update(status="skipped", reason=spend.reason())
                        progress.save()
                    print(f"{program['name']}: skipped, {spend.reason()}", flush=True)
                    return

            def started(run_id: str) -> None:
                if args.public:  # a visitor's run: labelled, and never offered for public re-verification
                    (REPO_ROOT / "runs" / run_id).mkdir(parents=True, exist_ok=True)
                    (REPO_ROOT / "runs" / run_id / "visitor").write_text(progress.id + "\n")
                with lock:
                    entry["runId"] = run_id
                    progress.save()

            granted = spend.remaining() if spend else None
            run_id = convert(samples / program["name"].lower(), started,
                             flags + (["--max-usd", f"{granted:.6f}"] if spend else []), convert_anyway)
            run = get_run(run_id) if run_id else None
            with lock:
                entry.update(runId=run_id, status="certified" if run and run["certified"] else "not-certified")
                if spend:
                    cost = (run or {}).get("efficiency", {}).get("estimatedCostUsd")
                    # No run record at all (the converter died): its cost is unknown, so charge what it was allowed to spend
                    spend.add(cost if run else granted)
                    entry.update(assurance=(run or {}).get("assurance") or ("failed" if not run else None),
                                 costUsd=cost,
                                 reason=((run or {}).get("assuranceReason") or (run or {}).get("error")
                                         or (None if run else "the converter stopped before a run was recorded")))
                    progress.state.update(spentUsd=spend.spent)
                    print(f"{program['name']}: {entry['assurance']}; cost "
                          f"{'n/a' if cost is None else f'${cost:.4f}'}; delivery total "
                          f"{'n/a' if spend.spent is None else f'${spend.spent:.4f}'} of ${spend.cap:.2f}", flush=True)
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
            print(deliver(report, samples, run_ids, target, args.dry_run, progress, args.onto, plan, args.domain_classes))
        progress.update(stage="done", finishedAt=_now())
    except BaseException as e:
        progress.update(stage="failed", error=str(e)[:500] or type(e).__name__, finishedAt=_now())
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
