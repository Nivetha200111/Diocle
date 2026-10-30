"""Create-the-target-repository option: contract (delivery v0.5), validation, owner allowlist, admin-only path,
and the delivery flow against a TEST DOUBLE for `gh` (see the fake_gh fixture). No real GitHub repository is ever created."""
import json

import jsonschema
import pytest

from diocle_api import deliver

CONTRACTS = deliver.REPO_ROOT / "contracts"
DELIVERY = json.loads((CONTRACTS / "delivery.schema.json").read_text())
REQUEST = {"$ref": "#/$defs/request", "$defs": DELIVERY["$defs"]}
BASE = {"id": "d", "legacy": {"repository": "https://github.com/o/r"}, "target": None, "stage": "analyzing",
        "programs": [], "startedAt": "2026-10-30T00:00:00+00:00"}


def test_contract_accepts_valid_and_old_records_and_rejects_invalid_ones():
    jsonschema.validate(BASE, DELIVERY)  # an old record: no createTarget
    jsonschema.validate({**BASE, "target": "https://github.com/me/x-java", "targetCreated": True,
                         "createTarget": {"name": "x-java", "owner": "me", "visibility": "private"}}, DELIVERY)
    jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": {"name": "x_1.2-java"}}, REQUEST)
    jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": {"name": "x", "owner": None, "visibility": "public"}}, REQUEST)
    bad = [{"name": ""}, {"name": ".."}, {"name": "."}, {"name": "a/b"}, {"name": "a b"}, {"name": "x" * 101}, {"name": "répo"},
           {"name": "x.git"}, {"name": "x", "visibility": "internal"}, {"name": "x", "owner": "a/b"}, {"name": "x", "extra": 1}, {}]
    for create in bad:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"legacy": "https://github.com/o/r", "createTarget": create}, REQUEST)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**BASE, "targetCreated": "yes"}, DELIVERY)


# ---- validation and the owner allowlist ----------------------------------------------------------

@pytest.fixture(autouse=True)
def allowlist(monkeypatch):
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "me")


@pytest.mark.parametrize("name", ["x", "quillmark-java", "a.b_c-1", "x" * 100, "..a", ".hidden", "-x"])
def test_good_names(name):
    assert deliver.validate_create_target(name)["visibility"] == "private"


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "../x", "x/../y", " x", "x ", "x\n", "x" * 101, "répo", "名前", "a b", "x;rm", "$(id)",
                                  "x.git", "-rf/x", None, 5])
def test_bad_names(name):
    with pytest.raises(SystemExit):
        deliver.validate_create_target(name)


def test_owner_must_be_well_formed_and_allowlisted_and_visibility_known():
    assert deliver.validate_create_target("x", "ME")["owner"] == "ME"  # same case-insensitive rule as target_repo
    for owner in ("other", "me/evil", "-me", "me ", "me\n", ""):
        with pytest.raises(SystemExit):
            deliver.validate_create_target("x", owner)
    with pytest.raises(SystemExit):
        deliver.validate_create_target("x", "me", "internal")


# ---- a TEST DOUBLE for gh -------------------------------------------------------------------------

