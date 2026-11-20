import pytest

from tools.pipeline_eval.qualification.scheduled_capture_waveform import selected
from tools.pipeline_eval.qualification.scheduled_capture_waveform_results import (
    expected_projection,
    review_visits,
    verified_schedule,
)


def test_schedule_is_per_rf_and_counts_all_earlier_scheduled_visits():
    schedule = [
        (k, 100 * k, ordinal, selected(ordinal, k)) for ordinal in range(8) for k in (1, 2, 3, 4)
    ]
    assert verified_schedule(schedule) == {0, 7, 10, 13, 16, 23, 26, 29}
    schedule[0] = (1, 100, 0, False)
    with pytest.raises(ValueError, match="independent per-RF progression"):
        verified_schedule(schedule)


def test_projection_keeps_both_physical_rows_and_provenance():
    probes = [dict(visit_index=v, receiver_id=rx, candidates=[v]) for v in (2, 3) for rx in (0, 1)]
    archive = {"source": {"probes": probes}, "delivery_clocks": [1, 2, 3, 4]}
    result = expected_projection(archive, {3})
    assert result["delivery_clocks"] == archive["delivery_clocks"]
    assert [r["receiver_id"] for r in result["source"]["probes"]] == [0, 1, 0, 1]
    assert [r["candidates"] for r in result["source"]["probes"]] == [[], [], [3], [3]]


def test_visit_audit_keeps_hardware_exclusion_distinct_from_scheduled_omission():
    rows = []
    for v, status in enumerate(("invalid_capture", "skipped_policy", "processed")):
        rows.append(
            dict(
                visit=v,
                status=status,
                selected=v != 1,
                grid_calls=2 if v == 2 else 0,
                rf_center_hz=100,
                detector_cpu_s=0.5,
                detector_wall_s=0.5,
                delivery_clock={"monotonic_ns": v},
            )
        )
    shards = {(0, 0): ({}, rows)}
    _, counts, coverage = review_visits(shards, {0, 2}, {0})
    assert counts == dict(invalid_capture=1, skipped_policy=1, processed=1)
    assert coverage["100"]["counts"]["selected_hardware_invalid"] == 1
    rows[1]["grid_calls"] = 2
    with pytest.raises(ValueError, match="measured original acquisition work"):
        review_visits(shards, {0, 2}, {0})
