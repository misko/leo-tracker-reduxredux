from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1
from leo.contracts.recording import HostIdentityV1, RecordingManifestV3
from leo.contracts.starlink_frequency import (
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import CaptureState, GainMode, RadioTransport, StarlinkEdge
from leo.domain.profiles import load_profile_revision
from leo.qualification.native_bandwidth import (
    NativeBandwidthCaptureEvidenceV1,
    NativeBandwidthCaptureModeV1,
    NativeBandwidthLadderCellV1,
    NativeBandwidthQualificationReceiptV1,
    NativeBandwidthStreamEvidenceV1,
    NativeBandwidthTransportEvidenceV1,
    build_native_bandwidth_capture_evidence_v1,
    native_bandwidth_qualification_receipt_digest,
)

_ROOT = Path(__file__).parents[2]
_REVISION = "a" * 40
_PPU_REVISION = "cb1d091cd5c5831d0a99347bf74fb4e517800c92"
_PROFILE_AUTHORITY = {
    (False, 2_500_000): (
        "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
        "sha256:fd7ebe29c1ed6bb9b85da0d35e2ce348af3f1a885dd53546e68a5f530dac9cba",
    ),
    (False, 3_000_000): (
        "starlink-ch4-lower-3m-60s-native-bandwidth-v4",
        "sha256:3964c526cdd6fc6228bedc3f2b066bd0b7aac14d03d9f699e79fb52a0cab4907",
    ),
    (False, 5_000_000): (
        "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        "sha256:37c144b63573556c70fd06bcc5a394a33a7070d6c99b519154b750bcdbd0dcd4",
    ),
    (True, 2_500_000): (
        "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
        "sha256:df2a9d8c76f03a8f5e062b6ff62d5fb5650213b5738828b8fa5ae72fef3ee2d2",
    ),
    (True, 5_000_000): (
        "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
        "sha256:ff8cc094a9f692352b354619fe479fd6f0e970304123706f409ff1a4af55d404",
    ),
}


def _digest(label: str) -> str:
    return canonical_digest({"native-bandwidth-test": label})


def _radios() -> tuple[RadioIdentityV1, RadioIdentityV1]:
    return (
        RadioIdentityV1(
            radio_id="radio_pluto_5d4d",
            serial="1040005e0b100007100010000bf33a5d4d",
            uri="ip:192.168.1.20",
            transport=RadioTransport.IIO_IP,
            firmware_version="v5",
        ),
        RadioIdentityV1(
            radio_id="radio_pluto_19f2",
            serial="10400056f695001322002d0010ad1719f2",
            uri="ip:192.168.1.21",
            transport=RadioTransport.IIO_IP,
            firmware_version="v5",
        ),
    )


def _stream(
    rate_hz: int,
    radio: RadioIdentityV1,
    *,
    mixed: bool,
) -> NativeBandwidthStreamEvidenceV1:
    channel = 4
    edge = StarlinkEdge.LOWER
    center = starlink_maximum_coverage_if_center_frequency_hz(
        channel,
        edge,
        bandwidth_hz=rate_hz,
    )
    channel_start, channel_stop = starlink_channel_if_bounds_hz(channel)
    profile_name, profile_revision = _PROFILE_AUTHORITY[(mixed, rate_hz)]
    count = rate_hz * 60
    return NativeBandwidthStreamEvidenceV1(
        radio=radio,
        profile_name=profile_name,
        profile_revision_digest=profile_revision,
        sample_rate_hz=rate_hz,
        rf_bandwidth_hz=rate_hz,
        center_frequency_hz=center,
        starlink_channel=channel,
        starlink_edge=edge,
        pilot_if_center_frequency_hz=starlink_edge_if_center_frequency_hz(channel, edge),
        channel_if_start_hz=channel_start,
        channel_if_stop_hz=channel_stop,
        captured_if_start_hz=center - rate_hz // 2,
        captured_if_stop_hz=center + rate_hz // 2,
        requested_sample_count=count,
        logical_sample_count=count,
        observed_sample_count=count,
        zero_fill_sample_count=0,
        queue_high_water_refills=12,
        gap_count=0,
        observed_iq_sha256=_digest(f"observed-{radio.radio_id}-{rate_hz}"),
        logical_iq_sha256=_digest(f"logical-{radio.radio_id}-{rate_hz}"),
        timeline_sha256=_digest(f"timeline-{radio.radio_id}-{rate_hz}"),
        gap_map_sha256=_digest(f"gap-{radio.radio_id}-{rate_hz}"),
        validity_inventory_sha256=_digest(f"validity-{radio.radio_id}-{rate_hz}"),
    )


def _capture(mode: NativeBandwidthCaptureModeV1) -> NativeBandwidthCaptureEvidenceV1:
    rates = {
        NativeBandwidthCaptureModeV1.ORDINARY_2P5: (2_500_000, 2_500_000),
        NativeBandwidthCaptureModeV1.ORDINARY_3: (3_000_000, 3_000_000),
        NativeBandwidthCaptureModeV1.ORDINARY_5: (5_000_000, 5_000_000),
        NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_FIRST: (5_000_000, 2_500_000),
        NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_SECOND: (2_500_000, 5_000_000),
    }[mode]
    radios = _radios()
    mixed = mode.value.startswith("mixed_")
    return NativeBandwidthCaptureEvidenceV1(
        mode=mode,
        session_id=f"native-bandwidth-{mode.value}",
        manifest_schema_version=4 if mixed else 3,
        manifest_sha256=_digest(f"manifest-{mode.value}"),
        capture_state=CaptureState.COMMITTED,
        streams=(
            _stream(rates[0], radios[0], mixed=mixed),
            _stream(rates[1], radios[1], mixed=mixed),
        ),
    )


def _transport(
    radio: RadioIdentityV1,
    endpoint: str,
) -> NativeBandwidthTransportEvidenceV1:
    return NativeBandwidthTransportEvidenceV1.model_validate(
        {
            "radio_id": radio.radio_id,
            "endpoint": endpoint,
            "serial": radio.serial,
            "evidence_sha256": _digest(f"ppu-{radio.radio_id}"),
            "pluto_plus_utils_revision": _PPU_REVISION,
            "frames": 6,
            "warmup_frames": 2,
            "kernel_buffer_configuration_basis": "setter_accepted",
            "cells": [
                NativeBandwidthLadderCellV1(
                    sample_rate_hz=rate,
                    actual_sample_rate_hz=rate,
                    delivery_fraction=0.99,
                    achieved_payload_mbps=rate * 8 / 1_000_000 * 0.99,
                ).model_dump(mode="json")
                for rate in (2_500_000, 3_000_000, 5_000_000)
            ],
        }
    )


def _receipt() -> NativeBandwidthQualificationReceiptV1:
    radios = _radios()
    values = {
        "target_revision": _REVISION,
        "host": HostIdentityV1(hostname="gauss", machine_id="machine"),
        "radios": radios,
        "pluto_plus_utils_revision": _PPU_REVISION,
        "transport_evidence": (
            _transport(radios[0], "192.168.1.20"),
            _transport(radios[1], "192.168.1.21"),
        ),
        "captures": tuple(_capture(mode) for mode in NativeBandwidthCaptureModeV1),
        "created_utc_ns": 1,
    }
    candidate = NativeBandwidthQualificationReceiptV1.model_construct(
        **values,
        receipt_digest="sha256:" + "0" * 64,
    )
    return NativeBandwidthQualificationReceiptV1.model_validate(
        {
            **candidate.model_dump(mode="json"),
            "receipt_digest": native_bandwidth_qualification_receipt_digest(candidate),
        }
    )


def test_native_bandwidth_receipt_is_closed_and_round_trips() -> None:
    receipt = _receipt()

    assert receipt.passed is True
    assert tuple(item.mode for item in receipt.captures) == tuple(NativeBandwidthCaptureModeV1)
    assert (
        NativeBandwidthQualificationReceiptV1.model_validate_json(receipt.model_dump_json())
        == receipt
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("rf_bandwidth_hz", 2_499_999, "bandwidth must equal"),
        ("center_frequency_hz", 1_709_687_501, "maximum in-channel coverage"),
        ("queue_high_water_refills", 25, "less than or equal to 24"),
        ("overflow_count", 1, "overflow, enqueue, or rejected"),
        ("sample_rate_hz", 10_000_000, "outside the enabled safe pool"),
    ),
)
def test_native_bandwidth_stream_rejects_rf_transport_and_integrity_tamper(
    field: str,
    value: int,
    message: str,
) -> None:
    stream = _stream(2_500_000, _radios()[0], mixed=False)
    document = stream.model_dump(mode="json")
    document[field] = value

    with pytest.raises(ValidationError, match=message):
        NativeBandwidthStreamEvidenceV1.model_validate(document)


