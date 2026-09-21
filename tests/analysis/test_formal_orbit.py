import numpy as np
from fit_formal_orbit import prepare_strict_phase_states

from leo.analysis.research.formal_orbit import (
    FormalOrbitConfig,
    FormalOrbitData,
    fit_formal_orbit,
    whiten_ar1,
)
from leo.analysis.research.regional_doppler import Region


def _synthetic(seed=3, collinear=False):
    rng = np.random.default_rng(seed)
    n = 160
    t = np.arange(n, dtype=float)
    track = np.repeat(np.arange(8), 20)
    segment = track.copy()
    source = np.tile(np.repeat([10, 11], 20), 4)
    age = np.where(source == 10, 12.0, 20.0)
    # Artificial but physically dimensioned ECEF satellite states. The fitter
    # itself, rather than this fixture, performs the Doppler calculation.
    theta = np.linspace(0.1, 5.8, n)
    if collinear:
        theta[:] = 0.7
    p = np.column_stack((7000 * np.cos(theta), 7000 * np.sin(theta), 900 + 500 * np.sin(2 * theta)))
    v = np.column_stack((-5 * np.sin(theta), 5 * np.cos(theta), 0.7 * np.cos(2 * theta)))
    dp = np.column_stack((8 * np.sin(theta), -5 * np.cos(theta), 3 * np.ones(n)))
    dv = np.column_stack((0.02 * np.cos(theta), 0.03 * np.sin(theta), -0.01 * np.ones(n)))
    region = Region(40.0, -75.0, 120, 120)
    true_x = np.array([8.0, -6.0])
    receiver = region.points([true_x[0]], [true_x[1]]).ecef_km[0]
    from leo.analysis.research.formal_orbit import doppler_hz, phase_rate_design_hz_per_s_h

    base = doppler_hz(receiver, p, v)
    design = phase_rate_design_hz_per_s_h(receiver, p - dp, v - dv, p + dp, v + dv, age)
    rate = np.where(source == 10, 0.035, -0.025)
    offsets = np.repeat(rng.normal(0, 300, 8), 20)
    noise = np.empty(n)
    for g in np.unique(track):
        m = track == g
        z = rng.normal(0, 12, m.sum())
        for k in range(1, len(z)):
            z[k] += 0.8 * z[k - 1]
        noise[m] = z
    y = base + design * rate + offsets + noise
    training = np.ones(n, bool)
    training[4::5] = False
    data = FormalOrbitData(
        y, training, segment, track, source, age, p, v, p - dp, v - dv, p + dp, v + dv, t
    )
    return data, region, true_x


def test_ar1_whitening_does_not_count_copies_as_iid():
    x = np.ones((20, 1))
    track = np.zeros(20, int)
    time = np.arange(20, dtype=float)
    white, logdet = whiten_ar1(x, track, time, 0.95, 1.0)
    assert np.sum(white**2) < 2.1
    assert np.isfinite(logdet)


def test_fit_recovers_position_and_heldout_is_isolated():
    data, region, truth = _synthetic()
    cfg = FormalOrbitConfig(measurement_sigma_hz=16, ar1_rho=0.8, robust_df=4)
    a = fit_formal_orbit(data, region, [0, 0], cfg)
    changed = FormalOrbitData(
        *(
            np.where(~data.training, data.y_hz + 1e6, data.y_hz) if i == 0 else v
            for i, v in enumerate(data.__dict__.values())
        )
    )
    b = fit_formal_orbit(changed, region, [0, 0], cfg)
    assert np.linalg.norm(np.asarray(a.x_km) - truth) < 2.0
    assert np.allclose(a.x_km, b.x_km, atol=1e-7)
    assert a.evaluation_rms_hz != b.evaluation_rms_hz


def test_degenerate_geometry_is_reported():
    data, region, _ = _synthetic(collinear=True)
    result = fit_formal_orbit(data, region, [0, 0], FormalOrbitConfig(measurement_sigma_hz=45))
    assert result.identifiability in {"weak", "insufficient"}
    assert result.position_covariance_km2 is None or result.major_95_km > 10


