"""Layout-aware conversion between mainframe EBCDIC records and the bytes GnuCOBOL (-std=ibm) reads and writes.

Converting a whole record as text corrupts packed and binary fields, so each field is handled by its type:
- alphanumeric and sign characters: code page translation (default cp037);
- zoned decimal (DISPLAY numeric): EBCDIC digits F0-F9, with the sign in the zone nibble of the last (or first)
  byte (C/F positive, D negative), become ASCII digits with GnuCOBOL's overpunch (negative digit + 0x40);
- packed (COMP-3) and binary (COMP/COMP-4/BINARY) bytes are identical on both sides and pass through unchanged;
- COMP-5 is native binary: big-endian on z/OS, little-endian here, so its bytes are reversed;
- COMP-1/COMP-2 are IBM hexadecimal floating point on z/OS and IEEE 754 here; values are converted, and the
  conversion is exact only when the value fits IEEE precision (HFP long has 56 fraction bits, IEEE double 53).
"""

from __future__ import annotations

import struct
from decimal import Decimal

from .layout import Field


def hfp_to_float(data: bytes) -> float:
    """IBM hexadecimal floating point (4 or 8 bytes, big-endian) to a Python float."""
    if not any(data):
        return 0.0
    sign = -1.0 if data[0] & 0x80 else 1.0
    exponent = (data[0] & 0x7F) - 64
    fraction = int.from_bytes(data[1:], "big") / float(1 << (8 * (len(data) - 1)))
    return sign * fraction * 16.0**exponent


def float_to_hfp(value: float, size: int = 8) -> bytes:
    """Python float to IBM hexadecimal floating point (rounded to the HFP fraction width)."""
    if value == 0:
        return bytes(size)
    sign = 0x80 if value < 0 else 0
    value = abs(value)
    exponent = 0
    while value >= 1:
        value /= 16
        exponent += 1
    while value < 1 / 16:
        value *= 16
        exponent -= 1
    bits = 8 * (size - 1)
    fraction = round(value * (1 << bits))
    if fraction >= 1 << bits:  # rounding carried into a new hex digit
        fraction >>= 4
        exponent += 1
    return bytes([sign | (exponent + 64)]) + fraction.to_bytes(size - 1, "big")


def _zoned_to_ascii(f: Field, raw: bytes, codepage: str) -> bytes:
    if f.sign.endswith("separate"):
        return raw.decode(codepage).encode("latin-1")
    sign_at = -1 if f.sign == "trailing" else 0 if f.sign == "leading" else None
    digits = bytearray(b"0123456789"[b & 0x0F] for b in raw)
    if sign_at is not None and f.signed and raw and (raw[sign_at] >> 4) == 0xD:
        digits[sign_at] += 0x40  # GnuCOBOL ASCII overpunch for a negative digit
    return bytes(digits)


def _zoned_to_ebcdic(f: Field, raw: bytes, codepage: str) -> bytes:
    if f.sign.endswith("separate"):
        return raw.decode("latin-1").encode(codepage)
    out = bytearray()
    for i, b in enumerate(raw):
        negative = 0x70 <= b <= 0x79
        digit = (b - 0x40 if negative else b) - 0x30
        sign_position = (i == len(raw) - 1 and f.sign == "trailing") or (i == 0 and f.sign == "leading")
        zone = (0xD if negative else 0xC) if (f.signed and sign_position) else 0xF
        out.append((zone << 4) | digit)
    return bytes(out)


def _float(f: Field, raw: bytes, to_mainframe: bool) -> bytes:
    fmt = "<f" if f.length == 4 else "<d"
    if to_mainframe:
        return float_to_hfp(struct.unpack(fmt, raw)[0], f.length)
    return struct.pack(fmt, hfp_to_float(raw))


def convert_record(record: bytes, fields: list[Field], *, to_mainframe: bool = False, codepage: str = "cp037") -> bytes:
    """Convert one record between EBCDIC/mainframe storage and GnuCOBOL storage, field by field."""
    out, pos = bytearray(), 0
    for f in fields:
        raw = record[pos : pos + f.length]
        pos += f.length
        if f.kind == "alnum":
            out += raw.decode("latin-1").encode(codepage) if to_mainframe else raw.decode(codepage).encode("latin-1")
        elif f.usage == "display":
            out += _zoned_to_ebcdic(f, raw, codepage) if to_mainframe else _zoned_to_ascii(f, raw, codepage)
        elif f.usage == "binary-native":
            out += raw[::-1]
        elif f.usage == "float":
            out += _float(f, raw, to_mainframe)
        else:  # packed and big-endian binary are the same bytes on both platforms
            out += raw
    return bytes(out)


def convert_file(data: bytes, fields: list[Field], record_length: int, **kw) -> list[bytes]:
    """Fixed-length mainframe file (RECFM=FB) to a list of converted records."""
    return [convert_record(data[i : i + record_length], fields, **kw) for i in range(0, len(data), record_length)]


def decimal_from_hfp(data: bytes) -> Decimal:
    """Exact decimal value of an HFP number (useful to show what a mainframe COMP-2 really held)."""
    if not any(data):
        return Decimal(0)
    sign = -1 if data[0] & 0x80 else 1
    exponent = (data[0] & 0x7F) - 64
    fraction = Decimal(int.from_bytes(data[1:], "big")) / Decimal(1 << (8 * (len(data) - 1)))
    return sign * fraction * Decimal(16) ** exponent
