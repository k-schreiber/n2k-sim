"""Compass PGNs: 127250 heading, 127251 rate of turn, 127257 attitude."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals

ROT_SCALE = 3.125e-8  # rad/s per bit


def encode_127250(s: Signals, sid: int) -> list[bytes]:
    """Vessel heading, magnetic reference, deviation not available.

    The variation field carries the GPS variation (east positive), like a gateway that completes
    the compass data, because some software reads variation only from here and not from 127258.
    """
    return [
        bytes([sid & 0xFF])
        + f.angle_u16(s.get("heading_mag"))
        + f.i16(None)
        + f.angle_i16(s.get("variation"))
        + b"\xfd"
    ]


def encode_127251(s: Signals, sid: int) -> list[bytes]:
    """Rate of turn, starboard positive."""
    return [bytes([sid & 0xFF]) + f.i32(s.get("rot"), ROT_SCALE) + f.reserved(3)]


def encode_127257(s: Signals, sid: int) -> list[bytes]:
    """Attitude: yaw, pitch, roll."""
    return [
        bytes([sid & 0xFF])
        + f.angle_i16(s.get("yaw"))
        + f.angle_i16(s.get("pitch"))
        + f.angle_i16(s.get("roll"))
        + f.reserved(1)
    ]