FAKE_GH = r"""#!/bin/sh
# TEST DOUBLE for the GitHub CLI. Records argv in $FAKE_GH_LOG and answers from $FAKE_GH_STATE. Creates only directories under
# $FAKE_GH_STATE: a bare git repository stands in for a GitHub repository. Never contacts GitHub.
{ printf 'gh'; for a in "$@"; do printf ' [%s]' "$a"; done; echo; } >> "$FAKE_GH_LOG"
case "$1 $2" in
  "api user") echo "${FAKE_GH_USER:-me}";;
  "api repos/"*) r="${2#repos/}"
    if [ -d "$FAKE_GH_STATE/$r.git" ]; then echo '{}'; else echo "gh: Not Found (HTTP 404)" >&2; exit 1; fi;;
  "repo create") [ -n "$FAKE_GH_FAIL_CREATE" ] && { echo "gh: boom" >&2; exit 1; }
    r="$3"; mkdir -p "$FAKE_GH_STATE/$r.git" && git init -q --bare -b main "$FAKE_GH_STATE/$r.git"
    w=$(mktemp -d) && git -C "$w" init -q -b main && echo "# $r" > "$w/README.md" && git -C "$w" add -A &&
    git -C "$w" -c user.name=t -c user.email=t@t commit -q -m init && git -C "$w" push -q "$FAKE_GH_STATE/$r.git" main;;
  "pr create") [ -n "$FAKE_GH_FAIL_PR" ] && { echo "gh: pr failed" >&2; exit 1; }
    echo "https://github.com/me/x-java/pull/1";;
  *) echo "fake gh: unexpected $*" >&2; exit 2;;
esac
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    import os
    import subprocess
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "ghstate"
    state.mkdir()
    gitconfig = tmp_path / "gitconfig"  # git clone https://github.com/... is redirected to the local bare repository
    gitconfig.write_text(f'[url "file://{state}/"]\n\tinsteadOf = https://github.com/\n[protocol "file"]\n\tallow = always\n')
    log = tmp_path / "gh.log"
    log.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    for k in ("FAKE_GH_FAIL_CREATE", "FAKE_GH_FAIL_PR", "FAKE_GH_USER"):
        monkeypatch.delenv(k, raising=False)

    class Gh:
        calls = lambda self: [line for line in log.read_text().splitlines() if line]
        creates = lambda self: [c for c in self.calls() if c.startswith("gh [repo] [create]")]
        repos = lambda self: sorted(p.name for p in state.glob("*/*.git"))
    return Gh()


def test_the_double_is_what_runs_and_nothing_is_created_by_a_plan(fake_gh):
    plan = deliver.plan_create(deliver.validate_create_target("x-java"), "https://github.com/o/legacy")
    assert plan["full"] == "me/x-java" and plan["visibility"] == "private"
    assert fake_gh.creates() == [] and fake_gh.repos() == []
    assert plan["command"] == ["gh", "repo", "create", "me/x-java", "--private", "--description",
                               "Java conversion of o/legacy, verified by Diocle", "--add-readme"]


def test_public_only_with_the_explicit_value(fake_gh):
    assert "--public" not in deliver.plan_create(deliver.validate_create_target("x"), "https://github.com/o/l")["command"]
    plan = deliver.plan_create(deliver.validate_create_target("x", None, "public"), "https://github.com/o/l")
    assert "--public" in plan["command"] and "--private" not in plan["command"]


def test_authenticated_user_must_be_on_the_allowlist(fake_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_USER", "stranger")
    with pytest.raises(SystemExit, match="not allowed"):
        deliver.plan_create(deliver.validate_create_target("x"), "https://github.com/o/l")
    assert fake_gh.creates() == []


def test_an_existing_repository_is_refused_and_pointed_to_as_a_target(fake_gh, tmp_path):
    (tmp_path / "ghstate" / "me" / "x.git").mkdir(parents=True)
    with pytest.raises(SystemExit, match="already exists.*as the target instead"):
        deliver.plan_create(deliver.validate_create_target("x"), "https://github.com/o/l")
    assert fake_gh.creates() == []


def test_an_unclear_existence_answer_creates_nothing(fake_gh, monkeypatch):
    monkeypatch.setattr(deliver, "_gh", lambda args, check=True: type("R", (), {"returncode": 1, "stderr": "gh: HTTP 500", "stdout": "me\n"})())
    with pytest.raises(SystemExit, match="could not tell"):
        deliver.plan_create(deliver.validate_create_target("x"), "https://github.com/o/l")


# ---- the delivery flow against the double --------------------------------------------------------

SRC = {"location": "https://github.com/o/legacy", "commit": "a" * 40}


@pytest.fixture
def flow(tmp_path, monkeypatch, fake_gh):
    """A small repository stands in for Diocle's checkout; analyzer, converter and runs are TEST DOUBLES."""
    import subprocess
    root = tmp_path / "diocle"
    (root / "runs" / "r1" / "java").mkdir(parents=True)
    (root / "runs" / "r1" / "java" / "Prog.java").write_text("class Prog {}")
    for cmd in (["init", "-q", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
    samples = tmp_path / "samples" / "prog"
    samples.mkdir(parents=True)
    (samples / "sample.json").write_text(json.dumps({"javaConversion": {"mainClass": "Prog"}}))
    run = {"id": "r1", "program": "PROG", "certified": True, "after": {"passed": 1, "total": 1, "stdoutMatch": True}, "before": None}
    monkeypatch.setattr(deliver, "REPO_ROOT", root)
    monkeypatch.setattr(deliver, "get_run", lambda rid: run)
    monkeypatch.setattr(deliver, "certificate", lambda *a, **k: {"program": "PROG", "agent": {"model": "m"}, "verification": {"passed": 1, "total": 1, "stdoutMatch": True}})
    monkeypatch.setattr(deliver, "_pr_body", lambda *a, **k: "PR BODY")
    monkeypatch.setattr(deliver, "_other_programs", lambda *a, **k: [])
    monkeypatch.setattr(deliver, "time", type("T", (), {"sleep": staticmethod(lambda s: None), "time": staticmethod(lambda: 0)}))
    report = {"source": SRC, "programs": [{"name": "PROG", "path": "PROG.cbl"}]}
    return report, tmp_path / "samples", {"PROG": "r1"}, fake_gh


def plan(name="x-java", visibility="private"):
    return deliver.plan_create(deliver.validate_create_target(name, None, visibility), "https://github.com/o/legacy")


def test_dry_run_prints_the_exact_command_and_creates_nothing(flow, capsys):
    report, samples, runs, gh = flow
    deliver.deliver(report, samples, runs, "https://github.com/me/x-java", True, create=plan())
    out = capsys.readouterr().out
    assert "DRY RUN: nothing was created, cloned or pushed" in out
    assert "gh repo create me/x-java --private --description 'Java conversion of o/legacy, verified by Diocle' --add-readme" in out
    assert "gh pr create --repo me/x-java" in out and ".github/workflows/reverify.yml" in out
    assert gh.creates() == [] and gh.repos() == [] and not any("pr" in c.split()[1] for c in gh.calls() if c.startswith("gh [pr]"))


def test_full_flow_creates_private_then_pushes_workflow_and_programs_and_opens_the_pr(flow, tmp_path):
    import subprocess
    report, samples, runs, gh = flow
    class P:  # progress double
        updates = []
        def update(self, **f): self.updates.append(f)
        def program(self, n): return {}
        def save(self): pass
    url = deliver.deliver(report, samples, runs, "https://github.com/me/x-java", False, P(), create=plan())
    assert url == "https://github.com/me/x-java/pull/1" and P.updates[0] == {"targetCreated": True}
    assert len(gh.creates()) == 1 and "[--private]" in gh.creates()[0] and "[--public]" not in gh.creates()[0]
    assert gh.repos() == ["x-java.git"]
    bare = tmp_path / "ghstate" / "me" / "x-java.git"
    branches = subprocess.run(["git", "-C", str(bare), "branch", "--list", "diocle/*"], capture_output=True, text=True).stdout
    assert branches.strip().startswith("diocle/")
    files = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", branches.strip()], capture_output=True, text=True).stdout.split()
    assert ".github/workflows/reverify.yml" in files and "programs/PROG/java/Prog.java" in files and "README.md" in files
    log = (tmp_path / "gh.log").read_text()  # the PR body is multi-line, so look at the whole record
    assert "gh [pr] [create] [--repo] [me/x-java]" in log and "This repository was created by Diocle" in log


def test_partial_failure_says_what_exists_and_deletes_nothing(flow, monkeypatch):
    report, samples, runs, gh = flow
    monkeypatch.setenv("FAKE_GH_FAIL_PR", "1")
    with pytest.raises(SystemExit) as e:
        deliver.deliver(report, samples, runs, "https://github.com/me/x-java", False, create=plan())
    msg = str(e.value)
    assert "me/x-java was created (private) and is still there" in msg and "pushed" in msg
    assert "gh repo delete me/x-java --yes" in msg and len(msg) < 480
    assert gh.repos() == ["x-java.git"] and not any("delete" in c for c in gh.calls())


def test_failed_creation_is_reported_and_nothing_follows(flow, monkeypatch):
    report, samples, runs, gh = flow
    monkeypatch.setenv("FAKE_GH_FAIL_CREATE", "1")
    with pytest.raises(SystemExit, match="gh repo create me/x-java failed"):
        deliver.deliver(report, samples, runs, "https://github.com/me/x-java", False, create=plan())
    assert gh.repos() == []


def test_nothing_certified_creates_no_repository(flow, monkeypatch):
    report, samples, runs, gh = flow
    monkeypatch.setattr(deliver, "get_run", lambda rid: {"id": "r1", "certified": False, "after": None, "program": "PROG"})
    with pytest.raises(SystemExit, match="Nothing certified"):
        deliver.deliver(report, samples, runs, "https://github.com/me/x-java", False, create=plan())
    assert gh.repos() == [] and gh.creates() == []


# ---- CLI argument rules ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [["https://github.com/me/t", "--create-target", "x"], ["--create-target", "x", "--onto", "b"],
                                   ["--create-target", "x", "--public"], ["--target-public"], ["--target-owner", "me"]])
