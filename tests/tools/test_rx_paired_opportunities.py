import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import rx_paired_opportunities as exporter  # noqa: E402


def candidate(rank, cfo, passed=True):
    return NS(
        candidate_rank=rank,
        integer_epoch_sample=100,
        fractional_epoch_offset_samples=0.0,
        fractional_tracking_cfo_hz=cfo,
        fractional_exact_score=3.0,
        fractional_control_score=1.0,
        fractional_margin=2.0,
        passed_fractional_margin_gate=passed,
    )


def probe(receiver_id, candidates, probe_start_ms=0, actual_rf_hz=11_325_000_000):
    return NS(
        visit_index=7,
        receiver_id=receiver_id,
        probe_index=0,
        probe_start_ms=probe_start_ms,
        channel=3,
        edge="lower",
        actual_rf_hz=actual_rf_hz,
        valid_start_counter=1_000,
        payload_start_sample=0,
        candidates=candidates,
    )


def input_value(probes):
    return NS(
        session_id="scan-test",
        qualified=True,
        sample_rate_hz=10_000_000,
        probe_ms=20,
        input_manifest_sha256="sha256:input",
        analysis_manifest_sha256="sha256:analysis",
        timing=NS(
            qualified=True,
            first_sample_estimate_utc_ns=20_000,
            session_start_device_sample_counter=0,
        ),
        probes=probes,
    )


def test_export_keeps_candidate_absence_and_unassigned_identity():
    value = input_value([probe(0, [candidate(0, 10.0)]), probe(1, [candidate(0, 2390.0)])])
    projected = {
        (7, 0, 0, 0): NS(
            candidate_id="projected-0",
            source_group_id="group",
            source_sample_start=10,
            source_sample_end=20,
            support_center_utc_ns=123,
            stream_id="rx-0",
        )
    }
    opportunities, bindings = exporter.export_input(
        value, split="calibration", cache_sha256="sha256:test", projected=projected
    )
    assert len(opportunities) == 1
    assert opportunities[0]["opportunity_status"] == "both_receivers_candidate_present"
    assert opportunities[0]["source_qualification"]["timestamp_present"]
    assert opportunities[0]["window_start_utc_ns"] == 120_000
    assert opportunities[0]["window_end_utc_ns"] == 20_120_000
    candidates = [
        *opportunities[0]["receivers"]["rx0"]["candidates"],
        *opportunities[0]["receivers"]["rx1"]["candidates"],
    ]
    assert len(candidates) == 2
    assert candidates[0]["anchor_key"] == "scan-test:7:0:0:0"
    assert candidates[0]["projected_candidate_id"] == "projected-0"
    assert candidates[1]["projected_candidate_id"] is None
    assert len(bindings) == 2
    assert {row["satellite_id"] for row in [*opportunities, *candidates]} == {None}


def test_export_distinguishes_observed_absence_from_missing_receiver():
    absent = input_value([probe(0, []), probe(1, [])])
    opportunities, _ = exporter.export_input(absent, split="holdout", cache_sha256="sha256:test")
    assert opportunities[0]["opportunity_status"] == "both_receivers_candidate_absent"
    assert opportunities[0]["receivers"]["rx0"]["candidates"] == []

    missing = input_value([probe(0, [])])
    opportunities, bindings = exporter.export_input(
        missing, split="holdout", cache_sha256="sha256:test"
    )
    assert opportunities[0]["opportunity_status"] == "receiver_probe_incomplete"
    assert opportunities[0]["receivers"]["rx1"]["receiver_status"] == "missing_receiver_probe"
    assert len(bindings) == 1


def test_counter_timing_includes_probe_offset_without_float_epoch_loss():
    value = input_value([probe(0, [], probe_start_ms=7), probe(1, [], probe_start_ms=7)])
    value.timing.first_sample_estimate_utc_ns = 1_790_474_857_327_806_285
    opportunities, _ = exporter.export_input(value, split="calibration", cache_sha256="sha256:test")
    row = opportunities[0]
    assert row["window_start_utc_ns"] == 1_790_474_857_334_906_285
    assert row["window_end_utc_ns"] == 1_790_474_857_354_906_285


def test_mismatched_receiver_window_is_labelled_inconsistent():
    value = input_value([probe(0, [], actual_rf_hz=1), probe(1, [], actual_rf_hz=2)])
    opportunities, _ = exporter.export_input(value, split="calibration", cache_sha256="sha256:test")
    assert opportunities[0]["opportunity_status"] == "inconsistent_receiver_pair"
