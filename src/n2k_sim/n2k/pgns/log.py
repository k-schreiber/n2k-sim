"""Speed log and depth PGNs: 128259, 128275, 128267."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals


def encode_128259(s: Signals, sid: int) -> list[bytes]:
    """Speed through water; speed over ground not available."""
    return [
        bytes([sid & 0xFF])
        + f.speed_u16(s.get("stw"))
        + f.speed_u16(None)
        + b"\x00"  # water reference type: paddle wheel
        + b"\xff\xff"
    ]


def encode_128275(s: Signals, sid: int) -> list[bytes]:
    """Distance log (14 bytes); total and trip in metres."""
    t = s.get("gnss_time")
    return [
        f.date_u16(t)
        + f.time_u32(t)
        + f.u32(s.get("log_total"))
        + f.u32(s.get("log_trip"))
    ]


def encode_128267(s: Signals, sid: int) -> list[bytes]:
    """Water depth below transducer; offset in metres (+ to waterline, - to keel)."""
    return [
        bytes([sid & 0xFF])
        + f.u32(s.get("depth"), 0.01)
        + f.i16(s.get("depth_offset"), 0.001)
        + f.u8(None)
    ]
