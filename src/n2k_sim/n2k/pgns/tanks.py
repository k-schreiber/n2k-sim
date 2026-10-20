"""PGN 127505 fluid level, one payload per tank."""

from __future__ import annotations

from ...signals.catalogue import TANKS
from .. import fields as f
from ..types import Signals


def encode_127505(s: Signals, sid: int) -> list[bytes]:
    """Fluid level for every configured tank (level in 0.004 %, capacity in 0.1 L)."""
    out = []
    for prefix, instance, fluid in TANKS:
        out.append(
            bytes([(fluid & 0x0F) << 4 | (instance & 0x0F)])
            + f.i16(s.get(prefix + ".level"), 0.004)
            + f.u32(s.get(prefix + ".capacity"), 0.1)
            + b"\xff"
        )
    return out
