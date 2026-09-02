from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.recording import RecordingManifestV3
from leo.contracts.states import CaptureState, SourceType
from leo.domain.profiles import load_profile_revision
from leo.pipeline.standard_native import (
    STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES,
    STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES,
    STANDARD_NATIVE_PROFILE_REVISION_DIGESTS,
    STANDARD_NATIVE_STAGE_KEYS,
    compile_standard_native_run_plan,
    standard_native_pipeline_definition_v1,
)

_ROOT = Path(__file__).parents[2]
_RELEASE = "1" * 40


def test_standard_native_pipeline_definition_is_pure_promotable_authority() -> None:
    graph_digest = canonical_digest({"graph": "native"})
    configuration_digest = canonical_digest({"configuration": "native"})

    first = standard_native_pipeline_definition_v1(
        executable_git_sha=_RELEASE,
        graph_digest=graph_digest,
        configuration_digest=configuration_digest,
    )
    second = standard_native_pipeline_definition_v1(
        executable_git_sha=_RELEASE,
        graph_digest=graph_digest,
        configuration_digest=configuration_digest,
    )

    assert first == second
    assert first.lane.value == "standard"
    assert first.product_namespace == "standard"
    assert first.automatic_eligible is True
    assert first.promotion_allowed is True


@dataclass(frozen=True)
class _Value:
    value: str


@dataclass(frozen=True)
class _Settings:
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    bandwidth_hz: int
    center_frequency_hz: int


class _Timing:
    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"schema_version": 1, "first": 1, "last": 2}


def _manifest(
    profile_name: str,
    *,
    radio_count: int = 2,
    requested_centers_hz: tuple[int, ...] | None = None,
) -> RecordingManifestV3:
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")
    rate = revision.profile.sample_rate_hz
    logical_count = rate * 60
    centers = requested_centers_hz or (revision.profile.center_frequency_hz,) * radio_count
    assert len(centers) == radio_count
    streams = tuple(
        SimpleNamespace(
            stream_id=f"stream-{index}",
            radio=SimpleNamespace(
                radio_id=f"radio-{index}",
                serial=f"serial-{index}",
                uri=f"ip:radio-{index}",
                transport=_Value("ethernet"),
            ),
            applied_settings=_Settings(
                (0, 1),
                rate,
                revision.profile.bandwidth_hz,
                centers[index],
            ),
            requested_settings=_Settings(
                (0, 1),
                rate,
                revision.profile.bandwidth_hz,
                centers[index],
            ),
            requested_sample_count=logical_count,
            logical_sample_count=logical_count,
            observed_sample_count=logical_count,
            timing=_Timing(),
            state=_Value("complete"),
        )
        for index in range(radio_count)
    )
    return RecordingManifestV3.model_construct(
        session_id="native-session",
        state=CaptureState.COMMITTED,
        source_type=SourceType.LIVE,
        streams=streams,
        tags=revision.profile.tags,
        capture_plan=SimpleNamespace(
            profile_revision=revision,
            resolved_sample_count=logical_count,
        ),
    )


@pytest.mark.parametrize(
    "profile_name",
    tuple(STANDARD_NATIVE_PROFILE_REVISION_DIGESTS),
)
def test_native_topology_accepts_only_reviewed_profile_capabilities(profile_name: str) -> None:
    manifest = _manifest(profile_name)
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": profile_name}),
        pipeline_release_id=_RELEASE,
    )
    assert len(plan.jobs) == 16
    assert len(plan.edges) == 15
    assert {job.stage_key for job in plan.jobs} == set(STANDARD_NATIVE_STAGE_KEYS) - {
        "paired-pss-glrt-presentation-native"
    }
    assert sum(job.stage_key == "path-standard-native" for job in plan.jobs) == 4
    assert all(
        job.iq_access.value == "none"
        for job in plan.jobs
        if job.stage_key not in {"path-standard-native", "path-pss-native"}
    )


