"""Limits on visitor imports: anyone may import a public repository, within a daily model budget (rule 10).

The budget is the hard limit: today's estimated model spend across all runs, read from the runs themselves.
The per-visitor limit is best effort (the address comes from the proxy and is never stored on disk).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone

from .runs import runs_dir

_seen: dict[str, list[float]] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """Visitor imports need the sandbox: imported COBOL and model-written Java never run beside the secrets."""
    return os.environ.get("DIOCLE_PUBLIC_IMPORTS") == "1" and bool(os.environ.get("DIOCLE_SANDBOX_URL"))


def limits() -> dict:
    return {
        "dailyBudgetUsd": float(os.environ.get("DIOCLE_PUBLIC_DAILY_USD", "2")),
        "perVisitorPerDay": int(os.environ.get("DIOCLE_PUBLIC_PER_VISITOR", "3")),
        "maxPrograms": int(os.environ.get("DIOCLE_PUBLIC_MAX_PROGRAMS", "3")),
        "maxLines": int(os.environ.get("DIOCLE_PUBLIC_MAX_LINES", "1500")),
    }


def spent_today() -> float:
    """Estimated model spend (USD, list prices) of every run started today (UTC), finished or not."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    total = 0.0
    for meta in runs_dir().glob(f"*-{today}-*/run.json"):
        try:
            total += float(json.loads(meta.read_text()).get("usage", {}).get("estimatedCostUsd") or 0)
        except (ValueError, OSError):
            continue
    return round(total, 4)


def status() -> dict:
    lim = limits()
    spent = spent_today()
    return {"enabled": enabled(), **lim, "spentTodayUsd": spent,
            "budgetLeft": spent < lim["dailyBudgetUsd"]}


def admit(visitor: str) -> None:
    """Raise PermissionError if a visitor import may not start now; otherwise count it."""
    lim = limits()
    if spent_today() >= lim["dailyBudgetUsd"]:
        raise PermissionError("today's model budget for visitor imports is used up; it resets at 00:00 UTC")
    key = hashlib.sha256(visitor.encode()).hexdigest()[:16]
    now = time.time()
    with _lock:
        recent = [t for t in _seen.get(key, []) if now - t < 86400]
        if len(recent) >= lim["perVisitorPerDay"]:
            raise PermissionError(f"each visitor may start {lim['perVisitorPerDay']} imports a day")
        _seen[key] = recent + [now]
