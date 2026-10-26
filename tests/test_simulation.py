import math

import pytest

from n2k_sim import geo
from n2k_sim.boat.model import leeway
from n2k_sim.boat.tables import Polar
from n2k_sim.calc.processor import dew_point, true_wind
from n2k_sim.config import Scenario
from n2k_sim.environment.wind import WindModel, gust_shape
from n2k_sim.simulation import Simulation, load_polar_file
from n2k_sim.units import c_to_k, kn_to_ms, ms_to_kn

import random


def run(scenario: Scenario, seconds: float, dt: float = 0.1):
    sim = Simulation(scenario, clock=lambda: 1_760_000_000.0)
    snap = None
    for _ in range(int(seconds / dt)):
        snap = sim.step(dt)
    return sim, snap


def calm_scenario(**autopilot) -> Scenario:
    s = Scenario()
    s.wind.fixed = True
    s.waves.enabled = False
    for k, v in autopilot.items():
        setattr(s.autopilot, k, v)
    return s


def test_wrap_and_vectors():
    assert geo.wrap_pi(math.radians(270)) == pytest.approx(math.radians(-90))
    speed, bearing = geo.polar(geo.vector(3.0, math.radians(45)))
    assert speed == pytest.approx(3.0) and math.degrees(bearing) == pytest.approx(45)


def test_polar_exact_at_grid_and_clamped():
    polar = load_polar_file("mock_cruiser_40.pol")
    assert polar.boat_speed(10, 90) == pytest.approx(6.9)
    assert polar.boat_speed(40, 90) == pytest.approx(8.0)  # clamped to 25 kn column
    assert polar.boat_speed(10, -90) == polar.boat_speed(10, 90)


def test_polar_parse_rejects_ragged_rows():
    with pytest.raises(ValueError):
        Polar.parse("TWA\\TWS\t4\t6\n40\t2.9\n")


def test_fixed_wind_is_constant():
    model = WindModel(random.Random(1))
    s = Scenario()
    s.wind.fixed = True
    for t in range(100):
        d, v, g = model.step(float(t), 1.0, s.wind)
        assert math.degrees(d) == pytest.approx(300) and ms_to_kn(v) == pytest.approx(12) and g == 0


def test_oscillating_wind_stays_plausible():
    model = WindModel(random.Random(7))
    cfg = Scenario().wind
    dirs, speeds = [], []
    for i in range(36000):  # one hour at 10 Hz
        d, v, _ = model.step(i * 0.1, 0.1, cfg)
        dirs.append(geo.wrap_pi(d - math.radians(cfg.twd)))
        speeds.append(ms_to_kn(v))
    assert max(abs(math.degrees(x)) for x in dirs) < 3 * cfg.osc_amplitude + cfg.gust_veer + 5
    assert max(speeds) > cfg.tws * 1.15  # gusts happened
    assert min(speeds) > cfg.tws * 0.8


def test_gust_shape():
    assert gust_shape(0) == 0 and gust_shape(1) == 0
    assert gust_shape(1 / 3) == pytest.approx(1.0)


def test_leeway_formula_and_sign():
    heel = math.radians(20)
    assert math.degrees(leeway(heel, kn_to_ms(6), 10, False)) == pytest.approx(10 * 20 / 36)
    assert leeway(-heel, kn_to_ms(6), 10, False) < 0
    assert leeway(heel, kn_to_ms(6), 10, True) == 0
    assert leeway(heel, kn_to_ms(0.5), 10, False) == 0


def test_true_wind_formula():
    # Boat at 6 m/s head to wind: apparent 16 from ahead -> true 10 from ahead.
    tws, twa = true_wind(16.0, 0.0, 6.0, 0.0)
    assert tws == pytest.approx(10.0) and twa == pytest.approx(0.0)


def test_dew_point():
    assert dew_point(c_to_k(20.0), 100.0) == pytest.approx(c_to_k(20.0), abs=0.01)
    assert dew_point(c_to_k(25.0), 50.0) - 273.15 == pytest.approx(13.85, abs=0.1)


@pytest.mark.parametrize("twa", [-45.0, 60.0, 120.0, -150.0])
def test_autopilot_holds_twa(twa):
    _, snap = run(calm_scenario(mode="twa", twa=twa), 120)
    assert math.degrees(snap.values["twa"]) == pytest.approx(twa, abs=1.0)


def test_heel_and_leeway_to_leeward():
    _, snap = run(calm_scenario(mode="twa", twa=-50.0), 120)  # wind from port
    v = snap.values
    assert v["boat.heel"] > math.radians(5)  # heels to starboard
    assert v["boat.leeway"] > 0  # slips to starboard