def test_cli_combinations_are_refused(extra, fake_gh):
    with pytest.raises(SystemExit) as e:
        deliver.main(["https://github.com/o/legacy", *extra])
    assert e.value.code == 2 and fake_gh.creates() == []


def test_cli_bad_name_and_owner_stop_before_any_work(fake_gh, monkeypatch):
    monkeypatch.setattr(deliver, "analyze", lambda *a, **k: pytest.fail("analysis started"))
    for argv in (["--create-target", "../x"], ["--create-target", "x", "--target-owner", "someone-else"]):
        with pytest.raises(SystemExit):
            deliver.main(["https://github.com/o/legacy", *argv])
    assert fake_gh.creates() == []


def test_cli_dry_run_records_the_request_but_not_a_creation(flow, monkeypatch, capsys):
    report, samples, runs, gh = flow
    monkeypatch.setattr(deliver, "analyze", lambda url, did, ca=False: ({"source": SRC, "programs": [
        {"name": "PROG", "path": "PROG.cbl", "convertible": True}]}, samples))
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: pytest.fail("converted"))
    deliver.main(["https://github.com/o/legacy", "--create-target", "x-java", "--dry-run", "--runs", "r1"])
    rec = json.loads(next((deliver.REPO_ROOT / "runs" / "deliveries").glob("*/delivery.json")).read_text())
    jsonschema.validate(rec, DELIVERY)
    assert rec["target"] == "https://github.com/me/x-java" and rec["targetCreated"] is False
    assert rec["createTarget"] == {"name": "x-java", "owner": None, "visibility": "private"}
    assert gh.creates() == [] and gh.repos() == []