def test_gaussian_ablation_matches_normalized_independent_likelihood():
    from leo.analysis.research.formal_orbit import doppler_hz

    data, region, _ = _synthetic()
    cfg = FormalOrbitConfig(
        gaussian_noise=True,
        ar1_rho=0,
        infer_measurement_sigma=False,
        measurement_sigma_hz=250,
        phase_rate_bound_s_h=0,
    )
    fit = fit_formal_orbit(data, region, [0, 0], cfg)
    receiver = region.points([fit.x_km[0]], [fit.x_km[1]]).ecef_km[0]
    residual = data.y_hz - doppler_hz(receiver, data.p_km, data.v_km_s)
    for segment, offset in fit.segment_offsets_hz.items():
        residual[data.segment == int(segment)] -= offset
    expected = np.sum(data.training) * np.log(250 * np.sqrt(2 * np.pi))
    expected += np.sum((residual[data.training] / 250) ** 2) / 2
    expected += len(fit.rate_corrections_s_h) * np.log(
        cfg.phase_rate_sigma_s_h * np.sqrt(2 * np.pi)
    )
    assert np.isclose(fit.negative_log_posterior, expected, atol=1e-6)
    assert all(rate == 0 for rate in fit.rate_corrections_s_h.values())
    assert np.isclose(fit.robust_weight_ess, np.sum(data.training))


def test_noise_bound_does_not_trap_simplex_after_distant_start():
    data, region, _ = _synthetic()
    result = fit_formal_orbit(
        data, region, [50, 50], FormalOrbitConfig(measurement_sigma_hz=2000, ar1_rho=0.8)
    )
    assert result.converged
    assert result.measurement_sigma_hz < 100
    assert result.optimizer_restarts == 1


def test_duplicate_observation_ids_rejected():
    data, region, _ = _synthetic()
    values = {**data.__dict__, "observation_id": np.zeros(len(data.y_hz), int)}
    data = FormalOrbitData(**values)
    try:
        fit_formal_orbit(data, region, [0, 0])
    except ValueError as error:
        assert "duplicate observation" in str(error)
    else:
        raise AssertionError("duplicates accepted")


def test_strict_preparation_uses_orbit_phase_and_epoch_age_for_no_history():
    z = {
        "y": np.zeros(4),
        "p": np.zeros((4, 3)),
        "v": np.zeros((4, 3)),
        "episode": np.array([0, 0, 1, 1]),
        "time": np.array([0.0, 1.0, 2.0, 3.0]),
        # Poisoned legacy clock-shift arrays must never be consulted.
        "p-0.5": np.full((4, 3), 999.0),
        "p0.5": np.full((4, 3), 999.0),
    }
    assignments = [{"session_id": "a", "episode_id": "x"}, {"session_id": "b", "episode_id": "y"}]
    targets = [
        {**assignments[0], "norad": 10, "predicted_phase_s": 0.4, "history": None},
        {**assignments[1], "norad": 11, "predicted_phase_s": -0.2, "history": {}},
    ]
    rows = [
        {
            **assignments[0],
            "best_norad": 10,
            "capture_start_utc_ns": 7_200_000_000_000,
            "winning_epoch_utc_ns": 3_600_000_000_000,
            "winning_collected_utc_ns": 6_000_000_000_000,
            "winning_tle_text": "A",
        },
        {
            **assignments[1],
            "best_norad": 11,
            "capture_start_utc_ns": 10_800_000_000_000,
            "winning_epoch_utc_ns": 3_600_000_000_000,
            "winning_collected_utc_ns": 7_000_000_000_000,
            "winning_tle_text": "B",
        },
    ]
    calls = []

    def propagate(cat, indices, start, time, orbit_time_s, clock_s):
        calls.append((cat, orbit_time_s, clock_s))
        p = np.full((1, len(time), 3), orbit_time_s)
        v = np.full_like(p, orbit_time_s + 1)
        return p, v, [0]

    arrays, source, age = prepare_strict_phase_states(
        z,
        assignments,
        targets,
        rows,
        propagate=propagate,
        expected_sources=2,
        parse_catalogue=lambda x: x,
    )
    assert set(source) == {10, 11}
    assert np.allclose(age, [1, 1, 2, 2])  # history absence does not erase causal TLE age
    assert all(clock == 0 for _, _, clock in calls)
    assert np.all(arrays["phase_p_plus"][:2] == 1.4)
    assert not np.any(arrays["phase_p_plus"] == 999)
    bad = [dict(row) for row in rows]
    bad[0]["winning_collected_utc_ns"] = None
    try:
        prepare_strict_phase_states(
            z,
            assignments,
            targets,
            bad,
            propagate=propagate,
            expected_sources=2,
            parse_catalogue=lambda x: x,
        )
    except ValueError as error:
        assert "availability" in str(error)
    else:
        raise AssertionError("missing catalogue availability accepted")
