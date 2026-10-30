#!/usr/bin/env python3
"""Diocle MCP server for Muse Code (stdio, JSON-RPC 2.0, Python standard library only).

A LOCAL server you run for your own coding agent. It is not an official Meta integration.

Tools (all read-only or cheap, except diocle_convert which is gated):
  diocle_analyze          analyze a COBOL file or directory inside the repo (free)
  diocle_verify_stored    re-verify a sample's checked-in certified Java with GnuCOBOL (free, no model)
  diocle_live_run         read a run summary from the public Diocle site (read-only GET)
  diocle_explain          plain-English summary of a stored run record (no model)
  diocle_coverage         what converts and what is refused, with reasons (reads the README)
  diocle_mutation_report  read a stored mutation report (no model, produces nothing)
  diocle_convert          REAL model spend; disabled unless DIOCLE_MCP_ALLOW_CONVERT=1, hard cap USD 0.25

Security: paths are confined to the repo root (resolved, symlink escapes rejected), names are regex-validated,
subprocesses use argv arrays (no shell), outputs and runtimes are capped, secrets are never accepted as arguments
and are scrubbed from output. Nothing here writes outside a temp directory, except diocle_convert, whose converter
writes its run record to the repo's gitignored runs/ directory.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SERVER_NAME = "diocle"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]

MAX_OUTPUT = 16_000          # bytes of text returned per tool call
MAX_RESOURCE = 60_000
MAX_CONVERT_USD = 0.25
DEFAULT_CONVERT_USD = 0.10
LIVE_BASE = "https://diocle.vercel.app/api"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
RUN_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class ToolError(Exception):
    """A user-facing failure; the message is returned to the agent as the tool result with isError."""


# ---------------------------------------------------------------- repo, environment, paths

def repo_root() -> Path:
    """DIOCLE_REPO, else repo.txt next to this file (written by install.sh), else three levels up (in-repo use)."""
    env = os.environ.get("DIOCLE_REPO")
    if env:
        return Path(env).expanduser().resolve()
    marker = Path(__file__).resolve().parent / "repo.txt"
    if marker.is_file():
        return Path(marker.read_text().strip()).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def confine(raw: str, root: Path | None = None) -> Path:
    """Resolve a path (relative to the repo root) and require it to stay inside the repo root, symlinks included."""
    root = (root or repo_root()).resolve()
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw or len(raw) > 400:
        raise ToolError("path must be a non-empty string")
    p = Path(raw).expanduser()
    p = (p if p.is_absolute() else root / p).resolve()
    if p != root and root not in p.parents:
        raise ToolError("path is outside the Diocle repository")
    return p


def reject_symlink_escapes(directory: Path, root: Path, limit: int = 5000) -> None:
    n = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for name in dirnames + filenames:
            n += 1
            if n > limit:
                raise ToolError("directory has too many entries")
            full = Path(dirpath) / name
            if full.is_symlink():
                target = full.resolve()
                if target != root and root not in target.parents:
                    raise ToolError("a symbolic link inside the directory points outside the repository")


def sample_dir(name: str) -> Path:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ToolError("sample must be a name made of letters, digits, - or _")
    d = confine(f"samples/{name}")
    if not d.is_dir():
        raise ToolError(f"no such sample: samples/{name}")
    return d


def python_exe(root: Path) -> str:
    env = os.environ.get("DIOCLE_PYTHON")
    if env:
        return env
    for rel in ("services/converter/.venv/bin/python", "services/verifier/.venv/bin/python",
                "services/analyzer/.venv/bin/python"):
        if (root / rel).exists():
            return str(root / rel)
    return sys.executable


SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)
PASS_THROUGH = re.compile(r"^(META_MODEL_|MODEL_|GUARD_MODEL_|REPO_MAX_USD$|OPEN_MODEL_|CROSSCHECK_)")


def child_env(root: Path, with_model: bool = False) -> dict:
    """A small environment for subprocesses: no inherited secrets unless the converter needs the model settings."""
    path = os.environ.get("PATH", "/usr/bin:/bin")
    extra = [p for p in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/homebrew/opt/openjdk@21/bin") if Path(p).is_dir()]
    env = {"PATH": os.pathsep.join(extra + [path]), "LANG": os.environ.get("LANG", "en_US.UTF-8"),
           "HOME": os.environ.get("HOME", ""), "TMPDIR": os.environ.get("TMPDIR", tempfile.gettempdir()),
           "PYTHONSAFEPATH": "1",
           "PYTHONPATH": os.pathsep.join(str(root / "services" / s) for s in ("analyzer", "verifier", "converter"))}
    for k in ("JAVA_HOME", "COB_CONFIG_DIR", "COB_COPY_DIR", "COB_LIBRARY_PATH"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    if with_model:
        for k, v in os.environ.items():
            if PASS_THROUGH.match(k):
                env[k] = v
    return env


def scrub(text: str) -> str:
    for k, v in os.environ.items():
        if SECRET_NAME.search(k) and len(v) >= 8:
            text = text.replace(v, "[redacted]")
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}", r"\1[redacted]", text)
    text = re.sub(r"\b(sk|fw|ms|meta)[-_][A-Za-z0-9_-]{16,}", "[redacted]", text)
    return text


def cap(text: str, limit: int = MAX_OUTPUT) -> str:
    text = scrub(text)
    raw = text.encode("utf-8", "replace")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore") + f"\n[... output truncated at {limit} bytes]"


def run_argv(argv: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             shell=False, start_new_session=True)
    except OSError as e:
        raise ToolError(f"could not start {Path(argv[0]).name}: {e.strerror or 'error'}")
    try:
        out, errs = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)  # the whole group: cobc, java and the converter's own children
        except (ProcessLookupError, PermissionError):
            p.kill()
        p.communicate()
        raise ToolError(f"timed out after {timeout} s")
    return p.returncode, (out or "") + (("\n" + errs) if errs else "")


def dump(obj) -> str:
    return cap(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


# ---------------------------------------------------------------- tools

def tool_analyze(args: dict) -> str:
    root = repo_root()
    target = confine(args.get("path", ""), root)
    only = None
    if target.is_file():
        if target.suffix.lower() not in (".cbl", ".cob", ".cobol", ".cpy"):
            raise ToolError("a file must be a COBOL source (.cbl, .cob, .cobol) or copybook")
        only, target = target.relative_to(root), target.parent
    if not target.is_dir():
        raise ToolError("path does not exist")
    reject_symlink_escapes(target, root)
    with tempfile.TemporaryDirectory(prefix="diocle-mcp-") as tmp:
        out = Path(tmp) / "analysis.json"
        rc, text = run_argv([python_exe(root), "-P", "-m", "diocle_analyzer", str(target), "--out", str(out)],
                            root / "services" / "analyzer", child_env(root), 90)
        if rc != 0 or not out.exists():
            raise ToolError("analyzer failed:\n" + cap(text, 2000))
        report = json.loads(out.read_text())
    progs = []
    for p in report["programs"]:
        if only is not None and Path(p["path"]).name != only.name:
            continue
        files = []
        for f in p["files"]:
            fields = [x for x in ((f.get("layout") or {}).get("fields") or [])]
            files.append({"dd": f["dd"], "direction": f["direction"], "organization": f.get("organization"),
                          "copybook": f.get("copybook"), "fieldCount": len(fields),
                          "fields": [{k: x[k] for k in ("name", "kind", "length", "digits", "scale", "signed", "usage")
                                      if k in x} for x in fields[:40]]})
        progs.append({"program": p["name"], "path": p["path"], "convertible": p["convertible"],
                      "refusalReason": p.get("notConvertibleReason"), "copybooks": p["copybooks"],
                      "callsModules": p.get("modules"), "files": files})
    findings = [f for f in report["findings"] if only is None or any(f["program"] == q["program"] for q in progs)]
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return dump({"programs": progs, "riskFindings": findings[:30], "findingsTotal": len(findings),
                 "dependencyEdges": len(report["dependencies"]), "jobs": len(report.get("jobs") or []),
                 "note": "Static analysis only. 'convertible' means Diocle can try to verify a conversion, not that one exists."})


def tool_verify_stored(args: dict) -> str:
    root = repo_root()
    sample = sample_dir(args.get("sample", ""))
    java = sample / "certified-java"
    if not java.is_dir():
        raise ToolError(f"samples/{sample.name} has no certified-java directory; samples with one: "
                        + ", ".join(sorted(p.parent.name for p in (root / "samples").glob("*/certified-java"))))
    reject_symlink_escapes(sample, root)
    random_n = args.get("random", 1000)
    if not isinstance(random_n, int) or isinstance(random_n, bool) or not 10 <= random_n <= 2000:
        raise ToolError("random must be an integer between 10 and 2000")
    with tempfile.TemporaryDirectory(prefix="diocle-mcp-") as tmp:
        out = Path(tmp) / "report.json"
        rc, text = run_argv([python_exe(root), "-P", "-m", "diocle_verifier", str(sample), "--java-dir", str(java),
                             "--random", str(random_n), "--seed", "4243", "--out", str(out)],
                            root / "services" / "verifier", child_env(root), 240)
        if not out.exists():
            raise ToolError("verifier produced no report (are GnuCOBOL 3.2 and JDK 21 installed?):\n" + cap(text, 2000))
        rep = json.loads(out.read_text())
    s, runs = rep["summary"], rep["runs"]
    bad = [r for r in rep["results"] if not r.get("match")][:3]
    return dump({"sample": sample.name, "total": s["total"], "passed": s["passed"], "failed": s["failed"],
                 "stdoutMatch": runs.get("stdoutMatch"), "exitCodeMatch": runs.get("exitCodeMatch"),
                 "originalCompiled": runs["original"].get("compiled"), "javaCompiled": runs["converted"].get("compiled"),
                 "seed": 4243, "failingExamples": bad,
                 "honestly": (f"The checked-in Java matched the GnuCOBOL original on {s['passed']} of {s['total']} generated "
                              "inputs (tested inputs, not a proof of equivalence). No model was called.")})


class _Refuse(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # a redirect could leave the Diocle API: treat it as an error
        return None


_NO_REDIRECT = urllib.request.build_opener(_Refuse)


def _get_json(url: str) -> object:
    if not url.startswith(LIVE_BASE) and not (os.environ.get("DIOCLE_API_BASE") and url.startswith(os.environ["DIOCLE_API_BASE"])):
        raise ToolError("refusing to fetch outside the Diocle API")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "diocle-muse-code/0.1"})
    try:
        with _NO_REDIRECT.open(req, timeout=15) as r:
            raw = r.read(400_000)
    except urllib.error.HTTPError as e:
        raise ToolError(f"the Diocle API answered HTTP {e.code}")
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ToolError("could not reach the Diocle API")
    try:
        return json.loads(raw)
    except ValueError:
        raise ToolError("the Diocle API did not return JSON")


def _api_base() -> str:
    base = os.environ.get("DIOCLE_API_BASE", "")
    if base and not re.match(r"^http://127\.0\.0\.1:\d+(/.*)?$", base):
        raise ToolError("DIOCLE_API_BASE may only point at 127.0.0.1")
    return base.rstrip("/") or LIVE_BASE


def tool_live_run(args: dict) -> str:
    run_id = args.get("run_id", "")
    base = _api_base()
    if not run_id:
        runs = _get_json(f"{base}/runs")
        rows = [{k: r.get(k) for k in ("id", "program", "certified", "status", "createdAt", "visitor")}
                for r in runs if isinstance(r, dict)][:40]
        return dump({"runs": rows, "hint": "call again with run_id to read one"})
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
        raise ToolError("run_id must be lowercase letters, digits and - (for example chqclr-20261028-214355)")
    r = _get_json(f"{base}/runs/{run_id}")
    if not isinstance(r, dict):
        raise ToolError("unexpected API answer")
    after, usage = r.get("after") or {}, r.get("usage") or {}
    return dump({"id": r.get("id"), "program": r.get("program"), "status": r.get("status"), "certified": r.get("certified"),
                 "model": r.get("model"), "createdAt": r.get("createdAt"), "javaOrigin": r.get("javaOrigin"),
                 "rounds": r.get("rounds"), "before": r.get("before"), "after": after,
                 "breaker": {k: (r.get("breaker") or {}).get(k) for k in ("rounds", "tried", "broke", "fixed")} if r.get("breaker") else None,
                 "modelCalls": usage.get("calls"), "estimatedCostUsd": usage.get("estimatedCostUsd"),
                 "link": f"https://diocle.vercel.app/runs/{run_id}",
                 "source": "public Diocle site, read-only GET",
                 "honestly": "Matched on the tested inputs (GnuCOBOL as the oracle); not proven equivalent."})


def _run_dir(arg: str) -> Path:
    root = repo_root()
    p = confine(arg, root)
    runs = (root / "runs").resolve()
    if runs not in p.parents or not p.is_dir():
        raise ToolError("run must be a directory under the repository's runs/ folder (for example runs/interest-accrual-20261030-091344)")
    if not RUN_DIR_RE.match(p.name):
        raise ToolError("unexpected run directory name")
    return p


def _readj(path: Path) -> dict | None:
    try:
        if path.stat().st_size > 2_000_000:
            raise ToolError(f"{path.name} is too large")
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError:
        raise ToolError(f"{path.name} is not valid JSON")


def explain_run(run: dict, report: dict | None, name: str) -> str:
    lines = [f"Run {name}: program {run.get('program')} ({run.get('command')}), status {run.get('status')}."]
    if run.get("certified"):
        lines.append("It is CERTIFIED: the Java matched the GnuCOBOL original on held-out generated inputs.")
    else:
        lines.append("It is NOT certified" + (f" ({run.get('error')})" if run.get("error") else "") + ".")
    for r in run.get("rounds") or []:
        s = r.get("summary") or {}
        lines.append(f"- Round {r.get('round')}: {s.get('passed')} of {s.get('total')} inputs matched"
                     f" (seed {r.get('seed')}), certified={r.get('certified')}.")
    if report:
        s = report.get("summary") or {}
        lines.append(f"Verification report: {s.get('passed')} of {s.get('total')} cases match; stdout match "
                     f"{(report.get('runs') or {}).get('stdoutMatch')}.")
    u = run.get("usage") or {}
    if u:
        lines.append(f"Model use: {u.get('calls')} calls, {u.get('inputTokens')} input and {u.get('outputTokens')} output tokens,"
                     f" estimated ${u.get('estimatedCostUsd')}.")
    if run.get("javaOrigin"):
        lines.append(f"Java origin: {run['javaOrigin']}.")
    t = (run.get("translation") or {}).get("notes")
    if t:
        lines.append("Translator notes: " + str(t)[:600])
    b = run.get("breaker")
    if b:
        lines.append(f"Breaker agent: {b.get('tried')} attack inputs tried, {b.get('broke')} broke the Java, fixed={b.get('fixed')}.")
    lines.append("Honest reading: this means the Java and the original agreed on the tested inputs; it is not a proof of "
                 "equivalence, and GnuCOBOL can differ from IBM COBOL in edge cases.")
    return "\n".join(lines)


def tool_explain(args: dict) -> str:
    d = _run_dir(args.get("run", ""))
    run = _readj(d / "run.json")
    if run is None:
        raise ToolError("no run.json in that directory")
    return cap(explain_run(run, _readj(d / "verification-report.json"), d.name))


def tool_mutation(args: dict) -> str:
    d = _run_dir(args.get("run", ""))
    m = _readj(d / "mutation-report.json")
    if m is None:
        return ("No mutation-report.json in that run. Diocle produces one with "
                "`python -m diocle_verifier mutate RUN_DIR` (local, no model) or the site's POST /runs/{id}/mutation; "
                "this tool only reads a stored one.")
    keep = {k: m.get(k) for k in ("program", "status", "reason", "seed", "counts", "inputs", "seconds", "notes") if k in m}
    surv = [{k: x.get(k) for k in ("operator", "location", "description", "original", "mutated")}
            for x in (m.get("mutants") or []) if isinstance(x, dict) and x.get("outcome") == "survived"][:8]
    return dump({"summary": keep, "survivorExamples": surv,
                 "honestly": "A survivor is a coverage question about the tests, not a verdict that the Java is wrong."})


def tool_coverage(args: dict) -> str:
    root = repo_root()
    text = (root / "README.md").read_text(errors="replace")
    m = re.search(r"^## Not supported yet\n(.*?)(?=^## )", text, re.S | re.M)
    items = []
    if m:
        for b in re.split(r"^- ", m.group(1), flags=re.M)[1:]:
            b = re.sub(r"\s+", " ", b).strip()
            items.append(b[:700] + (" ..." if len(b) > 700 else ""))
    samples = []
    for sj in sorted((root / "samples").glob("*/sample.json")):
        j = _readj(sj) or {}
        samples.append({"sample": sj.parent.name, "description": str(j.get("description", ""))[:160],
                        "storedCertifiedJava": (sj.parent / "certified-java").is_dir()})
    return dump({"refusedOrLimited": items,
                 "analyzerRefusals": "EXEC SQL outside the verified subset, CICS/DLI, INDEXED/RELATIVE outside ksds-subset-1, "
                                     "dynamic or external CALL, no output file and no DISPLAY (see refusedOrLimited for the full list).",
                 "samples": samples, "source": "README.md 'Not supported yet' and samples/*/sample.json"})


def allow_marker() -> Path:
    base = os.environ.get("DIOCLE_MCP_CONFIG_DIR") or os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "diocle-muse")
    return Path(base) / "allow-convert"


def convert_allowed() -> bool:
    """On only when the owner set DIOCLE_MCP_ALLOW_CONVERT=1, or created the allow-convert marker file (install.sh --allow-convert),
    because Muse Code starts plugin servers with a small fixed environment."""
    return os.environ.get("DIOCLE_MCP_ALLOW_CONVERT") == "1" or allow_marker().is_file()


def tool_convert(args: dict) -> str:
    if not convert_allowed():
        raise ToolError("diocle_convert is disabled. It spends real model money on the owner's Meta key. The owner can enable it "
                        "by setting DIOCLE_MCP_ALLOW_CONVERT=1 or running install.sh --allow-convert (see editors/muse-code/README.md). "
                        "Nothing was run. Ask the owner; do not try to work around this.")
    root = repo_root()
    sample = sample_dir(args.get("sample", ""))
    cap_usd = args.get("max_usd", DEFAULT_CONVERT_USD)
    if isinstance(cap_usd, bool) or not isinstance(cap_usd, (int, float)) or not 0 < cap_usd <= MAX_CONVERT_USD:
        raise ToolError(f"max_usd must be a number above 0 and at most {MAX_CONVERT_USD}")
    for k in args:
        if k not in ("sample", "max_usd"):
            raise ToolError(f"unknown argument {k!r} (a key is never an argument; it comes from the owner's environment or .env)")
    reject_symlink_escapes(sample, root)
    before = {p.name for p in (root / "runs").glob("*")} if (root / "runs").is_dir() else set()
    rc, text = run_argv([python_exe(root), "-P", "-m", "diocle_converter", "run", str(sample), "--no-memory",
                         "--max-usd", f"{cap_usd:.2f}"], root / "services" / "converter", child_env(root, with_model=True), 900)
    head = re.findall(r"^(?:CERTIFIED|NOT CERTIFIED|CERTIFIED AGAINST).*$", text, re.M)
    saved = re.findall(r"^run saved to (runs/[A-Za-z0-9_.-]+)", text, re.M)
    out: dict = {"exitCode": rc, "capUsd": cap_usd, "result": head[-1] if head else None}
    if saved:
        d = _run_dir(saved[-1])
        out["runDir"] = saved[-1]
        run = _readj(d / "run.json") or {}
        out["certified"] = bool(run.get("certified"))
        out["usage"] = {k: (run.get("usage") or {}).get(k) for k in ("calls", "inputTokens", "outputTokens", "estimatedCostUsd")}
        out["explanation"] = explain_run(run, _readj(d / "verification-report.json"), d.name)
        out["javaDir"] = f"{saved[-1]}/java"
    else:
        out["certified"] = False
        out["log"] = cap(text[-2500:], 2500)
    return dump(out)


NAME_SCHEMA = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"}
TOOLS = [
    {"name": "diocle_analyze", "fn": tool_analyze, "readOnly": True,
     "description": "Analyze COBOL (a file or directory inside the Diocle repo, for example samples/interest-accrual): programs, record "
                    "layouts from copybooks, files, legacy-arithmetic risk flags, and for refused programs the reason. Free, no model.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "repo-relative path"}},
                     "required": ["path"], "additionalProperties": False}},
    {"name": "diocle_verify_stored", "fn": tool_verify_stored, "readOnly": True,
     "description": "Re-verify a sample's checked-in certified Java against the original COBOL: GnuCOBOL compiles the original and "
                    "both run on the same generated inputs. Free, no model, a few seconds. Needs cobc 3.2 and JDK 21.",
     "inputSchema": {"type": "object", "properties": {"sample": NAME_SCHEMA, "random": {"type": "integer", "minimum": 10, "maximum": 2000}},
                     "required": ["sample"], "additionalProperties": False}},
    {"name": "diocle_live_run", "fn": tool_live_run, "readOnly": True,
     "description": "Read a run summary from the public Diocle site (read-only GET). Without run_id, lists recent runs.",
     "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"}},
                     "additionalProperties": False}},
    {"name": "diocle_explain", "fn": tool_explain, "readOnly": True,
     "description": "Plain-English summary of a stored run (runs/<id> in the repo) from run.json and its verification report. No model.",
     "inputSchema": {"type": "object", "properties": {"run": {"type": "string", "description": "repo-relative runs/<id>"}},
                     "required": ["run"], "additionalProperties": False}},
    {"name": "diocle_coverage", "fn": tool_coverage, "readOnly": True,
     "description": "What Diocle converts and what it refuses or limits, with reasons, plus the bundled synthetic samples.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "diocle_mutation_report", "fn": tool_mutation, "readOnly": True,
     "description": "Read a stored mutation-testing report (how strong the verification inputs are) from runs/<id>, if one exists.",
     "inputSchema": {"type": "object", "properties": {"run": {"type": "string"}}, "required": ["run"], "additionalProperties": False}},
    {"name": "diocle_convert", "fn": tool_convert, "readOnly": False,
     "description": "REAL MODEL SPEND on the owner's Meta key (typically USD 0.02 to 0.05). Converts samples/<sample> COBOL to Java with Muse "
                    "Spark and certifies it against GnuCOBOL. Disabled unless the owner enabled it; call it only after the user explicitly "
                    "agreed. Always capped (default USD 0.10, hard maximum 0.25). Never takes a key.",
     "inputSchema": {"type": "object", "properties": {"sample": NAME_SCHEMA,
                                                     "max_usd": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_CONVERT_USD}},
                     "required": ["sample"], "additionalProperties": False}},
]
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}

PROMPTS = {
    "certify-a-cobol-program": {
        "description": "Convert a COBOL sample to Java and certify it against GnuCOBOL, step by step and with consent.",
        "arguments": [{"name": "sample", "description": "sample name under samples/", "required": True}],
        "text": ("Certify the COBOL program in samples/{sample} with Diocle. 1) diocle_analyze samples/{sample} and report layouts, risk "
                 "flags, and any refusal with its reason. 2) If it is refused, explain why via diocle_coverage and stop. 3) Tell me what "
                 "diocle_convert will cost (cap and typical cost) and ask for my explicit OK before calling it. 4) After conversion, "
                 "diocle_explain the run. 5) Report honestly: matched on the tested inputs, not proven equivalent."),
    },
    "explain-a-run": {
        "description": "Explain a stored or live Diocle run in plain English.",
        "arguments": [{"name": "run", "description": "runs/<id> in the repo, or a live run id", "required": True}],
        "text": "Explain the Diocle run {run}: use diocle_explain for a repo path or diocle_live_run for a live id. State what was tested, "
                "the result, the cost, and the honest limit (tested inputs, not a proof).",
    },
}


def sample_resources() -> list[dict]:
    root = repo_root()
    out = []
    for sj in sorted((root / "samples").glob("*/sample.json")):
        for sub, pats in (("src", ("*.cbl", "*.cob")), ("copybooks", ("*.cpy",))):
            for pat in pats:
                for f in sorted((sj.parent / sub).glob(pat)):
                    out.append({"uri": f"diocle://samples/{sj.parent.name}/{sub}/{f.name}", "name": f"{sj.parent.name}/{sub}/{f.name}",
                                "mimeType": "text/plain", "description": "synthetic COBOL (read-only)"})
    return out


def read_resource(uri: str) -> dict:
    if not isinstance(uri, str):
        raise ToolError("unknown resource")
    m = re.match(r"^diocle://samples/([A-Za-z0-9][A-Za-z0-9_-]{0,63})/(src|copybooks)/([A-Za-z0-9][A-Za-z0-9_.-]{0,63})$", uri or "")
    if not m or m.group(3).rsplit(".", 1)[-1].lower() not in ("cbl", "cob", "cpy"):
        raise ToolError("unknown resource")
    samples_root = (repo_root() / "samples").resolve()
    raw = samples_root / m.group(1) / m.group(2) / m.group(3)
    f = confine(str(raw))
    if raw.is_symlink() or samples_root not in f.parents or not f.is_file():
        raise ToolError("unknown resource")
    return {"uri": uri, "mimeType": "text/plain", "text": cap(f.read_text(errors="replace"), MAX_RESOURCE)}


# ---------------------------------------------------------------- JSON-RPC

def ok(i, result):
    return {"jsonrpc": "2.0", "id": i, "result": result}


def err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


def public_tool(t: dict) -> dict:
    d = {k: t[k] for k in ("name", "description", "inputSchema")}
    d["annotations"] = {"readOnlyHint": t["readOnly"], "destructiveHint": False, "openWorldHint": t["name"] == "diocle_live_run"}
    return d


def handle(msg: dict) -> dict | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return err(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    method, i, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:
        return None  # notification
    if not isinstance(params, dict):
        return err(i, -32602, "params must be an object")
    if method == "initialize":
        want = params.get("protocolVersion")
        return ok(i, {"protocolVersion": want if want in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                      "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}, "prompts": {"listChanged": False}},
                      "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                      "instructions": "Diocle checks COBOL-to-Java conversions against GnuCOBOL. Report results as 'matched on the tested "
                                      "inputs', never 'proven equivalent'. diocle_convert spends real money: only with the user's explicit OK."})
    if method == "ping":
        return ok(i, {})
    if method == "tools/list":
        return ok(i, {"tools": [public_tool(t) for t in TOOLS]})
    if method == "tools/call":
        tname = params.get("name")
        t = TOOL_BY_NAME.get(tname) if isinstance(tname, str) else None
        if not t:
            return err(i, -32602, "unknown tool")
        a = params.get("arguments") or {}
        if not isinstance(a, dict):
            return err(i, -32602, "arguments must be an object")
        try:
            text = t["fn"](a)
            return ok(i, {"content": [{"type": "text", "text": text}], "isError": False})
        except ToolError as e:
            return ok(i, {"content": [{"type": "text", "text": cap(str(e), 3000)}], "isError": True})
        except Exception as e:  # never leak internals or secrets
            return ok(i, {"content": [{"type": "text", "text": f"internal error ({type(e).__name__})"}], "isError": True})
    if method == "resources/list":
        return ok(i, {"resources": sample_resources()})
    if method == "resources/templates/list":
        return ok(i, {"resourceTemplates": []})
    if method == "resources/read":
        try:
            return ok(i, {"contents": [read_resource(params.get("uri", ""))]})
        except ToolError as e:
            return err(i, -32002, str(e))
    if method == "prompts/list":
        return ok(i, {"prompts": [{"name": n, "description": p["description"], "arguments": p["arguments"]} for n, p in PROMPTS.items()]})
    if method == "prompts/get":
        pname = params.get("name")
        p = PROMPTS.get(pname) if isinstance(pname, str) else None
        if not p:
            return err(i, -32602, "unknown prompt")
        a = params.get("arguments") or {}
        if not isinstance(a, dict):
            return err(i, -32602, "arguments must be an object")
        vals = {x["name"]: str(a.get(x["name"], "")) for x in p["arguments"]}
        if not all(re.match(r"^[A-Za-z0-9_/.-]{1,96}$", v) for v in vals.values()):
            return err(i, -32602, "invalid prompt argument")
        return ok(i, {"description": p["description"], "messages": [{"role": "user", "content": {"type": "text", "text": p["text"].format(**vals)}}]})
    return err(i, -32601, "method not found")


MAX_LINE = 1_000_000


def main() -> int:
    while True:
        line = sys.stdin.readline(MAX_LINE)
        if not line:
            return 0
        if len(line) >= MAX_LINE and not line.endswith("\n"):
            while True:  # drain the rest of the oversized line without holding it
                rest = sys.stdin.readline(MAX_LINE)
                if not rest or rest.endswith("\n"):
                    break
            resp = err(None, -32600, "message too large")
        else:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                resp = err(None, -32700, "parse error")
            else:
                try:
                    resp = handle(msg)
                except Exception:  # never die on a bad request, never leak detail
                    resp = err(msg.get("id") if isinstance(msg, dict) and isinstance(msg.get("id"), (int, str)) else None, -32603, "internal error")
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
