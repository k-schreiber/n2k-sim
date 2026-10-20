"""PGN 129291 set & drift, rapid update."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals


def encode_129291(s: Signals, sid: int) -> list[bytes]:
    """Current set (true reference) and drift."""
    return [
        bytes([sid & 0xFF, 0xFC])
        + f.angle_u16(s.get("current_set"))
        + f.speed_u16(s.get("current_drift"))
        + f.reserved(2)
    ]
