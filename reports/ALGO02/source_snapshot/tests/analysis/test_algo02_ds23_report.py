"""Truth-only reporting must retain failures and paired membership."""

import pytest

from report_algo02_ds23 import REFERENCE, position_error, rows_for_case, summarize


def member():
    return dict(dataset_label="DS23-0001", recording_id="a", recording_format="adaptive")


def test_failed_or_missing_recording_retains_both_rows_without_imputed_error():
    rows = rows_for_case(member())
    assert len(rows) == 2
    assert {row["arm"] for row in rows} == {"c0", "fitted_c"}
    assert all(row["error_km"] is None for row in rows)
    stats = summarize([.1, .9], population=3)
    assert stats["localized"] == 2 and stats["failures_or_pending"] == 1
    assert stats["fraction_all_recordings_below_half_km"] == 1/3


def test_accepted_pair_requires_both_finite_positions_and_no_truth_inference():
    record = dict(endpoint_latlon=REFERENCE, active_points=5, RMS_hz=10.)
    result = dict(case="DS23-0001", status="accepted", GPS_used=False,
        future_TLE_used=False, policy_arms=dict(c0=record, fitted_c=record))
    assert all(row["error_km"] == 0 for row in rows_for_case(member(), result))
    result["GPS_used"] = True
    with pytest.raises(ValueError, match="GPS-free"):
        rows_for_case(member(), result)


def test_failed_execution_cannot_silently_count_existing_position_as_success():
    result = dict(case="DS23-0001", status="accepted")
    rows = rows_for_case(member(), result, dict(code=124))
    assert all(r["status"] == "execution_failed" and r["error_km"] is None for r in rows)


def test_haversine_evaluation_only_distance():
    assert position_error(REFERENCE) == 0
    north = (REFERENCE[0] + 1/111.195, REFERENCE[1])
    assert position_error(north) == pytest.approx(1., abs=.001)
