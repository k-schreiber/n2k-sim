"""Wave orbital velocity: the hull surges with the orbit, the paddle wheel reads the local water
(docs/spec/wave-orbital-stw.md §9). Amplitudes are ½ peak-to-peak on the 10 Hz truth."""

import math

import pytest

from n2k_sim import geo
from n2k_sim.boat.model import HULL_DEPTH, SECONDARY_FREQ, orbital_fwd, surge_ratio
from n2k_sim.config import G, Scenario
from n2k_sim.n2k.gateway import Gateway
from n2k_sim.simulation import Simulation
from n2k_sim.units import KNOT

WARMUP = 600  # steps of 0.1 s
TAU = 8.0  # boat.stw_time_constant_s default
HEAD, FOLLOWING, BEAM = 290.0, 110.0, 20.0  # headings; the waves come from 290°


def orbital_scenario(heading: float, height: float = 1.0, **sections) -> Scenario:
    """Beam reach (wind from 200°) in heading mode, no current, one wave component, no averaging."""
    s = Scenario()
    s.wind.fixed = True
    s.wind.twd = 200.0
    s.current.drift = 0.0
    s.autopilot.mode = "heading"
    s.autopilot.heading = heading
    s.waves.orbital = True
    s.waves.height = height
    s.waves.irregularity = 0.0
    s.sensors.stw_average_s = 0.0
    for name, fields in sections.items():
        for k, v in fields.items():
            setattr(getattr(s, name), k, v)
    return s


def motoring(heading: float, speed_kn: float, **sections) -> Scenario:
    s = orbital_scenario(heading, **sections)
    s.autopilot.mode = "motor"
    s.autopilot.rpm = speed_kn / s.boat.motor_speed_per_1000rpm * 1000.0
    return s


def run(s: Scenario, steps: int = 3000):
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    rows = []
    for i in range(steps):
        v = sim.step(0.1).values
        if i >= WARMUP:
            rows.append((v, sim.boat_state))
    return sim, rows


def amp(xs) -> float:
    xs = list(xs)
    return (max(xs) - min(xs)) / 2


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)


def stw_wave(rows) -> list[float]:
    return [v["boat.stw_local"] - b.stw for v, b in rows]


def surge(rows) -> list[float]:
    return [b.wave_surge for _, b in rows]


def linear_response(sim: Simulation, rows, component: int = 0) -> tuple[float, float, float, complex, float]:
    """(ω_e, expected STW amplitude, expected surge amplitude, H = w/u_h, U_h) of one wave component
    from the linear response H = κ′ + (1 − κ′)/(1 + j·ω_e·τ), κ′ = sinc(k·LWL·|cos μ_w|/2)·ω/ω_e."""
    env, b = sim.env_state, sim.boat_state
    f = SECONDARY_FREQ if component else 1.0
    omega0 = 2 * math.pi / env.wave_period
    k0 = omega0**2 / G
    omega_e = f * (omega0 + k0 * mean(r[1].sog for r in rows) * math.cos(b.wave_mu))
    k = f * k0
    omega = math.sqrt(f) * omega0
    a = env.wave_height / 2 * (env.wave_irregularity / f if component else 1.0)
    along = abs(math.cos(b.mu_w))
    x = k * sim.scenario.boat.lwl * along / 2
    ratio = max(-2.0, min(2.0, omega / omega_e))
    kp = sim.scenario.boat.wave_surge_factor * (math.sin(x) / x) * ratio
    h = kp + (1 - kp) / complex(1, abs(omega_e) * TAU)
    u_h = a * omega * math.exp(-k * HULL_DEPTH) * along
    depth_ratio = math.exp(-k * (sim.scenario.sensors.paddlewheel_depth - HULL_DEPTH))
    return abs(omega_e), abs(h - depth_ratio) * u_h, abs(h) * u_h, h, u_h


def frames(s: Scenario, steps: int = 900):
    """Existing-key values and PGN payloads of a run that includes a tack."""
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    gw = Gateway(s.output.source, s.output.pgns)
    new = ("boat.stw_local", "boat.wave_surge", "boat.orbital_fwd")
    out = []
    for i in range(steps):
        snap = sim.step(0.1)
        if i == 300:
            sim.boat.maneuver(True)
            s.autopilot.twa = -s.autopilot.twa
        vals = {k: v for k, v in snap.values.items() if k not in new}
        out.append((vals, [f.data for f in gw.poll(1_760_000_000.0 + i * 0.1, snap.sent)]))
    return out


# --- off switches ------------------------------------------------------------------------------------


