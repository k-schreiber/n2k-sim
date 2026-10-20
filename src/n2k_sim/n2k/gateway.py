"""The gateway: schedules PGNs, encodes the latest snapshot and frames them as CAN frames, all from
one source address (docs/spec/n2k-output.md)."""

from __future__ import annotations

import socket
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Mapping

from n2k_sim.config import PgnSetting
from n2k_sim.n2k.canid import build_can_id
from n2k_sim.n2k.fastpacket import FastPacketFramer
from n2k_sim.n2k.pgns import default_pgns
from n2k_sim.n2k.pgns.system import address_claim
from n2k_sim.n2k.types import CanFrame, PgnSpec, Signals

ADDRESS_CLAIM_PGN = 60928
ADDRESS_CLAIM_INTERVAL = 300.0  # s
RATE_WINDOW = 5.0  # s


def gateway_name() -> dict:
    return {
        "unique_number": zlib.crc32(socket.gethostname().encode()) & 0x1FFFFF,
        "manufacturer_code": 2046,
        "device_instance": 0,
        "device_function": 136,  # PC gateway
        "device_class": 25,  # inter/intranetwork device
        "system_instance": 0,
        "industry_group": 4,
        "arbitrary_address": True,
    }


@dataclass
class PgnStats:
    frames: deque  # timestamps of frames sent
    last_hex: str = ""


class Gateway:
    def __init__(self, source: int, settings: Mapping[str, PgnSetting] | None = None):
        self.source = source
        self.specs: dict[str, PgnSpec] = {p.id: p for p in default_pgns()}
        self.settings: dict[str, PgnSetting] = dict(settings or {})
        self._framer = FastPacketFramer()
        self._next_due: dict[str, float] = {}
        self._next_claim = 0.0
        self._sid_interval = self._sensor_intervals()
        self.stats: dict[str, PgnStats] = defaultdict(lambda: PgnStats(deque()))

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
        frames: list[CanFrame] = []
        if now >= self._next_claim:
            frames += self._frames(ADDRESS_CLAIM_PGN, 6, [address_claim(gateway_name())], False, now, "60928")
            self._next_claim = now + ADDRESS_CLAIM_INTERVAL
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

    def _frames(self, pgn, priority, payloads, fast, now, key) -> list[CanFrame]:
        destination = 0xFF
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
