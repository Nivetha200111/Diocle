"""Fixed-width record layouts from COBOL copybooks, byte for byte as GnuCOBOL (-std=ibm) stores them.

Records are handled as latin-1 strings: one character per byte, so packed and binary fields round-trip exactly.
Display numerics: unsigned, SIGN LEADING/TRAILING SEPARATE, and overpunch (sign carried in the first or last digit;
GnuCOBOL's ASCII convention writes a negative digit d as chr(ord(d) + 0x40), i.e. 'p'..'y').
Other usages: packed (COMP-3), binary (COMP/COMP-4/BINARY, big-endian), binary-native (COMP-5, little-endian here),
float (COMP-1/COMP-2, IEEE little-endian). P scaling is a negative scale: PIC 9(3)PP has digits 5, scale -2.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_EBCDIC_POSITIVE = "{ABCDEFGHI"  # overpunch as it arrives from EBCDIC files converted to ASCII; accepted when reading
_EBCDIC_NEGATIVE = "}JKLMNOPQR"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # "alnum" or "numeric"
    length: int  # bytes in the record
    digits: int = 0  # integer digit positions (including P scaling positions), numeric only
    scale: int = 0  # decimal digits; negative for P scaling
    signed: bool = False
    values: tuple[str, ...] = ()
    sign: str = ""  # leading-separate | trailing-separate | trailing | leading (overpunch)
    usage: str = "display"  # display | packed | binary | binary-native | float

    @property
    def stored_digits(self) -> int:
        return self.digits + self.scale

    @property
    def max_value(self) -> Decimal:
        if self.usage == "float":
            return Decimal("1E15")
        return Decimal(10**self.stored_digits - 1).scaleb(-self.scale)

    @property
    def unit(self) -> Decimal:
        return Decimal(1).scaleb(-self.scale)


def _binary_size(stored: int) -> int:
    return 2 if stored <= 4 else 4 if stored <= 9 else 8


def load_fields(spec: dict) -> list[Field]:
    fields = []
    for f in spec["fields"]:
        if f.get("redefines"):
            continue  # an alternative view of bytes another field already covers
        if f["kind"] == "alnum":
            fields.append(Field(f["name"], "alnum", f["length"], values=tuple(f.get("values", ()))))
            continue
        if f["kind"] != "numeric":
            raise ValueError(f"{f['name']}: unsupported field kind {f['kind']!r}")
        usage = f.get("usage", "display")
        signed = f.get("signed", False)
        sign = f.get("sign") or ("trailing" if signed and usage == "display" else "")
        if signed and usage == "display" and sign not in ("leading-separate", "trailing-separate", "trailing", "leading"):
            raise ValueError(f"{f['name']}: unsupported sign {sign!r}")
        stored = f["digits"] + f["scale"]
        if usage == "display":
            length = stored + (1 if sign.endswith("separate") else 0)
        elif usage == "packed":
            length = stored // 2 + 1
        elif usage in ("binary", "binary-native"):
            length = _binary_size(stored)
        elif usage == "float":
            length = f.get("bytes", 8)
        else:
            raise ValueError(f"{f['name']}: unsupported usage {usage!r}")
        fields.append(Field(f["name"], "numeric", length, f["digits"], f["scale"], signed, (), sign, usage))
    return fields


def record_length(fields: list[Field]) -> int:
    return sum(f.length for f in fields)


def record_format(spec: dict) -> str:
    return spec.get("format", "line")


def _hex(raw: str) -> str:
    return "x'" + raw.encode("latin-1").hex().upper() + "'"


def _parse_display(f: Field, raw: str) -> Decimal:
    negative = False
    if f.sign == "leading-separate":
        negative, raw = raw[:1] == "-", raw[1:]
    elif f.sign == "trailing-separate":
        negative, raw = raw[-1:] == "-", raw[:-1]
    elif f.sign in ("trailing", "leading"):
        i = -1 if f.sign == "trailing" else 0
        ch = raw[i]
        if "p" <= ch <= "y":
            negative, ch = True, chr(ord(ch) - 0x40)
        elif ch in _EBCDIC_NEGATIVE:
            negative, ch = True, str(_EBCDIC_NEGATIVE.index(ch))
        elif ch in _EBCDIC_POSITIVE:
            ch = str(_EBCDIC_POSITIVE.index(ch))
        raw = raw[:-1] + ch if i == -1 else ch + raw[1:]
    if not raw.isdigit():
        raise InvalidOperation
    value = Decimal(int(raw)).scaleb(-f.scale)
    return -value if negative else value


def _parse_packed(f: Field, raw: str) -> Decimal:
    nibbles = raw.encode("latin-1").hex()
    digits, sign = nibbles[:-1], nibbles[-1]
    if not digits.isdigit() or sign not in "abcdef":
        raise InvalidOperation
    value = Decimal(int(digits)).scaleb(-f.scale)
    return -value if sign in "bd" else value


def _parse_value(f: Field, raw: str) -> Decimal:
    if f.usage == "display":
        return _parse_display(f, raw)
    if f.usage == "packed":
        return _parse_packed(f, raw)
    data = raw.encode("latin-1")
    if f.usage in ("binary", "binary-native"):
        order = "big" if f.usage == "binary" else "little"
        return Decimal(int.from_bytes(data, order, signed=f.signed)).scaleb(-f.scale)
    value = struct.unpack("<f" if f.length == 4 else "<d", data)[0]
    return Decimal(repr(value))


def parse_record(line: str, fields: list[Field]) -> dict[str, Decimal | str]:
    """Split a record into field values. Numerics become Decimal; unparseable numerics stay raw (hex if not text)."""
    line = line.rstrip("\r\n").ljust(record_length(fields)) if all(f.usage == "display" for f in fields) else line
    values: dict[str, Decimal | str] = {}
    pos = 0
    for f in fields:
        raw = line[pos : pos + f.length]
        pos += f.length
        if f.kind == "alnum":
            values[f.name] = raw
            continue
        try:
            values[f.name] = _parse_value(f, raw)
        except (InvalidOperation, ValueError, IndexError, struct.error):
            values[f.name] = raw if raw.isprintable() else _hex(raw)
    return values


def _digits(f: Field, value: Decimal) -> str:
    return str(int(abs(value).scaleb(f.scale))).zfill(f.stored_digits)


def format_value(f: Field, value: Decimal | str) -> str:
    if f.kind == "alnum":
        return str(value)[: f.length].ljust(f.length)
    value = Decimal(value)
    if f.usage == "float":
        return struct.pack("<f" if f.length == 4 else "<d", float(value)).decode("latin-1")
    if abs(value) > f.max_value or (value < 0 and not f.signed):
        raise ValueError(f"{f.name}: {value} does not fit")
    if (value / f.unit) != (value / f.unit).to_integral_value():
        raise ValueError(f"{f.name}: {value} has more precision than the PIC holds")
    negative = value < 0
    if f.usage == "packed":
        nibbles = _digits(f, value)
        if len(nibbles) % 2 == 0:
            nibbles = "0" + nibbles
        return bytes.fromhex(nibbles + ("d" if negative else "c" if f.signed else "f")).decode("latin-1")
    if f.usage in ("binary", "binary-native"):
        number = int(value.scaleb(f.scale))
        order = "big" if f.usage == "binary" else "little"
        return number.to_bytes(f.length, order, signed=f.signed).decode("latin-1")
    digits = _digits(f, value)
    if not f.signed:
        return digits
    if f.sign == "leading-separate":
        return ("-" if negative else "+") + digits
    if f.sign == "trailing-separate":
        return digits + ("-" if negative else "+")
    if f.sign == "trailing":
        return digits[:-1] + (chr(ord(digits[-1]) + 0x40) if negative else digits[-1])
    return (chr(ord(digits[0]) + 0x40) if negative else digits[0]) + digits[1:]


def format_record(values: dict[str, Decimal | str], fields: list[Field]) -> str:
    return "".join(format_value(f, values[f.name]) for f in fields)