@pytest.mark.parametrize("off", [{"height": 0.0}, {"enabled": False}])
def test_off_switches_match_orbital_disabled(off):
    reference, test = Scenario(), Scenario()
    test.waves.orbital = True
    test.sensors.paddlewheel_lag_s = 0.5
    for k, v in off.items():
        setattr(reference.waves, k, v)
        setattr(test.waves, k, v)
    assert frames(test) == frames(reference)


def test_orbital_off_leaves_stw_and_ground_untouched():
    _, rows = run(Scenario(), 900)
    for v, b in rows:
        assert b.wave_surge == 0.0 and v["stw"] == b.stw and v["boat.stw_local"] == b.stw


# --- amplitudes, frequency, means ----------------------------------------------------------------------


def test_head_seas_at_6_kn_match_the_spec_table():
    """Spec §6, pinned: 1 m / 5 s head seas at 6 kn give STW ±0.40 kn and SOG ±0.73 kn."""
    _, rows = run(motoring(HEAD, 6.0))
    assert amp(stw_wave(rows)) / KNOT == pytest.approx(0.40, rel=0.05)
    assert amp(b.sog for _, b in rows) / KNOT == pytest.approx(0.73, rel=0.05)


@pytest.mark.parametrize("heading", [HEAD, FOLLOWING])
@pytest.mark.parametrize("height", [1.0, 2.0])
def test_stw_and_surge_amplitudes_follow_linear_response(heading, height):
    sim, rows = run(orbital_scenario(heading, height))
    _, stw_amp, surge_amp, _, _ = linear_response(sim, rows)
    assert amp(stw_wave(rows)) == pytest.approx(stw_amp, rel=0.05)
    assert amp(surge(rows)) == pytest.approx(surge_amp, rel=0.05)


def test_drag_only_hull_leaves_the_orbit_on_the_wheel():
    sim, rows = run(orbital_scenario(HEAD, boat={"wave_surge_factor": 0.0}))
    _, stw_amp, surge_amp, _, _ = linear_response(sim, rows)
    assert amp(stw_wave(rows)) == pytest.approx(stw_amp, rel=0.05)
    assert amp(surge(rows)) == pytest.approx(surge_amp, rel=0.05)
    assert amp(surge(rows)) < 0.1 * amp(stw_wave(rows))


def test_secondary_component_adds_its_own_response():
    sim, rows = run(orbital_scenario(HEAD, waves={"irregularity": 0.6}), 6000)
    primary, secondary = linear_response(sim, rows, 0), linear_response(sim, rows, 1)
    assert amp(stw_wave(rows)) == pytest.approx(primary[1] + secondary[1], rel=0.05)
    assert amp(surge(rows)) == pytest.approx(primary[2] + secondary[2], rel=0.05)


def test_beam_seas_barely_move_the_wheel():
    _, rows = run(orbital_scenario(BEAM))
    assert amp(stw_wave(rows)) < 0.1 * KNOT


@pytest.mark.parametrize("heading", [HEAD, FOLLOWING])
def test_stw_oscillates_at_the_encounter_frequency(heading):
    sim, rows = run(orbital_scenario(heading))
    omega_e = linear_response(sim, rows)[0]
    x = stw_wave(rows)
    up = [i for i in range(1, len(x)) if x[i - 1] < 0 <= x[i]]
    period = (up[-1] - up[0]) / (len(up) - 1) * 0.1
    assert period == pytest.approx(2 * math.pi / omega_e, rel=0.03)


@pytest.mark.parametrize("heading", [HEAD, FOLLOWING])
def test_means_over_many_cycles(heading):
    """Mean STW equals v. The hull drifts in the wave travel direction (it lingers where it moves
    with the waves): ⟨w⟩ ≈ k·U_h²·Re(H)/(2·ω_e), forward in following seas, aft in head seas."""
    sim, rows = run(orbital_scenario(heading), 6000)  # ≥ 50 cycles
    omega_e, _, _, h, u_h = linear_response(sim, rows)
    k = (2 * math.pi / sim.env_state.wave_period) ** 2 / G
    drift = -math.cos(sim.boat_state.mu_w) * k * u_h**2 * h.real / (2 * omega_e)
    assert mean(stw_wave(rows)) == pytest.approx(0.0, abs=0.02 * KNOT)
    assert mean(surge(rows)) == pytest.approx(drift, rel=0.15)


# --- kinematics and signs ---------------------------------------------------------------------------------


def test_ground_minus_wheel_is_current_plus_orbit():
    s = orbital_scenario(HEAD)
    s.current.drift = 0.8
    sim, rows = run(s, 1200)
    for v, b in rows:
        u_wheel = orbital_fwd(sim.env_state, b.wave_phase, b.mu_w, s.sensors.paddlewheel_depth)
        rest = geo.sub(geo.vector(b.sog, b.cog), geo.vector(v["boat.stw_local"], b.ctw))
        expected = geo.add(geo.vector(v["env.current_drift"], v["env.current_set"]), geo.vector(u_wheel, b.ctw))
        assert rest == pytest.approx(expected, abs=1e-9)


