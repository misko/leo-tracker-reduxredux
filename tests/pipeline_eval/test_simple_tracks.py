from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.variants import simple_tracks as sparse


def configuration():
    return asdict(TrackConfig(max_slope_hz_s=8000))


def test_folded_curve_retains_original_full_support_except_outliers():
    cfg = configuration()
    t = np.arange(70.0) * 0.75
    expected = 105000 + 2200 * t + 14 * t**2
    clutter = [7, 21, 51]
    observed = expected.copy()
    observed[clutter] += 45000
    period = cfg["alias_spacing_hz"]
    [(ids, values)] = sparse.fit_lane(t, sparse.wrap(observed, period), cfg)
    np.testing.assert_array_equal(ids, np.delete(np.arange(len(t)), clutter))
    np.testing.assert_allclose(values, expected[ids], atol=1e-9)


def test_crossing_tracks_keep_continuity_and_no_duplicate_support():
    cfg = configuration()
    t = np.arange(70.0) * 0.75
    parity = np.arange(len(t)) % 2
    y = np.where(parity == 0, 115000 - 1400 * t, 52000 + 1000 * t)
    tracks = sparse.fit_lane(t, sparse.wrap(y, cfg["alias_spacing_hz"]), cfg)
    assert sorted(len(ids) for ids, _ in tracks) == [34, 35]
    assert {int(ids[0] % 2) for ids, _ in tracks} == {0, 1}
    for ids, values in tracks:
        assert np.all(ids % 2 == ids[0] % 2)
        period = cfg["alias_spacing_hz"]
        assert values[0] == pytest.approx(sparse.wrap(y[ids[0]], period))
        np.testing.assert_allclose(np.diff(values), np.diff(y[ids]), atol=1e-9)


def test_unsupported_alias_branches_and_unstructured_clutter_are_not_promoted():
    cfg = configuration()
    t = np.arange(70.0) * 0.75
    period = cfg["alias_spacing_hz"]
    raw = np.random.default_rng(1).uniform(-period / 2, period / 2, len(t))
    assert sparse.fit_lane(t, raw, cfg) == []
    with pytest.raises(ValueError, match="multiple alias branches"):
        sparse.edges(t, raw, 100, 8000, period)
