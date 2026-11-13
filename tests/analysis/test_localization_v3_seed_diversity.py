from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery

POLICY = "anchor-round-robin-v1"


def seed_statistics():
    slopes = np.array([[10., 20., 30.], [40., 50., 60.], [70., 80., 90.]])
    shape = np.array([[1., 2., 3.], [3., 1., 2.], [3., 2., 1.]])
    count = np.array([30, 20, 10])
    return dict(
        active=np.ones(3, bool), count=count, ci=np.arange(3),
        fragment_active=np.ones(3, bool), g=np.arange(3), q=np.ones(3),
        fragments=[dict(times=np.array([0., 30.])) for _ in range(3)],
        xz=slopes, xx=np.ones(3), n=count.copy(), mx=np.zeros(3),
        mean=np.array([[100., 200., 300.], [1000., 2000., 3000.],
                       [10000., 20000., 30000.]]),
        component_visible=np.ones((3, 3), bool), shape_rms=shape,
        starts=np.arange(3), rss=slopes**2 + shape**2 * count[:, None],
        hm=np.zeros((3, 3)), xh=np.zeros((3, 3)),
        zh=np.zeros((3, 3)), hh=np.zeros((3, 3)),
    )


def calibration_vectors(intercepts, slopes):
    return np.array([[intercept] * 4 + [slope] * 4
                     for intercept, slope in zip(intercepts, slopes, strict=True)])


def test_legacy_seed_vectors_retain_the_original_anchor_major_order():
    expected = calibration_vectors(
        [0, 100, 200, 300, 2000, 3000, 1000, 30000, 20000, 10000],
        [0, 10, 20, 30, 50, 60, 40, 90, 80, 70],
    )
    stats = seed_statistics()
    for kwargs in ({}, dict(seed_policy="legacy")):
        np.testing.assert_allclose(
            list(discovery.seed_calibrations(stats, np.zeros(8), **kwargs)), expected,
            rtol=0, atol=2e-11,
        )


@pytest.mark.parametrize("budget", [0, 1, 4, 160])
def test_legacy_vectors_exactly_match_the_existing_numerical_oracle(budget):
    from analyze_dsx01_fixed_site import seed_calibrations as oracle

    stats = seed_statistics()
    stats["q"][:] = [0.9, 1.0, 1.1]
    stats["mx"][:] = [-0.9, 0.1, 0.8]
    stats["component_visible"][0, 0] = False
    beta = np.array([100., -200., 300., -400., -1000., 1000., -2000., 2000.])
    expected = list(oracle(stats, beta, budget))
    for kwargs in ({}, dict(seed_policy="legacy")):
        actual = list(discovery.seed_calibrations(stats, beta, budget, **kwargs))
        np.testing.assert_array_equal(actual, expected)


def test_round_robin_spends_the_same_cap_across_active_anchors():
    stats = seed_statistics()
    actual = list(discovery.seed_calibrations(stats, np.zeros(8), 3, seed_policy=POLICY))
    np.testing.assert_allclose(actual, calibration_vectors(
        [0, 100, 2000, 30000], [0, 10, 50, 90],
    ), rtol=0, atol=2e-11)
    full = list(discovery.seed_calibrations(stats, np.zeros(8), seed_policy=POLICY))
    legacy = np.array(list(discovery.seed_calibrations(stats, np.zeros(8))))
    np.testing.assert_array_equal(full, legacy[[0, 1, 4, 7, 2, 5, 8, 3, 6, 9]])


@pytest.mark.parametrize("budget", [-1, 0, 1, 2, 160])
@pytest.mark.parametrize("seed_policy", ["legacy", POLICY])
def test_generator_keeps_its_historical_nonzero_seed_cap(budget, seed_policy):
    actual = list(discovery.seed_calibrations(
        seed_statistics(), np.zeros(8), budget, seed_policy=seed_policy,
    ))
    assert len(actual) == 1 + min(9, max(1, budget))
    np.testing.assert_array_equal(actual[0], np.zeros(8))


