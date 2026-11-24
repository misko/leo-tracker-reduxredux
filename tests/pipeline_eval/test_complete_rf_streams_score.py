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


def test_figure_uses_meter_errors_for_both_calibrations_and_all_comparators():
    from reports.ALGO08.v3.complete_rf_streams_figure import observations

    rows = observations()
    assert [r[:2] for r in rows] == [
        ("North simulation", "Fixed c = 0"), ("North simulation", "Fitted c"),
        ("DS30-0016 recording", "Fixed c = 0"), ("DS30-0016 recording", "Fitted c"),
    ]
    assert [[round(x) for x in row[2]] for row in rows] == [
        [106, 112, 1250], [141, 128, 865], [1644, 490, 504], [1661, 980, 3040]]
