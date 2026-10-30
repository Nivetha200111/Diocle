"""Limits on visitor imports: anyone may import a public repository, within a daily model budget (rule 10).

The budget is the hard limit: estimated model spend over the last 24 hours across all runs, read from the runs.
The per-visitor limit is best effort (the address comes from the proxy and is never stored on disk).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time

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
        # compile-only check of the originals before any model call (deliver.py): bounded, so it cannot burn sandbox time
        "maxPrecheck": int(os.environ.get("DIOCLE_PUBLIC_MAX_PRECHECK", "12")),
        "precheckSeconds": float(os.environ.get("DIOCLE_PUBLIC_PRECHECK_SECONDS", "240")),
    }


def spent_today() -> float:
    """Estimated model spend (USD, list prices) of every run active in the last 24 hours, finished or not.
    A run with model calls but no price (a model missing from the price list) makes this infinite: the budget
    fails closed rather than counting unknown spend as free."""
    cutoff = time.time() - 86400
    total = 0.0
    for meta in runs_dir().glob("*/run.json"):
        try:
            if meta.stat().st_mtime < cutoff:
                continue
            usage = json.loads(meta.read_text()).get("usage", {})
        except (ValueError, OSError):
            continue
        cost = usage.get("estimatedCostUsd")
        if cost is None and usage.get("calls"):
            return float("inf")
        total += float(cost or 0)
    from .asks import spent as asks_spent  # nor is the ask button's
    from .livesamples import printout_spent  # the printout button's spend is not in a run record
    extra = printout_spent() + asks_spent()
    return float("inf") if extra == float("inf") else round(total + extra, 4)


def status() -> dict:
    lim = limits()
    spent = spent_today()
    return {"enabled": enabled(), **lim, "spentTodayUsd": spent if spent != float("inf") else None,
            "budgetLeft": spent < lim["dailyBudgetUsd"]}


def admit(visitor: str) -> None:
    """Raise PermissionError if a visitor import may not start now; otherwise count it."""
    lim = limits()
    if spent_today() >= lim["dailyBudgetUsd"]:
        raise PermissionError("the model budget for visitor imports is used up for the last 24 hours; try again later")
    key = hashlib.sha256(visitor.encode()).hexdigest()[:16]
    now = time.time()
    with _lock:
        recent = [t for t in _seen.get(key, []) if now - t < 86400]
        if len(recent) >= lim["perVisitorPerDay"]:
            raise PermissionError(f"each visitor may start {lim['perVisitorPerDay']} imports a day")
        _seen[key] = recent + [now]


def visitor_key(visitor: str) -> str:
    return hashlib.sha256(visitor.encode()).hexdigest()[:16]


def visitor_left(bucket: str, visitor: str, limit: int) -> int:
    """Starts a visitor has left in the last 24 hours in a named bucket (the live sample buttons count separately
    from imports and from each other). Best effort, like admit(): in memory, by address, never stored on disk."""
    now = time.time()
    with _lock:
        return max(0, limit - len([t for t in _seen.get(f"{bucket}:{visitor_key(visitor)}", []) if now - t < 86400]))


def visitor_hit(bucket: str, visitor: str, limit: int) -> None:
    """Count one start in the bucket, or raise PermissionError when the visitor is out of starts for the day."""
    key, now = f"{bucket}:{visitor_key(visitor)}", time.time()
    with _lock:
        recent = [t for t in _seen.get(key, []) if now - t < 86400]
        if len(recent) >= limit:
            raise PermissionError(f"each visitor may start {limit} a day")
        _seen[key] = recent + [now]
