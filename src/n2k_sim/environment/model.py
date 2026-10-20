"""Tier 1: the environment. Knows nothing about the boat except where it is (for depth)."""

from __future__ import annotations

import math
import random

from n2k_sim.config import Scenario
from n2k_sim.environment.state import EnvironmentState
from n2k_sim.environment.wind import WindModel
from n2k_sim.units import kn_to_ms

G = 9.81
SHALLOW_DEPTH = 3.0  # m
SHALLOW_DURATION = 60.0  # s
SHALLOW_RAMP = 15.0  # s


def wave_period(length: float) -> float:
    """Deep-water wave period from wavelength."""
    return math.sqrt(2 * math.pi * max(length, 0.1) / G)


class Environment:
    def __init__(self, seed: int):
        self._rng = random.Random(seed)
        self.wind = WindModel(self._rng)
        self._depth_phase = self._rng.uniform(0, 2 * math.pi)
        self._shallow_start: float | None = None

    def trigger_shallow(self, t: float) -> None:
        self._shallow_start = t

    def step(self, t: float, dt: float, cfg: Scenario) -> EnvironmentState:
        wind_dir, wind_speed, gust = self.wind.step(t, dt, cfg.wind)

        cur = cfg.current
        drift = cur.drift
        if not cur.fixed:
            period = max(cur.tidal_period_h, 0.01) * 3600.0
            drift *= 1 + cur.tidal_amplitude_pct / 100.0 * math.sin(2 * math.pi * t / period)

        waves = cfg.waves
        height = waves.height if waves.enabled else 0.0

        return EnvironmentState(
            t=t,
            wind_dir=wind_dir,
            wind_speed=wind_speed,
            gust=gust,
            current_set=math.radians(cur.set % 360.0),
            current_drift=kn_to_ms(max(drift, 0.0)),
            wave_dir=math.radians(waves.direction % 360.0),
            wave_height=max(height, 0.0),
            wave_length=max(waves.length, 1.0),
            wave_period=wave_period(waves.length),
            wave_irregularity=waves.irregularity,
            depth=self._depth(t, cfg),
        )

    def _depth(self, t: float, cfg: Scenario) -> float:
        bed = cfg.seabed
        if bed.fixed:
            depth = bed.depth
        else:
            # Two incommensurate sines give a smooth, non-repeating-looking bottom profile.
            period = max(bed.change_period_min, 0.1) * 60.0
            x = 0.5 + 0.35 * math.sin(2 * math.pi * t / period + self._depth_phase) + 0.15 * math.sin(
                2 * math.pi * t / (period * 2.7) + 1.3 * self._depth_phase
            )
            depth = bed.depth_min + (bed.depth_max - bed.depth_min) * x
        if self._shallow_start is not None:
            elapsed = t - self._shallow_start
            if elapsed > SHALLOW_DURATION:
                self._shallow_start = None
            else:
                ramp = min(elapsed, SHALLOW_DURATION - elapsed) / SHALLOW_RAMP
                w = min(max(ramp, 0.0), 1.0)
                depth = depth * (1 - w) + SHALLOW_DEPTH * w
        return max(depth, bed.keel_depth + 0.2)
