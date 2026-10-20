"""PGN 127508 battery status, one payload per battery."""

from __future__ import annotations

from ...signals.catalogue import BATTERIES
from .. import fields as f
from ..types import Signals


def encode_127508(s: Signals, sid: int) -> list[bytes]:
    """Battery voltage (0.01 V), current (0.1 A) and temperature (0.01 K)."""
    return [
        bytes([instance & 0xFF])
        + f.i16(s.get(prefix + ".voltage"), 0.01)
        + f.i16(s.get(prefix + ".current"), 0.1)
        + f.temp_u16_K(s.get(prefix + ".temp"))
        + bytes([sid & 0xFF])
        for prefix, instance in BATTERIES
    ]
