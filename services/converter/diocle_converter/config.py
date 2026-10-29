"""Settings from the environment and the repo-root .env (keys are never logged)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# USD per million tokens (input, cached input, output), from dev.meta.ai and fireworks.ai pricing, 2026-10-28, and
# baseten.co/library/muse-spark-open, 2026-10-29.
# Reasoning tokens bill as output.
PRICES = {
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "accounts/fireworks/models/muse-spark-open": (1.25, 0.15, 4.25),  # Fireworks serverless
    "meta-models/muse-spark-open-1026": (1.25, 0.15, 4.25),  # Baseten (same list price as Fireworks)
    # Muse Wonder: $4 / $0.20 / $20 per third-party coverage (Oct 2026); not yet confirmed on dev.meta.ai. Used only for
    # the escalation tiers and the cost cap; an unpriced model makes the run's cost n/a rather than guessed.
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
}


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    mode: str
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str
    max_calls_per_run: int
    max_calls_per_round: int
    max_rounds: int
    max_attack_rounds: int = 3  # breaker agent: attack rounds before the first repair
    max_breaker_cycles: int = 1  # breaker agent: repair-and-re-attack cycles after a break
    # Escalation tiers (hosted mode only, opt-in with --tiers): model IDs on the same host and key as `model`, simplest
    # first. tiers[0] is tier 2, tiers[1] is tier 3; `model` itself is tier 1. Calls on a tier above 1 have their own
    # hard caps (rule 10): a call count and a dollar amount per run.
    tiers: tuple[str, ...] = ()
    escalation_max_calls: int = 12
    escalation_max_usd: float = 0.50
    # Which tier does what with --tiers. Defaults are tier 2 (muse-spark-1.3): in a real run one Muse Wonder breaker
    # call cost about $0.22-0.37 (reasoning tokens bill at $20/M), 96% of the run's cost. Set 3 to opt in to Wonder.
    breaker_tier: int = 2  # the tier that designs breaker attacks
    after_break_tier: int = 2  # the tier the repair agent resumes at when a certified Java is broken

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        mode = os.environ.get("MODEL_MODE", "hosted")
        prefix = {"hosted": "META_MODEL", "private": "OPEN_MODEL"}.get(mode)
        if prefix is None:
            raise SystemExit(f"MODEL_MODE must be 'hosted' or 'private', got {mode!r}")
        api_key = os.environ.get(f"{prefix}_API_KEY", "")
        base_url = os.environ.get(f"{prefix}_BASE_URL", "")
        model = os.environ.get(f"{prefix}_ID", "")
        missing = [n for n, v in ((f"{prefix}_API_KEY", api_key), (f"{prefix}_BASE_URL", base_url), (f"{prefix}_ID", model)) if not v]
        if missing:
            raise SystemExit(f"Missing in .env for {mode} mode: {', '.join(missing)}")
        tiers = tuple(t for t in (os.environ.get("MODEL_TIER_2_ID", ""), os.environ.get("MODEL_TIER_3_ID", "")) if t) \
            if mode == "hosted" else ()
        return cls(
            mode=mode,
            base_url=base_url,
            api_key=api_key,
            model=model,
            tiers=tiers,
            escalation_max_calls=int(os.environ.get("MODEL_ESCALATION_MAX_CALLS", "12")),
            escalation_max_usd=float(os.environ.get("MODEL_ESCALATION_MAX_USD", "0.50")),
            breaker_tier=int(os.environ.get("MODEL_TIER_BREAKER", "2")),
            after_break_tier=int(os.environ.get("MODEL_TIER_AFTER_BREAK", "2")),
            reasoning_effort=os.environ.get("MODEL_REASONING_EFFORT", "medium"),
            max_calls_per_run=int(os.environ.get("MODEL_MAX_CALLS_PER_RUN", "60")),
            max_calls_per_round=int(os.environ.get("MODEL_MAX_CALLS_PER_ROUND", "20")),
            max_rounds=int(os.environ.get("MODEL_MAX_ROUNDS", "3")),
            max_attack_rounds=int(os.environ.get("MODEL_MAX_ATTACK_ROUNDS", "3")),
            max_breaker_cycles=int(os.environ.get("MODEL_MAX_BREAKER_CYCLES", "1")),
        )

    def for_crosscheck(self) -> "Settings | None":
        """Settings for the independent cross-check: Muse Spark Open on its own host with its own hard call cap.
        CROSSCHECK_MODEL_* wins; OPEN_MODEL_* is the fallback. None when nothing is configured, or when this run is
        already on the open model (a model cannot independently check itself)."""
        if self.mode == "private":
            return None
        load_dotenv()
        pick = lambda name: os.environ.get(f"CROSSCHECK_MODEL_{name}") or os.environ.get(f"OPEN_MODEL_{name}", "")
        api_key, base_url, model = pick("API_KEY"), pick("BASE_URL"), pick("ID")
        if not (api_key and base_url and model):
            return None
        return replace(
            self, mode="private", base_url=base_url, api_key=api_key, model=model,
            reasoning_effort=os.environ.get("CROSSCHECK_REASONING_EFFORT", self.reasoning_effort),
            max_calls_per_run=int(os.environ.get("CROSSCHECK_MAX_CALLS", "2")),
        )

    @classmethod
    def guard_from_env(cls) -> "Settings | None":
        """The guard agent's own model and key (GUARD_MODEL_*), separate from the agents it checks; None when not set."""
        load_dotenv()
        api_key = os.environ.get("GUARD_MODEL_API_KEY", "")
        base_url = os.environ.get("GUARD_MODEL_BASE_URL", "")
        model = os.environ.get("GUARD_MODEL_ID", "")
        if not (api_key and base_url and model):
            return None
        try:
            max_calls = int(os.environ.get("GUARD_MAX_CALLS", "2"))
        except ValueError:  # a bad cap degrades to the policy-only guard instead of crashing the run
            return None
        return cls(
            mode="private" if "muse-spark-open" in model else "hosted",
            base_url=base_url,
            api_key=api_key,
            model=model,
            reasoning_effort=os.environ.get("GUARD_REASONING_EFFORT", "medium"),
            max_calls_per_run=max_calls,
            max_calls_per_round=1,
            max_rounds=1,
        )

    def tier_model(self, tier: int) -> str | None:
        """The model for tier 1 (the default: None), 2 or 3; the highest configured tier if `tier` is above it."""
        if tier <= 1 or not self.tiers:
            return None
        return self.tiers[min(tier - 2, len(self.tiers) - 1)]
