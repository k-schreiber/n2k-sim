"""System PGNs: identity and protocol (59392, 60928, 126208, 126464, 126993, 126996, 126998), plus
126992 system time and 129033 time & date. Layouts as in canboat (docs/canboat.json)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .. import fields as f
from ..types import Signals


ISO_NAK = 1
GROUP_ACKNOWLEDGE = 2
PGN_LIST_TRANSMIT, PGN_LIST_RECEIVE = 0, 1
PRODUCT_STRING_LENGTH = 32  # bytes
DESCRIPTION_LENGTH = 70  # bytes
HEARTBEAT_INTERVAL_MS = 60000


def _string_fix(text: str, length: int = PRODUCT_STRING_LENGTH) -> bytes:
    """STRING_FIX: the text cut to the field and padded with the "unknown" byte 0xFF."""
    return text.encode("utf-8")[:length].ljust(length, b"\xff")


def string_lau(text: str, length: int = DESCRIPTION_LENGTH) -> bytes:
    """STRING_LAU: length (including these two header bytes), 1 = ASCII/UTF-8, text."""
    raw = text.encode("utf-8")[:length]
    return bytes([len(raw) + 2, 1]) + raw


def _pgn(pgn: int) -> bytes:
    return pgn.to_bytes(3, "little")


def product_information(
    version: int, code: int, model: str, software: str, model_version: str, serial: str
) -> bytes:
    """126996, 134 bytes. Certification level 1 and one LEN, as the ttlappalainen library's default."""
    return (
        version.to_bytes(2, "little")
        + code.to_bytes(2, "little")
        + _string_fix(model)
        + _string_fix(software)
        + _string_fix(model_version)
        + _string_fix(serial)
        + bytes([1, 1])
    )


def configuration_information(description1: str, description2: str, manufacturer: str) -> bytes:
    """126998: installation descriptions 1 and 2 and the manufacturer information."""
    return string_lau(description1) + string_lau(description2) + string_lau(manufacturer)


def pgn_list(function: int, pgns: Iterable[int]) -> bytes:
    """126464: transmit (0) or receive (1) PGN list."""
    return bytes([function]) + b"".join(_pgn(p) for p in sorted(pgns))


def iso_nak(pgn: int) -> bytes:
    """59392: NAK of the requested PGN (group function, reserved bytes unused)."""
    return bytes([ISO_NAK, 0xFF]) + f.reserved(3) + _pgn(pgn)


def group_acknowledge(
    pgn: int, pgn_error: int, parameter_errors: Sequence[int] = (), interval_error: int = 0
) -> bytes:
    """126208 Acknowledge: PGN error code (low nibble), interval/priority error (high nibble), the
    number of parameters and one error nibble per parameter, padded with 1s."""
    nibbles = list(parameter_errors) + [0xF] * (len(parameter_errors) % 2)
    errors = bytes(nibbles[i] | nibbles[i + 1] << 4 for i in range(0, len(nibbles), 2))
    return bytes([GROUP_ACKNOWLEDGE]) + _pgn(pgn) + bytes([pgn_error & 0x0F | interval_error << 4, len(parameter_errors)]) + errors


def encode_126993(s: Signals, sid: int) -> list[bytes]:
    """Heartbeat: interval, sequence counter, both controllers error active, equipment operational."""
    return [HEARTBEAT_INTERVAL_MS.to_bytes(2, "little") + bytes([sid & 0xFF, 0xC0]) + f.reserved(4)]


def address_claim(name: Mapping[str, Any]) -> bytes:
    """Builds the 8-byte NAME of PGN 60928 from its fields.

    Keys: unique_number, manufacturer_code, device_instance, device_function, device_class,
    system_instance, industry_group, arbitrary_address (missing keys default to 0, industry 4).
    """
    low = (int(name.get("unique_number", 0)) & 0x1FFFFF) | (
        (int(name.get("manufacturer_code", 0)) & 0x7FF) << 21
    )
    byte6 = (int(name.get("device_class", 0)) & 0x7F) << 1
    byte7 = (
        (int(name.get("system_instance", 0)) & 0x0F)
        | ((int(name.get("industry_group", 4)) & 0x07) << 4)
        | (0x80 if name.get("arbitrary_address", True) else 0)
    )
    return (
        low.to_bytes(4, "little")
        + bytes([int(name.get("device_instance", 0)) & 0xFF])
        + bytes([int(name.get("device_function", 0)) & 0xFF, byte6, byte7])
    )


def encode_126992(s: Signals, sid: int) -> list[bytes]:
    """System time, source 0 = GPS."""
    t = s.get("gnss_time")
    return [bytes([sid & 0xFF, 0xF0]) + f.date_u16(t) + f.time_u32(t)]


def encode_129033(s: Signals, sid: int) -> list[bytes]:
    """Time & date with local offset in minutes."""
    t = s.get("gnss_time")
    return [f.date_u16(t) + f.time_u32(t) + f.i16(s.get("local_offset"))]
