"""System PGNs: 60928 address claim, 126992 system time, 129033 time & date."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .. import fields as f
from ..types import Signals


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
