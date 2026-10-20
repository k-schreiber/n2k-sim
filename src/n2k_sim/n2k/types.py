"""Shared N2K types: PGN specifications and CAN frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

# A snapshot maps signal names (see signals/catalogue.py) to SI values; None = not available.
Signals = Mapping[str, Any]

# An encoder turns a snapshot and a sequence id into zero or more payloads (one per instance).
# An empty list means "nothing to send this time" (e.g. engine off).
Encoder = Callable[[Signals, int], list[bytes]]


@dataclass(frozen=True)
class PgnSpec:
    pgn: int
    name: str
    interval_s: float
    priority: int
    encode: Encoder
    fast_packet: bool = False
    sensor: str = ""  # sensor module whose SID counter is used ("gps", "compass", …)
    enabled: bool = True
    key: str = ""  # unique key when one PGN has several schedules (e.g. "130306.apparent")

    @property
    def id(self) -> str:
        return self.key or str(self.pgn)


@dataclass(frozen=True)
class CanFrame:
    can_id: int
    data: bytes
    timestamp: float  # UNIX epoch seconds
    pgn: int = field(default=0, compare=False)
