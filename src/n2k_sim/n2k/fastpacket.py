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


class FastPacketAssembler:
    """Reassembles incoming fast-packet messages per (source, PGN); drops incomplete ones.

    canboatjs sends a message of exactly 8 bytes as one plain frame without the fast-packet header.
    Its first byte is a nonzero frame index for no started message, which is how it is recognised.
    """

    def __init__(self) -> None:
        self._open: dict[tuple[int, int], tuple[int, int, int, bytearray]] = {}

    def add(self, source: int, pgn: int, data: bytes) -> bytes | None:
        """Returns the complete message when `data` finishes one, else None."""
        key = (source, pgn)
        seq, index = data[0] >> 5, data[0] & 0x1F
        if index == 0:
            if len(data) < 2:
                return None
            self._open[key] = (seq, 1, data[1], bytearray(data[2:]))
        else:
            started = self._open.get(key)
            if started is None or started[0] != seq or started[1] != index:
                self._open.pop(key, None)
                return bytes(data) if started is None and len(data) == 8 else None
            self._open[key] = (seq, index + 1, started[2], started[3] + data[1:])
        seq, index, length, buffer = self._open[key]
        if len(buffer) < length:
            return None
        del self._open[key]
        return bytes(buffer[:length])
