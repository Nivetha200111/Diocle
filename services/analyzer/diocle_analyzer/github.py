"""Shallow, read-only clone of an allowed GitHub repository."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


MAX_MB = 300  # repositories carry PDFs and images too; anything bigger is refused (disk, analysis time)


def allowed_owners() -> set[str] | None:
    """Owners whose repositories may be imported; None means any public repository. DIOCLE_IMPORT_ANY=1 is set
    only for visitor imports, which the API runs with every build and program execution in the sandbox."""
    if os.environ.get("DIOCLE_IMPORT_ANY") == "1":
        return None
    return {o.strip().lower() for o in os.environ.get("DIOCLE_IMPORT_OWNERS", "Nivetha200111").split(",") if o.strip()}


def parse_url(url: str) -> tuple[str, str]:
    m = URL.match(url.strip())
    if not m:
        raise ValueError("expected https://github.com/<owner>/<repo>")
    owner, repo = m.group(1), m.group(2)
    allowed = allowed_owners()
    if allowed is not None and owner.lower() not in allowed:
        raise PermissionError(f"imports from {owner!r} are not allowed (DIOCLE_IMPORT_OWNERS)")
    return owner, repo


def clone(url: str, dest_root: Path) -> tuple[Path, str]:
    """Clone into dest_root/<owner>-<repo>-<sha12>; returns (path, full commit sha)."""
    owner, repo = parse_url(url)
    tmp = dest_root / f"{owner}-{repo}-incoming"
    if tmp.exists():
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
    dest_root.mkdir(parents=True, exist_ok=True)
    # core.symlinks=false: a link to a server file (say /proc/1/environ) becomes a small text file, never followed.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    subprocess.run(["git", "-c", "core.symlinks=false", "clone", "--depth", "1", "--single-branch", "--no-tags", "--quiet",
                    "--", f"https://github.com/{owner}/{repo}.git", str(tmp)], check=True, timeout=120, env=env)
    size = sum(f.stat().st_size for f in tmp.rglob("*") if f.is_file() and not f.is_symlink())
    if size > MAX_MB * 1024 * 1024:
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
        raise ValueError(f"{owner}/{repo} is over {MAX_MB} MB; import a smaller repository")
    sha = subprocess.run(["git", "-C", str(tmp), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    final = dest_root / f"{owner}-{repo}-{sha[:12]}"
    if final.exists():
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
    else:
        tmp.rename(final)
    return final, sha
