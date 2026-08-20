from __future__ import annotations

from leo.application.presentation import _radio_setups
from leo.contracts.profile import CaptureProfileRevisionV1
from leo.contracts.recording import ContinuitySummaryV1, RecordingManifestV1
from leo.contracts.states import CaptureState, StreamState
from leo.domain.profiles import compile_capture_plan
from tests.station.manifest_examples import manifest_example


def test_randomized_per_stream_tuning_projects_applied_if_rf_and_firmware() -> None:
    base = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    profile = base.capture_plan.profile_revision.profile.model_copy(
        update={"lnb_lo_hz": 9_750_000_000}
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        base.capture_plan.radio_ids,
        source_type=base.source_type,
    )
    centers = (1_440_312_500, 1_209_687_500)
    firmware = ("0.39-5d4d", "0.39-19f2")
    streams = tuple(
        stream.model_copy(
            update={
                "radio": stream.radio.model_copy(
                    update={"firmware_version": firmware[index]}
                ),
                "applied_settings": stream.applied_settings.model_copy(
                    update={"center_frequency_hz": centers[index]}
                ),
            }
        )
        for index, stream in enumerate(base.streams)
    )
    payload = base.model_dump(mode="json")
    payload.update(
        capture_plan=plan.model_dump(mode="json"),
        tags=("TEST", "tuning:stream-0:ch2:upper", "tuning:stream-1:ch2:lower"),
        streams=tuple(stream.model_dump(mode="json") for stream in streams),
    )
    manifest = RecordingManifestV1.model_validate(payload)

    setups = _radio_setups(manifest)

    assert [item.applied_if_center_frequency_hz for item in setups] == list(centers)
    assert [item.target_rf_center_frequency_hz for item in setups] == [
        11_190_312_500,
        10_959_687_500,
    ]
    assert [(item.starlink_channel, item.starlink_edge) for item in setups] == [
        ("ch2", "upper"),
        ("ch2", "lower"),
    ]
    assert [item.firmware_version for item in setups] == list(firmware)
    assert all(item.applied_bandwidth_hz == 2_500_000 for item in setups)
    assert all(item.applied_sample_rate_hz == 2_500_000 for item in setups)


def test_failed_stream_never_labels_requested_settings_as_applied() -> None:
    base = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    failed = base.streams[0].model_copy(
        update={
            "applied_settings": None,
            "state": StreamState.FAILED,
            "captured_sample_count": 0,
            "timing": None,
            "chunks": (),
            "timeline_relative_path": None,
            "timeline_sha256": None,
            "continuity": ContinuitySummaryV1(refill_count=0, segment_count=0),
            "error": "radio did not apply settings",
        }
    )
    payload = base.model_dump(mode="json")
    payload.update(
        state=CaptureState.DEGRADED,
        streams=(failed.model_dump(mode="json"), base.streams[1].model_dump(mode="json")),
    )
    manifest = RecordingManifestV1.model_validate(payload)

    failed_setup = _radio_setups(manifest)[0]

    assert failed_setup.applied_if_center_frequency_hz is None
    assert failed_setup.target_rf_center_frequency_hz is None
    assert failed_setup.applied_bandwidth_hz is None
    assert failed_setup.applied_sample_rate_hz is None


def test_partial_or_duplicate_per_stream_tuning_tags_fail_closed() -> None:
    base = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    partial = base.model_copy(update={"tags": ("TEST", "tuning:stream-0:ch2:upper")})
    duplicate = base.model_copy(
        update={
            "tags": (
                "TEST",
                "tuning:stream-0:ch2:lower",
                "tuning:stream-0:ch2:upper",
            )
        }
    )

    for manifest in (partial, duplicate):
        try:
            _radio_setups(manifest)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid tuning tags must fail closed")
