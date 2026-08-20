from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV2, StandardPathInputBindV3
from leo.contracts.states import StarlinkEdge


def _v2_values() -> dict[str, object]:
    return {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
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
        "science_configuration_digest": canonical_digest({"configuration": 1}),
        "science_implementation_digest": canonical_digest({"implementation": 1}),
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": 959_687_500,
        "sample_rate_hz": 2_500_000,
        "declared_sample_count": 150_000_000,
        "timing": {
            "schema_version": 1,
            "first_estimate_utc_ns": 1,
            "first_earliest_utc_ns": 1,
            "first_latest_utc_ns": 1,
            "last_estimate_utc_ns": 2,
            "last_earliest_utc_ns": 2,
            "last_latest_utc_ns": 2,
        },
        "frequency_reference": {
            "schema_version": 1,
            "reference": "uncalibrated_prior",
            "center_frequency_hz": None,
            "uncertainty_hz": None,
            "calibration_digest": None,
        },
    }


def _v3_values(channel: int, edge: StarlinkEdge) -> dict[str, object]:
    return {
        **_v2_values(),
        "schema_version": 3,
        "algorithm_version": "standard-path-input-bind-v3",
        "starlink_channel": channel,
        "starlink_edge": edge.value,
        "starlink_tuning_evidence_source": "capture_profile",
    }


@pytest.mark.parametrize(
    ("channel", "edge"),
    ((1, StarlinkEdge.LOWER), (8, StarlinkEdge.UPPER)),
)
def test_v3_requires_and_preserves_explicit_manifest_tuning(
    channel: int, edge: StarlinkEdge
) -> None:
    values = _v3_values(channel, edge)
    binding = StandardPathInputBindV3.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )

    assert binding.starlink_channel == channel
    assert binding.starlink_edge is edge
    assert binding.starlink_tuning_evidence_source == "capture_profile"


@pytest.mark.parametrize("channel", (0, 9, "ch4", None))
def test_v3_rejects_missing_or_out_of_range_channel(channel: object) -> None:
    values = _v3_values(4, StarlinkEdge.LOWER)
    values["starlink_channel"] = channel
    with pytest.raises(ValidationError):
        StandardPathInputBindV3.model_validate(
            {**values, "binding_digest": canonical_digest(values)}
        )


def test_v3_rejects_missing_edge_while_v2_contract_remains_unchanged() -> None:
    v3_values = _v3_values(4, StarlinkEdge.LOWER)
    del v3_values["starlink_edge"]
    with pytest.raises(ValidationError):
        StandardPathInputBindV3.model_validate(
            {**v3_values, "binding_digest": canonical_digest(v3_values)}
        )

    v2_values = _v2_values()
    assert StandardPathInputBindV2.model_validate(
        {**v2_values, "binding_digest": canonical_digest(v2_values)}
    ).schema_version == 2
