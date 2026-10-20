"""Tier 1 output: the environment's true state (SI units)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentState:
    t: float  # simulation time, s
    wind_dir: float  # rad, wind over ground comes FROM
    wind_speed: float  # m/s, over ground
    gust: float  # current gust factor (0 = no gust), for display
    current_set: float  # rad, current flows TO
    current_drift: float  # m/s
    wave_dir: float  # rad, waves come FROM
    wave_height: float  # m (0 = no waves)
    wave_length: float  # m
    wave_period: float  # s
    wave_irregularity: float
    depth: float  # m below waterline at the boat
