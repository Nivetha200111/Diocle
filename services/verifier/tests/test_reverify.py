import json
import shutil
import subprocess
from pathlib import Path

from diocle_analyzer.analyze import analyze
from diocle_verifier.reverify import reverify

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
REFERENCE = Path(__file__).parent / "fixtures" / "reference" / "IntAccr.java"


def _legacy_repo(tmp: Path) -> tuple[str, str]:
    """A local stand-in for the legacy GitHub repository: <tmp>/legacy.git with the COBOL committed."""
    work = tmp / "legacy-work"
    (work / "cobol").mkdir(parents=True)
    shutil.copytree(SAMPLE / "copybooks", work / "copybooks")
    shutil.copy2(SAMPLE / "src" / "INTACCR.cbl", work / "cobol" / "INTACCR.cbl")
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "legacy"], check=True)
    commit = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(tmp / "legacy.git")], check=True)
    return str(tmp / "legacy"), commit


def _delivery(tmp: Path, repository: str, commit: str, java: Path, *, layouts=None, path="cobol/INTACCR.cbl") -> Path:
    """A delivery as Diocle writes it: sample.json layouts derived by the analyzer from the copybooks."""
    program = tmp / "delivery" / "programs" / "INTACCR"
    (program / "java").mkdir(parents=True)
    shutil.copy2(java, program / "java" / "IntAccr.java")
    [derived] = analyze(SAMPLE)["programs"]
    files = {f["direction"]: f for f in derived["files"]}
    meta = {"dd": {d: files[d]["dd"] for d in ("input", "output")},
            "layouts": layouts or {d: files[d]["layout"] for d in ("input", "output")}}
    (program / "sample.json").write_text(json.dumps(meta))
    (program / "certificate.json").write_text(json.dumps({
        "program": "INTACCR", "java": {"mainClass": "IntAccr"},
        "legacy": {"repository": repository, "commit": commit, "path": path,
                   "copybooks": ["copybooks/ACCTREC.cpy", "copybooks/INTREC.cpy"]}}))
    return program.parent


def test_reverify_passes_faithful_java_and_fails_naive_java(tmp_path):
    repository, commit = _legacy_repo(tmp_path)
    good = reverify(_delivery(tmp_path / "good", repository, commit, REFERENCE), seed=777, random_count=150,
                    expect_legacy=repository)
    assert [r["ok"] for r in good] == [True] and good[0]["total"] > 150
    naive = SAMPLE / "java-conversion" / "IntAccr.java"
    bad = reverify(_delivery(tmp_path / "bad", repository, commit, naive), seed=777, random_count=150,
                   expect_legacy=repository)
    assert [r["ok"] for r in bad] == [False] and bad[0]["firstMismatch"]



def test_reverify_rejects_certificates_ci_must_not_trust(tmp_path):
    repository, commit = _legacy_repo(tmp_path)

    def run(name, **kw):
        cert_repo = kw.pop("cert_repo", repository)
        cert_commit = kw.pop("cert_commit", commit)
        [r] = reverify(_delivery(tmp_path / name, cert_repo, cert_commit, REFERENCE, **kw), seed=1, random_count=5,
                       expect_legacy=repository)
        assert not r["ok"]
        return r["buildError"]

    assert "CI expects" in run("other-repo", cert_repo=str(tmp_path / "elsewhere"))
    assert "40-character SHA" in run("short-sha", cert_commit=commit[:7])
    assert "escapes the legacy checkout" in run("traversal", path="../../etc/passwd")
    [derived] = analyze(SAMPLE)["programs"]
    weakened = {d: {"record": "R", "fields": [{"name": "X", "kind": "alnum", "length": 1}]} for d in ("input", "output")}
    assert "differ from the legacy copybooks" in run("weakened-layout", layouts=weakened)