def test_processor_recovers_environment_without_waves():
    _, snap = run(calm_scenario(mode="twa", twa=-50.0), 300)
    v = snap.values
    assert ms_to_kn(v["tws"]) == pytest.approx(ms_to_kn(v["env.wws"]), abs=0.05)
    assert math.degrees(geo.wrap_pi(v["twd"] - v["env.wwd"])) == pytest.approx(0, abs=0.5)
    assert math.degrees(v["leeway_calc"]) == pytest.approx(math.degrees(v["boat.leeway"]), abs=0.1)
    assert ms_to_kn(v["current_drift"]) == pytest.approx(ms_to_kn(v["env.current_drift"]), abs=0.05)
    assert math.degrees(geo.wrap_pi(v["current_set"] - v["env.current_set"])) == pytest.approx(0, abs=3)


def test_wrong_processor_k_shows_leeway_in_current():
    s = calm_scenario(mode="twa", twa=-50.0)
    s.processor.leeway_k = 0.0
    _, snap = run(s, 300)
    v = snap.values
    assert abs(ms_to_kn(v["current_drift"]) - ms_to_kn(v["env.current_drift"])) > 0.1


def test_motoring_has_no_heel_and_engine_data():
    s = calm_scenario(mode="motor", heading=90.0, rpm=2000.0)
    _, snap = run(s, 60)
    v = snap.values
    assert v["boat.heel"] == pytest.approx(0, abs=1e-3)
    assert v["engine.rpm"] == 2000.0 and v["engine.coolant_temp"] is not None
    assert ms_to_kn(v["stw"]) == pytest.approx(2.0 * 2.6, abs=0.1)


def test_engine_values_absent_when_off():
    _, snap = run(calm_scenario(mode="twa"), 5)
    assert snap.values["engine.rpm"] is None and snap.values["engine.coolant_temp"] is None


def test_overrides_are_transmit_only():
    s = calm_scenario(mode="twa", twa=-50.0)
    s.overrides["aws"] = 25.0
    _, snap = run(s, 60)
    assert ms_to_kn(snap.sent["aws"]) == pytest.approx(25.0)
    assert ms_to_kn(snap.values["aws"]) != pytest.approx(25.0, abs=1)
    # Calculations still use the simulated apparent wind.
    assert ms_to_kn(snap.values["tws"]) == pytest.approx(ms_to_kn(snap.values["env.wws"]), abs=0.1)


def test_position_moves_along_cog():
    s = calm_scenario(mode="motor", heading=0.0, rpm=2500.0)
    s.current.drift = 0.0
    sim, snap = run(s, 60)
    assert snap.values["lat"] > s.boat.lat
    assert snap.values["lon"] == pytest.approx(s.boat.lon, abs=1e-5)


def test_sensors_consistent_with_current_in_waves():
    """GPS track minus (heading + true leeway, STW) is exactly the current, even while yawing in waves."""
    sim = Simulation(Scenario(), clock=lambda: 1_760_000_000.0)
    for i in range(3000):
        v = sim.step(0.1).values
        if i < 300:
            continue
        ctw = v["heading_mag"] + v["variation"] + v["boat.leeway"]
        drift, set_ = geo.polar(geo.sub(geo.vector(v["sog"], v["cog"]), geo.vector(v["stw"], ctw)))
        assert ms_to_kn(drift) == pytest.approx(0.5, abs=0.01)
        assert math.degrees(geo.wrap_pi(set_ - math.radians(135))) == pytest.approx(0, abs=1)


def test_processor_current_is_steady_in_waves_and_gusts():
    sim = Simulation(Scenario(), clock=lambda: 1_760_000_000.0)
    for i in range(6000):
        v = sim.step(0.1).values
        if i < 1200:
            continue
        assert ms_to_kn(v["current_drift"]) == pytest.approx(0.5, abs=0.06)
        assert math.degrees(geo.wrap_pi(v["current_set"] - math.radians(135))) == pytest.approx(0, abs=6)


def test_wave_period_drives_wavelength_and_old_files_load():
    from n2k_sim.config import Waves
    from n2k_sim.environment.model import wavelength

    assert wavelength(5.0) == pytest.approx(39.0, abs=0.1)
    assert wavelength(8.0) == pytest.approx(99.9, abs=0.2)
    assert Waves.model_validate({"length": 40.0}).period == pytest.approx(5.1)
    s = Scenario()
    s.waves.period = 8.0
    _, snap = run(s, 1)
    assert snap.values["env.wave_period"] == 8.0
    assert snap.values["env.wave_length"] == pytest.approx(99.9, abs=0.2)


