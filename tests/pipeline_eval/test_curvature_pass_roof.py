from fractions import Fraction
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from curvature_pass_roof import contrast_weights, report, whitened_floor


def contrast(weights, values):
    return sum(w * value for w, value in zip(weights, values, strict=True))


def test_uneven_times_cancel_uniform_alias_rf_and_drift():
    times = (1001, 1003, 1010)
    weights = contrast_weights(times)
    affine = [227_273 - 117 + 13 * t for t in times]
    assert weights == (7, -9, 2)
    assert contrast(weights, affine) == 0
    assert contrast((1, -2, 1), affine) != 0
    assert contrast(weights, [a + b for a, b in zip(affine, (0, 227_273, 0), strict=True)]) != 0
    assert contrast(weights, [a + (t - 1000)**2 for a, t in zip(affine, times, strict=True)]) != 0


def test_group_mean_time_preserves_affine_not_quadratic_prediction():
    groups = ((0, 2), (4, 6), (9, 13))
    means = tuple(Fraction(sum(group), len(group)) for group in groups)
    average = lambda function: [Fraction(sum(function(t) for t in group), len(group)) for group in groups]
    weights = contrast_weights(means)
    assert contrast(weights, average(lambda t: 13 + t)) == 0
    assert contrast(weights, average(lambda t: t*t)) != contrast(weights, [t*t for t in means])


def test_interval_floor_and_disjoint_clock_budget():
    assert whitened_floor(9, (1, 5), 32) == Fraction(1, 2)
    assert whitened_floor(5, (1, 5), 32) == 0
    with pytest.raises(ValueError):
        contrast_weights((1, 1, 2))
    receipt = report()
    assert receipt["rank_signatures"] == 7 and receipt["profiled_association"]["calls"] == 16
    assert receipt["required_fraction_of_paid_cpu"]["rank"]["0"] == pytest.approx(.5633, abs=.0001)
    assert receipt["disjoint_association_statistics_full_grant_cpu_s"] < 2.5