def test_native_bandwidth_receipt_rejects_profile_and_inventory_tamper() -> None:
    receipt = _receipt()
    document = receipt.model_dump(mode="json")
    document["captures"][0]["streams"][0]["profile_revision_digest"] = _digest("foreign")

    with pytest.raises(ValidationError, match="profile identity is not reviewed"):
        NativeBandwidthQualificationReceiptV1.model_validate(document)

    document = receipt.model_dump(mode="json")
    document["captures"][0], document["captures"][1] = (
        document["captures"][1],
        document["captures"][0],
    )
    with pytest.raises(ValidationError, match="incomplete or reordered"):
        NativeBandwidthQualificationReceiptV1.model_validate(document)

    document = receipt.model_dump(mode="json")
    document["transport_evidence"][0]["endpoint"] = "192.168.1.21"
    with pytest.raises(ValidationError, match="endpoint or serial"):
        NativeBandwidthQualificationReceiptV1.model_validate(document)

    document = receipt.model_dump(mode="json")
    document["captures"][0]["streams"][0]["radio"]["serial"] = "different-serial"
    with pytest.raises(ValidationError, match="radio identity or order"):
        NativeBandwidthQualificationReceiptV1.model_validate(document)


def test_native_bandwidth_transport_rejects_sub_keep_pace_delivery() -> None:
    evidence = _transport(_radios()[0], "192.168.1.20")
    document = evidence.model_dump(mode="json")
    document["cells"][2]["delivery_fraction"] = 0.899

    with pytest.raises(ValidationError, match="90% keep-pace"):
        NativeBandwidthTransportEvidenceV1.model_validate(document)


