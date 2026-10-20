"""Environmental PGNs: 130310-130314 and 130316."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals

PERCENT = 0.004  # humidity resolution
SRC_SEA, SRC_OUTSIDE, SRC_CABIN, SRC_DEW_POINT = 0, 1, 4, 9


def _sid(sid: int) -> bytes:
    return bytes([sid & 0xFF])


def _hpa(pa) -> float | None:
    return None if pa is None else pa / 100.0


def encode_130310(s: Signals, sid: int) -> list[bytes]:
    """Environmental parameters (obsolete): water temp, air temp, pressure in hPa."""
    return [
        _sid(sid)
        + f.temp_u16_K(s.get("water_temp"))
        + f.temp_u16_K(s.get("air_temp"))
        + f.u16(_hpa(s.get("pressure")))
        + f.reserved(1)
    ]


def encode_130311(s: Signals, sid: int) -> list[bytes]:
    """Environmental parameters; temperature and humidity source = outside."""
    sources = (SRC_OUTSIDE & 0x3F) | (SRC_OUTSIDE << 6)
    return [
        _sid(sid)
        + bytes([sources])
        + f.temp_u16_K(s.get("air_temp"))
        + f.i16(s.get("humidity"), PERCENT)
        + f.u16(_hpa(s.get("pressure")))
    ]


def _temperature(sid: int, instance: int, source: int, kelvin) -> bytes:
    return _sid(sid) + bytes([instance, source]) + f.temp_u16_K(kelvin) + f.u16(None) + f.reserved(1)


def encode_130312(s: Signals, sid: int) -> list[bytes]:
    """Temperature: water (instance 0, source 0) and main cabin (instance 1, source 4)."""
    return [
        _temperature(sid, 0, SRC_SEA, s.get("water_temp")),
        _temperature(sid, 1, SRC_CABIN, s.get("cabin_temp")),
    ]


def encode_130313(s: Signals, sid: int) -> list[bytes]:
    """Humidity, outside source."""
    return [
        _sid(sid)
        + bytes([0, 1])
        + f.i16(s.get("humidity"), PERCENT)
        + f.i16(None)
        + f.reserved(1)
    ]


def encode_130314(s: Signals, sid: int) -> list[bytes]:
    """Actual pressure, atmospheric source, 0.1 Pa."""
    return [_sid(sid) + bytes([0, 0]) + f.i32(s.get("pressure"), 0.1) + f.reserved(1)]


def encode_130316(s: Signals, sid: int) -> list[bytes]:
    """Temperature, extended range: dew point (source 9), 0.001 K."""
    return [
        _sid(sid)
        + bytes([0, SRC_DEW_POINT])
        + f.u24(s.get("dew_point"), 0.001)
        + f.u16(None)
    ]
