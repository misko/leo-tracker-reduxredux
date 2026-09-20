import pytest

from leo.application.scanner_trajectory import timing_is_qualified_for_tle
from leo.cli.firmware_adaptive_import import _receipt, _timing
from leo.scanner.counter_utc import CounterUtcTimingV4
from tests.cli.test_firmware_adaptive_import import sparse_document


def counter_document(rate=10_000_000, *, calibrated=True):
    from pluto_plus.counter_utc import (
        CounterObservation,
        CounterUtcEvidence,
        HostClock,
        TimeAnchor,
        TimingPolicy,
    )

    document = sparse_document(rate)
    receipt = _receipt(document, "sha256:" + "b" * 64)
    utc, mono = 1_800_000_000_000_000_000, 10**12
    first = receipt.terminal.first_counter
    anchors = []
    for index, second in enumerate(range(0, 301, 5)):
        event = mono + second * 10**9
        clocks = [
            HostClock(
                monotonic_before_ns=t,
                monotonic_after_ns=t + 100,
                realtime_ns=utc + t - mono + 50,
                source="independent-reference",
                utc_error_bound_ns=1_000_000,
                reason="synthetic",
            )
            for t in (event - 10_001_000, event + 10_001_000)
        ]
        observation = CounterObservation(
            request=index + 1,
            session=11,
            generation=7,
            boot_id="01" * 16,
            epoch=99,
            counter=first + second * rate,
            device_before_ns=event - 100,
            device_after_ns=event + 100,
            sample_rate_hz=rate,
            maximum_snapshot_age_ns=10_000,
        )
        anchors.append(
            TimeAnchor(
                observation=observation,
                send_monotonic_ns=event - 10_000_000,
                receive_monotonic_ns=event + 10_000_000,
                clock_before=clocks[0],
                clock_after=clocks[1],
            )
        )
    policy = (
        TimingPolicy(
            calibration_reference="synthetic-independent-clock",
            calibration_radio_serial=document["evidence"]["radio_serial"],
            calibration_boot_id="01" * 16,
            maximum_rate_error_ppm=100,
            maximum_acquisition_delay_ns=10_000,
        )
        if calibrated
        else TimingPolicy()
    )
    evidence = CounterUtcEvidence(
        session=11,
        generation=7,
        radio_serial=document["evidence"]["radio_serial"],
        policy=policy,
        anchors=tuple(anchors),
    )
    document["evidence"]["counter_utc_timing"] = evidence.model_dump(mode="json")
    document["evidence"]["utc_timing"] = {
        "begin_before_realtime_ns": utc - 100_000_000,
        "begin_after_realtime_ns": utc + 100_000_000,
    }
    return document, receipt


@pytest.mark.parametrize("rate", [10_000_000, 15_000_000, 20_000_000])
def test_imported_counter_timing_preserves_evidence_and_binds_full_capture(rate):
    document, receipt = counter_document(rate)
    timing = _timing(document, receipt)
    assert isinstance(timing, CounterUtcTimingV4)
    assert timing.qualified
    assert timing.maximum_error_ns <= 100_000_000
    assert timing_is_qualified_for_tle(timing)
    assert CounterUtcTimingV4.model_validate_json(timing.model_dump_json()) == timing
    assert timing.evidence == document["evidence"]["counter_utc_timing"]


def test_unknown_hardware_bounds_cannot_use_relaxed_legacy_gate():
    document, receipt = counter_document(calibrated=False)
    timing = _timing(document, receipt)
    assert timing.first_sample_bracket_width_ns == 200_000_000
    assert timing.maximum_error_ns is None
    assert not timing.qualified
    assert not timing_is_qualified_for_tle(timing)


def test_wrong_session_and_tampered_evidence_are_rejected():
    document, receipt = counter_document()
    timing = _timing(document, receipt)
    payload = timing.model_dump()
    payload["evidence"]["generation"] += 1
    with pytest.raises(ValueError, match="digest"):
        CounterUtcTimingV4.model_validate(payload)
    document["evidence"]["counter_utc_timing"]["generation"] += 1
    with pytest.raises(ValueError, match="another capture"):
        _timing(document, receipt)
