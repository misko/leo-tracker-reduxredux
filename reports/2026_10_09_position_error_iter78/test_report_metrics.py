import pytest
from report_metrics import distribution, paired


def test_empty_results_are_missing_not_zero_error():
    assert distribution([]) == dict(n=0, mean=None, median=None, p95=None, worst=None)


def test_error_tail_remains_in_denominator():
    assert distribution([0, 0, 30])["mean"] == 10
    assert distribution([0, 0, 30])["worst"] == 30


def test_paired_tolerance_and_membership():
    assert paired([0, 2, 1.0001], [1, 1, 1]) == dict(n=3, improved=1, regressed=1, tied=1)
    with pytest.raises(ValueError, match="identical membership"):
        paired([1], [])


def test_nonfinite_not_silently_removed():
    with pytest.raises(ValueError, match="Nonfinite"):
        distribution([1, float("nan")])
