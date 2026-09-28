from copy import deepcopy

import pytest

from summarize_results import distance_km, independent_selections, summarize


def _payload():
    models = ["lambda_0", "lambda_100", "lambda_1000", "lambda_10000", "hard_shared"]
    hypotheses = [
        {"model": model, "location_id": str(index), "latitude_deg": 0.0,
         "longitude_deg": float(index), "reference_error_km": 2.0 + index,
         "regularized_equal_scan_rms_hz": 4.0 + index,
         "regularized_pooled_rms_hz": 6.0 - index,
         "scans": [{"session_id": "s", "training_objective": 2-index, "fixed_weight_seconds": 10}]}
        for model in models for index in range(2)
    ]
    return {"groups": [{
        "group_id": "g", "role": "test", "hypotheses": hypotheses,
        "independent_scan_lambda_0_control": [{"reference_error_km": 2.0}, {"reference_error_km": 4.0}],
        "top_hypotheses": {model: [row for row in hypotheses if row["model"] == model] for model in models},
        "production_hard_parity": [{"difference_hz": 1e-12}],
    }]}


def test_summary_reports_distinct_weighting_and_does_not_mutate():
    payload = _payload()
    original = deepcopy(payload)
    result = summarize([payload])
    assert "| g | test | 3.00 / 4.00 | 2.00" in result
    assert "4.000 | 1.000 | 111.20 | 3.00" in result
    assert payload == original


def test_duplicate_checkpoints_fail_instead_of_inflating_sample_size():
    with pytest.raises(ValueError, match="duplicate groups"):
        summarize([_payload(), _payload()])


def test_distance_uses_kilometers():
    assert distance_km({"latitude_deg": 0, "longitude_deg": 0}, {"latitude_deg": 0, "longitude_deg": 1}) == pytest.approx(111.19508, rel=1e-6)


def test_clock_only_selection_uses_training_not_reference_error():
    group = _payload()["groups"][0]
    winner = independent_selections(group, "lambda_0")[0]
    assert winner["location_id"] == "1"
    assert winner["reference_error_km"] == 3.0