def test_ground_wind_matches_environment():
    """130306 refs 0/3 carry the ground wind: it must equal the simulated wind over ground."""
    _, snap = run(Scenario(), 300)
    v = snap.values
    assert ms_to_kn(v["gws"]) == pytest.approx(ms_to_kn(v["env.gws"]), abs=0.05)
    assert math.degrees(geo.wrap_pi(v["gwd"] - v["env.gwd"])) == pytest.approx(0, abs=0.2)
    assert math.degrees(geo.wrap_pi(v["gwd"] - v["heading_true"] - v["gwa"])) == pytest.approx(0, abs=1e-6)


def test_sail_roll_damping_factor():
    from n2k_sim.boat.model import sail_roll_damping

    assert sail_roll_damping(kn_to_ms(20), True, 0.35, 15) == 1.0  # motoring: sails down
    assert sail_roll_damping(kn_to_ms(20), False, 0.35, 15) == pytest.approx(0.35)
    assert sail_roll_damping(kn_to_ms(7.5), False, 0.35, 15) == pytest.approx(0.675)
    assert sail_roll_damping(0.0, False, 0.35, 15) == 1.0


def _wave_roll_amplitude(**autopilot) -> float:
    s = Scenario()
    s.wind.fixed = True
    for k, v in autopilot.items():
        setattr(s.autopilot, k, v)
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    amp = 0.0
    for i in range(1500):
        v = sim.step(0.1).values
        if i > 600:
            amp = max(amp, abs(v["roll"] - v["boat.heel"]))
    return math.degrees(amp)


def test_sails_damp_wave_roll_upwind_but_not_under_motor():
    # Same heading relative to the waves (waves from 290°): 245° true heading in both cases.
    upwind = _wave_roll_amplitude(mode="twa", twa=55.0)  # TWD 300 -> heading 245
    motoring = _wave_roll_amplitude(mode="motor", heading=245.0, rpm=2500.0)
    assert upwind < 0.5 * motoring


def test_wave_attitude_follows_surface_slope():
    """Wave roll/pitch have the sign of the sea-surface slope the 3D view draws."""
    from n2k_sim.boat.model import PITCH_FACTOR, ROLL_FACTOR

    s = Scenario()
    s.wind.fixed = True
    s.boat.sail_roll_damping = 1.0  # undamped, so roll − heel is the pure wave roll
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    for i in range(1200):
        sim.step(0.1)
        b, e = sim.boat_state, sim.env_state
        if i < 300:
            continue
        a = math.atan(math.pi * e.wave_height / e.wave_length)
        p, irr = b.wave_phase, e.wave_irregularity
        sp = math.sin(p) + irr * math.sin(1.6 * p + 0.7)
        assert b.pitch == pytest.approx(-PITCH_FACTOR * a * math.cos(b.wave_mu) * sp, abs=1e-9)
        assert b.roll - b.heel == pytest.approx(ROLL_FACTOR * a * math.sin(b.wave_mu) * sp, abs=1e-9)


@pytest.mark.parametrize("twa", [40.0, -40.0, 90.0, -90.0, 150.0, -150.0])
@pytest.mark.parametrize("toward_wind", [True, False])
def test_tack_turns_through_wind_and_gybe_away(twa, toward_wind):
    """Tack heads up through the wind, gybe bears away through dead downwind; both end on the mirrored TWA."""
    sim = Simulation(calm_scenario(mode="twa", twa=twa), clock=lambda: 1_760_000_000.0)
    sim.step(0.1)
    sim.boat.maneuver(toward_wind)
    sim.scenario.autopilot.twa = -twa
    side = 1 if twa > 0 else -1
    expected_dir = side if toward_wind else -side  # +1 = turning to starboard
    last, turned = sim.boat_state.heading, 0.0
    for _ in range(1200):
        sim.step(0.1)
        step = geo.wrap_pi(sim.boat_state.heading - last)
        last = sim.boat_state.heading
        assert step * expected_dir >= -1e-6
        turned += step
    twa_end = math.degrees(geo.wrap_pi(sim.snapshot.values["env.wwd"] - sim.boat_state.heading))
    assert twa_end == pytest.approx(-twa, abs=2)
    # tack sweeps across 0° TWA (2|twa|), gybe across 180° (360 − 2|twa|)
    expected = 2 * abs(twa) if toward_wind else 360 - 2 * abs(twa)
    assert math.degrees(abs(turned)) == pytest.approx(expected, abs=3)
