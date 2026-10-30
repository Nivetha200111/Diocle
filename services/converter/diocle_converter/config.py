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

# Muse Voice Transcribe is billed by audio duration, not tokens. USD per SECOND of audio. UNCONFIRMED: Meta publishes no
# price we could find and the service returns no usage field, so this is a conservative placeholder (about twice a typical
# speech-to-text list price, $0.72 per hour). The second field says whether the price is confirmed; while it is False
# every result shows `priceConfirmed: false`. A model missing from this table is unpriced and fails closed (no call).
VOICE_PRICES = {
    "muse-voice-transcribe-1.0": (0.0002, False),
}


@dataclass(frozen=True)
class DocCaps:
    """Hard limits (rule 10) of one verified-documentation run. Reasoning tokens bill as output, so output is capped."""
    max_calls: int = 2
    max_usd: float = 0.10
    max_output_tokens: int = 9000


def _tier_from_env(name: str, default: int = 2) -> int:
    """A tier number (1 to 3) from the environment; a missing, empty or non-numeric value means the default, so a typo
    in an optional tuning knob cannot crash a run. Numbers outside 1-3 are clamped."""
    try:
        return max(1, min(3, int(os.environ.get(name, "") or default)))
    except ValueError:
        return default


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
    # Convert-anyway: a hard dollar cap for this client's calls (the delivery passes what is left of REPO_MAX_USD). None = off.
    # An unpriced model counts as over the cap (fail closed).
    max_usd: float | None = None

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
            breaker_tier=_tier_from_env("MODEL_TIER_BREAKER"),
            after_break_tier=_tier_from_env("MODEL_TIER_AFTER_BREAK"),
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

    def for_document(self) -> tuple["Settings", "DocCaps"]:
        """Settings and hard caps for the verified-documentation call (--document): the run's own host, key and model
        (the cheap contributor model in hosted mode by default) unless DOC_MODEL_ID / DOC_MODEL_BASE_URL / DOC_MODEL_API_KEY say otherwise.
        Raises ValueError for a malformed cap; the caller skips the feature rather than failing the run."""
        load_dotenv()
        caps = DocCaps(max_calls=int(os.environ.get("DOC_MAX_CALLS", "2")), max_usd=float(os.environ.get("DOC_MAX_USD", "0.10")),
                       max_output_tokens=int(os.environ.get("DOC_MAX_OUTPUT_TOKENS", "9000")))
        if min(caps.max_calls, caps.max_output_tokens) < 1 or caps.max_usd <= 0:
            raise ValueError("DOC_* caps must be positive")
        return replace(
            self, model=os.environ.get("DOC_MODEL_ID") or self.model,
            base_url=os.environ.get("DOC_MODEL_BASE_URL") or self.base_url,
            api_key=os.environ.get("DOC_MODEL_API_KEY") or self.api_key,
            reasoning_effort=os.environ.get("DOC_REASONING_EFFORT", "low"),
            max_calls_per_run=caps.max_calls, max_calls_per_round=caps.max_calls,
        ), caps

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

    @classmethod
    def vision_from_env(cls) -> "Settings | None":
        """The vision model for printout transcription (VISION_MODEL_ID). Empty ID = feature off (None). The host and key
        fall back to the hosted META_MODEL_* ones, because Muse Wonder is served on the same Meta Model API key."""
        load_dotenv()
        model = os.environ.get("VISION_MODEL_ID", "")
        base_url = os.environ.get("VISION_MODEL_BASE_URL") or os.environ.get("META_MODEL_BASE_URL", "")
        api_key = os.environ.get("VISION_MODEL_API_KEY") or os.environ.get("META_MODEL_API_KEY", "")
        if not (model and base_url and api_key):
            return None
        try:
            max_calls = max(1, int(os.environ.get("VISION_MAX_CALLS", "3")))
        except ValueError:
            max_calls = 3
        return cls(mode="hosted", base_url=base_url, api_key=api_key, model=model,
                   reasoning_effort=os.environ.get("VISION_REASONING_EFFORT", "low"),
                   max_calls_per_run=max_calls, max_calls_per_round=max_calls, max_rounds=1)

    def tier_model(self, tier: int) -> str | None:
        """The model for tier 1 (the default: None), 2 or 3; the highest configured tier if `tier` is above it. Tier
        numbers compact over what is configured: with only MODEL_TIER_3_ID set it is tier 2. Zero or less is tier 1."""
        if tier <= 1 or not self.tiers:
            return None
        return self.tiers[min(tier - 2, len(self.tiers) - 1)]
