import pytest

from tools.plot_scanner_tle_rate_comparison import distribution


def test_distribution_reports_quartiles_and_range():
    assert distribution([1, 2, 3, 4, 5]) == {
        "count": 5,
        "minimum": 1.0,
        "q1": 2.0,
        "median": 3.0,
        "q3": 4.0,
        "maximum": 5.0,
    }


@pytest.mark.parametrize("values", [[], [1, float("nan")]])
def test_distribution_rejects_empty_or_nonfinite_values(values):
    with pytest.raises(ValueError, match="finite and non-empty"):
        distribution(values)
