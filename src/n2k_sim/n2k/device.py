"""The simulator as a device on the bus: how it identifies itself and answers other devices.

Covers what network management tools such as Signal K use (docs/spec/n2k-output.md): the ISO address
claim with contention, ISO requests, product and configuration information, PGN lists and instance
and label changes by 126208 commands. Layouts follow canboat (docs/canboat.json).
"""

from __future__ import annotations

import socket
import zlib
from importlib import metadata
from typing import Callable, Iterable, NamedTuple

from n2k_sim.config import Device as DeviceConfig
from n2k_sim.n2k.canid import GLOBAL
from n2k_sim.n2k.pgns import system

ISO_ACK, ISO_REQUEST, ADDRESS_CLAIM = 59392, 59904, 60928
GROUP_FUNCTION, PGN_LIST, PRODUCT_INFO, CONFIGURATION_INFO = 126208, 126464, 126996, 126998
NULL_ADDRESS = 254  # the source of a device that has no address yet
MAX_ADDRESS = 251
NMEA2000_VERSION = 2101  # 2.101, the ttlappalainen library's default
DEVICE_FUNCTION = 136  # NMEA Network Gateway
DEVICE_CLASS = 25  # Internetwork device
INDUSTRY_MARINE = 4
MANUFACTURER_INFORMATION = "Simulated data, not for navigation"

GROUP_REQUEST, GROUP_COMMAND, GROUP_READ, GROUP_WRITE = 0, 1, 3, 5
# PGN_ERROR_CODE and PARAMETER_FIELD lookups
ACKNOWLEDGE, PGN_NOT_SUPPORTED, READ_WRITE_NOT_SUPPORTED, NOT_SUPPORTED = 0, 1, 6, 4
PARAMETER_INVALID, PARAMETER_RANGE, PARAMETER_NOT_SUPPORTED = 1, 3, 5

INTERVAL_NOT_SUPPORTED = 1  # TRANSMISSION_INTERVAL lookup
INTERVAL_KEEP = b"\xff\xff\xff\xff"  # 126208 Request: leave the transmission interval unchanged

# 60928 fields settable by 126208, by field order
INSTANCE_LOWER, INSTANCE_UPPER, SYSTEM_INSTANCE = 3, 4, 8

TRANSMITTED = (ISO_ACK, ADDRESS_CLAIM, GROUP_FUNCTION, PGN_LIST, PRODUCT_INFO, CONFIGURATION_INFO)
RECEIVED = (ISO_REQUEST, ADDRESS_CLAIM, GROUP_FUNCTION)


class Message(NamedTuple):
    pgn: int
    priority: int
    payload: bytes
    fast: bool = False
    destination: int = GLOBAL


def software_version() -> str:
    try:
        return metadata.version("n2k-sim")
    except metadata.PackageNotFoundError:
        return "unknown"


def host_unique_number() -> int:
    """Stable per machine, so that the CAN Name survives restarts. Never the all-ones "unset" value."""
    return zlib.crc32(socket.gethostname().encode()) % 0x1FFFFF


def decode_lau(raw: bytes) -> str:
    """The text of a STRING_LAU body: canboat reads control byte 1 as UTF-8, else Latin-1."""
    try:
        return raw.decode("utf-8").rstrip("\x00")
    except UnicodeDecodeError:
        return raw.decode("latin-1").rstrip("\x00")


