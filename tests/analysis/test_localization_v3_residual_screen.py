import numpy as np
import pytest
from scipy.special import logsumexp

from leo.analysis.localization_v3 import residual_evidence as evidence
from leo.analysis.localization_v3 import residual_screen as screen
from leo.analysis.localization_v3.region import SearchRegion


def test_random_partitions_keep_whole_time_blocks_and_guard_neighbours():
    times = np.arange(0.0, 120.0, 0.5)
    for seed in screen.SEEDS:
        train, held, chosen = screen.split(times, seed)
        repeat = screen.split(times, seed)
        assert all(np.array_equal(a, b) for a, b in zip((train, held, chosen), repeat, strict=True))
        assert train.sum() >= 8 and held.sum() >= 4 and not (train & held).any()
        assert np.array_equal(held, np.isin(np.floor(times / 12).astype(int), chosen))
        for group in chosen:
            assert not train[(times >= group * 12 - 2) & (times < (group + 1) * 12 + 2)].any()
    assert not np.array_equal(
        screen.split(times, screen.SEEDS[0])[1], screen.split(times, screen.SEEDS[1])[1]
    )


def test_held_values_cannot_change_fitted_nuisance_or_training_evidence():
    times = np.arange(100.0)
    train, held, _ = screen.split(times, screen.SEEDS[0])
    predictions = np.stack([3 * times**2 + shift for shift in (-2, 0, 2)])
    y = predictions[1] + 7 + 0.1 * times
    before = evidence.components(y, predictions, np.ones(3, bool), times, [0], 1.0, mask=train)
    changed = y.copy()
    changed[held] += 100000
    after = evidence.components(changed, predictions, np.ones(3, bool), times, [0], 1.0, mask=train)
    for key in ("loglik", "beta", "coefficient_covariance", "quadratic"):
        np.testing.assert_array_equal(after[key], before[key])


def test_gaussian_nuisance_marginal_matches_direct_covariance_density():
    times = np.array([0.0, 1.0, 3.0, 6.0])
    y = np.array([2.0, 4.0, 8.0, 10.0])
    prediction = np.array([[0.0, 1.0, 2.0, 3.0]])
    result = evidence.components(
        y, prediction, [True], times, [0], 1.0, noise_hz=2.0, bias_hz=3.0, rate_hz_s=0.4
    )
    design = np.column_stack([np.ones(4), times - times.mean()])
    covariance = 4 * np.eye(4) + design @ np.diag([9.0, 0.16]) @ design.T
    residual = y - prediction[0]
    expected = -0.5 * (
        residual @ np.linalg.solve(covariance, residual)
        + np.linalg.slogdet(covariance)[1]
        + 4 * np.log(2 * np.pi)
    )
    assert result["loglik"][0, 0] == pytest.approx(expected, abs=1e-12)


def test_phase_alias_mixture_is_normalized_and_excludes_invisible_hypotheses():
    phases = np.arange(-2.0, 3.0)
    assert logsumexp(evidence.phase_prior(phases, 5.0)) == pytest.approx(0.0, abs=1e-15)
    result = evidence.components(
        np.arange(6.0),
        np.zeros((5, 6)),
        [False, True, True, True, False],
        np.arange(6.0),
        [-1, 0, 1],
        100.0,
    )
    mixed = evidence.marginal(result, phases, 5.0)
    assert mixed["weights"].sum() == pytest.approx(1.0)
    assert mixed["weights"][:, [0, 4]].sum() == 0
    assert np.isfinite(mixed["score"])


@pytest.mark.parametrize(
    "fault", ["epoch_future", "collection_future", "epoch_old", "collection_old", "cutoff"]
)
def test_catalogue_causality_and_age_are_enforced_before_propagation(monkeypatch, fault):
    cutoff = 1_000_000_000_000_000
    row = dict(element_epoch_utc_ns=cutoff, collected_utc_ns=cutoff, lines=[])
    catalogue = dict(cutoff_utc_ns=cutoff, elements={"1": row})
    packet = dict(scan_receipt=dict(cutoff_utc_ns=cutoff))
    if fault == "cutoff":
        catalogue["cutoff_utc_ns"] += 1
    else:
        key = "element_epoch_utc_ns" if fault.startswith("epoch") else "collected_utc_ns"
        row[key] += 1 if fault.endswith("future") else -73 * 3600 * 1_000_000_000
    monkeypatch.setattr(
        screen, "ecef_states", lambda *a: pytest.fail("invalid catalogue propagated")
    )
    with pytest.raises(ValueError, match="[Cc]ausal catalogue"):
        screen.screen_candidates(packet, catalogue, SearchRegion((1.0, 2.0)))


def test_default_age_screen_has_no_recency_penalty_and_excludes_expired_rows():
    costs = np.array([1.0, 2.0, 3.0, 4.0])
    ages = np.array([71.0, 1.0, 73.0, 20.0])
    assert screen.top_indices(costs, ages, 72, False) == [0, 1, 3]
    assert screen.top_indices(costs, ages, 72, True) == [1, 0, 3]
    assert screen.top_indices(costs, ages, 48, False) == [1, 3]


@pytest.mark.parametrize("phases,sigma", [([0, 1], 1), ([0, 1, 3], 1), ([0, 1, 2], 0)])
def test_invalid_phase_prior_is_rejected(phases, sigma):
    with pytest.raises(ValueError):
        evidence.phase_prior(phases, sigma)
