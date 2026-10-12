import numpy as np
import pytest

from leo.analysis.glrt_orbit_phase import OrbitPhasePort
from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, fit_wrapped, nuisance_design
from leo.sky.frames import EARTH_ROTATION_RATE_RAD_S, teme_to_ecef


def test_orbit_phase_frequency_and_horizon_derivatives_match_finite_differences():
    nodes = np.arange(-2.0, 5.25, 0.25)
    positions = np.zeros((2, len(nodes), 3))
    velocities = np.zeros_like(positions)
    positions[0, :, 0] = 6900
    positions[0, :, 1] = 7 * nodes
    velocities[0, :, 1] = 7
    positions[1, :, 0] = 6500
    positions[1, :, 1] = 2000 + 7 * nodes
    velocities[1, :, 1] = 7
    times = np.array([0.03, 1.03, 2.03])
    port = OrbitPhasePort(positions, velocities, nodes, times, np.full(3, 11e9), 0, 0, 0)
    frequency, opportunity, df, dq = port.predict(0.08)
    left = port.predict(0.08 - 1e-4)
    right = port.predict(0.08 + 1e-4)
    np.testing.assert_allclose(df, (right[0] - left[0]) / 2e-4, rtol=1e-7, atol=1e-6)
    np.testing.assert_allclose(dq, (right[1] - left[1]) / 2e-4, rtol=1e-6, atol=1e-9)
    assert np.all(opportunity[:, 0] == 1)
    assert np.all((opportunity[:, 1] > 0) & (opportunity[:, 1] < 1))
    np.testing.assert_allclose(port.predict(0.08, [1])[0], frequency[:, 1, None])
    varying = port.predict(np.array([0.08, -0.13]))
    for s, phase in enumerate([0.08, -0.13]):
        independent = port.predict(phase, [s])
        for actual, expected in zip(varying, independent, strict=True):
            np.testing.assert_allclose(actual[:, s, None], expected)
    with pytest.raises(ValueError, match="one finite phase"):
        port.predict([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="outside"):
        port.predict(30)


def test_shared_orbit_phase_is_recovered_separately_from_receiver_drift():
    n = 320
    times = np.linspace(0, 300, n)
    groups = np.arange(n) % 4
    rf = 10.45e9 + 0.25e9 * ((groups % 2) * 4 + (np.arange(n) // 4) % 4 + 1)
    base = np.column_stack((20000 * np.sin(times / 70), -35000 * np.cos(times / 50), 70000 + times))
    timing = np.column_stack(
        (500 * np.sin(times / 20), -700 * np.cos(times / 27), np.full(n, 100.0))
    )
    blank = FrequencyEvidence(
        tuple(map(str, range(n))),
        np.zeros((n, 1)),
        np.ones((n, 1)),
        np.full(n, 0.95),
        groups,
        times,
    )
    design, _, span = nuisance_design(blank, rf, coefficient=True)
    beta = np.array([-80000.0, -104000.0, -54000.0, -16000.0, 2 * span, 1.5 * span, -600.0])
    identity = (np.arange(n) // 20) % 2
    phase = 1.25
    y = (base + timing * phase)[np.arange(n), identity] + design @ beta
    data = FrequencyEvidence(
        blank.ids, y[:, None], blank.candidate_weight, blank.signal_probability, groups, times
    )

    class Provider:
        def predict(self, t, indices=None):
            idx = np.arange(3) if indices is None else np.array(indices)
            pred = (base + timing * t)[:, idx]
            return pred, np.ones_like(pred), timing[:, idx], np.zeros_like(pred)

    config = WrappedConfig(
        scale_hz=125.0,
        satellite_penalty=8.0,
        maximum_satellites=3,
        iterations=15,
        nuisance_iterations=60,
        em_iterations=80,
    )
    result = fit_wrapped(
        data,
        base,
        np.ones_like(base),
        rf,
        [dict(beta=beta, phase_s=0.8, active=[0, 1])],
        coefficient=True,
        config=config,
        orbit_provider=Provider(),
    )
    assert result["phase_s"] == pytest.approx(phase, abs=0.01)
    np.testing.assert_allclose(result["offsets_hz"], beta[:4], atol=2.0)
    np.testing.assert_allclose(result["drift_hz_s"], [2.0, 1.5], atol=0.02)
    assert result["coefficient_hz_ghz"] == pytest.approx(-600.0, abs=3.0)


def test_unobservable_null_does_not_pay_a_nuisance_seed_penalty():
    n = 32
    groups = np.arange(n) % 4
    data = FrequencyEvidence(
        tuple(map(str, range(n))),
        np.zeros((n, 1)),
        np.ones((n, 1)),
        np.ones(n),
        groups,
        np.arange(n, dtype=float),
    )
    result = fit_wrapped(
        data,
        np.zeros((n, 3)),
        np.zeros((n, 3)),
        np.full(n, 11e9),
        [dict(beta=[100.0, 200.0, 300.0, 400.0, 1000.0, 1000.0])],
    )
    assert result["score"] == 0
    assert result["active"] == []
    assert result["drift_hz_s"] == [0.0, 0.0]


def test_orbital_phase_holds_earth_rotation_fixed_and_matches_numeric_derivatives():
    nodes = np.arange(-2.0, 5.25, 0.25)
    fixed = np.broadcast_to([6900.0, 1000.0, 1000.0], (1, len(nodes), 3))
    p, v = teme_to_ecef(fixed, np.zeros_like(fixed), nodes * EARTH_ROTATION_RATE_RAD_S)
    times = np.array([0.03, 1.03, 2.03])
    args = (p, v, nodes, times, np.full(3, 11e9), 0, 0, 0)
    clock = OrbitPhasePort(*args)
    orbital = OrbitPhasePort(*args, inertial_phase=True)
    np.testing.assert_allclose(orbital.predict(0)[0], clock.predict(0)[0], atol=1e-10)
    np.testing.assert_allclose(orbital.predict(0.8)[0], orbital.predict(0)[0], atol=1e-5)
    assert np.max(abs(clock.predict(0.8)[0] - clock.predict(0)[0])) > 1e-4
    moving = fixed.copy()
    moving[0, :, 1] += 7 * nodes
    inertial_velocity = np.zeros_like(moving)
    inertial_velocity[0, :, 1] = 7
    p, v = teme_to_ecef(moving, inertial_velocity, nodes * EARTH_ROTATION_RATE_RAD_S)
    port = OrbitPhasePort(p, v, nodes, times, np.full(3, 11e9), 0, 0, 0, inertial_phase=True)
    _, _, df, dq = port.predict(0.08)
    left, right = port.predict(0.08 - 1e-4), port.predict(0.08 + 1e-4)
    np.testing.assert_allclose(df, (right[0] - left[0]) / 2e-4, rtol=1e-7, atol=1e-6)
    np.testing.assert_allclose(dq, (right[1] - left[1]) / 2e-4, rtol=1e-6, atol=1e-9)


@pytest.mark.parametrize("solver", ["irls", "lbfgs"])
def test_individual_ephemeris_errors_are_recovered_with_a_charged_prior(solver):
    n = 320
    times = np.linspace(0, 300, n)
    groups = np.arange(n) % 4
    rf = 10.45e9 + 0.25e9 * ((groups % 2) * 4 + (np.arange(n) // 4) % 4 + 1)
    base = np.column_stack((20000 * np.sin(times / 70), -35000 * np.cos(times / 50)))
    timing = np.column_stack((500 * np.sin(times / 20), -700 * np.cos(times / 27)))
    blank = FrequencyEvidence(
        tuple(map(str, range(n))),
        np.zeros((n, 1)),
        np.ones((n, 1)),
        np.full(n, 0.95),
        groups,
        times,
    )
    design, _, span = nuisance_design(blank, rf, coefficient=True)
    beta = np.array([-80000.0, -104000.0, -54000.0, -16000.0, 2 * span, 1.5 * span, -600.0])
    identity = (np.arange(n) // 20) % 2
    phases = np.array([1.25, -0.75])
    y = (base + timing * phases)[np.arange(n), identity] + design @ beta
    data = FrequencyEvidence(
        blank.ids, y[:, None], blank.candidate_weight, blank.signal_probability, groups, times
    )

    class Provider:
        def predict(self, phase, indices=None):
            idx = np.arange(2) if indices is None else np.asarray(indices)
            pred = base[:, idx] + timing[:, idx] * np.asarray(phase)
            return pred, np.ones_like(pred), timing[:, idx], np.zeros_like(pred)

    config = WrappedConfig(
        scale_hz=125,
        satellite_penalty=8,
        maximum_satellites=2,
        iterations=10,
        nuisance_iterations=60,
        em_iterations=80,
        relative_phase_sigma_s=1.0,
        nuisance_solver=solver,
    )
    result = fit_wrapped(
        data,
        base,
        np.ones_like(base),
        rf,
        [dict(beta=beta, active=[0, 1])],
        coefficient=True,
        config=config,
        orbit_provider=Provider(),
    )
    delta = np.array(result["satellite_phase_s"])
    np.testing.assert_allclose(result["phase_s"] + delta, phases, atol=0.01)
    assert result["relative_phase_prior_cost"] == pytest.approx(0.5 * delta @ delta)
    cost = (
        16
        + result["relative_phase_prior_cost"]
        + 0.5 * (result["phase_s"] / 3) ** 2
        + 0.5 * sum((np.array(result["drift_hz_s"]) / 10) ** 2)
        + 0.5 * (result["coefficient_hz_ghz"] / 2000) ** 2
    )
    assert result["score"] == pytest.approx(result["log_ratio"] - cost, abs=1e-6)