def test_head_sea_crest_speeds_up_the_wheel_and_slows_the_hull():
    _, rows = run(orbital_scenario(HEAD))
    crests = [(v, b) for v, b in rows if math.cos(b.wave_phase) > 0.99]
    assert crests
    for v, b in crests:
        assert v["boat.stw_local"] > b.stw and b.wave_surge < 0


def test_overtaking_the_waves_reverses_the_pressure_response():
    assert surge_ratio(1.0, 0.8) == pytest.approx(1.25)
    assert surge_ratio(1.0, -0.8) == pytest.approx(-1.25)
    assert surge_ratio(1.0, 0.3) == 2.0 and surge_ratio(1.0, -0.3) == -2.0 and surge_ratio(1.0, 0.0) == 2.0


def test_switching_on_mid_run_keeps_sog_continuous():
    s = orbital_scenario(FOLLOWING)
    s.waves.orbital = False
    sim = Simulation(s, clock=lambda: 1_760_000_000.0)
    for _ in range(600):
        sim.step(0.1)
    before = sim.boat_state.sog
    s.waves.orbital = True
    sim.step(0.1)
    assert abs(sim.boat_state.sog - before) < 0.05 * KNOT


# --- paddle wheel processing ------------------------------------------------------------------------------


def test_wheel_reports_speed_whichever_way_it_turns():
    """At rest in head seas the hull follows the water almost like a cork, but the rest flows back and
    forth past the wheel. The log counts pulses in both directions, so it reports |speed|: a positive
    mean (~0.07 kn here) although the boat doesn't move."""
    _, rows = run(motoring(HEAD, 0.0))
    local = [v["boat.stw_local"] for v, _ in rows]
    assert sum(x < 0 for x in local) > 0.3 * len(local) and abs(mean(local)) < 0.005 * KNOT
    for v, _ in rows:
        assert v["stw"] == abs(v["boat.stw_local"])
    _, averaged = run(motoring(HEAD, 0.0, sensors={"stw_average_s": 1.0}))
    assert min(v["stw"] for v, _ in averaged) >= 0
    assert mean(v["stw"] for v, _ in averaged) > 0.05 * KNOT


def test_log_averages_the_wheel_over_its_interval():
    sim, rows = run(orbital_scenario(HEAD, sensors={"stw_average_s": 1.0}))
    omega_e = linear_response(sim, rows)[0]
    x = math.pi * 1.0 / (2 * math.pi / omega_e)
    reported = amp(v["stw"] - b.stw for v, b in rows)
    assert reported == pytest.approx(abs(math.sin(x) / x) * amp(stw_wave(rows)), rel=0.10)


def test_paddlewheel_lag_is_first_order():
    lag = 1.0
    sim, rows = run(orbital_scenario(HEAD, sensors={"paddlewheel_lag_s": lag}))
    omega_e = linear_response(sim, rows)[0]
    expected = amp(stw_wave(rows)) / abs(complex(1, omega_e * lag))
    assert amp(v["stw"] - b.stw for v, b in rows) == pytest.approx(expected, rel=0.05)


@pytest.mark.parametrize("orbital", [False, True])
def test_stw_factor_scales_only_the_reported_stw(orbital):
    runs = []
    for factor in (1.0, 1.05):
        s = orbital_scenario(HEAD, sensors={"stw_factor": factor, "stw_average_s": 1.0})
        s.waves.orbital = orbital
        runs.append(run(s, 900)[1])
    for (v1, _), (v2, _) in zip(*runs):
        assert v2["stw"] == pytest.approx(1.05 * v1["stw"], rel=1e-12)
        assert v2["boat.stw_local"] == v1["boat.stw_local"]


# --- processor and scenario options -----------------------------------------------------------------------


def test_processor_stw_damping_smooths_leeway():
    """Leeway ∝ 1/STW² is the processor value most sensitive to the wheel's wave part."""

    def leeway_spread(tau):
        _, rows = run(orbital_scenario(HEAD, processor={"stw_damping_s": tau}))
        return amp(v["leeway_calc"] for v, _ in rows)

    assert leeway_spread(5.0) < 0.25 * leeway_spread(0.0)


def test_waves_follow_the_mean_wind_when_asked():
    s = Scenario()
    s.wind.twd = 250.0
    s.waves.follow_wind = True
    _, rows = run(s, 700)
    assert all(math.degrees(v["env.wave_dir"]) == pytest.approx(250.0) for v, _ in rows)
