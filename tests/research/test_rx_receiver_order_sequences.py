import pytest

from tools.rx_receiver_order_sequences import (
    anchor_equivalent_native_hz,
    build_sequences,
    circular_residual_hz,
    classify_opportunities,
)


def fixtures(*, second_hypothesis=False, candidates=None):
    window = {
        "source_window_id": "w",
        "role": "reception",
        "window_start_utc_ns": 0,
        "window_end_utc_ns": 10,
        "prediction_utc_ns": 5,
        "predicted_hz": 1000.0,
        "visible": True,
    }
    top = [
        {
            "catalog_number": 11,
            "rank": 1,
            "conditional_top3_probability": 0.7,
            "profiled_cfo_hz": 10_000.0,
            "window_predictions": [window],
        }
    ]
    if second_hypothesis:
        top.append(
            {
                "catalog_number": 12,
                "rank": 2,
                "conditional_top3_probability": 0.3,
                "profiled_cfo_hz": -8.0,
                "window_predictions": [{**window, "predicted_hz": 1001.0}],
            }
        )
    bank = {
        "schema": "rx-training-candidate-bank/v1",
        "status": "complete",
        "tracks": [
            {
                "session_id": "s",
                "track_id": "t",
                "retained_catalogue_probability_mass": 0.9,
                "top_candidates": top,
            }
        ],
    }
    mapping = {
        "schema": "rx-training-alias-mapping/v1",
        "status": "complete",
        "tracks": [
            {
                "session_id": "s",
                "track_id": "t",
                "receiver_id": 0,
                "channel": 2,
                "edge": "lower",
                "actual_rf_hz": 5_600_000_000.0,
                "canonical_scale": 2.0,
                "normalized_alias_spacing_hz": 200_000.0,
            }
        ],
        "receiver_calibrations": [
            {
                "session_id": "s",
                "channel": 2,
                "edge": "lower",
                "actual_rf_hz": 5_600_000_000.0,
                "bias_rx1_minus_rx0_hz": 100.0,
                "qualified": True,
            }
        ],
    }
    partitions = {
        "schema": "rx-grouped-partition/v1",
        "windows": [
            {
                "source_window_id": "w",
                "role": "reception",
                "window_start_utc_ns": 0,
                "window_end_utc_ns": 10,
                "window_midpoint_utc_ns": 5,
            }
        ],
    }
    if candidates is None:
        candidates = [
            {
                "candidate_id": "raw",
                "candidate_rank": 0,
                "fractional_tracking_cfo_hz": 500.0,
                "fractional_margin": 2.0,
                "passed_fractional_margin_gate": True,
            }
        ]
    opportunity = {
        "source_window_id": "w",
        "window_start_utc_ns": 0,
        "window_end_utc_ns": 10,
        "source_window": {"session_id": "s", "channel": 2, "edge": "lower"},
        "receivers": {
            "rx0": {
                "receiver_id": 0,
                "actual_rf_hz": 5_600_000_000.0,
                "receiver_status": "observed_candidate_present",
                "candidates": candidates,
            },
            "rx1": {
                "receiver_id": 1,
                "actual_rf_hz": 5_600_000_000.0,
                "receiver_status": "observed_candidate_present",
                "candidates": [
                    {
                        **candidates[0],
                        "candidate_id": "raw-rx1",
                        "fractional_tracking_cfo_hz": 600.0,
                    }
                ],
            },
        },
    }
    return bank, mapping, partitions, [opportunity]


def test_radial_rf_scaling_and_signed_receiver_transfer():
    assert anchor_equivalent_native_hz(600.0, 1, 0, 100.0) == 500.0
    assert anchor_equivalent_native_hz(500.0, 0, 1, 100.0) == 600.0
    bank, mapping, partitions, opportunities = fixtures()
    rows, _ = classify_opportunities(bank, mapping, partitions, opportunities)
    assert {row["status"] for row in rows} == {"unique_hit"}
    assert {row["matches"][0]["anchor_equivalent_canonical_hz"] for row in rows} == {1000.0}
    assert bank["tracks"][0]["top_candidates"][0]["profiled_cfo_hz"] == 10_000.0


