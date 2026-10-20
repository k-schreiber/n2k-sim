"""PGN 130306 wind data in three references."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals

TRUE_GROUND, APPARENT, TRUE_BOAT = 0, 2, 3


def _wind(sid: int, speed, angle, reference: int) -> list[bytes]:
    return [
        bytes([sid & 0xFF])
        + f.speed_u16(speed)
        + f.angle_u16(angle)
        + bytes([0xF8 | reference])
        + f.reserved(2)
    ]


def encode_apparent(s: Signals, sid: int) -> list[bytes]:
    """Apparent wind from awa/aws (reference 2)."""
    return _wind(sid, s.get("aws"), s.get("awa"), APPARENT)


def encode_true(s: Signals, sid: int) -> list[bytes]:
    """True wind, boat referenced, from twa/tws (reference 3)."""
    return _wind(sid, s.get("tws"), s.get("twa"), TRUE_BOAT)


def encode_ground(s: Signals, sid: int) -> list[bytes]:
    """True wind direction, north referenced, from twd/tws (reference 0)."""
    return _wind(sid, s.get("tws"), s.get("twd"), TRUE_GROUND)
