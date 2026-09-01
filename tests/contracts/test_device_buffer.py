from pathlib import Path

import pytest

from leo.contracts.device_buffer import (
    DDR_RING_PROFILE_TAG_V1,
    DirectAsyncEvidenceV1,
    DirectAsyncRamDropEvidenceV2,
    DirectAsyncRamDropEvidenceV3,
    DirectAsyncRamDropRequestV2,
    DirectAsyncRamDropRequestV3,
    DirectAsyncRamStatusV2,
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


@pytest.mark.parametrize("rx", [0, 1])
def test_25m_v8_profiles_use_internal_two_buffer_prime_without_a_ram_ring(rx):
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / f"starlink-ch4-lower-25m-60s-rx{rx}-direct-async-v8.yaml"
    )
    revision = load_profile_revision(path)
    profile = revision.profile
    request = device_buffer_request(profile, 1_500_000_000)

    assert isinstance(request, DirectAsyncRequestV1)
    assert profile.prime_refills == 0
    assert profile.kernel_buffers == 15
    assert profile.refill_queue_capacity == 64
    assert profile.receivers == (rx,)
    assert request.target_frames == 1431
    assert request.segment_count == 23


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


@pytest.mark.parametrize("rate,frames", [(10, 573), (15, 859), (20, 1145), (25, 1431)])
@pytest.mark.parametrize("rx", [0, 1])
def test_ram_drop_profiles_bind_one_session_and_maximum_whole_frame_ram(rate, frames, rx):
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / f"starlink-ch4-lower-{rate}m-60s-rx{rx}-direct-async-ram-drop-v9.yaml"
    )
    revision = load_profile_revision(path)
    plan = compile_capture_plan(revision, ["radio-a"])
    request = device_buffer_request(revision.profile, plan.resolved_sample_count)

    assert isinstance(request, DirectAsyncRamDropRequestV2)
    assert request.target_frames == frames
    assert request.segment_count == 1
    assert request.next_segment_frames(0) == frames
    assert request.capacity_frames == 47
    assert request.requested_ram_bytes == 200_000_000
    assert request.admitted_ram_bytes == 197_132_288
    assert request.drop_backlog_on_overrun is True
    assert revision.profile.kernel_buffers == 12


def test_ram_drop_evidence_closes_spill_drain_drop_and_device_span():
    request = DirectAsyncRamDropRequestV2(
        target_frames=3,
        requested_device_samples=2 * 1_048_576 + 100,
    )
    status = DirectAsyncRamStatusV2(
        version=1,
        state="complete",
        terminal_reason="target_complete",
        error_code=0,
        requested_capacity_iq_bytes=200_000_000,
        admitted_capacity_iq_bytes=197_132_288,
        target_frames=0,
        produced_frames=12,
        consumed_frames=7,
        high_water_frames=10,
        wrap_count=1,
        producer_position=12,
        consumer_position=7,
    )
    evidence = DirectAsyncRamDropEvidenceV2(
        request=request,
        status=status,
        returned_frames=3,
        returned_device_span_samples=4 * 1_048_576,
        segment_count=1,
        upstream_stream_generations=("one-session",),
        counter_missing_sample_count=1_048_576,
        inter_segment_skipped_samples=0,
        stored_observed_samples=2 * 1_048_576 + 100,
        drained_outside_window_samples=1_048_576 - 100,
    )

    assert evidence.ram_spilled_frames == 12
    assert evidence.ram_drained_frames == 7
    assert evidence.ram_dropped_frames == 5


@pytest.mark.parametrize("rate,frames", [(10, 573), (15, 859), (20, 1145), (25, 1431)])
@pytest.mark.parametrize("rx", [0, 1])
def test_qualified_ram_drop_profiles_bind_one_session_and_32_frame_ram(rate, frames, rx):
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / f"starlink-ch4-lower-{rate}m-60s-rx{rx}-direct-async-ram-drop-v10.yaml"
    )
    revision = load_profile_revision(path)
    plan = compile_capture_plan(revision, ["radio-a"])
    request = device_buffer_request(revision.profile, plan.resolved_sample_count)

    assert isinstance(request, DirectAsyncRamDropRequestV3)
    assert request.target_frames == frames
    assert request.segment_count == 1
    assert request.capacity_frames == 32
    assert request.requested_ram_bytes == request.admitted_ram_bytes == 134_217_728
    assert request.drop_backlog_on_overrun is True
    assert revision.profile.kernel_buffers == 11


def test_qualified_ram_drop_evidence_preserves_v3_request_generation():
    request = DirectAsyncRamDropRequestV3(
        target_frames=3,
        requested_device_samples=2 * 1_048_576 + 100,
    )
    evidence = DirectAsyncRamDropEvidenceV3(
        request=request,
        status=DirectAsyncRamStatusV2(
            version=1,
            state="complete",
            terminal_reason="target_complete",
            error_code=0,
            requested_capacity_iq_bytes=134_217_728,
            admitted_capacity_iq_bytes=134_217_728,
            target_frames=0,
            produced_frames=12,
            consumed_frames=7,
            high_water_frames=10,
            wrap_count=1,
            producer_position=12,
            consumer_position=7,
        ),
        returned_frames=3,
        returned_device_span_samples=4 * 1_048_576,
        segment_count=1,
        upstream_stream_generations=("one-session",),
        counter_missing_sample_count=1_048_576,
        inter_segment_skipped_samples=0,
        stored_observed_samples=2 * 1_048_576 + 100,
        drained_outside_window_samples=1_048_576 - 100,
    )

    assert evidence.schema_version == evidence.request.schema_version == 3
    assert evidence.ram_dropped_frames == 5
