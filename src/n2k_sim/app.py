"""The runtime: owns the scenario, simulation, gateway and transports, and runs the main loop."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

from n2k_sim.boat.tables import Polar
from n2k_sim.config import SECTIONS, PgnSetting, Scenario
from n2k_sim.formats.ydraw import format_frame
from n2k_sim.n2k.gateway import Gateway
from n2k_sim.signals.catalogue import BY_NAME, SIGNALS, Layer
from n2k_sim.simulation import POLAR_DIR, Simulation, load_polar_file
from n2k_sim.transport.net import Recorder, TcpOutput, UdpOutput
from n2k_sim.units import UI_UNITS, to_ui

log = logging.getLogger(__name__)

SIM_DT = 0.1  # s
LOOP_INTERVAL = 0.01  # s
RAW_TAIL = 200
RECORDINGS = Path.cwd() / "recordings"


class Runtime:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.sim = Simulation(scenario)
        self.gateway = Gateway(scenario.output.source, scenario.output.pgns)
        self.running = True
        self.udp: UdpOutput | None = None
        self.tcp: TcpOutput | None = None
        self.recorder = Recorder(RECORDINGS)
        self.raw_tail: deque[str] = deque(maxlen=RAW_TAIL)
        self.raw_seq = 0  # number of lines ever produced, for incremental pushes
        self.frames_sent: deque[tuple[float, int]] = deque()
        self._task: asyncio.Task | None = None
        self.sim.step(SIM_DT)

    # --- lifecycle ------------------------------------------------------------------------------
    async def start(self) -> None:
        await self.restart_transports()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        for t in (self.udp, self.tcp):
            if t:
                await t.stop()
        self.recorder.stop()

    async def restart_transports(self) -> None:
        out = self.scenario.output
        for t in (self.udp, self.tcp):
            if t:
                await t.stop()
        self.udp = UdpOutput(out.udp.host, out.udp.port) if out.udp.enabled else None
        self.tcp = TcpOutput(out.tcp.host, out.tcp.port) if out.tcp.enabled else None
        for t in (self.udp, self.tcp):
            if t:
                await t.start()
        self.recorder.stop()
        if out.recorder:
            self.recorder.start()

    async def _loop(self) -> None:
        next_step = time.monotonic()
        while True:
            try:
                now_mono = time.monotonic()
                steps = 0
                while self.running and now_mono >= next_step and steps < 5:
                    self.sim.step(SIM_DT)
                    next_step += SIM_DT
                    steps += 1
                if not self.running or now_mono - next_step > 1.0:
                    next_step = now_mono  # don't catch up after pauses or stalls
                self._emit(time.time())
            except Exception:  # keep the simulator alive; log and continue
                log.exception("main loop error")
            await asyncio.sleep(LOOP_INTERVAL)

    def _emit(self, now: float) -> None:
        snap = self.sim.snapshot
        frames = self.gateway.poll(now, snap.sent)
        if not frames:
            return
        lines = [format_frame(f) for f in frames]
        data = [line.encode("ascii") for line in lines]
        for t in (self.udp, self.tcp):
            if t:
                t.send(data)
        self.recorder.send(data)
        self.raw_tail.extend(line.rstrip("\r\n") for line in lines)
        self.raw_seq += len(lines)
        self.frames_sent.append((now, len(frames)))
        while self.frames_sent and now - self.frames_sent[0][0] > 5.0:
            self.frames_sent.popleft()

    # --- state for the UI -------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        snap = self.sim.snapshot
        signals = []
        for sig in SIGNALS:
            if not sig.scalar:
                continue
            value = snap.values.get(sig.name)
            sent = None if sig.layer is Layer.ENV else snap.sent.get(sig.name)
            signals.append(
                {
                    "name": sig.name,
                    "label": sig.label,
                    "group": sig.group,
                    "layer": sig.layer.value,
                    "unit": UI_UNITS[sig.ui][2],
                    "value": _round(to_ui(value, sig.ui)),
                    "sent": _round(to_ui(sent, sig.ui)),
                    "overridden": sig.name in self.scenario.overrides,
                    "pgns": list(sig.pgns),
                }
            )
        return {
            "running": self.running,
            "sim_time": round(snap.t, 1),
            "utc": snap.utc,
            "signals": signals,
            "scenario": self.scenario.model_dump(),
            "output": self.output_status(),
        }

    def output_status(self) -> dict[str, Any]:
        now = time.time()
        out = self.scenario.output
        total = sum(n for _, n in self.frames_sent) / 5.0

        def transport(cfg, t):
            st = t.status() if t else None
            return {
                "enabled": cfg.enabled,
                "host": cfg.host,
                "port": cfg.port,
                "bytes_per_s": round(st.bytes_per_s) if st else 0,
                "clients": st.clients if st else 0,
                "error": st.error if st else None,
            }

        pgns = []
        for spec in self.gateway.specs.values():
            pgns.append(
                {
                    "id": spec.id,
                    "pgn": spec.pgn,
                    "name": spec.name,
                    "enabled": self.gateway.enabled(spec),
                    "interval_s": self.gateway.interval(spec),
                    "frames_per_s": round(self.gateway.frames_per_s(spec.id, now), 1),
                    "last_hex": self.gateway.stats[spec.id].last_hex,
                }
            )
        return {
            "frames_per_s": round(total, 1),
            "source": out.source,
            "udp": transport(out.udp, self.udp),
            "tcp": transport(out.tcp, self.tcp),
            "recorder": {"enabled": out.recorder, "path": str(self.recorder.path) if self.recorder.path else None},
            "pgns": pgns,
        }

    def raw_since(self, seq: int) -> tuple[list[str], int]:
        new = min(self.raw_seq - seq, len(self.raw_tail))
        lines = list(self.raw_tail)[-new:] if new > 0 else []
        return lines, self.raw_seq

    # --- mutations ----------------------------------------------------------------------------------
    def patch_section(self, section: str, patch: dict[str, Any]) -> None:
        if section not in SECTIONS:
            raise ValueError(f"unknown section {section}")
        model = getattr(self.scenario, section)
        merged = type(model).model_validate({**model.model_dump(), **patch})
        if section == "boat" and merged.polar_file != model.polar_file:
            self.sim.set_polar(load_polar_file(merged.polar_file))
        setattr(self.scenario, section, merged)
        if section == "boat" and ("lat" in patch or "lon" in patch):
            self.sim.boat.teleport(merged.lat, merged.lon)

    def patch_static(self, patch: dict[str, Any]) -> None:
        for name, value in patch.items():
            sig = BY_NAME.get(name)
            if sig is None or sig.layer is not Layer.STATIC:
                raise ValueError(f"{name} is not a static signal")
            self.scenario.static[name] = float(value)

    def set_override(self, name: str, value: float | None) -> None:
        sig = BY_NAME.get(name)
        if sig is None or sig.layer is Layer.ENV or not sig.scalar:
            raise ValueError(f"{name} cannot be overridden")
        if value is None:
            self.scenario.overrides.pop(name, None)
        else:
            self.scenario.overrides[name] = float(value)

    async def patch_output(self, patch: dict[str, Any]) -> None:
        out = self.scenario.output
        merged = type(out).model_validate(_deep_merge(out.model_dump(), patch))
        self.scenario.output = merged
        self.gateway.source = merged.source
        if any(k in patch for k in ("udp", "tcp", "recorder")):
            await self.restart_transports()

    def patch_pgn(self, pgn_id: str, patch: dict[str, Any]) -> None:
        if pgn_id not in self.gateway.specs:
            raise ValueError(f"unknown PGN {pgn_id}")
        current = self.scenario.output.pgns.get(pgn_id, PgnSetting())
        setting = PgnSetting.model_validate({**current.model_dump(), **patch})
        self.scenario.output.pgns[pgn_id] = setting
        self.gateway.settings[pgn_id] = setting

    def tack(self) -> None:
        ap = self.scenario.autopilot
        if ap.mode == "twa":
            ap.twa = -ap.twa
        else:
            wind = math.degrees(self.sim.snapshot.values["env.wwd"])
            ap.heading = (2 * wind - ap.heading) % 360.0

    def adjust(self, delta: float) -> None:
        """Turns by delta degrees (+ = to starboard)."""
        ap = self.scenario.autopilot
        if ap.mode == "twa":
            ap.twa = max(-180.0, min(180.0, ap.twa - delta))
        else:
            ap.heading = (ap.heading + delta) % 360.0

    async def load_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.sim = Simulation(scenario)
        self.sim.step(SIM_DT)
        self.gateway = Gateway(scenario.output.source, scenario.output.pgns)
        await self.restart_transports()

    def reset(self) -> None:
        self.sim.reset()
        self.sim.step(SIM_DT)

    def upload_polar(self, text: str) -> None:
        polar = Polar.parse(text, "uploaded.pol")
        (POLAR_DIR / "uploaded.pol").write_text(text)
        self.scenario.boat.polar_file = "uploaded.pol"
        self.sim.set_polar(polar)


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _round(v):
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    return v


