"""Regression checks for coverage accounting and the independently applied scoring rule."""
import math

import pytest

from compare import distance_km, scored_rows, summarize, validate_rows
from paired_controls import compare_endpoints


def test_mixed_coverage_preserves_abstention_and_pairs_by_case():
    estimate = dict(status="estimate", latlon=[1., 2.], rms_hz=None)
    abstain = dict(status="abstain", reason="insufficient information")
    rows = [dict(case="a", wall_s=.1, arms=dict(c0=estimate, fitted_c=abstain)),
            dict(case="b", wall_s=.2, arms=dict(c0=abstain, fitted_c=estimate))]
    scored = scored_rows("test", {"cases":rows}, ["a","b"], [1.,2.])
    metrics = summarize(scored, {("a","c0"): 1., ("a","fitted_c"): 10.})
    assert metrics["c0"]["statuses"] == {"estimate":1,"abstain":1}
    assert metrics["c0"]["median_error_km"] == 0
    assert metrics["c0"]["paired_v5_mean_delta_km"] == -1.
    assert metrics["fitted_c"]["paired_v5_n"] == 0
    with pytest.raises(ValueError, match="exactly one"):
        validate_rows([rows[0], rows[0]], ["a","b"])


def test_geographic_error_crosses_longitude_seam():
    assert distance_km([0,179.5], [0,-179.5]) == pytest.approx(6371.0088 * math.pi/180)


def test_forecast_control_keeps_each_arms_coordinate_and_missing_coverage():
    row = {"case": "DS26-demo", "arms": {
        "c0": {"latlon": [0, 0], "last_anchor_control": {"latlon": [0, 1]}},
        "fitted_c": {"last_anchor_control": {"latlon": [0, 2]}}}}
    report = {"checks": {}, "cases": [row]}
    c0, fitted = compare_endpoints("05_stationary", report, (0, 0), distance_km)
    assert c0["primary_minus_control_km"] == pytest.approx(-111.19508)
    assert fitted["control_error_km"] == pytest.approx(222.39016)
    assert fitted["primary_minus_control_km"] is None