def test_native_topology_rejects_expired_manifest_schema() -> None:
    with pytest.raises(ValueError, match="recording schema 3, 5, or 6"):
        compile_standard_native_run_plan(
            SimpleNamespace(schema_version=4),  # type: ignore[arg-type]
            manifest_digest=canonical_digest({"manifest": "expired-v4"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_is_disjoint_from_frozen_standard_stage_ids() -> None:
    plan = compile_standard_native_run_plan(
        _manifest("starlink-ch4-lower-3m-60s-device-axis-v3"),
        manifest_digest=canonical_digest({"manifest": "native"}),
        pipeline_release_id=_RELEASE,
    )

    assert not {
        "path-standard",
        "path-alternate-tracks",
        "radio-scientific-report",
        "paired-scientific-report",
        "paired-presentation",
    }.intersection(job.stage_key for job in plan.jobs)


def test_native_topology_accepts_two_radio_random_tuning_centers() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-5m-60s-device-axis-v3",
        requested_centers_hz=(10_700_000_000, 11_200_000_000),
    )

    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": "random-centers"}),
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 16


@pytest.mark.parametrize(
    ("profile_name", "expected_rate_hz"),
    (
        ("starlink-ch4-lower-2p5m-60s-native-bandwidth-v4", 2_500_000),
        ("starlink-ch4-lower-3m-60s-native-bandwidth-v4", 3_000_000),
        ("starlink-ch4-lower-5m-60s-native-bandwidth-v4", 5_000_000),
        ("starlink-ch4-lower-10m-60s-native-bandwidth-v4", 10_000_000),
    ),
)
def test_native_topology_admits_exact_maximum_bandwidth_profiles(
    profile_name: str,
    expected_rate_hz: int,
) -> None:
    manifest = _manifest(profile_name)
    profile = manifest.capture_plan.profile_revision.profile

    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": profile_name}),
        pipeline_release_id=_RELEASE,
    )

    assert profile.sample_rate_hz == profile.bandwidth_hz == expected_rate_hz
    assert profile.refill_samples == 1_048_576
    assert profile.kernel_buffers == 4
    assert len(plan.jobs) == 16


@pytest.mark.parametrize(
    ("rate_hz", "receiver_id"),
    tuple(
        (rate_hz, receiver_id)
        for rate_hz in (10_000_000, 15_000_000, 20_000_000)
        for receiver_id in (0, 1)
    ),
)
def test_production_ddr_ring_profiles_have_exact_reviewed_identity(
    rate_hz: int,
    receiver_id: int,
) -> None:
    profile_name = f"starlink-ch4-lower-{rate_hz // 1_000_000}m-60s-rx{receiver_id}-ddr-ring-v6"
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")

    assert STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES[profile_name] == (
        rate_hz,
        (receiver_id,),
        revision.revision_digest,
        revision.profile.refill_samples,
    )
    assert revision.profile.refill_samples == 1_000_000


@pytest.mark.parametrize("rate_hz", (10_000_000, 15_000_000, 20_000_000, 25_000_000))
@pytest.mark.parametrize("receiver_id", (0, 1))
def test_ram_drop_profiles_have_exact_standard_native_identity(
    rate_hz: int,
    receiver_id: int,
) -> None:
    profile_name = (
        f"starlink-ch4-lower-{rate_hz // 1_000_000}m-60s-rx{receiver_id}-direct-async-ram-drop-v9"
    )
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")

    assert STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES[profile_name] == (
        rate_hz,
        (receiver_id,),
        revision.revision_digest,
    )
    assert revision.profile.kernel_buffers == 12
    assert "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2" in revision.profile.tags


@pytest.mark.parametrize("rate_hz", (10_000_000, 15_000_000, 20_000_000, 25_000_000))
@pytest.mark.parametrize("receiver_id", (0, 1))
def test_qualified_ram_drop_profiles_have_exact_standard_native_identity(
    rate_hz: int,
    receiver_id: int,
) -> None:
    profile_name = (
        f"starlink-ch4-lower-{rate_hz // 1_000_000}m-60s-rx{receiver_id}-direct-async-ram-drop-v10"
    )
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")

    assert STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES[profile_name] == (
        rate_hz,
        (receiver_id,),
        revision.revision_digest,
    )
    assert revision.profile.kernel_buffers == 11
    assert "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3" in revision.profile.tags


@pytest.mark.parametrize("rate_hz", (20_000_000, 25_000_000))
@pytest.mark.parametrize("receiver_id", (0, 1))
def test_bounded_ram_drop_profiles_have_exact_standard_native_identity(
    rate_hz: int,
    receiver_id: int,
) -> None:
    profile_name = (
        f"starlink-ch4-lower-{rate_hz // 1_000_000}m-60s-rx{receiver_id}-direct-async-ram-drop-v11"
    )
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")

    assert STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES[profile_name] == (
        rate_hz,
        (receiver_id,),
        revision.revision_digest,
    )
    assert revision.profile.kernel_buffers == 11
    assert "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4" in revision.profile.tags


@pytest.mark.parametrize("rate_hz", (10_000_000, 15_000_000, 20_000_000, 25_000_000))
@pytest.mark.parametrize("receiver_id", (0, 1))
def test_exact_dma_drop_profiles_have_exact_standard_native_identity(
    rate_hz: int,
    receiver_id: int,
) -> None:
    profile_name = (
        f"starlink-ch4-lower-{rate_hz // 1_000_000}m-60s-rx{receiver_id}-"
        "direct-async-exact-dma-drop-v12"
    )
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")

    assert STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES[profile_name] == (
        rate_hz,
        (receiver_id,),
        revision.revision_digest,
    )
    assert revision.profile.refill_samples == 1_000_000
    assert revision.profile.kernel_buffers == 50
    assert "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5" in revision.profile.tags


def test_native_topology_rejects_nonoptimal_wideband_center_even_with_matching_readback() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-10m-60s-native-bandwidth-v4",
        requested_centers_hz=(1_709_687_500, 1_709_687_500),
    )

    with pytest.raises(ValueError, match="does not maximize in-channel coverage"):
        compile_standard_native_run_plan(
            manifest,
            manifest_digest=canonical_digest({"manifest": "shifted-wideband"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_accepts_bounded_applied_center_quantization() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-3m-60s-device-axis-v3",
        requested_centers_hz=(10_700_000_000, 11_200_000_000),
    )
    stream = manifest.streams[1]
    retargeted = SimpleNamespace(
        **{
            **vars(stream),
            "applied_settings": _Settings(
                receiver_ids=(0, 1),
                sample_rate_hz=3_000_000,
                bandwidth_hz=stream.requested_settings.bandwidth_hz,
                center_frequency_hz=stream.requested_settings.center_frequency_hz - 2,
            ),
        }
    )
    quantized = manifest.model_copy(update={"streams": (manifest.streams[0], retargeted)})

    plan = compile_standard_native_run_plan(
        quantized,
        manifest_digest=canonical_digest({"manifest": "quantized"}),
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 16


def test_native_topology_rejects_applied_center_retarget() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-3m-60s-device-axis-v3",
        requested_centers_hz=(10_700_000_000, 11_200_000_000),
    )
    stream = manifest.streams[1]
    retargeted = SimpleNamespace(
        **{
            **vars(stream),
            "applied_settings": _Settings(
                receiver_ids=(0, 1),
                sample_rate_hz=3_000_000,
                bandwidth_hz=stream.requested_settings.bandwidth_hz,
                center_frequency_hz=stream.requested_settings.center_frequency_hz + 20_000,
            ),
        }
    )
    foreign = manifest.model_copy(update={"streams": (manifest.streams[0], retargeted)})

    with pytest.raises(ValueError, match="stream geometry"):
        compile_standard_native_run_plan(
            foreign,
            manifest_digest=canonical_digest({"manifest": "retargeted"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_profile_revision_substitution() -> None:
    manifest = _manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    revision = manifest.capture_plan.profile_revision.model_copy(
        update={"revision_digest": canonical_digest({"foreign": "profile"})}
    )
    foreign = manifest.model_copy(
        update={"capture_plan": SimpleNamespace(profile_revision=revision)}
    )

    with pytest.raises(ValueError, match="profile identity"):
        compile_standard_native_run_plan(
            foreign,
            manifest_digest=canonical_digest({"manifest": "foreign"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_unreviewed_manifest_schema() -> None:
    with pytest.raises(ValueError, match="recording schema 3, 5, or 6"):
        compile_standard_native_run_plan(
            SimpleNamespace(schema_version=1),  # type: ignore[arg-type]
            manifest_digest=canonical_digest({"manifest": "old"}),
            pipeline_release_id=_RELEASE,
        )
