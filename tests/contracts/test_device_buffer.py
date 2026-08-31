from pathlib import Path

import pytest

from leo.contracts.device_buffer import (
    DDR_RING_PROFILE_TAG_V1,
    DirectAsyncEvidenceV1,
    DirectAsyncRequestV1,
    device_buffer_request,
    device_buffer_request_v1,
)
from leo.domain.profiles import compile_capture_plan, load_profile_revision


@pytest.mark.parametrize("rate,frames", [(10, 600), (15, 900), (20, 1200)])
@pytest.mark.parametrize("rx", [0, 1])
def test_ring_profiles_bind_exact_geometry_without_changing_published_schema(rate, frames, rx):
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / (f"starlink-ch4-lower-{rate}m-60s-rx{rx}-ddr-ring-v6.yaml")
    )
    revision = load_profile_revision(path)
    plan = compile_capture_plan(revision, ["radio-a"])
    request = device_buffer_request_v1(revision.profile, plan.resolved_sample_count)
    assert revision.schema_version == plan.schema_version == 2
    assert request is not None
    assert request.target_frames == frames
    assert request.capacity_frames == 50
    assert request.requested_bytes == 200_000_000
    assert request.frame_samples == 1_000_000


def test_ordinary_profiles_remain_ordinary_and_unknown_buffer_tags_fail_closed():
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / ("starlink-ch4-lower-20m-60s-rx0-production-v5.yaml")
    )
    profile = load_profile_revision(path).profile
    assert device_buffer_request_v1(profile, 1_200_000_000) is None
    with pytest.raises(ValueError, match="unsupported"):
        device_buffer_request_v1(
            profile.model_copy(update={"tags": ("DEVICE_BUFFER:typo",)}), 1_200_000_000
        )
    with pytest.raises(ValueError, match="geometry"):
        device_buffer_request_v1(
            profile.model_copy(update={"tags": (DDR_RING_PROFILE_TAG_V1,)}), 1_200_000_000
        )


@pytest.mark.parametrize("rate,frames", [(10, 573), (15, 859), (25, 1431)])
@pytest.mark.parametrize("rx", [0, 1])
def test_direct_async_profiles_bind_bounded_segment_geometry(rate, frames, rx):
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / (f"starlink-ch4-lower-{rate}m-60s-rx{rx}-direct-async-v7.yaml")
    )
    revision = load_profile_revision(path)
    plan = compile_capture_plan(revision, ["radio-a"])
    request = device_buffer_request(revision.profile, plan.resolved_sample_count)
    assert isinstance(request, DirectAsyncRequestV1)
    assert request.target_frames == frames
    assert request.segment_count == (frames + 63) // 64
    assert request.next_segment_frames(0) == min(64, frames)
    assert request.next_segment_frames(frames - 1) == 1


def test_direct_async_evidence_closes_segment_gaps_and_tail():
    request = DirectAsyncRequestV1(
        target_frames=65,
        requested_device_samples=64 * 1_048_576 + 100,
    )
    evidence = DirectAsyncEvidenceV1(
        request=request,
        returned_frames=65,
        returned_device_span_samples=65 * 1_048_576 + 2 * 1_048_576,
        segment_count=2,
        upstream_stream_generations=("segment-a", "segment-b"),
        counter_missing_sample_count=2 * 1_048_576,
        inter_segment_skipped_samples=2 * 1_048_576,
        stored_observed_samples=64 * 1_048_576 + 100,
        drained_outside_window_samples=1_048_576 - 100,
    )
    assert evidence.request.segment_count == 2
