"""The gateway: schedules PGNs, encodes the latest snapshot and frames them as CAN frames, all from
one source address, and answers the bus through its BusDevice (docs/spec/n2k-output.md)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Mapping

from n2k_sim.config import Device as DeviceConfig
from n2k_sim.config import PgnSetting
from n2k_sim.n2k.canid import GLOBAL, build_can_id, parse_can_id
from n2k_sim.n2k.device import (
    ADDRESS_CLAIM,
    CONFIGURATION_INFO,
    GROUP_FUNCTION,
    ISO_REQUEST,
    PGN_LIST,
    PRODUCT_INFO,
    BusDevice,
    Message,
)
from n2k_sim.n2k.fastpacket import FastPacketAssembler, FastPacketFramer
from n2k_sim.n2k.pgns import default_pgns
from n2k_sim.n2k.types import CanFrame, PgnSpec, Signals

# Receive-only links (UDP) can't ask for the identity, and a device that joins misses the start.
IDENTITY_INTERVAL = 60.0  # s
RATE_WINDOW = 5.0  # s


@dataclass
class PgnStats:
    frames: deque  # timestamps of frames sent
    last_hex: str = ""


class Gateway:
    def __init__(
        self, source: int, settings: Mapping[str, PgnSetting] | None = None, device: DeviceConfig | None = None
    ):
        self.device = BusDevice(device or DeviceConfig(), source)
        self.specs: dict[str, PgnSpec] = {p.id: p for p in default_pgns()}
        self.settings: dict[str, PgnSetting] = dict(settings or {})
        self._framer = FastPacketFramer()
        self._assembler = FastPacketAssembler()
        self._signals: Signals = {}
        self._next_due: dict[str, float] = {}
        self._next_identity = 0.0
        self._sid_interval = self._sensor_intervals()
        self.stats: dict[str, PgnStats] = defaultdict(lambda: PgnStats(deque()))

    @property
    def source(self) -> int:
        return self.device.address

    @source.setter
    def source(self, address: int) -> None:
        self.device.address = address

    def _sensor_intervals(self) -> dict[str, float]:
        intervals: dict[str, float] = {}
        for spec in self.specs.values():
            intervals[spec.sensor] = min(intervals.get(spec.sensor, spec.interval_s), spec.interval_s)
        return intervals

    def enabled(self, spec: PgnSpec) -> bool:
        setting = self.settings.get(spec.id)
        return spec.enabled if setting is None else setting.enabled

    def interval(self, spec: PgnSpec) -> float:
        setting = self.settings.get(spec.id)
        if setting is None or setting.interval_s is None:
            return spec.interval_s
        return max(setting.interval_s, 0.01)

    def sid(self, sensor: str, now: float) -> int:
        """Same SID for all PGNs a sensor emits within one of its measurement cycles."""
        return int(now / self._sid_interval.get(sensor, 1.0)) % 253

    def poll(self, now: float, signals: Signals) -> list[CanFrame]:
        """Returns the frames of every PGN that is due at `now`."""
        self._signals = signals
        frames: list[CanFrame] = []
        if now >= self._next_identity:
            frames += self.announce(now)
        for spec in self.specs.values():
            if not self.enabled(spec):
                continue
            due = self._next_due.get(spec.id, now)
            if now < due:
                continue
            interval = self.interval(spec)
            # Keep a steady cadence, but don't burst to catch up after a stall.
            self._next_due[spec.id] = due + interval if now - due < interval else now + interval
            payloads = spec.encode(signals, self.sid(spec.sensor, now))
            frames += self._frames(spec.pgn, spec.priority, payloads, spec.fast_packet, now, spec.id)
        return frames

    def announce(self, now: float) -> list[CanFrame]:
        """The identity messages; sent at the start, regularly and when a client connects."""
        self._next_identity = now + IDENTITY_INTERVAL
        return self._send(self.device.identity(), now)

    def receive(self, can_id: int, data: bytes, now: float) -> list[CanFrame]:
        """Handles a frame from the bus; returns the frames of the answer."""
        _, pgn, source, destination = parse_can_id(can_id)
        if not data or (destination not in (self.source, GLOBAL)):
            return []
        if pgn == ADDRESS_CLAIM:
            return self._send(self.device.on_address_claim(source, data), now)
        if pgn == ISO_REQUEST:
            return self._send(self.device.on_iso_request(source, destination, data, self._on_demand), now)
        if pgn == GROUP_FUNCTION:
            message = self._assembler.add(source, pgn, data)
            if message is not None:
                return self._send(self.device.on_group_function(source, message, self._on_demand), now)
        return []

    def _on_demand(self, pgn: int, reply_to: int) -> list[Message] | None:
        """The messages of a PGN somebody asked for, None if this device doesn't send it."""
        if pgn == ADDRESS_CLAIM:
            return [self.device.claim()]
        if pgn == PRODUCT_INFO:
            return [self.device.product_information()]
        if pgn == CONFIGURATION_INFO:
            return [self.device.configuration_information()]
        if pgn == PGN_LIST:
            transmitted = {s.pgn for s in self.specs.values() if self.enabled(s)}
            return self.device.pgn_lists(transmitted, reply_to)
        specs = [s for s in self.specs.values() if s.pgn == pgn and self.enabled(s)]
        if not specs or not self._signals:
            return None
        return [
            Message(s.pgn, s.priority, payload, s.fast_packet)
            for s in specs
            for payload in s.encode(self._signals, self.sid(s.sensor, 0.0))
        ]

    def _send(self, messages: list[Message], now: float) -> list[CanFrame]:
        frames: list[CanFrame] = []
        for m in messages:
            frames += self._frames(m.pgn, m.priority, [m.payload], m.fast, now, str(m.pgn), m.destination)
        return frames

    def _frames(self, pgn, priority, payloads, fast, now, key, destination=GLOBAL) -> list[CanFrame]:
        can_id = build_can_id(priority, pgn, self.source, destination)
        out = []
        stats = self.stats[key]
        for payload in payloads:
            for data in self._framer.frames(pgn, payload, fast):
                out.append(CanFrame(can_id, data, now, pgn))
                stats.frames.append(now)
            stats.last_hex = " ".join(f"{b:02X}" for b in payload)
        while stats.frames and now - stats.frames[0] > RATE_WINDOW:
            stats.frames.popleft()
        return out

    def frames_per_s(self, key: str, now: float) -> float:
        frames = self.stats[key].frames
        while frames and now - frames[0] > RATE_WINDOW:
            frames.popleft()
        return len(frames) / RATE_WINDOW
