from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)

_DIGEST = "sha256:" + "1" * 64


def _inventory() -> ValidityInventoryV1:
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=_DIGEST,
        gap_map_content_digest=_DIGEST,
        first_device_sample_counter=100,
        logical_sample_count=8,
        observed_sample_count=6,
        missing_sample_count=2,
        continuity_boundary_count=1,
        runs=(
            ValidityRunV1(
                run_index=0,
                device_sample_start=0,
                sample_count=4,
                content_kind=DeviceAxisContentKind.OBSERVED,
                stored_sample_start=0,
                continuity_segment_index=0,
            ),
            ValidityRunV1(
                run_index=1,
                device_sample_start=4,
                sample_count=2,
                content_kind=DeviceAxisContentKind.ZERO_FILL,
            ),
            ValidityRunV1(
                run_index=2,
                device_sample_start=6,
                sample_count=2,
                content_kind=DeviceAxisContentKind.OBSERVED,
                stored_sample_start=4,
                continuity_segment_index=1,
            ),
        ),
        segments=(
            ContinuitySegmentV1(
                segment_index=0,
                device_sample_start=0,
                device_sample_stop=4,
                stored_sample_start=0,
                stored_sample_stop=4,
            ),
            ContinuitySegmentV1(
                segment_index=1,
                device_sample_start=6,
                device_sample_stop=8,
                stored_sample_start=4,
                stored_sample_stop=6,
                preceding_missing_sample_count=2,
                preceding_boundary_reason="counter_gap",
                preceding_boundary_header_sha256=_DIGEST,
            ),
        ),
    )


def test_validity_contract_serializes_complete_canonical_coordinate_closure() -> None:
    inventory = _inventory()

    assert inventory.model_dump(mode="json") == {
        "schema_version": 1,
        "algorithm_version": "counter-authoritative-validity-v1",
        "stream_id": "stream-0",
        "timeline_sha256": _DIGEST,
        "gap_map_content_digest": _DIGEST,
        "first_device_sample_counter": 100,
        "logical_sample_count": 8,
        "observed_sample_count": 6,
        "missing_sample_count": 2,
        "continuity_boundary_count": 1,
        "runs": [
            {
                "schema_version": 1,
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": 4,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
            {
                "schema_version": 1,
                "run_index": 1,
                "device_sample_start": 4,
                "sample_count": 2,
                "content_kind": "zero_fill",
                "stored_sample_start": None,
                "continuity_segment_index": None,
            },
            {
                "schema_version": 1,
                "run_index": 2,
                "device_sample_start": 6,
                "sample_count": 2,
                "content_kind": "observed",
                "stored_sample_start": 4,
                "continuity_segment_index": 1,
            },
        ],
        "segments": [
            {
                "schema_version": 1,
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": 4,
                "stored_sample_start": 0,
                "stored_sample_stop": 4,
                "preceding_missing_sample_count": 0,
                "preceding_boundary_reason": None,
                "preceding_boundary_header_sha256": None,
            },
            {
                "schema_version": 1,
                "segment_index": 1,
                "device_sample_start": 6,
                "device_sample_stop": 8,
                "stored_sample_start": 4,
                "stored_sample_stop": 6,
                "preceding_missing_sample_count": 2,
                "preceding_boundary_reason": "counter_gap",
                "preceding_boundary_header_sha256": _DIGEST,
            },
        ],
    }
    assert inventory.inventory_digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("content_kind", "stored_start", "segment_index"),
    [
        (DeviceAxisContentKind.OBSERVED, None, None),
        (DeviceAxisContentKind.ZERO_FILL, 0, 0),
    ],
)
def test_validity_run_cannot_erase_observed_vs_zero_fill_meaning(
    content_kind: DeviceAxisContentKind,
    stored_start: int | None,
    segment_index: int | None,
) -> None:
    with pytest.raises(ValidationError, match="observed validity runs require"):
        ValidityRunV1(
            run_index=0,
            device_sample_start=0,
            sample_count=1,
            content_kind=content_kind,
            stored_sample_start=stored_start,
            continuity_segment_index=segment_index,
        )


def test_validity_inventory_rejects_noncanonical_run_or_segment_coordinates() -> None:
    document = _inventory().model_dump(mode="json")
    document["runs"][1]["sample_count"] = 1
    with pytest.raises(ValidationError, match="canonical segment expansion"):
        ValidityInventoryV1.model_validate(document)

    document = _inventory().model_dump(mode="json")
    document["segments"][1]["stored_sample_start"] = 3
    document["segments"][1]["stored_sample_stop"] = 5
    with pytest.raises(ValidationError, match="stored coordinates are not contiguous"):
        ValidityInventoryV1.model_validate(document)
