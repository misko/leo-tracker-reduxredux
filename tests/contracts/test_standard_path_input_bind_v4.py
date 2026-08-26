from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.validity import ValidityInventoryV1


def _validity(sample_rate_hz: int) -> ValidityInventoryV1:
    timeline_digest = canonical_digest({"timeline": sample_rate_hz})
    gap_map_digest = canonical_digest({"gap-map": sample_rate_hz})
    header_digest = canonical_digest({"header": sample_rate_hz})
    observed = sample_rate_hz - 2
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=timeline_digest,
        gap_map_content_digest=gap_map_digest,
        first_device_sample_counter=100,
        logical_sample_count=sample_rate_hz,
        observed_sample_count=observed,
        missing_sample_count=2,
        continuity_boundary_count=1,
        runs=(
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": 4,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
            {
                "run_index": 1,
                "device_sample_start": 4,
                "sample_count": 2,
                "content_kind": "zero_fill",
            },
            {
                "run_index": 2,
                "device_sample_start": 6,
                "sample_count": observed - 4,
                "content_kind": "observed",
                "stored_sample_start": 4,
                "continuity_segment_index": 1,
            },
        ),
        segments=(
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": 4,
                "stored_sample_start": 0,
                "stored_sample_stop": 4,
            },
            {
                "segment_index": 1,
                "device_sample_start": 6,
                "device_sample_stop": sample_rate_hz,
                "stored_sample_start": 4,
                "stored_sample_stop": observed,
                "preceding_missing_sample_count": 2,
                "preceding_boundary_reason": "counter_gap",
                "preceding_boundary_header_sha256": header_digest,
            },
        ),
    )


def _values(sample_rate_hz: int) -> dict[str, Any]:
    validity = _validity(sample_rate_hz)
    return {
        "schema_version": 4,
        "algorithm_version": "standard-path-input-bind-v4",
        "session_id": "session-1",
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": canonical_digest({"manifest": 1}),
        "raw_integrity_attestation_digest": canonical_digest({"integrity": 1}),
        "selected_stream_digest": canonical_digest({"stream": 1}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": 1}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": 1}),
        "synchronization_inventory_digest": canonical_digest({"sync": 1}),
        "profile_revision_digest": canonical_digest({"profile": 1}),
        "capture_plan_digest": canonical_digest({"plan": 1}),
        "receiver_settings_digest": canonical_digest({"settings": 1}),
        "science_configuration_digest": canonical_digest({"configuration": sample_rate_hz}),
        "science_implementation_digest": canonical_digest({"implementation": 1}),
        "capture_lineage_resolution": "resolved",
        "physical_receiver_id": "physical-rx-0",
        "hardware_epoch_id": "epoch-1",
        "tuned_center_frequency_hz": 959_687_500,
        "sample_rate_hz": sample_rate_hz,
        "declared_sample_count": sample_rate_hz,
        "starlink_channel": 1,
        "starlink_edge": "lower",
        "starlink_tuning_evidence_source": "capture_profile",
        "rf_bandwidth_hz": 10_000_000,
        "requested_sample_count": sample_rate_hz,
        "requested_duration_seconds": "1",
        "logical_sample_count": sample_rate_hz,
        "observed_sample_count": sample_rate_hz - 2,
        "missing_sample_count": 2,
        "observed_iq_digest": canonical_digest({"observed-iq": sample_rate_hz}),
        "logical_iq_digest": canonical_digest({"logical-iq": sample_rate_hz}),
        "timeline_sha256": validity.timeline_sha256,
        "gap_map_sha256": canonical_digest({"gap-map-file": sample_rate_hz}),
        "gap_map_content_digest": validity.gap_map_content_digest,
        "validity_inventory_sha256": validity.inventory_digest,
        "first_device_sample_counter": 100,
        "last_device_sample_counter_inclusive": 99 + sample_rate_hz,
        "validity_inventory": validity.model_dump(mode="json"),
        "timing": {
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 2_000_000_000,
            "last_earliest_utc_ns": 1_999_999_900,
            "last_latest_utc_ns": 2_000_000_100,
        },
        "frequency_reference": {
            "schema_version": 1,
            "reference": "uncalibrated_prior",
            "center_frequency_hz": None,
            "uncertainty_hz": None,
            "calibration_digest": None,
        },
    }


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_v4_closes_native_rate_device_axis(sample_rate_hz: int) -> None:
    values = _values(sample_rate_hz)
    binding = StandardPathInputBindV4.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )

    assert binding.logical_sample_count == sample_rate_hz
    assert binding.observed_sample_count == sample_rate_hz - 2
    assert binding.missing_sample_count == 2
    assert tuple(item.segment_index for item in binding.validity_inventory.segments) == (0, 1)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("sample_rate_hz", 4_000_000),
        ("logical_sample_count", 2_499_999),
        ("observed_sample_count", 2_499_999),
        ("requested_duration_seconds", "2"),
        ("last_device_sample_counter_inclusive", 2_500_100),
        ("timeline_sha256", canonical_digest({"foreign": "timeline"})),
        ("gap_map_content_digest", canonical_digest({"foreign": "gap-map"})),
        ("validity_inventory_sha256", canonical_digest({"foreign": "validity"})),
    ),
)
def test_v4_rejects_foreign_or_inconsistent_native_authority(
    field: str, replacement: object
) -> None:
    values = _values(2_500_000)
    values[field] = replacement

    with pytest.raises(ValidationError):
        StandardPathInputBindV4.model_validate(
            {**values, "binding_digest": canonical_digest(values)}
        )
