"""Independent synthetic checks for the single-track validation rules."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/improvements/validation/validate.py"
SPEC = importlib.util.spec_from_file_location("single_track_validation", PATH)
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


def test_train_first_20ms_and_holdout_rest_are_disjoint():
    train, held = V.time_partition([0, .019999, .020, .119])
    np.testing.assert_array_equal(train, [1, 1, 0, 0])
    np.testing.assert_array_equal(held, [0, 0, 1, 1])
    assert not np.any(train & held)


def test_interpolation_support_crossing_20ms_is_excluded():
    train, held = V.support_partition([.018, .0195, .020, .021],
                                      [.019, .0205, .021, .022])
    np.testing.assert_array_equal(train, [1, 0, 0, 0])
    np.testing.assert_array_equal(held, [0, 0, 1, 1])


def test_even_and_odd_tones_are_disjoint_and_complete():
    train, held = V.tone_partition(np.arange(8))
    np.testing.assert_array_equal(np.flatnonzero(train), [0, 2, 4, 6])
    np.testing.assert_array_equal(np.flatnonzero(held), [1, 3, 5, 7])
    assert np.all(train ^ held)


def test_future_phase_cannot_change_causal_fit():
    t = np.arange(12) * .01
    phase = V.wrap_radians(.2 + 4 * t)
    train, held = V.time_partition(t)
    first, fit1 = V.causal_linear_predictions(t, phase, train)
    corrupted = phase.copy(); corrupted[held] = V.wrap_radians(corrupted[held] + 2.1)
    second, fit2 = V.causal_linear_predictions(t, corrupted, train)
    np.testing.assert_allclose(first, second)
    assert fit1 == fit2


def test_comparison_uses_only_common_support():
    baseline = np.array([0., np.nan, .2, .3])
    candidate = np.array([0., .1, np.nan, .3])
    observed = np.arange(4.)
    np.testing.assert_array_equal(
        V.common_finite_support(observed, baseline, candidate), [1, 0, 0, 1])


def test_wrapped_error_and_interval_coverage_cross_branch_cut():
    observed = np.radians([-179., 179.])
    predicted = np.radians([179., -179.])
    metric = V.circular_metrics(observed, predicted)
    assert metric["wrapped_rms_deg"] == pytest.approx(2.)
    coverage = V.uncertainty_coverage(observed, predicted, np.radians([2.1, 1.9]))
    assert coverage == {"count": 2, "covered": 1, "coverage": .5}


def test_unwrap_never_bridges_visit_gap():
    phase = np.radians([170., -170., -160., 170.])
    result = V.unwrap_within_segments(phase, [259, 259, 260, 260])
    np.testing.assert_allclose(np.degrees(result), [170., 190., -160., -190.])


def test_internal_gap_or_reused_segment_is_rejected():
    with pytest.raises(ValueError, match="non-contiguous"):
        V.unwrap_within_segments([0., .1, .2], [259, 260, 259])
    with pytest.raises(ValueError, match="internal data gap"):
        V.unwrap_within_segments([0., np.nan, .2], [259, 259, 259])
