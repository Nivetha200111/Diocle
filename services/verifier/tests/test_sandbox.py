"""Verification jobs run in the sandbox: only regular files go in, only the report comes back."""

import io
import os
import tarfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_verifier import sandbox
from diocle_verifier.verify import verify_sample

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "interest-accrual"


def test_pack_takes_regular_files_only(tmp_path: Path):
    (tmp_path / "sample.json").write_text("{}")
    (tmp_path / "secret-link").symlink_to("/etc/hosts")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    names = tarfile.open(fileobj=io.BytesIO(sandbox.pack(tmp_path, None))).getnames()
    assert names == ["sample/sample.json"]


def test_bundle_cannot_write_outside_the_job(tmp_path: Path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    import base64
    with pytest.raises(tarfile.TarError):
        sandbox.run_job({"bundle": base64.b64encode(buf.getvalue()).decode()})
    assert not (Path(os.environ.get("TMPDIR", "/tmp")) / "escape.txt").exists()


@pytest.fixture
def server(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    yield
    httpd.shutdown()


def test_remote_verification_matches_local(server, monkeypatch):
    remote = verify_sample(SAMPLE, seed=7, random_count=50)
    monkeypatch.delenv("DIOCLE_SANDBOX_URL")
    local = verify_sample(SAMPLE, seed=7, random_count=50)
    assert remote["summary"] == local["summary"] and remote["summary"]["total"] > 50
