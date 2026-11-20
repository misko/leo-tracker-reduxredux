import pytest

from tools.pipeline_eval.qualification import complete_timing as timing


def test_sequential_core_context_is_not_just_matching_pin_numbers():
    source = str(timing.UNION.relative_to(timing.SCREEN))
    stock = dict(
        source=source,
        cores=[4, 5],
        boot_id="same-boot",
        start_monotonic_s=1,
        end_monotonic_s=5,
        position_status="ok",
    )
    fifth = dict(stock, start_monotonic_s=7, end_monotonic_s=11)
    assert timing.context(stock, fifth) == ("same_core_same_study", "stock_first")
    assert timing.context(stock, dict(fifth, source="elsewhere")) == ("separate_same_cores", None)
    assert timing.context(stock, dict(fifth, position_status="pending")) == ("pending", None)
    with pytest.raises(ValueError, match="overlapped"):
        timing.context(stock, dict(fifth, start_monotonic_s=4))


def test_complete_raw_timeout_counts_calls_but_has_no_worker_elapsed():
    row = dict(
        position_status="timed_out",
        full_raw_verified=True,
        both_positions=False,
        detector_calls=12,
        detector_wall_within_20=7,
        raw_s=334,
        raw_within_recorded_span=False,
        worker_s=None,
    )
    pending = dict(position_status="pending")
    result = timing.stats([row, pending])
    assert result["scheduled"] == 2
    assert result["terminal"] == 1
    assert result["raw_verified"] == 1
    assert result["detector_wall_within_20"] == 7
    assert result["detector_wall_fraction"] == 7 / 12
    assert result["worker_measured"] == 0
    assert result["median_worker_s"] is None
    assert result["median_raw_s"] == 334
    assert timing.clock_budget(299, 301, 300) == (True, False)
    assert timing.clock_budget(300, None, 300) == (True, None)


def test_recording_match_checks_actual_exclusions_when_both_raw_legs_are_complete():
    common = dict(
        id="case",
        clock_authority="signed-source",
        capture_sha256="source",
        catalog_sha256="cat",
        request_sha256="req",
        receiver_release_sha256="release",
        scheduled_windows=46,
        full_raw_verified=True,
        raw_authority="raw",
        clock_sha256="clock",
        excluded_sha256="exclude",
        probes_sha256="probes",
        detector_calls=43,
        invalid_visits=3,
        recorded_clock_span_s=30,
    )
    timing.same_recording(common, dict(common))
    with pytest.raises(ValueError, match="waveform support"):
        timing.same_recording(common, dict(common, excluded_sha256="different"))
    timing.same_recording(common, dict(common, full_raw_verified=False, excluded_sha256=None))
    with pytest.raises(ValueError, match="installed solver"):
        timing.same_recording(common, dict(common, receiver_release_sha256="different"))


def test_batch_statistics_do_not_average_per_recording_deadline_percentages():
    small = dict(
        position_status="ok",
        full_raw_verified=True,
        both_positions=True,
        detector_calls=1,
        detector_wall_within_20=1,
        raw_within_recorded_span=True,
        worker_within_recorded_span=False,
        worker_s=1,
        raw_s=0.25,
    )
    long = dict(small, detector_calls=99, detector_wall_within_20=0, worker_s=4)
    stats = timing.stats([small, long])
    assert stats["detector_wall_fraction"] == pytest.approx(0.01)
    assert stats["median_worker_s"] == 2.5