def test_builder_projects_exact_v3_rf_and_device_axis_authority() -> None:
    revision = load_profile_revision(
        _ROOT / "profiles/starlink-ch4-lower-5m-60s-native-bandwidth-v4.yaml"
    )
    rate = revision.profile.sample_rate_hz
    count = rate * 60
    radios = _radios()
    center = revision.profile.center_frequency_hz
    settings = RadioSettingsV1(
        center_frequency_hz=center,
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=revision.profile.gains,
    )
    continuity = SimpleNamespace(
        kernel_buffers=4,
        queue_capacity_refills=32,
        queue_high_water_refills=8,
        gap_count=0,
        overflow_count=0,
        enqueue_failure_count=0,
        terminal_rejected_gap_count=0,
        terminal_rejected_missing_sample_count=0,
        terminal_rejected_overflow_count=0,
    )
    streams = tuple(
        SimpleNamespace(
            stream_id=f"stream-{index}",
            radio=radio,
            applied_settings=settings,
            requested_sample_count=count,
            logical_sample_count=count,
            observed_sample_count=count,
            zero_fill_sample_count=0,
            continuity=continuity,
            observed_iq_sha256=_digest(f"observed-{index}"),
            logical_iq_sha256=_digest(f"logical-{index}"),
            timeline_sha256=_digest(f"timeline-{index}"),
            gap_map_sha256=_digest(f"gap-{index}"),
            validity_inventory_sha256=_digest(f"validity-{index}"),
        )
        for index, radio in enumerate(radios)
    )
    manifest = RecordingManifestV3.model_construct(
        session_id="native-bandwidth-builder",
        state=CaptureState.COMMITTED,
        streams=streams,
        tags=("tuning:stream-0:ch4:lower", "tuning:stream-1:ch4:lower"),
        capture_plan=SimpleNamespace(profile_revision=revision),
    )

    evidence = build_native_bandwidth_capture_evidence_v1(
        manifest,
        mode=NativeBandwidthCaptureModeV1.ORDINARY_5,
        manifest_sha256=_digest("builder-manifest"),
    )

    assert tuple(stream.center_frequency_hz for stream in evidence.streams) == (center, center)
    assert all(
        stream.rf_bandwidth_hz == stream.sample_rate_hz == rate for stream in evidence.streams
    )
