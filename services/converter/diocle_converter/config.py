"""Settings from the environment and the repo-root .env (keys are never logged)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# USD per million tokens (input, cached input, output), from dev.meta.ai and fireworks.ai pricing, 2026-10-28.
# Reasoning tokens bill as output.
PRICES = {
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "accounts/fireworks/models/muse-spark-open": (1.25, 0.15, 4.25),  # Fireworks serverless
    "meta-models/muse-spark-open-1026": (1.25, 0.15, 4.25),  # Baseten (same list price as Fireworks)
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
        return cls(
            mode=mode,
            base_url=base_url,
            api_key=api_key,
            model=model,
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
