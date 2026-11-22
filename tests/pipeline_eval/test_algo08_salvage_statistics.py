from collections import Counter

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from tools.pipeline_eval.variants import algo08_salvage_statistics as variant, v5_tiled_salvage


def observations():
    rng = np.random.default_rng(573985)
    measured = rng.normal(200000, 60000, 121)
    noise = rng.uniform(40, 175, len(measured))
    frequency = rng.normal(-10000, 140000, (43, len(measured)))
    slope = rng.normal(15000, 9000, frequency.shape)
    elevation = rng.uniform(-25, 2., frequency.shape)
    elevation[:4] = -1.0
    return measured, noise, frequency, elevation, slope, 0.99, np.linspace(-10, 10, 81)


def test_phase_statistics_preserve_costs_and_phase_dependent_aliases():
    measured, noise, frequency, _, slope, q, phases = observations()
    shape = len(frequency), len(phases)
    prediction = q * (frequency[:, None] + slope[:, None] * phases[None, :, None])
    direct = profile(measured, prediction.reshape(-1, len(measured)), np.diag(1 / noise))
    cost, _, aliases = variant.phase_costs(measured, noise, frequency, slope, q, phases)
    np.testing.assert_array_equal(aliases, direct["alias"].reshape(shape))
    assert np.any(np.diff(aliases, axis=1))
    np.testing.assert_allclose(cost, direct["cost"].reshape(shape), atol=1e-6, rtol=1e-12)


@pytest.mark.parametrize("subset", [False, True])
def test_shortlists_match_original_on_full_and_windowed_observations(subset):
    inputs = observations()
    mask = (np.arange(len(inputs[0])) % 3 == 0) if subset else None
    stock = v5_tiled_salvage.coarse_scores
    expected = stock(profile, *inputs, mask, Counter())
    counters = Counter()
    actual = variant.coarse_scores(stock, profile, *inputs, mask, counters)
    quota = 10 if subset else 30
    np.testing.assert_array_equal(np.argsort(actual)[:quota], np.argsort(expected)[:quota])
    assert counters["statistics_windows"] == 1
    assert counters["coarse_windows"] == 0


def test_near_alias_boundary_uses_direct_profile():
    frequency = np.full((1, 12), PERIOD / 2)
    inputs = (np.zeros(12), np.ones(12) * 40, frequency, np.ones_like(frequency),
              np.zeros_like(frequency), 1., np.linspace(-10., 10., 81))
    stock = v5_tiled_salvage.coarse_scores
    expected = stock(profile, *inputs, None, Counter())
    counters = Counter()
    actual = variant.coarse_scores(stock, profile, *inputs, None, counters)
    np.testing.assert_array_equal(actual, expected)
    assert counters["alias_replays"] == 1


def test_tied_shortlist_cutoff_uses_direct_profile():
    frequency = np.ones((32, 12))
    inputs = (np.zeros(12), np.ones(12) * 40, frequency, np.ones_like(frequency),
              np.zeros_like(frequency), 1., np.linspace(-10., 10., 81))
    stock = v5_tiled_salvage.coarse_scores
    expected = stock(profile, *inputs, None, Counter())
    counters = Counter()
    actual = variant.coarse_scores(stock, profile, *inputs, None, counters)
    np.testing.assert_array_equal(actual, expected)
    assert counters["rank_replays"] == 1


def test_visibility_ties_at_shortlist_cutoff_use_direct_profile():
    measured, noise, frequency, elevation, slope, q, phases = observations()
    elevation[:20] = -1.0
    inputs = measured, noise, frequency, elevation, slope, q, phases
    stock = v5_tiled_salvage.coarse_scores
    expected = stock(profile, *inputs, None, Counter())
    counters = Counter()
    actual = variant.coarse_scores(stock, profile, *inputs, None, counters)
    np.testing.assert_array_equal(actual, expected)
    assert counters["visibility_replays"] == 1