@pytest.mark.parametrize("budget", [-1, 0, 1, 2, 160])
def test_single_anchor_is_exactly_legacy_and_inputs_are_preserved(budget):
    stats = seed_statistics()
    stats["active"][:] = [False, True, False]
    original = deepcopy(stats)
    beta = np.array([1., 2., 3., 4., -2000., 2000., -2000., 2000.])
    before = beta.copy()
    expected = list(discovery.seed_calibrations(stats, beta, budget))
    actual = list(discovery.seed_calibrations(stats, beta, budget, seed_policy=POLICY))
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual[0], [1., 2., 3., 4., -750., 750., -750., 750.])
    actual[0][:] = 999
    np.testing.assert_array_equal(beta, before)
    for key in stats.keys() - {"fragments"}:
        np.testing.assert_array_equal(stats[key], original[key])


@pytest.mark.parametrize("seed_policy", ["legacy", POLICY])
def test_yielded_seeds_and_later_input_changes_do_not_mutate_other_seeds(seed_policy):
    stats = seed_statistics()
    beta = np.zeros(8)
    seeds = discovery.seed_calibrations(stats, beta, 3, seed_policy=seed_policy)
    zero = next(seeds)
    beta[:] = 999.
    zero[:] = 1000.
    first = next(seeds)
    np.testing.assert_array_equal(first, calibration_vectors([100], [10])[0])
    first[:] = 2000.
    expected = ([200], [20]) if seed_policy == "legacy" else ([2000], [50])
    np.testing.assert_array_equal(next(seeds), calibration_vectors(*expected)[0])
    np.testing.assert_array_equal(beta, np.full(8, 999.))


def test_round_robin_skips_ineligible_candidates_and_exhausted_anchors():
    stats = seed_statistics()
    stats["component_visible"][:] = False
    stats["component_visible"][0, 2] = True
    stats["component_visible"][1, [0, 2]] = True
    stats["component_visible"][2, 2] = True
    stats["xz"][[0, 1], 2] = 4000.
    actual = list(discovery.seed_calibrations(stats, np.zeros(8), seed_policy=POLICY))
    np.testing.assert_allclose(actual, calibration_vectors(
        [0, 1000, 30000], [0, 40, 90],
    ), rtol=0, atol=2e-11)


def test_round_robin_retains_deterministic_anchor_and_candidate_ties():
    stats = seed_statistics()
    stats["count"][:] = 30
    stats["shape_rms"][:] = 1.
    expected = calibration_vectors([0, 100, 1000, 10000], [0, 10, 40, 70])
    for _ in range(3):
        np.testing.assert_array_equal(list(discovery.seed_calibrations(
            stats, np.zeros(8), 3, seed_policy=POLICY,
        )), expected)


def test_round_robin_retains_the_twenty_anchor_and_eight_candidate_limits():
    stats = seed_statistics()
    for key in ("active", "ci", "fragment_active", "g", "q", "xx", "mx"):
        stats[key] = np.repeat(stats[key][0], 22)
    stats["ci"] = np.arange(22)
    stats["count"] = stats["n"] = np.arange(22, 0, -1)
    stats["fragments"] = [dict(times=np.array([0., 30.])) for _ in range(22)]
    stats["component_visible"] = np.ones((22, 10), bool)
    stats["shape_rms"] = np.tile(np.arange(10.), (22, 1))
    stats["mean"] = 1000 * np.arange(22)[:, None] + 100 * np.arange(10)[None, :]
    stats["xz"] = np.tile(np.arange(10.), (22, 1))
    actual = np.array(list(discovery.seed_calibrations(
        stats, np.zeros(8), 1000, seed_policy=POLICY,
    )))
    assert actual.shape == (161, 8)
    np.testing.assert_allclose(actual[1:21, 0], 1000 * np.arange(20), rtol=0, atol=2e-11)
    assert np.max(actual[1:, 0]) < 20000
    assert np.max(actual[1:, 4:]) == 7


