"""Engine PGNs: 127488 rapid, 127489 dynamic. Nothing is sent while the engine is off."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals


def _running(s: Signals) -> bool:
    return bool(s.get("engine.rpm"))


def encode_127488(s: Signals, sid: int) -> list[bytes]:
    """Engine parameters, rapid update."""
    if not _running(s):
        return []
    return [b"\x00" + f.u16(s.get("engine.rpm"), 0.25) + f.u16(None) + f.i8(None) + f.reserved(2)]


def encode_127489(s: Signals, sid: int) -> list[bytes]:
    """Engine parameters, dynamic (26 bytes)."""
    if not _running(s):
        return []
    return [
        b"\x00"
        + f.u16(s.get("engine.oil_pressure"), 100.0)
        + f.u16(s.get("engine.oil_temp"), 0.1)
        + f.u16(s.get("engine.coolant_temp"), 0.01)
        + f.i16(s.get("engine.alternator_v"), 0.01)
        + f.i16(s.get("engine.fuel_rate"), 0.1)
        + f.u32(s.get("engine.hours"))
        + f.u16(None)
        + f.u16(None)
        + b"\xff"
        + b"\x00\x00\x00\x00"  # discrete status 1 and 2: no alarms
        + f.i8(s.get("engine.load"))
        + f.i8(None)
    ]
