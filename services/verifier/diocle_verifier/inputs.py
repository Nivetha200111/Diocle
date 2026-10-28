"""Deterministic test-input generation from a record layout: PIC boundaries plus seeded random values."""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from .layout import Field, format_record


@dataclass(frozen=True)
class Case:
    id: str
    source: str  # "boundary" | "random"
    record: str


def _boundaries(f: Field) -> list[Decimal | str]:
    if f.kind == "alnum":
        return list(f.values) + [" " * f.length] if f.values else []
    values = [Decimal(0), f.unit, f.max_value]
    if f.digits > 0:
        values.append(Decimal(1))
    if f.signed:
        values += [-v for v in values if v != 0]
    return values


def _random_value(f: Field, rng: random.Random, index: int) -> Decimal | str:
    if f.kind == "alnum":
        if f.values:
            return rng.choice(f.values)
        return f"C{index:0{f.length - 1}d}"[-f.length :]
    # Log-uniform magnitude so small and large values are both common.
    total_digits = f.digits + f.scale
    width = rng.randint(1, total_digits)
    magnitude = rng.randint(0, 10**width - 1)
    value = Decimal(magnitude).scaleb(-f.scale)
    if f.signed and rng.random() < 0.3:
        value = -value
    return value


def generate_cases(fields: list[Field], *, seed: int = 1026, random_count: int = 200) -> list[Case]:
    rng = random.Random(seed)
    cases: list[Case] = []

    def add(source: str, values: dict) -> None:
        index = len(cases) + 1
        values = {
            f.name: (f"C{index:0{f.length - 1}d}"[-f.length :] if f.kind == "alnum" and not f.values else values[f.name])
            for f in fields
        }
        cases.append(Case(f"case-{index:04d}", source, format_record(values, fields)))

    base = {f.name: _random_value(f, rng, 0) for f in fields}
    for f in fields:
        for value in _boundaries(f):
            add("boundary", {**base, f.name: value})
    extremes = [lambda f: f.max_value] + ([lambda f: -f.max_value] if any(f.signed for f in fields) else [])
    for extreme in extremes:
        add("boundary", {f.name: (extreme(f) if f.kind == "numeric" and (f.signed or extreme(f) > 0) else base[f.name]) for f in fields})
    for _ in range(random_count):
        add("random", {f.name: _random_value(f, rng, len(cases) + 1) for f in fields})
    return cases