# ---- the API: admin only, argv from validated fields ----------------------------------------------

@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from diocle_api.app import app
    monkeypatch.setenv("DIOCLE_ADMIN_TOKEN", "secret")
    monkeypatch.setenv("DIOCLE_PUBLIC_IMPORTS", "1")
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    started = []
    monkeypatch.setattr("diocle_api.app.start_delivery", lambda *a, **k: started.append((a, k)) or "delivery-x")
    monkeypatch.setattr("diocle_api.app.public.admit", lambda v: None)
    monkeypatch.setattr("diocle_api.app.running_delivery", lambda: None)
    return TestClient(app), started


LEGACY = "https://github.com/o/legacy"


def test_public_path_rejects_create_target_and_any_target(client):
    c, started = client
    for extra in ({"createTarget": {"name": "x"}}, {"target": "https://github.com/me/t"}):
        assert c.post("/deliveries", json={"legacy": LEGACY, **extra}).status_code == 403
        assert c.post("/deliveries", json={"legacy": LEGACY, **extra}, headers={"X-Diocle-Admin": "wrong"}).status_code == 403
    assert started == []


def test_admin_may_create_and_gets_validated_fields_only(client):
    c, started = client
    h = {"X-Diocle-Admin": "secret"}
    r = c.post("/deliveries", json={"legacy": LEGACY, "createTarget": {"name": "x-java", "visibility": "public"}}, headers=h)
    assert r.status_code == 202 and started[-1][1]["create_target"] == {"name": "x-java", "owner": None, "visibility": "public"}
    for bad in ({"name": "../x"}, {"name": "x", "owner": "someone-else"}, {"name": "x", "visibility": "internal"}):
        r = c.post("/deliveries", json={"legacy": LEGACY, "createTarget": bad}, headers=h)
        assert r.status_code in (400, 422), bad
    assert len(started) == 1
    both = c.post("/deliveries", json={"legacy": LEGACY, "target": "https://github.com/me/t", "createTarget": {"name": "x"}}, headers=h)
    assert both.status_code == 400
    assert c.post("/deliveries", json={"legacy": LEGACY, "createTarget": {"name": "x", "extra": 1}}, headers=h).status_code == 422


