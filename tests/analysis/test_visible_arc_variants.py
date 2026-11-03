"""Owned numerical tests for multi-peak graph, joint and exclusive EM variants."""

import numpy as np

from leo.analysis.research import visible_arc_variants as variants


def test_deduplication_preserves_resolved_peaks_and_chooses_highest_margin():
    y = np.array([1000.0, 1000.0 + variants.PERIOD, 1100.0, 4000.0, 1020.0])
    reps, members = variants.deduplicate(y, [0.9, 0.7, 0.8, 0.6, 0.5], [1, 1, 1, 1, 2])
    np.testing.assert_array_equal(reps, [0, 3, 4])
    assert members == [[0, 2, 1], [3], [4]]


def test_alias_wrapping_is_invariant_under_integer_periods():
    values = np.linspace(-900000, 900000, 31)
    np.testing.assert_allclose(
        variants.wrap(values + 3 * variants.PERIOD), variants.wrap(values), atol=1e-9
    )


def test_c1_polynomial_prefers_one_line_without_inventing_curvature():
    rng = np.random.default_rng(140)
    t = np.linspace(0, 100, 80)
    fit = variants.fit_polynomial(t, 200000 - 2500 * t + rng.normal(0, 30, len(t)), 60.0)
    assert fit is not None and fit["degree"] == 1 and len(fit["knots"]) == 0
    assert variants.curvature_rms(t, fit) < 1e-6


def test_step_is_not_accepted_as_continuous_polynomial():
    t = np.linspace(0, 100, 80)
    y = 200000 - 2500 * t + 20000 * (t > 50)
    assert variants.fit_polynomial(t, y, 60.0) is None


def test_exclusive_e_step_never_credits_one_peak_to_two_families():
    odds = np.array([[10.0, 9.0], [9.0, 10.0]])
    owner, weights, _ = variants.exclusive_assignment(odds, np.array([0, 0]), soft=True)
    np.testing.assert_array_equal(owner, [0, 1])
    assert np.all(weights.sum(axis=0) <= 1 + 1e-12)
    assert np.all(weights.sum(axis=1) <= 1 + 1e-12)
    assert weights[0, 0] > weights[0, 1]


def test_ambiguous_single_peak_remains_ambiguous_in_em():
    owner, weights, _ = variants.exclusive_assignment(
        np.array([[10.0], [10.0]]), np.array([0]), soft=True
    )
    assert owner[0] in (0, 1)
    np.testing.assert_allclose(weights[:, 0], 0.5, atol=2e-5)
    assert np.all(weights[:, 0] < 0.8)


def test_same_trajectory_is_alternative_identity_but_crossing_curves_are_allowed():
    left = dict(indices=np.arange(30))
    alias_identity = dict(indices=np.arange(10, 30))
    crossing = dict(indices=np.r_[0, 1, np.arange(30, 58)])
    assert variants.duplicate_explanations(left, alias_identity)
    assert not variants.duplicate_explanations(left, crossing)


def fake_hypothesis(candidate, indices):
    return dict(
        candidate_index=candidate, indices=np.asarray(indices), orbit=dict(parameters=np.zeros(3))
    )


def test_joint_search_reconsiders_greedy_ownership(monkeypatch):
    a = np.r_[np.arange(12), np.arange(16, 28)]
    b, c = np.arange(16), np.arange(16, 32)
    hypotheses = [fake_hypothesis(i, ix) for i, ix in enumerate([a, b, c])]
    full = np.full((3, 32), -100.0)
    for i, ix in enumerate([a, b, c]):
        full[i, ix] = 10.0
    monkeypatch.setattr(
        variants,
        "model_odds",
        lambda bank, data, models: full[[h["candidate_index"] for h in models]],
    )
    monkeypatch.setattr(
        variants,
        "finalize",
        lambda bank, data, models: dict(selected=[h["candidate_index"] for h in models]),
    )
    data = dict(probes=np.arange(32))
    greedy = variants.greedy_repair(None, data, hypotheses)
    joint, _, _ = variants.joint_selection(None, data, hypotheses)
    assert greedy["selected"] == [0]
    assert joint["selected"] == [1, 2]


def test_duplicate_model_ablation_reproduces_residual_splitting(monkeypatch):
    hypotheses = [fake_hypothesis(i, np.arange(24)) for i in range(2)]
    odds = np.array([np.r_[np.full(12, 10.0), np.ones(12)], np.r_[np.ones(12), np.full(12, 10.0)]])
    monkeypatch.setattr(
        variants,
        "model_odds",
        lambda bank, data, models: odds[[h["candidate_index"] for h in models]],
    )
    monkeypatch.setattr(
        variants,
        "finalize",
        lambda bank, data, models: dict(selected=[h["candidate_index"] for h in models]),
    )
    data = dict(probes=np.arange(24))
    guarded, _, _ = variants.joint_selection(None, data, hypotheses)
    unguarded, _, _ = variants.joint_selection(None, data, hypotheses, duplicate_overlap=None)
    assert len(guarded["selected"]) == 1
    assert len(unguarded["selected"]) == 2


def physical_bank():
    from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

    site = (37.0, -122.0)
    observer = geodetic_to_ecef_km(*site, 0.0)
    east, north, up = ecef_to_enu_matrix(*site)
    t = np.arange(-20.0, 141.0)
    p = (
        observer
        + (550 - 0.003 * (t[:, None] - 50) ** 2) * up
        + (7 * (t[:, None] - 60)) * east
        + 80 * north
    )
    v = np.broadcast_to(7 * east, p.shape) - 0.006 * (t[:, None] - 50) * up
    return dict(time_s=t, position_km=p[None], velocity_km_s=v[None]), site


def test_weighted_satellite_fit_ignores_zero_weight_clutter():
    bank, site = physical_bank()
    t = np.linspace(0, 100, 51)
    y = variants.frequency(bank, 0, t, [1.2, 120.0, 0.001], site, 11e9)
    noisy = y + np.random.default_rng(141).normal(0, 20, len(t))
    alone = variants.fit_satellite(bank, 0, t, noisy, site, 11e9, 40.0, iterations=36)
    extended = variants.fit_satellite(
        bank,
        0,
        np.r_[t, t],
        np.r_[noisy, noisy + 10000],
        site,
        11e9,
        40.0,
        weights=np.r_[np.ones(len(t)), np.zeros(len(t))],
        iterations=36,
    )
    np.testing.assert_allclose(extended["parameters"], alone["parameters"], atol=1e-6)
    assert alone["rms_hz"] < 40.0


def test_exclusive_em_objective_does_not_increase_and_preserves_one_curve():
    bank, site = physical_bank()
    t = np.linspace(0, 100, 51)
    y = variants.frequency(bank, 0, t, [1.2, 120.0, 0.001], site, 11e9)
    y += np.random.default_rng(142).normal(0, 20, len(t))
    fitted = variants.fit_satellite(bank, 0, t, y, site, 11e9, 40.0, iterations=36)
    hypothesis = dict(candidate_index=0, indices=np.arange(len(t)), orbit=fitted)
    data = dict(
        times=t,
        values=y,
        probes=np.arange(len(t)),
        quality=np.ones(len(t)),
        site=site,
        rf_hz=11e9,
        sigma=40.0,
    )
    result = variants.em_association(bank, data, [hypothesis], [(1.0, (0,))], rounds=4)
    history = result["em_runs"][0]["history"]
    assert max(np.diff(history)) < 1e-6
    assert len(result["tracks"]) == 1
    assert len(result["tracks"][0]["indices"]) >= 49
