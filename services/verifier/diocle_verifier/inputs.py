"""Deterministic test-input generation from a record layout: PIC boundaries plus seeded random values."""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from .layout import Field, format_record, format_value, load_fields, redefine_views


@dataclass(frozen=True)
class Case:
    id: str
    source: str  # "boundary" | "random"
    record: str


def _boundaries(f: Field) -> list[Decimal | str]:
    if f.kind == "alnum":
        return list(f.values) + [" " * f.length] if f.values else []
    values = [Decimal(0), f.unit, f.max_value]
    if f.digits > 0 and f.scale >= 0:  # 1 is not representable in a P-scaled field
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


def _with_view(record: str, values: dict, fields: list[Field], views: dict[str, list[list[Field]]], rng: random.Random) -> str:
    """The record with each redefined body filled through one of its views, so its numbers carry real values. When the
    field before the body lists as many values as there are views (CQ-TYPE 'C', 'R'; two bodies), they are paired in
    declaration order, as a record-type byte and its layouts usually are; otherwise the view is chosen at random."""
    offset = 0
    for i, f in enumerate(fields):
        options = views.get(f.name)
        if options:
            kind = fields[i - 1] if i else None
            paired = kind is not None and len(kind.values) == len(options) and values.get(kind.name) in kind.values
            view = options[kind.values.index(values[kind.name])] if paired else rng.choice(options)
            body = "".join(format_value(v, " " * v.length if v.name == "FILLER" else _random_value(v, rng, rng.randrange(10**6)))
                           for v in view)
            record = record[:offset] + body + record[offset + f.length :]
        offset += f.length
    return record


def generate_cases(fields: list[Field], *, seed: int = 1026, random_count: int = 200,
                   views: dict[str, list[list[Field]]] | None = None) -> list[Case]:
    """views (layout.redefine_views): random records fill those bodies with real values. Their random numbers come from a
    separate stream, so a layout without views gets exactly the records it always got."""
    rng = random.Random(seed)
    view_rng = random.Random(f"views:{seed}")
    cases: list[Case] = []

    def add(source: str, values: dict) -> None:
        index = len(cases) + 1
        values = {
            f.name: (f"C{index:0{f.length - 1}d}"[-f.length :] if f.kind == "alnum" and not f.values else values[f.name])
            for f in fields
        }
        record = format_record(values, fields)
        if views and source == "random":
            record = _with_view(record, values, fields, views, view_rng)
        cases.append(Case(f"case-{index:04d}", source, record))

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


def generate_for_layout(spec: dict, *, seed: int = 1026, random_count: int = 200) -> list[Case]:
    """generate_cases for one record layout, REDEFINES views included."""
    return generate_cases(load_fields(spec), seed=seed, random_count=random_count, views=redefine_views(spec))
