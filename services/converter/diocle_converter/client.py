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
    _sdk: object = None

    def __post_init__(self) -> None:
        if self._sdk is None:
            from openai import OpenAI

            self._sdk = OpenAI(base_url=self.settings.base_url, api_key=self.settings.api_key, max_retries=0)

    def chat(self, *, role: str, round: int, messages: list[dict], tools=None, response_format=None):
        if len(self.calls) >= self.settings.max_calls_per_run:
            raise BudgetExceeded(f"model call cap reached ({self.settings.max_calls_per_run} per run)")
        kwargs = {"model": self.settings.model, "messages": messages, "reasoning_effort": self.settings.reasoning_effort}
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format
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
                model=self.settings.model,
                inputTokens=usage.prompt_tokens if usage else 0,
                cachedInputTokens=(getattr(prompt_details, "cached_tokens", None) or 0) if prompt_details else 0,
                outputTokens=usage.completion_tokens if usage else 0,
                reasoningTokens=(getattr(details, "reasoning_tokens", None) or 0) if details else 0,
                latencyMs=int((time.monotonic() - started) * 1000),
            )
        )
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

    def usage_summary(self) -> dict:
        return usage_of(self.calls)


def _call_cost(c: ModelCall) -> float | None:
    price = PRICES.get(c.model)
    if price is None:
        return None
    return ((c.inputTokens - c.cachedInputTokens) * price[0] + c.cachedInputTokens * price[1] + c.outputTokens * price[2]) / 1e6


def usage_of(calls: list[ModelCall]) -> dict:
    """Token use and estimated cost of a set of calls, priced per call: the guard's model can differ from the agents'.
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
