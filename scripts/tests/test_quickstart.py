"""Non-network logic of scripts/quickstart.sh: prerequisite checks, arguments, cost cap, key detection. No model, no key."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quickstart.sh"


def run(args, tmp_path, env_extra=None, stubs=None, with_env_file=None):
    tmp_path = tmp_path / f"case{len(list(tmp_path.glob('case*')))}"  # a fresh sandbox per call
    tmp_path.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, text in (stubs if stubs is not None else {"cobc": "cobc (GnuCOBOL) 3.2.0", "javac": "javac 21.0.2", "python3": None}).items():
        target = bin_dir / name
        if text is None:  # the real python3 so the version probe works
            target.symlink_to(shutil.which("python3"))
        else:
            target.write_text(f'#!/bin/sh\necho "{text}"\n')
            target.chmod(0o755)
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, root / "scripts" / "quickstart.sh")
    (root / "samples" / "interest-accrual").mkdir(parents=True, exist_ok=True)
    if with_env_file is not None:
        (root / ".env").write_text(with_env_file)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    env.update(env_extra or {})
    return subprocess.run(["/bin/sh", str(root / "scripts" / "quickstart.sh"), *args], env=env, capture_output=True, text=True)


def test_check_without_key_falls_through_to_no_key(tmp_path):
    r = run(["--check"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "mode=nokey" in r.stdout and "cp .env.example .env" in r.stdout and "no model will be called" in r.stdout


def test_key_in_environment_selects_key_mode_and_is_never_printed(tmp_path):
    r = run(["--check"], tmp_path, {"META_MODEL_API_KEY": "sk-secret-value"})
    assert "mode=key" in r.stdout and "sk-secret-value" not in r.stdout + r.stderr


def test_key_in_dotenv_and_empty_placeholder(tmp_path):
    assert "mode=key" in run(["--check"], tmp_path, with_env_file="META_MODEL_API_KEY=abc123\n").stdout
    assert "mode=nokey" in run(["--check"], tmp_path, with_env_file="META_MODEL_API_KEY=\n").stdout


def test_no_key_flag_wins_over_a_configured_key(tmp_path):
    assert "mode=nokey" in run(["--check", "--no-key"], tmp_path, {"META_MODEL_API_KEY": "x"}).stdout


def test_cap_default_clamp_and_garbage(tmp_path):
    assert "cap=0.10" in run(["--check"], tmp_path).stdout
    assert "cap=1.00" in run(["--check"], tmp_path, {"QUICKSTART_MAX_USD": "50"}).stdout
    assert "cap=0.25" in run(["--check"], tmp_path, {"QUICKSTART_MAX_USD": "0.25"}).stdout
    assert "cap=0.01" in run(["--check"], tmp_path, {"QUICKSTART_MAX_USD": "0"}).stdout
    assert "cap=0.10" in run(["--check"], tmp_path, {"QUICKSTART_MAX_USD": "1e9; rm -rf"}).stdout


def test_a_key_argument_is_refused(tmp_path):
    r = run(["--api-key", "sk-abc"], tmp_path)
    assert r.returncode == 2 and "never pass a key" in r.stderr and "sk-abc" not in r.stdout


def test_bad_arguments(tmp_path):
    assert run(["--bogus"], tmp_path).returncode == 2
    assert run(["--sample", "../etc"], tmp_path).returncode == 2
    assert run(["--sample", "nope"], tmp_path).returncode == 2


def test_missing_and_old_prerequisites(tmp_path):
    r = run(["--check"], tmp_path, stubs={"cobc": "cobc (GnuCOBOL) 3.1.2", "javac": "javac 17.0.1", "python3": None})
    assert r.returncode == 3 and "GnuCOBOL 3.2 or newer (found 3.1)" in r.stdout and "JDK 21 or newer (found 17)" in r.stdout
    assert "brew install" in r.stdout or "apt install" in r.stdout
    r = run(["--check"], tmp_path, stubs={})
    assert r.returncode == 3 and "MISSING: cobc" in r.stdout


def test_help_exits_zero(tmp_path):
    r = run(["--help"], tmp_path)
    assert r.returncode == 0 and "--no-key" in r.stdout
