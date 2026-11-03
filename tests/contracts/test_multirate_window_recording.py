import pytest
from pydantic import ValidationError

from leo.contracts.fast_scan import FastScanPolicyV1
from leo.contracts.fast_scan_native import FastScanPolicyV2, parse_fast_policy
from leo.contracts.short_window_recording import ShortWindowIndexV1, ShortWindowManifestV1
from leo.contracts.multirate_window_recording import ShortWindowIndexV2


def test_published_v1_geometry_remains_fixed():
    with pytest.raises(ValidationError):
        FastScanPolicyV1(sample_rate_hz=10_000_000)
    assert ShortWindowManifestV1.model_fields["sample_rate_hz"].default == 2_500_000
    values = dict(sequence=0, target_id="target", sample_count=200_000,
                  receiver_count=2, payload_offset_bytes=0, payload_bytes=1_600_000,
                  iq_sha256="sha256:" + "a" * 64, acquisition={}, powers=({}, {}))
    with pytest.raises(ValidationError):
        ShortWindowIndexV1(**values)
    assert ShortWindowIndexV2(**values).schema_version == 2


def test_native_predictor_can_never_gate_capture_analysis():
    assert parse_fast_policy(FastScanPolicyV2().model_dump()).sample_rate_hz == 10_000_000
    with pytest.raises(ValidationError):
        FastScanPolicyV2(mode="gated")
