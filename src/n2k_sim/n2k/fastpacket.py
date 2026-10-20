"""Fast-packet framing for payloads longer than 8 bytes."""

from __future__ import annotations

MAX_PAYLOAD = 223


def frame_count(length: int) -> int:
    """Number of fast-packet frames for a payload length."""
    return 1 + -(-max(0, length - 6) // 7)


def split_fast_packet(payload: bytes, seq: int) -> list[bytes]:
    """Splits a payload into 8-byte fast-packet frames with the given sequence counter."""
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError("fast-packet payload must be 1..223 bytes")
    head = (seq & 7) << 5
    frames = [bytes([head, len(payload)]) + payload[:6]]
    for k, pos in enumerate(range(6, len(payload), 7), start=1):
        frames.append(bytes([head | k]) + payload[pos : pos + 7])
    return [f + b"\xff" * (8 - len(f)) for f in frames]


class FastPacketFramer:
    """Frames payloads; keeps a 0..7 sequence counter per PGN."""

    def __init__(self) -> None:
        self._seq: dict[int, int] = {}

    def frames(self, pgn: int, payload: bytes, fast_packet: bool = True) -> list[bytes]:
        """Returns the CAN data fields for one message (single frames are padded to 8 bytes)."""
        if not fast_packet:
            if len(payload) > 8:
                raise ValueError("single-frame payload longer than 8 bytes")
            return [payload + b"\xff" * (8 - len(payload))]
        seq = self._seq.get(pgn, 0)
        self._seq[pgn] = (seq + 1) & 7
        return split_fast_packet(payload, seq)
