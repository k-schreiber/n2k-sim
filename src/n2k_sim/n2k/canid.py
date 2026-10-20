"""29-bit CAN identifiers: priority, PGN, source and destination (PDU1 vs PDU2)."""

from __future__ import annotations

GLOBAL = 0xFF


def is_pdu1(pgn: int) -> bool:
    """True when the PGN is destination-addressed (PF < 240)."""
    return ((pgn >> 8) & 0xFF) < 240


def build_can_id(priority: int, pgn: int, source: int, destination: int = GLOBAL) -> int:
    """Builds a CAN id. For PDU1 PGNs the PS byte is the destination, for PDU2 the PGN's low byte."""
    if not 0 <= priority <= 7:
        raise ValueError("priority out of range")
    if not 0 <= source <= 0xFF or not 0 <= destination <= 0xFF:
        raise ValueError("address out of range")
    dp = (pgn >> 16) & 1
    pf = (pgn >> 8) & 0xFF
    ps = destination if pf < 240 else pgn & 0xFF
    return priority << 26 | dp << 24 | pf << 16 | ps << 8 | source


def parse_can_id(can_id: int) -> tuple[int, int, int, int]:
    """Returns (priority, pgn, source, destination); destination is 0xFF for PDU2."""
    priority = (can_id >> 26) & 7
    dp = (can_id >> 24) & 1
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    source = can_id & 0xFF
    if pf < 240:
        return priority, dp << 16 | pf << 8, source, ps
    return priority, dp << 16 | pf << 8 | ps, source, GLOBAL
