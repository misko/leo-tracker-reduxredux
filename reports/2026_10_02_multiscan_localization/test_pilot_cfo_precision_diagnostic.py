from types import SimpleNamespace

import numpy as np
import pytest

import pilot_cfo_precision_diagnostic as diagnostic


def probe(visit, receiver, *, channel=1, residual=0.0, epoch=100):
    return diagnostic.CandidateProbe(
        visit_index=visit,
        receiver_id=receiver,
        receiver_axis=receiver,
        probe_index=0,
        probe_start_ms=0,
        channel=channel,
        edge="lower",
        candidate_rank=0,
        integer_epoch_sample=epoch,
        integer_session_sample=visit * 200_000 + epoch,
        fractional_epoch_offset_samples=0.35 if receiver == 0 else -0.45,
        acquired_cfo_hz=1000.0 + 20.0 * receiver,
        native_residual_cfo_hz=residual,
        persisted_tracking_cfo_hz=1000.0 + 20.0 * receiver + residual,
        fractional_margin=0.2,
    )


def test_selection_is_deterministic_paired_and_stratified():
    rows = []
    residuals = (
        0.0,
        diagnostic.NATIVE_RESIDUAL_BIN_HZ,
        253 * diagnostic.NATIVE_RESIDUAL_BIN_HZ,
        7 * diagnostic.NATIVE_RESIDUAL_BIN_HZ,
    )
    for visit in range(24):
        for receiver in (0, 1):
            rows.append(
                probe(
                    visit,
                    receiver,
                    channel=visit % 4 + 1,
                    residual=residuals[visit % len(residuals)] if receiver == 0 else 0.0,
                )
            )
    forward = diagnostic.select_paired_visits(rows, maximum_visits=12)
    reverse = diagnostic.select_paired_visits(reversed(rows), maximum_visits=12)
    assert forward == reverse
    assert len(forward) == 12
    assert all(tuple(item.receiver_id for item in pair) == (0, 1) for pair in forward)
    classes = {
        diagnostic.classify_native_residual(item.native_residual_cfo_hz)
        for pair in forward
        for item in pair
    }
    assert {"zero", "plus_or_minus_one", "edge", "other_nonzero"} <= classes
    assert {item.channel for pair in forward for item in pair} == {1, 2, 3, 4}


def test_full_alias_difference_is_invariant_to_integer_alias_additions():
    alias_hz = diagnostic.FULL_ALIAS_HZ
    baseline = diagnostic.circular_difference_hz(1123.4, -98.7)
    for left_alias in range(-3, 4):
        for right_alias in range(-3, 4):
            assert diagnostic.circular_difference_hz(
                1123.4 + left_alias * alias_hz,
                -98.7 + right_alias * alias_hz,
            ) == pytest.approx(baseline, abs=1e-9)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def estimate_result(center, correction):
    return SimpleNamespace(
        status=SimpleNamespace(value="complete"),
        measurement_supported=True,
        rejection_reasons=(),
        residual_cfo_hz=correction,
        absolute_cfo_hz=center + correction,
        frequency_uncertainty_hz=12.0,
        exact_coherence=0.8,
        control_coherence=0.2,
        coherence_margin=0.6,
        even_residual_cfo_hz=correction - 1.0,
        odd_residual_cfo_hz=correction + 1.0,
        even_odd_disagreement_hz=2.0,
        timing_spread_hz=3.0,
        half_frame_difference_z=0.5,
        tone_deletion_spread_hz=4.0,
        search_boundary=False,
    )


def test_fake_ports_process_three_frames_and_preserve_rounding_diagnostics():
    clock = Clock()
    pairs = ((probe(0, 0), probe(0, 1)),)
    read_calls = []
    estimate_calls = []
    checkpoints = []

    def read_visit(visit):
        read_calls.append(visit)
        clock.advance(1.0)
        return np.zeros((200_000, 2, 2), dtype=np.int16)

    def estimator(samples, rate, **options):
        estimate_calls.append((samples.shape, rate, options))
        clock.advance(0.1)
        correction = 10.0 if options["acquisition_absolute_cfo_hz"] < 1010 else 12.0
        return estimate_result(options["acquisition_absolute_cfo_hz"], correction)

    result = diagnostic.run_selected_diagnostic(
        pairs,
        sample_rate_hz=10_000_000,
        probe_ms=20,
        read_visit=read_visit,
        estimator=estimator,
        deadline=100.0,
        clock=clock,
        checkpoint=lambda value: checkpoints.append(value),
    )

    assert read_calls == [0]
    assert len(estimate_calls) == 6
    assert result["processed_probe_count"] == 2
    assert result["actual_iq_bytes"] == 1_600_000
    assert result["summaries"]["paired_receiver_count"] == 1
    for row in result["probes"]:
        assert row["summary"]["returned_frame_count"] == 3
        assert row["fractional_epoch_rounding_error_samples"] == pytest.approx(
            -row["fractional_epoch_offset_samples"]
        )
        assert all(frame["timing_spread_hz"] == 3.0 for frame in row["frames"])
    assert len(checkpoints) == 2


def test_deadline_guard_reads_nothing_and_represents_every_request():
    clock = Clock()
    pairs = tuple((probe(visit, 0), probe(visit, 1)) for visit in range(3))
    reads = []
    result = diagnostic.run_selected_diagnostic(
        pairs,
        sample_rate_hz=10_000_000,
        probe_ms=20,
        read_visit=lambda visit: reads.append(visit),
        estimator=lambda *args, **kwargs: None,
        deadline=10.0,
        clock=clock,
        read_guard_s=15.0,
    )
    assert reads == []
    assert result["requested_probe_count"] == 6
    assert result["unprocessed_probe_count"] == 6
    assert result["stopped_reason"] == "deadline_guard_before_visit_read"
    assert {row["reason"] for row in result["probes"]} == {
        "deadline_guard_before_visit_read"
    }


def test_read_failure_does_not_suppress_later_visits():
    clock = Clock()
    pairs = tuple((probe(visit, 0), probe(visit, 1)) for visit in range(2))

    def read_visit(visit):
        if visit == 0:
            raise OSError("fixture")
        return np.zeros((200_000, 2, 2), dtype=np.int16)

    result = diagnostic.run_selected_diagnostic(
        pairs,
        sample_rate_hz=10_000_000,
        probe_ms=20,
        read_visit=read_visit,
        estimator=lambda samples, rate, **options: estimate_result(
            options["acquisition_absolute_cfo_hz"], 5.0
        ),
        deadline=100.0,
        clock=clock,
    )
    assert result["processed_probe_count"] == 2
    assert result["unprocessed_probe_count"] == 2
    assert len(result["failures"]) == 1
    assert result["failures"][0]["stage"] == "read"
