"""Fixed-width record layouts (display-format fields from COBOL copybooks)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # "alnum" or "numeric"
    length: int
    digits: int = 0  # integer digits, numeric only
    scale: int = 0  # decimal digits, numeric only
    signed: bool = False
    values: tuple[str, ...] = ()

    @property
    def max_value(self) -> Decimal:
        return Decimal(10**self.digits * 10**self.scale - 1).scaleb(-self.scale)

    @property
    def unit(self) -> Decimal:
        return Decimal(1).scaleb(-self.scale)


def load_fields(spec: dict) -> list[Field]:
    fields = []
    for f in spec["fields"]:
        if f["kind"] == "alnum":
            fields.append(Field(f["name"], "alnum", f["length"], values=tuple(f.get("values", ()))))
        elif f["kind"] == "numeric":
            signed = f.get("signed", False)
            if signed and f.get("sign") != "leading-separate":
                raise ValueError(f"{f['name']}: only SIGN LEADING SEPARATE is supported for signed fields")
            length = f["digits"] + f["scale"] + (1 if signed else 0)
            fields.append(Field(f["name"], "numeric", length, f["digits"], f["scale"], signed))
        else:
            raise ValueError(f"{f['name']}: unsupported field kind {f['kind']!r}")
    return fields


def record_length(fields: list[Field]) -> int:
    return sum(f.length for f in fields)


def parse_record(line: str, fields: list[Field]) -> dict[str, Decimal | str]:
    """Split a record into field values. Numerics become Decimal; unparseable numerics stay raw strings."""
    line = line.rstrip("\r\n").ljust(record_length(fields))
    values: dict[str, Decimal | str] = {}
    pos = 0
    for f in fields:
        raw = line[pos : pos + f.length]
        pos += f.length
        if f.kind == "alnum":
            values[f.name] = raw
            continue
        try:
            values[f.name] = Decimal(raw).scaleb(-f.scale)
        except InvalidOperation:
            values[f.name] = raw
    return values


def format_value(f: Field, value: Decimal | str) -> str:
    if f.kind == "alnum":
        return str(value)[: f.length].ljust(f.length)
    value = Decimal(value)
    if abs(value) > f.max_value or (value < 0 and not f.signed):
        raise ValueError(f"{f.name}: {value} does not fit")
    digits = str(int(abs(value).scaleb(f.scale))).zfill(f.digits + f.scale)
    return ("-" if value < 0 else "+") + digits if f.signed else digits


def format_record(values: dict[str, Decimal | str], fields: list[Field]) -> str:
    return "".join(format_value(f, values[f.name]) for f in fields)
