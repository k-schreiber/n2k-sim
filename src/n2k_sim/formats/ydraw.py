"""YD RAW text format: one CAN frame per line."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timezone

from ..n2k.types import CanFrame


def format_frame(frame: CanFrame) -> str:
    """Formats `hh:mm:ss.mmm R XXXXXXXX B0 B1 ...\\r\\n` (UTC time of the frame)."""
    ms_total = math.floor(frame.timestamp * 1000)
    t = datetime.fromtimestamp(ms_total // 1000, timezone.utc)
    stamp = f"{t:%H:%M:%S}.{ms_total % 1000:03d}"
    data = " ".join(f"{b:02X}" for b in frame.data)
    return f"{stamp} R {frame.can_id:08X} {data}\r\n"


def frames_to_bytes(frames: Iterable[CanFrame]) -> bytes:
    """Concatenates formatted frames as ASCII bytes."""
    return "".join(format_frame(f) for f in frames).encode("ascii")


def parse_client_line(line: str) -> tuple[int, bytes] | None:
    """Parses what a client sends: `XXXXXXXX B0 B1 ...` or a full line with time and direction.
    Returns (can_id, data), or None for anything else (gateways also get text commands)."""
    tokens = line.split()
    if len(tokens) >= 3 and tokens[1] in ("R", "T"):
        tokens = tokens[2:]
    if len(tokens) < 2 or len(tokens) > 9 or len(tokens[0]) != 8 or any(len(t) != 2 for t in tokens[1:]):
        return None
    try:
        return int(tokens[0], 16), bytes(int(t, 16) for t in tokens[1:])
    except ValueError:
        return None


def parse_line(line: str) -> tuple[int, bytes]:
    """Parses one YD RAW line into (can_id, data); raises ValueError on a bad line."""
    tokens = line.rstrip("\r\n").split(" ")
    if len(tokens) < 4 or tokens[1] != "R" or "" in tokens:
        raise ValueError(f"bad YD RAW line: {line!r}")
    if len(tokens[2]) != 8 or any(len(t) != 2 for t in tokens[3:]) or len(tokens) > 11:
        raise ValueError(f"bad YD RAW line: {line!r}")
    return int(tokens[2], 16), bytes(int(t, 16) for t in tokens[3:])