@pytest.mark.parametrize("seed_policy", ["legacy", POLICY])
def test_no_active_anchors_yields_only_the_clipped_zero_seed(seed_policy):
    stats = seed_statistics()
    stats["active"][:] = False
    np.testing.assert_array_equal(list(discovery.seed_calibrations(
        stats, np.zeros(8), seed_policy=seed_policy,
    )), np.zeros((1, 8)))


def test_unknown_policy_fails_before_a_seed_or_discovery_fit():
    with pytest.raises(ValueError, match="seed policy"):
        next(discovery.seed_calibrations(None, None, seed_policy="unknown"))
    with pytest.raises(ValueError, match="seed policy"):
        discovery.fresh_discovery(None, None, seed_policy="unknown")


def test_real_single_anchor_discovery_is_exactly_legacy():
    from check_algo07v3_scan_likelihood import fingerprint

    from tests.analysis.test_localization_v3_position import prepared

    original, _ = prepared()
    diverse, _ = prepared()
    expected = discovery.fresh_discovery(original, 150., budget=4)
    actual = discovery.fresh_discovery(diverse, 150., budget=4, seed_policy=POLICY)
    assert fingerprint(actual) == fingerprint(expected)


@pytest.mark.parametrize("budget, expected", [(0, 0), (1, 1), (4, 4), (40, 10)])
def test_fresh_discovery_keeps_matched_proposal_and_refinement_work(monkeypatch, budget, expected):
    stats = seed_statistics()
    scan = SimpleNamespace(
        geometry=None, groups=[], times=np.arange(3.), tracks=[dict(channel=1)],
        norads=np.arange(3), sigma=np.ones(3), rx_basis=[np.zeros((1, 1))],
        search_region=SimpleNamespace(center=(0., 0.), native_point=lambda *args: (0., 0.)),
    )
    work = dict(improve=0, explore=0, problem=0, association=0)
    monkeypatch.setattr(discovery, "phase_linear_frequency", lambda *args: (None,) * 3)
    monkeypatch.setattr(discovery, "statistics", lambda *args: stats)
    monkeypatch.setattr(discovery, "augment_phase_statistics", lambda stats, *args: stats)
    monkeypatch.setattr(discovery, "proposal_phases", lambda *args, **kwargs:
                        (np.zeros((3, 3)), None) if kwargs else np.zeros(3))
    monkeypatch.setattr(discovery, "nomination_rows", lambda *args: [])

    def improve(stats, beta, phase, *args, **kwargs):
        work["improve"] += 1
        return 0., beta.copy(), phase.copy(), None, {}

    def association(*args):
        work["association"] += 1
        return None, [], [], None

    def explore(scan, state, *args, **kwargs):
        work["explore"] += 1
        return dict(rows=[], state=state), {}

    def problem(scan, seed, sigma):
        work["problem"] += 1
        return SimpleNamespace(rows=[], alias=[], state=lambda point: seed["state"],
                               residual=lambda point: np.zeros(1))

    scan.association = association
    monkeypatch.setattr(discovery, "improve", improve)
    monkeypatch.setattr(discovery, "explore", explore)
    monkeypatch.setattr(discovery, "standard_problem", problem)
    outcomes = []
    for seed_policy in ("legacy", POLICY):
        work = dict.fromkeys(work, 0)
        candidates = discovery.fresh_discovery(scan, 150., budget=budget, seed_policy=seed_policy)
        assert [candidate["hypothesis"] for candidate in candidates] == list(range(expected))
        outcomes.append(work)
    assert outcomes[0] == outcomes[1] == dict(
        improve=max(0, expected - 1), explore=2 * expected,
        problem=3 * expected, association=expected,
    )
