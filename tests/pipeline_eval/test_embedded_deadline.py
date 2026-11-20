import pytest

from tools.pipeline_eval.qualification.embedded_deadline import budget


def _recording():
    return dict(
        source=dict(
            sample_rate_hz=10_000_000,
            probe_ms=20,
            qualified=True,
            probes=[
                dict(visit_index=visit, receiver_id=rx) for visit in (0, 1, 3) for rx in (0, 1)
            ],
        ),
        provenance=dict(
            window_count=4,
            processed_windows=3,
            invalid_capture=1,
            skipped_fast_score=0,
            excluded_windows=[dict(visit=2)],
        ),
        delivery_clocks=[
            dict(monotonic_ns=value)
            for value in (1_000_000_000, 1_075_000_000, 1_100_000_000, 3_000_000_000)
        ],
    )


def test_uses_recorded_span_and_counts_one_dual_receiver_call():
    result = budget(_recording())
    assert result["delivery_span_s"] == 2
    assert result["eligible_dual_rx_visits"] == 3
    assert result["scheduled_visits_per_s"] == 2
    assert result["eligible_visits_per_s"] == 1.5
    assert result["max_scheduled_arrivals_in_rolling_second"] == 3
    assert result["max_eligible_arrivals_in_rolling_second"] == 2
    assert result["bytes_per_complete_ci16_visit"] == 1_600_000
    assert result["ci16_bytes_per_s_if_all_scheduled_valid"] == 3_200_000
    assert result["eligible_ci16_bytes_per_s"] == 2_400_000
    assert result["unbroken_dual_rx_ci16_bytes_per_s"] == 80_000_000
    assert result["single_serial_lane_cpu_ms_per_visit_ceiling"] == pytest.approx(2000 / 3)
    assert result["two_core_cpu_ms_per_visit_ceiling"] == pytest.approx(4000 / 3)


def test_receipt_rejects_nonmonotonic_clocks_and_invalid_coverage():
    document = _recording()
    document["delivery_clocks"].reverse()
    with pytest.raises(ValueError, match="increasing delivery clock"):
        budget(document)

    document = _recording()
    document["provenance"]["excluded_windows"][0]["visit"] = 1
    with pytest.raises(ValueError, match="cover the recorded visits"):
        budget(document)


def test_missing_receiver_and_gated_visits_do_not_enter_real_time_budget():
    document = _recording()
    document["source"]["probes"].pop()
    with pytest.raises(ValueError, match="two receiver probes"):
        budget(document)

    document = _recording()
    document["provenance"]["skipped_fast_score"] = 1
    with pytest.raises(ValueError, match="no score-gated exclusions"):
        budget(document)