def test_local_mode_without_a_token_allows_create_only_from_this_machine(monkeypatch):
    from fastapi.testclient import TestClient
    from diocle_api.app import app
    monkeypatch.delenv("DIOCLE_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("DIOCLE_HOSTED", raising=False)
    started = []
    monkeypatch.setattr("diocle_api.app.start_delivery", lambda *a, **k: started.append(k) or "delivery-x")
    monkeypatch.setattr("diocle_api.app.running_delivery", lambda: None)
    body = {"legacy": LEGACY, "createTarget": {"name": "x"}}
    assert TestClient(app, client=("203.0.113.9", 5000)).post("/deliveries", json=body).status_code == 403
    assert TestClient(app, client=("127.0.0.1", 5000)).post("/deliveries", json=body, headers={"x-forwarded-for": "1.2.3.4"}).status_code == 403
    assert TestClient(app, client=("127.0.0.1", 5000)).post("/deliveries", json=body).status_code == 202
    assert len(started) == 1


def test_child_argv_is_a_list_of_validated_fields_and_the_record_is_valid(tmp_path, monkeypatch):
    import sys
    from diocle_api import deliveries
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("GH_TOKEN", "TOKEN-VALUE-NOT-REAL")
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "me")
    monkeypatch.setattr(deliveries, "running_delivery", lambda: None)
    seen = {}
    monkeypatch.setattr(deliveries.subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd, kw=kw) or type("P", (), {"pid": 1, "poll": lambda s: None})())
    did = deliveries.start_delivery(LEGACY, None, False, False, create_target={"name": "x-java", "owner": "me", "visibility": "public"})
    cmd = seen["cmd"]
    assert isinstance(cmd, list) and cmd[:3] == [sys.executable, "-m", "diocle_api.deliver"] and not seen["kw"].get("shell")
    assert cmd[cmd.index("--create-target") + 1] == "x-java" and cmd[cmd.index("--target-owner") + 1] == "me" and "--target-public" in cmd
    assert seen["kw"]["env"]["GH_TOKEN"] == "TOKEN-VALUE-NOT-REAL"  # gh needs it; the log below must not hold it
    rec = json.loads((tmp_path / "deliveries" / did / "delivery.json").read_text())
    jsonschema.validate(rec, DELIVERY)
    assert rec["targetCreated"] is False and rec["target"] is None
    with pytest.raises(ValueError):
        deliveries.start_delivery(LEGACY, None, False, False, public=True, create_target={"name": "x"})
    with pytest.raises(ValueError):
        deliveries.start_delivery(LEGACY, "https://github.com/me/t", False, False, create_target={"name": "x"})
    with pytest.raises(SystemExit):
        deliveries.start_delivery(LEGACY, None, False, False, create_target={"name": "$(id)"})
