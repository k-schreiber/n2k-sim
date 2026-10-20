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
