import pytest

from reports.ALGO08.v3.complete_rf_streams_score import coverage


def test_join_counts_only_actual_signed_owner_support():
    factors = {"a": dict(signal=(1, .0, 100.), channel=1, rf_hz=10e9, time_s=1., receiver=0),
               "b": dict(signal=(2, .1, 300.), channel=4, rf_hz=11e9, time_s=11., receiver=1),
               "empty": dict(signal=None, channel=1, rf_hz=10e9, time_s=12., receiver=0)}
    result = coverage([("a", 51, "conditional"), ("b", 51, "predictive")], factors)[51]
    assert result["channels"] == {1: 1, 4: 1}
    assert result["span_s"] == 10.
    assert result["receivers"] == [0, 1]
    assert result["roles"] == {"conditional": 1, "predictive": 1}
    with pytest.raises(ValueError, match="no measured"):
        coverage([("empty", 51, "conditional")], factors)
