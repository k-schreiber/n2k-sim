"""Little-endian N2K field packers.

Every packer takes a physical value and a resolution (`scale`, physical units per bit), rounds to
the field resolution, clamps to the valid range and returns the bytes. ``None`` (or NaN/inf)
yields the field's "not available" sentinel. Reserved bytes are 0xFF.
"""

from __future__ import annotations

import math
import struct

TWO_PI = 2.0 * math.pi
RESERVED_BYTE = 0xFF
# The top three codes of every field are reserved (error/out of range/not available).
_MARGIN = 3


def reserved(n: int = 1) -> bytes:
    """Returns n reserved bytes (0xFF)."""
    return b"\xff" * n


def _round(x: float) -> int:
    return math.floor(x + 0.5)


def _pack_int(value, scale: float, bits: int, signed: bool, fmt: str) -> bytes:
    """Rounds, clamps and packs one integer field; the NA sentinel is the maximum code."""
    size = bits // 8
    if signed:
        na, lo = (1 << (bits - 1)) - 1, -(1 << (bits - 1))
    else:
        na, lo = (1 << bits) - 1, 0
    if value is None or not math.isfinite(value):
        raw = na
    else:
        raw = max(lo, min(na - _MARGIN, _round(value / scale)))
    if size == 3:
        return (raw & 0xFFFFFF).to_bytes(3, "little")
    return struct.pack("<" + fmt, raw)


def u8(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 8, False, "B")


def i8(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 8, True, "b")


def u16(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 16, False, "H")


def i16(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 16, True, "h")


def u24(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 24, False, "")


def u32(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 32, False, "I")


def i32(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 32, True, "i")


def i64(value, scale: float = 1.0) -> bytes:
    return _pack_int(value, scale, 64, True, "q")


def angle_u16(rad) -> bytes:
    """Angle 0..2π in 0.0001 rad (wrapped)."""
    if rad is None or not math.isfinite(rad):
        return u16(None)
    return u16(min(rad % TWO_PI, 6.2831), 1e-4)


def angle_i16(rad) -> bytes:
    """Angle ±π in 0.0001 rad (wrapped)."""
    if rad is None or not math.isfinite(rad):
        return i16(None)
    return i16((rad + math.pi) % TWO_PI - math.pi, 1e-4)


def speed_u16(mps) -> bytes:
    """Speed in 0.01 m/s."""
    return u16(mps, 0.01)


def temp_u16_K(kelvin) -> bytes:
    """Temperature in 0.01 K."""
    return u16(kelvin, 0.01)


def date_u16(epoch) -> bytes:
    """Days since 1970-01-01 UTC from UNIX epoch seconds."""
    if epoch is None or not math.isfinite(epoch):
        return u16(None)
    return u16(math.floor(epoch / 86400.0))


def time_u32(epoch) -> bytes:
    """Time of day in 0.0001 s since midnight UTC from UNIX epoch seconds."""
    if epoch is None or not math.isfinite(epoch):
        return u32(None)
    return u32(epoch % 86400.0, 1e-4)