@pytest.mark.parametrize(
    ("target", "field"),
    (
        ("prediction", "window_start_utc_ns"),
        ("prediction", "prediction_utc_ns"),
        ("opportunity", "window_end_utc_ns"),
    ),
)
def test_same_window_id_with_inconsistent_timing_fails_closed(target, field):
    bank, mapping, partitions, opportunities = fixtures()
    if target == "prediction":
        bank["tracks"][0]["top_candidates"][0]["window_predictions"][0][field] += 1
    else:
        opportunities[0][field] += 1
    rows, _ = classify_opportunities(bank, mapping, partitions, opportunities)
    assert {row["status"] for row in rows} == {"missing_or_invalid"}
    assert {row["exclusion_reason"] for row in rows} == {
        "missing_or_inconsistent_partition_or_opportunity"
    }


def test_alias_period_invariance_without_integer_alias_choice():
    period = 227_272.72727272726
    base = circular_residual_hz(1234.0, 1000.0, period)
    assert circular_residual_hz(1234.0 + 7 * period, 1000.0, period) == pytest.approx(base)


def test_global_raw_candidate_collision_marks_every_hypothesis_ambiguous():
    bank, mapping, partitions, opportunities = fixtures(second_hypothesis=True)
    rows, _ = classify_opportunities(bank, mapping, partitions, opportunities)
    assert len(rows) == 4
    assert {row["status"] for row in rows} == {"ambiguous_hypothesis"}
    assert all(row["colliding_hypothesis_ids"] for row in rows)


def test_multiple_matching_candidate_ids_are_retained_and_counted_ambiguous():
    candidates = [
        {
            "candidate_id": name,
            "candidate_rank": rank,
            "fractional_tracking_cfo_hz": value,
            "fractional_margin": 2.0,
            "passed_fractional_margin_gate": True,
        }
        for rank, (name, value) in enumerate((("a", 500.0), ("b", 501.0)))
    ]
    bank, mapping, partitions, opportunities = fixtures(candidates=candidates)
    rows, _ = classify_opportunities(bank, mapping, partitions, opportunities)
    rx0 = next(row for row in rows if row["receiver_id"] == 0)
    assert rx0["status"] == "ambiguous_candidate"
    assert [match["candidate_id"] for match in rx0["matches"]] == ["a", "b"]


def test_sequence_censoring_left_right_earlier_ambiguity_and_tie():
    base = {
        "hypothesis_id": "h",
        "session_id": "s",
        "track_id": "t",
        "catalog_number": 1,
        "rank": 1,
        "conditional_top3_probability": 1.0,
        "role": "reception",
        "matches": [],
    }
    rows = []
    for rid, statuses in (
        (0, ("ambiguous_candidate", "unique_hit")),
        (1, ("unique_hit", "no_matching_candidate")),
    ):
        for index, status in enumerate(statuses):
            rows.append(
                {
                    **base,
                    "receiver_id": rid,
                    "status": status,
                    "source_window_id": f"w{index}",
                    "prediction_utc_ns": index,
                }
            )
    hypotheses = [
        {
            "hypothesis_id": "h",
            "session_id": "s",
            "track_id": "t",
            "catalog_number": 1,
            "rank": 1,
            "conditional_top3_probability": 1.0,
        }
    ]
    reception = build_sequences(rows, hypotheses)[0]
    assert reception["receivers"]["rx0"]["censoring"] == "earlier_ambiguity"
    assert reception["receivers"]["rx1"]["censoring"] == "left"
    assert reception["uncensored_lag_rx1_minus_rx0_s"] is None
    held = build_sequences([], hypotheses)[1]
    assert held["receivers"]["rx0"]["censoring"] == "unavailable"

    right_rows = [
        {
            **base,
            "receiver_id": rid,
            "status": "no_matching_candidate",
            "source_window_id": "w0",
            "prediction_utc_ns": 0,
        }
        for rid in (0, 1)
    ]
    right = build_sequences(right_rows, hypotheses)[0]
    assert right["receivers"]["rx0"]["censoring"] == "right"

    tie_rows = [{**row, "status": "unique_hit"} for row in right_rows]
    tie = build_sequences(tie_rows, hypotheses)[0]
    assert tie["same_window_tie"] is True
    assert tie["uncensored_lag_rx1_minus_rx0_s"] is None
