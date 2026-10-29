"""Meta model client (OpenAI-compatible Chat Completions) with call logging, retries and hard call caps."""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field

from .config import PRICES, Settings


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ModelCall:
    role: str
    round: int
    mode: str
    model: str
    inputTokens: int
    cachedInputTokens: int
    outputTokens: int
    reasoningTokens: int
    latencyMs: int


@dataclass
class ModelClient:
    settings: Settings
    calls: list[ModelCall] = field(default_factory=list)
    escalated_calls: int = 0  # calls made with a higher tier's model, counted here (not inferred from the model ID)
    escalated_usd: float = 0.0  # their cost; an unpriced model counts as the whole cap (fail closed)
    escalated_max_call_usd: float = 0.0  # the dearest single escalated call so far, to project the next one
    _sdk: object = None

    def __post_init__(self) -> None:
        if self._sdk is None:
            from openai import OpenAI

            self._sdk = OpenAI(base_url=self.settings.base_url, api_key=self.settings.api_key, max_retries=0)

    def escalation_exhausted(self) -> bool:
        """True once calls made on a higher tier (chat(model=...)) hit their own caps: a call count and a dollar amount."""
        # Projected: another call like the dearest one so far must still fit, so one large call cannot blow far past the cap.
        return (self.escalated_calls >= self.settings.escalation_max_calls
                or self.escalated_usd + self.escalated_max_call_usd > self.settings.escalation_max_usd
                or self.escalated_usd >= self.settings.escalation_max_usd)

    def chat(self, *, role: str, round: int, messages: list[dict], tools=None, response_format=None, model: str | None = None,
             max_tokens: int | None = None):
        """model: a higher tier's ID for this one call (the same host and key); None is the run's default model."""
        if len(self.calls) >= self.settings.max_calls_per_run:
            raise BudgetExceeded(f"model call cap reached ({self.settings.max_calls_per_run} per run)")
        escalated = bool(model and model != self.settings.model)
        if escalated and self.escalation_exhausted():
            raise BudgetExceeded(f"escalation cap reached ({self.settings.escalation_max_calls} calls or "
                                 f"${self.settings.escalation_max_usd:.2f} per run on tiers above the default)")
        model = model or self.settings.model
        kwargs = {"model": model, "messages": messages, "reasoning_effort": self.settings.reasoning_effort}
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        started = time.monotonic()
        response = self._with_retries(kwargs)
        usage = response.usage
        details = getattr(usage, "completion_tokens_details", None)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        self.calls.append(
            ModelCall(
                role=role,
                round=round,
                mode=self.settings.mode,
                model=model,
                inputTokens=usage.prompt_tokens if usage else 0,
                cachedInputTokens=(getattr(prompt_details, "cached_tokens", None) or 0) if prompt_details else 0,
                outputTokens=usage.completion_tokens if usage else 0,
                reasoningTokens=(getattr(details, "reasoning_tokens", None) or 0) if details else 0,
                latencyMs=int((time.monotonic() - started) * 1000),
            )
        )
        if escalated:
            cost = _call_cost(self.calls[-1])
            self.escalated_calls += 1
            cost = self.settings.escalation_max_usd if cost is None else cost
            self.escalated_usd += cost
            self.escalated_max_call_usd = max(self.escalated_max_call_usd, cost)
        return response.choices[0]

    def _with_retries(self, kwargs: dict, attempts: int = 4):
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        for attempt in range(attempts):
            try:
                return self._sdk.chat.completions.create(**kwargs)
            except APIStatusError as e:
                retryable = e.status_code == 429 or e.status_code >= 500
                if not retryable or attempt == attempts - 1:
                    raise
            except (APIConnectionError, APITimeoutError):
                if attempt == attempts - 1:
                    raise
            time.sleep(min(30, 2**attempt) + random.random())

    @staticmethod
    def _call_cost(c: ModelCall) -> float | None:
        """USD for one call at its own model's list price (a run can mix Muse Spark and Muse Spark Open)."""
        price = PRICES.get(c.model)
        return ((c.inputTokens - c.cachedInputTokens) * price[0] + c.cachedInputTokens * price[1] + c.outputTokens * price[2]) / 1e6 if price else None

    def usage_summary(self) -> dict:
        return usage_of(self.calls)


def _call_cost(c: ModelCall) -> float | None:
    """USD for one call at its own model's list price (a run can mix Muse Spark and Muse Spark Open)."""
    price = PRICES.get(c.model)
    if price is None:
        return None
    return ((c.inputTokens - c.cachedInputTokens) * price[0] + c.cachedInputTokens * price[1] + c.outputTokens * price[2]) / 1e6


def usage_of(calls: list[ModelCall]) -> dict:
    """Token use and estimated cost of a set of calls, priced per call by its own model.
    The cost is None when any call's model has no known price."""
    input_tokens = sum(c.inputTokens for c in calls)
    cached_tokens = sum(c.cachedInputTokens for c in calls)
    output_tokens = sum(c.outputTokens for c in calls)
    costs = [_call_cost(c) for c in calls]
    cost = None if any(x is None for x in costs) else sum(costs)
    return {
        "calls": len(calls),
        "inputTokens": input_tokens,
        "cachedInputTokens": cached_tokens,
        "outputTokens": output_tokens,
        "estimatedCostUsd": round(cost, 6) if cost is not None else None,
        "modelCalls": [asdict(c) for c in calls],
    }
