"""PGN 130306 wind data in the references defined by the ttlappalainen library (N2kTypes.h)."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals

# tN2kWindReference
TRUE_NORTH = 0  # ground referenced, referenced to true north (COG/SOG based)
APPARENT = 2  # relative to the centreline
TRUE_BOAT = 3  # to the centreline, ground referenced (COG/SOG based)
TRUE_WATER = 4  # to the centreline, water referenced (heading/STW based)


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


def encode_water(s: Signals, sid: int) -> list[bytes]:
    """Instrument true wind, water referenced, from twa/tws (reference 4)."""
    return _wind(sid, s.get("tws"), s.get("twa"), TRUE_WATER)


def encode_ground_boat(s: Signals, sid: int) -> list[bytes]:
    """Ground wind relative to the centreline, from gwa/gws (reference 3)."""
    return _wind(sid, s.get("gws"), s.get("gwa"), TRUE_BOAT)


def encode_ground(s: Signals, sid: int) -> list[bytes]:
    """Ground wind direction, true north referenced, from gwd/gws (reference 0)."""
    return _wind(sid, s.get("gws"), s.get("gwd"), TRUE_NORTH)
