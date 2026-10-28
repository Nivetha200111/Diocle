"""Shallow, read-only clone of an allowed GitHub repository."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def allowed_owners() -> set[str]:
    # Imported code is compiled and executed by the verifier, so only trusted owners until imports run in a sandbox.
    return {o.strip().lower() for o in os.environ.get("DIOCLE_IMPORT_OWNERS", "Nivetha200111").split(",") if o.strip()}


def parse_url(url: str) -> tuple[str, str]:
    m = URL.match(url.strip())
    if not m:
        raise ValueError("expected https://github.com/<owner>/<repo>")
    owner, repo = m.group(1), m.group(2)
    if owner.lower() not in allowed_owners():
        raise PermissionError(f"imports from {owner!r} are not allowed (DIOCLE_IMPORT_OWNERS)")
    return owner, repo


def clone(url: str, dest_root: Path) -> tuple[Path, str]:
    """Clone into dest_root/<owner>-<repo>-<sha12>; returns (path, full commit sha)."""
    owner, repo = parse_url(url)
    tmp = dest_root / f"{owner}-{repo}-incoming"
    if tmp.exists():
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
    dest_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", "--quiet", f"https://github.com/{owner}/{repo}.git", str(tmp)],
                   check=True, timeout=120)
    sha = subprocess.run(["git", "-C", str(tmp), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    final = dest_root / f"{owner}-{repo}-{sha[:12]}"
    if final.exists():
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
    else:
        tmp.rename(final)
    return final, sha
