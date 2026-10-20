"""GPS PGNs: 129025, 129026, 129029, 129539, 129540 and 127258."""

from __future__ import annotations

import math

from .. import fields as f
from ..types import Signals

MAX_SATS = 18  # (223 - 3) // 12


DOP_MODE_AUTO = 3  # tN2kGNSSDOPmode


def _sid(sid: int) -> bytes:
    return bytes([sid & 0xFF])


def encode_129025(s: Signals, sid: int) -> list[bytes]:
    """Position, rapid update."""
    return [f.i32(s.get("lat"), 1e-7) + f.i32(s.get("lon"), 1e-7)]


def encode_129026(s: Signals, sid: int) -> list[bytes]:
    """COG & SOG, rapid update (true reference)."""
    return [_sid(sid) + b"\xfc" + f.angle_u16(s.get("cog")) + f.speed_u16(s.get("sog")) + f.reserved(2)]


def _nibbles(low, high) -> bytes:
    if low is None or high is None:
        return b"\xff"
    return bytes([(int(low) & 0x0F) | ((int(high) & 0x0F) << 4)])


def encode_129029(s: Signals, sid: int) -> list[bytes]:
    """GNSS position data (43 bytes, no reference stations)."""
    t = s.get("gnss_time")
    integrity = s.get("integrity")
    integrity = 1 if integrity is None else int(integrity) & 3  # 1 = safe, as the library sends
    sats = s.get("sats_used")
    return [
        _sid(sid)
        + f.date_u16(t)
        + f.time_u32(t)
        + f.i64(s.get("lat"), 1e-16)
        + f.i64(s.get("lon"), 1e-16)
        + f.i64(s.get("altitude"), 1e-6)
        + _nibbles(s.get("gnss_type"), s.get("fix_method"))
        + bytes([0xFC | integrity])
        + f.u8(sats)
        + f.i16(s.get("hdop"), 0.01)
        + f.i16(s.get("pdop"), 0.01)
        + f.i32(s.get("geoidal_separation"), 0.01)
        + b"\x00"
    ]


def encode_129539(s: Signals, sid: int) -> list[bytes]:
    """GNSS DOPs; desired mode = auto (3), actual mode = `fix_mode` (2 = 3D)."""
    mode = s.get("fix_mode")
    byte1 = 0xFF if mode is None else DOP_MODE_AUTO | ((int(mode) & 7) << 3) | 0xC0
    return [
        _sid(sid)
        + bytes([byte1])
        + f.i16(s.get("hdop"), 0.01)
        + f.i16(s.get("vdop"), 0.01)
        + f.i16(s.get("tdop"), 0.01)
    ]


def _satellite(sat: tuple) -> bytes:
    prn, elevation, azimuth, snr, status = sat
    return (
        f.u8(prn)
        + f.i16(elevation, 1e-4)
        + f.angle_u16(azimuth)
        + f.i16(snr, 0.01)
        + f.i32(None)
        + bytes([0xF0 | (int(status) & 0x0F)])
    )


def encode_129540(s: Signals, sid: int) -> list[bytes]:
    """GNSS satellites in view (3 + 12 n bytes); nothing when the list is unavailable."""
    sats = s.get("satellites")
    if sats is None:
        return []
    sats = list(sats)[:MAX_SATS]
    # Range residual mode 3 = unavailable: the residual fields are not available.
    return [_sid(sid) + b"\xff" + bytes([len(sats)]) + b"".join(_satellite(x) for x in sats)]


def encode_127258(s: Signals, sid: int) -> list[bytes]:
    """Magnetic variation (east positive), source 8 = WMM2020, age of service = GNSS date."""
    return [
        _sid(sid)
        + b"\xf8"
        + f.date_u16(s.get("gnss_time"))
        + f.i16(s.get("variation"), 1e-4)
        + f.reserved(2)
    ]
