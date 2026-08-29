from pathlib import Path

import pytest

from leo.contracts.device_buffer import (
    DDR_RING_PROFILE_TAG_V1,
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
