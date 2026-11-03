"""Masthead motion: roll and pitch rates move the wind sensor and show up in the measured AWA/AWS."""

import dataclasses
import math

import pytest

from n2k_sim import geo
from n2k_sim.config import Scenario
from n2k_sim.sensors.devices import SensorInput, WindDamping, masthead_velocity, wind_sensor
from n2k_sim.simulation import Simulation
from n2k_sim.units import kn_to_ms


def trace(s: Scenario, steps: int, warmup: int = 300):
    """(values, boat state) per step after the warm-up."""
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    out = []
    for i in range(steps):
        v = sim.step(0.1).values
        if i >= warmup:
            out.append((v, sim.boat_state))
    return sim, out


def test_zero_mast_height_passes_hull_apparent_wind_unchanged():
    s = Scenario()
    s.sensors.mast_height = 0.0
    _, rows = trace(s, 600)
    for v, b in rows:
        assert v["awa"] == b.awa and v["aws"] == b.aws  # bit-identical, not approx


def test_masthead_velocity_signs():
    # Rolling to starboard moves the masthead to starboard; bow down moves it forward.
    assert masthead_velocity(10.0, 0.1, 0.0) == pytest.approx((0.0, 1.0))
    assert masthead_velocity(10.0, 0.0, -0.1) == pytest.approx((1.0, 0.0))


def test_mast_motion_changes_apparent_wind_like_boat_motion():
    sim = Simulation(Scenario(), clock=lambda: 1_760_000_000.0)
    sim.step(0.1)
    cfg = sim.scenario
    base = dataclasses.replace(sim.boat_state, aws=kn_to_ms(10.0), awa=0.0, roll_rate=0.0, pitch_rate=0.0)
    h = cfg.sensors.mast_height

    def read(**rates):
        return wind_sensor(SensorInput(sim.env_state, dataclasses.replace(base, **rates), cfg, 0.0))

    # Head wind; masthead moving to starboard at 1 m/s -> wind appears from starboard (+AWA).
    r = read(roll_rate=1.0 / h)
    assert r["awa"] == pytest.approx(math.atan2(1.0, kn_to_ms(10.0)))
    # Masthead moving forward at 1 m/s (bow dropping) -> 1 m/s more head wind.
    r = read(pitch_rate=-1.0 / h)
    assert r["awa"] == pytest.approx(0.0) and r["aws"] == pytest.approx(kn_to_ms(10.0) + 1.0)


def test_attitude_rates_are_derivatives_of_attitude():
    _, rows = trace(Scenario(), 1500)
    for i in range(1, len(rows) - 1):
        (_, prev), (_, b), (_, nxt) = rows[i - 1], rows[i], rows[i + 1]
        assert b.roll_rate == pytest.approx((nxt.roll - prev.roll) / 0.2, abs=math.radians(0.1))
        assert b.pitch_rate == pytest.approx((nxt.pitch - prev.pitch) / 0.2, abs=math.radians(0.15))


def test_awa_oscillates_with_masthead_velocity_in_waves():
    s = Scenario()
    s.wind.fixed = True
    _, rows = trace(s, 2000)
    h = s.sensors.mast_height
    dev = []
    for v, b in rows:
        # Measured minus hull apparent wind ("from" vectors, boat frame) is the masthead velocity.
        dx = v["aws"] * math.cos(v["awa"]) - b.aws * math.cos(b.awa)
        dy = v["aws"] * math.sin(v["awa"]) - b.aws * math.sin(b.awa)
        assert (dx, dy) == pytest.approx(masthead_velocity(h, b.roll_rate, b.pitch_rate), abs=1e-9)
        dev.append(geo.wrap_pi(v["awa"] - b.awa))
    assert math.degrees(max(dev)) > 1.5 and math.degrees(min(dev)) < -1.5


def test_heel_change_in_a_tack_moves_the_masthead():
    s = Scenario()
    s.wind.fixed = True
    s.waves.enabled = False
    sim, _ = trace(s, 300, warmup=300)
    sim.boat.maneuver(True)
    sim.scenario.autopilot.twa = -sim.scenario.autopilot.twa
    peak = 0.0
    for _ in range(300):
        v = sim.step(0.1).values
        peak = max(peak, abs(geo.wrap_pi(v["awa"] - sim.boat_state.awa)))
    assert math.degrees(peak) > 1.0


def test_wind_damping_is_a_first_order_lag():
    damp = WindDamping()
    assert damp.step({"awa": 0.0, "aws": 5.0}, 0.1, 1.0) == {"awa": 0.0, "aws": 5.0}
    out = None
    for _ in range(10):  # 1 s = one time constant
        out = damp.step({"awa": 0.2, "aws": 6.0}, 0.1, 1.0)
    assert out["awa"] == pytest.approx(0.2 * (1 - 0.9**10))
    assert out["aws"] == pytest.approx(5.0 + 1.0 - 0.9**10)
    # Across ±180° it takes the short way round.
    damp = WindDamping()
    damp.step({"awa": math.radians(179), "aws": 5.0}, 0.1, 1.0)
    out = damp.step({"awa": math.radians(-179), "aws": 5.0}, 0.1, 1.0)
    assert abs(math.degrees(out["awa"])) > 179
    # Time constant 0 is a pass-through.
    r = {"awa": 0.3, "aws": 4.0}
    assert WindDamping().step(r, 0.1, 0.0) is r


def test_wind_damping_smooths_the_mast_motion():
    def awa_spread(tau):
        s = Scenario()
        s.wind.fixed = True
        s.sensors.wind_damping_s = tau
        _, rows = trace(s, 1500)
        d = [geo.wrap_pi(v["awa"] - b.awa) for v, b in rows]
        return max(d) - min(d)

    assert awa_spread(1.0) < 0.6 * awa_spread(0.0)


def test_invert_pitch_fault_affects_only_the_attitude_sensor():
    s = Scenario()
    s.sensors.invert_pitch = True
    _, rows = trace(s, 400)
    assert any(b.pitch != 0 for _, b in rows)
    for v, b in rows:
        assert v["pitch"] == -b.pitch
