"""PGN 127245 rudder."""

from __future__ import annotations

from .. import fields as f
from ..types import Signals


def encode_127245(s: Signals, sid: int) -> list[bytes]:
    """Rudder position (starboard positive); no direction order, angle order not available."""
    return [
        b"\x00"
        + b"\xf8"
        + f.i16(None)
        + f.i16(s.get("rudder"), 1e-4)
        + f.reserved(2)
    ]