class BusDevice:
    def __init__(self, cfg: DeviceConfig, address: int):
        self.cfg = cfg
        self.address = address
        self.others: dict[int, bytes] = {}  # address -> NAME of the other devices on the bus

    @property
    def unique_number(self) -> int:
        return host_unique_number() if self.cfg.unique_number is None else self.cfg.unique_number

    def name(self) -> bytes:
        """The 8-byte ISO NAME, also Signal K's "CAN Name" key of this device."""
        return system.address_claim(
            {
                "unique_number": self.unique_number,
                "manufacturer_code": self.cfg.manufacturer_code,
                "device_instance": self.cfg.device_instance,
                "device_function": DEVICE_FUNCTION,
                "device_class": DEVICE_CLASS,
                "system_instance": self.cfg.system_instance,
                "industry_group": INDUSTRY_MARINE,
                "arbitrary_address": True,
            }
        )

    def claim(self) -> Message:
        return Message(ADDRESS_CLAIM, 6, self.name())

    def product_information(self) -> Message:
        cfg = self.cfg
        payload = system.product_information(
            NMEA2000_VERSION, cfg.product_code, cfg.product_model, software_version(), cfg.product_version,
            str(self.unique_number),
        )
        return Message(PRODUCT_INFO, 6, payload, fast=True)

    def configuration_information(self) -> Message:
        cfg = self.cfg
        payload = system.configuration_information(
            cfg.installation_description1, cfg.installation_description2, MANUFACTURER_INFORMATION
        )
        return Message(CONFIGURATION_INFO, 6, payload, fast=True)

    def pgn_lists(self, transmitted: Iterable[int], destination: int) -> list[Message]:
        return [
            Message(PGN_LIST, 6, system.pgn_list(function, pgns), True, destination)
            for function, pgns in (
                (system.PGN_LIST_TRANSMIT, set(transmitted) | set(TRANSMITTED)),
                (system.PGN_LIST_RECEIVE, RECEIVED),
            )
        ]

    def identity(self) -> list[Message]:
        return [self.claim(), self.product_information(), self.configuration_information()]

    def on_address_claim(self, source: int, name: bytes) -> list[Message]:
        """ISO contention: of two devices on one address the lower NAME keeps it, the other moves."""
        if len(name) != 8 or source > MAX_ADDRESS:
            return []
        self.others[source] = name
        if source != self.address or name == self.name():
            return []
        if int.from_bytes(self.name(), "little") > int.from_bytes(name, "little"):
            self.address = self._free_address()
        return [self.claim()]

    def _free_address(self) -> int:
        candidates = ((self.address + i) % (MAX_ADDRESS + 1) for i in range(1, MAX_ADDRESS + 1))
        return next((a for a in candidates if a not in self.others), NULL_ADDRESS)

    def on_iso_request(
        self, source: int, destination: int, data: bytes, send: Callable[[int, int], list[Message] | None]
    ) -> list[Message]:
        """`send(pgn, reply_to)` gives the messages of a supported PGN, None for an unknown one. A
        NAK goes only to a request addressed to this device, from a device that has an address."""
        if len(data) < 3:
            return []
        pgn = int.from_bytes(data[:3], "little")
        reply_to = source if destination != GLOBAL and source != NULL_ADDRESS else GLOBAL
        messages = send(pgn, reply_to)
        if messages is not None:
            return messages
        if destination == GLOBAL or source == NULL_ADDRESS:
            return []
        return [Message(ISO_ACK, 6, system.iso_nak(pgn), False, source)]

    def on_group_function(
        self, source: int, data: bytes, send: Callable[[int, int], list[Message] | None]
    ) -> list[Message]:
        if len(data) < 4:
            return []
        function, pgn = data[0], int.from_bytes(data[1:4], "little")
        if function == GROUP_COMMAND:
            return self._command(source, pgn, data)
        if function == GROUP_REQUEST:
            messages = send(pgn, GLOBAL)
            if messages is None:
                return [self._acknowledge(source, pgn, PGN_NOT_SUPPORTED)]
            if data[4:8] not in (b"", INTERVAL_KEEP):  # intervals are the scenario's to change
                return [self._acknowledge(source, pgn, ACKNOWLEDGE, interval_error=INTERVAL_NOT_SUPPORTED)]
            return [self._acknowledge(source, pgn, ACKNOWLEDGE), *messages]
        if function in (GROUP_READ, GROUP_WRITE):
            return [self._acknowledge(source, pgn, READ_WRITE_NOT_SUPPORTED)]
        return []  # acknowledgements and replies need no answer

    @staticmethod
    def _acknowledge(
        destination: int, pgn: int, error: int, parameters: tuple[int, ...] = (), interval_error: int = 0
    ) -> Message:
        payload = system.group_acknowledge(pgn, error, parameters, interval_error)
        return Message(GROUP_FUNCTION, 3, payload, True, destination)

    def _command(self, source: int, pgn: int, data: bytes) -> list[Message]:
        """126208 Command: writes instances (60928) and installation descriptions (126998)."""
        if pgn not in (ADDRESS_CLAIM, CONFIGURATION_INFO) or len(data) < 6:
            return [self._acknowledge(source, pgn, NOT_SUPPORTED)]
        write = self._write_instance if pgn == ADDRESS_CLAIM else self._write_description
        errors, position = [], 6
        for _ in range(data[5]):
            error, position = write(data, position)
            errors.append(error)
        ack = self._acknowledge(source, pgn, ACKNOWLEDGE, tuple(errors))
        return [ack, self.claim() if pgn == ADDRESS_CLAIM else self.configuration_information()]

    def _write_instance(self, data: bytes, position: int) -> tuple[int, int]:
        """One (field, value) of 60928; every value is one byte. Returns (error, next position)."""
        if position + 2 > len(data):
            return PARAMETER_INVALID, len(data)
        field, value, cfg = data[position], data[position + 1], self.cfg
        limit = {INSTANCE_LOWER: 7, INSTANCE_UPPER: 31, SYSTEM_INSTANCE: 15}.get(field)
        next_position = position + 2
        if limit is None:
            return PARAMETER_NOT_SUPPORTED, next_position
        if value > limit:
            return PARAMETER_RANGE, next_position
        if field == INSTANCE_LOWER:
            cfg.device_instance = cfg.device_instance & 0xF8 | value
        elif field == INSTANCE_UPPER:
            cfg.device_instance = cfg.device_instance & 0x07 | value << 3
        else:
            cfg.system_instance = value
        return ACKNOWLEDGE, next_position

    def _write_description(self, data: bytes, position: int) -> tuple[int, int]:
        """One (field, STRING_LAU) of 126998. Returns (error, next position)."""
        if position + 3 > len(data):
            return PARAMETER_INVALID, len(data)
        field, length, encoding = data[position], data[position + 1], data[position + 2]
        next_position = position + 1 + max(length, 2)
        if length < 2 or next_position > len(data):
            return PARAMETER_INVALID, len(data)
        if field not in (1, 2):
            return PARAMETER_NOT_SUPPORTED, next_position
        body = data[position + 3 : next_position]
        text = body.decode("utf-16-le", "replace").rstrip("\x00") if encoding == 0 else decode_lau(body)
        if len(text.encode("utf-8")) > system.DESCRIPTION_LENGTH:
            return PARAMETER_RANGE, next_position
        setattr(self.cfg, f"installation_description{field}", text)
        return ACKNOWLEDGE, next_position
