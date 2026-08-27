from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CapturePlanV2
from leo.contracts.recording import (
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingStreamV2,
)
from leo.contracts.states import CaptureState, SourceType, StarlinkEdge
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.pipeline.standard_native import (
    STANDARD_NATIVE_MIXED_PROFILE_NAMES,
    STANDARD_NATIVE_PROFILE_REVISION_DIGESTS,
    STANDARD_NATIVE_STAGE_KEYS,
    STANDARD_NATIVE_V2_PROFILE_ADMISSIONS,
    compile_standard_native_run_plan,
    compile_standard_native_scope_inventory,
    standard_native_pipeline_definition_v1,
)
from leo.pipeline.topology import compile_scope_inventory
from tests.rate_analysis_examples import rate_manifest

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


def _reviewed_v2_manifest(sample_rate_hz: int) -> RecordingManifestV2:
    source = rate_manifest(
        sample_rate_hz if sample_rate_hz in {3_000_000, 5_000_000} else 3_000_000
    )
    profile_by_rate = {
        2_500_000: "starlink-ch4-lower-2p5m-60s-continuity-v2",
        3_000_000: "starlink-ch4-lower-3m-60s-capture-v2",
        5_000_000: "starlink-ch4-lower-5m-60s-segmented-v2",
    }
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_by_rate[sample_rate_hz]}.yaml")
    profile = revision.profile
    plan = compile_capture_plan(
        revision,
        source.capture_plan.radio_ids,
        source_type=SourceType.LIVE,
    )
    assert isinstance(plan, CapturePlanV2)
    expected_count = sample_rate_hz * 60
    streams: list[RecordingStreamV2] = []
    for old in source.streams:
        requested = old.requested_settings.model_copy(
            update={
                "sample_rate_hz": sample_rate_hz,
                "bandwidth_hz": profile.bandwidth_hz,
            }
        )
        applied = requested
        missing = old.continuity.missing_sample_count if sample_rate_hz == 5_000_000 else 0
        observed = expected_count - missing
        chunks = []
        sample_cursor = 0
        for index, old_chunk in enumerate(old.chunks if missing else old.chunks[:1]):
            sample_count = observed - sample_cursor if index else min(observed, 100)
            if not missing:
                sample_count = observed
            chunks.append(
                old_chunk.model_copy(
                    update={
                        "sample_start": sample_cursor,
                        "sample_count": sample_count,
                        "uncompressed_bytes": sample_count * 8,
                    }
                )
            )
            sample_cursor += sample_count
        continuity = old.continuity.model_copy(
            update={
                "refill_count": len(chunks),
                "segment_count": len(chunks),
                "gap_count": int(missing > 0),
                "missing_sample_count": missing,
                "first_source_sequence": 0,
                "last_source_sequence": len(chunks) - 1,
                "first_device_sample_counter": 0,
                "last_device_sample_counter": expected_count - 1,
                "observed_sample_count": observed,
                "device_span_sample_count": expected_count,
            }
        )
        streams.append(
            RecordingStreamV2.model_validate(
                {
                    **old.model_dump(mode="json"),
                    "requested_settings": requested.model_dump(mode="json"),
                    "applied_settings": applied.model_dump(mode="json"),
                    "requested_sample_count": expected_count,
                    "captured_sample_count": observed,
                    "chunks": [item.model_dump(mode="json") for item in chunks],
                    "continuity": continuity.model_dump(mode="json"),
                }
            )
        )
    runtime_tags = set(source.tags) - set(source.capture_plan.profile_revision.profile.tags)
    return RecordingManifestV2.model_validate(
        {
            **source.model_dump(mode="json"),
            "session_id": f"historical-v2-{sample_rate_hz}",
            "capture_plan": plan.model_dump(mode="json"),
            "tags": sorted((*profile.tags, *runtime_tags)),
            "streams": [stream.model_dump(mode="json") for stream in streams],
        }
    )


def _mixed_manifest(
    dwell_class: ProductionDwellClass = ProductionDwellClass.MIXED_2P5_5,
) -> RecordingManifestV4:
    high_rate_hz = {
        ProductionDwellClass.MIXED_2P5_5: 5_000_000,
        ProductionDwellClass.MIXED_2P5_10: 10_000_000,
        ProductionDwellClass.MIXED_2P5_15: 15_000_000,
    }[dwell_class]
    rates = (2_500_000, high_rate_hz)
    revisions = tuple(
        load_profile_revision(
            _ROOT
            / "profiles"
            / (
                f"{STANDARD_NATIVE_MIXED_PROFILE_NAMES[rate]}.yaml"
                if rate in STANDARD_NATIVE_MIXED_PROFILE_NAMES
                else "starlink-ch4-lower-15m-60s-mixed-device-axis-v4.yaml"
            )
        )
        for rate in rates
    )
    radio_plans = tuple(
        SimpleNamespace(
            radio_id=f"radio-{index}",
            profile_revision=revision,
            resolved_sample_count=rate * 60,
            requested_settings=_Settings(
                (0, 1),
                rate,
                revision.profile.bandwidth_hz,
                revision.profile.center_frequency_hz,
            ),
        )
        for index, (rate, revision) in enumerate(zip(rates, revisions, strict=True))
    )
    streams = tuple(
        SimpleNamespace(
            stream_id=f"stream-{index}",
            radio=SimpleNamespace(
                radio_id=leg.radio_id,
                serial=f"serial-{index}",
                uri=f"ip:radio-{index}",
                transport=_Value("ethernet"),
            ),
            applied_settings=leg.requested_settings,
            requested_settings=leg.requested_settings,
            requested_sample_count=leg.resolved_sample_count,
            logical_sample_count=leg.resolved_sample_count,
            observed_sample_count=leg.resolved_sample_count,
            timing=_Timing(),
            state=_Value("complete"),
        )
        for index, leg in enumerate(radio_plans)
    )
    plan = SimpleNamespace(
        dwell_class=dwell_class,
        radio_plans=radio_plans,
        duration_seconds=revisions[0].profile.duration_seconds,
        starlink_channel=4,
        starlink_edge=StarlinkEdge.LOWER,
    )
    return RecordingManifestV4.model_construct(
        session_id="mixed-native-session",
        state=CaptureState.COMMITTED,
        source_type=SourceType.LIVE,
        streams=streams,
        tags=tuple(sorted({tag for revision in revisions for tag in revision.profile.tags})),
        capture_plan=plan,
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
    assert len(plan.jobs) == 12
    assert len(plan.edges) == 15
    assert {job.stage_key for job in plan.jobs} == set(STANDARD_NATIVE_STAGE_KEYS)
    assert sum(job.stage_key == "path-standard-native" for job in plan.jobs) == 4
    assert all(
        job.iq_access.value == "none"
        for job in plan.jobs
        if job.stage_key != "path-standard-native"
    )


@pytest.mark.parametrize(
    "dwell_class",
    (ProductionDwellClass.MIXED_2P5_5, ProductionDwellClass.MIXED_2P5_10),
)
def test_native_topology_accepts_reviewed_mixed_without_resampling(
    dwell_class: ProductionDwellClass,
) -> None:
    manifest = _mixed_manifest(dwell_class)

    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": dwell_class.value}),
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 12
    assert len(plan.edges) == 15
    assert sum(job.stage_key == "path-standard-native" for job in plan.jobs) == 4
    topology = compile_standard_native_scope_inventory(manifest)
    assert topology.paired is not None


def test_native_topology_rejects_unqualified_mixed_2p5_15() -> None:
    with pytest.raises(ValueError, match="2.5/15 remains disabled"):
        compile_standard_native_run_plan(
            _mixed_manifest(ProductionDwellClass.MIXED_2P5_15),
            manifest_digest=canonical_digest({"manifest": "mixed-2p5-15"}),
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

    assert len(plan.jobs) == 12


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
    assert profile.refill_samples == 4_194_304
    assert profile.kernel_buffers == 4
    assert len(plan.jobs) == 12


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


def test_historical_v2_native_admission_table_is_closed_and_exact() -> None:
    assert {
        name: (
            admission.revision_digest,
            admission.sample_rate_hz,
            admission.expected_sample_count,
            admission.counter_gaps_allowed,
        )
        for name, admission in STANDARD_NATIVE_V2_PROFILE_ADMISSIONS.items()
    } == {
        "starlink-ch4-lower-2p5m-60s-continuity-v2": (
            "sha256:8b4b47a1c5abcc5cb8b5bb41796fd08a6221a862aceb7139c5cd43819e79820f",
            2_500_000,
            150_000_000,
            True,
        ),
        "starlink-ch4-lower-3m-60s-capture-v2": (
            "sha256:6dbcb80f92b605a20564bac17001ae6ce394e5961fda2d11c808cdff8a81a652",
            3_000_000,
            180_000_000,
            False,
        ),
        "starlink-ch4-lower-5m-60s-segmented-v2": (
            "sha256:52a5fa028ae3d5975188e2221e7f00af850366ede0903645d952ba6ad4636640",
            5_000_000,
            300_000_000,
            True,
        ),
    }


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_native_topology_admits_only_exact_reviewed_historical_v2_profiles(
    sample_rate_hz: int,
) -> None:
    manifest = _reviewed_v2_manifest(sample_rate_hz)

    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": sample_rate_hz}),
        pipeline_release_id=_RELEASE,
    )

    admission = STANDARD_NATIVE_V2_PROFILE_ADMISSIONS[
        manifest.capture_plan.profile_revision.profile.name
    ]
    assert admission.revision_digest == manifest.capture_plan.profile_revision.revision_digest
    assert admission.sample_rate_hz == sample_rate_hz
    assert len(plan.jobs) == 12
    assert {job.stage_key for job in plan.jobs} == set(STANDARD_NATIVE_STAGE_KEYS)


def test_historical_v2_native_keeps_frozen_synchronization_inventory_identity() -> None:
    manifest = _reviewed_v2_manifest(5_000_000)

    assert compile_standard_native_scope_inventory(manifest) == compile_scope_inventory(manifest)


def test_native_topology_rejects_historical_v2_profile_substitution() -> None:
    manifest = _reviewed_v2_manifest(3_000_000)
    revision = manifest.capture_plan.profile_revision.model_copy(
        update={"revision_digest": canonical_digest({"foreign": "historical-v2"})}
    )
    foreign = manifest.model_copy(
        update={
            "capture_plan": manifest.capture_plan.model_copy(update={"profile_revision": revision})
        }
    )

    with pytest.raises(ValueError, match="profile identity"):
        compile_standard_native_run_plan(
            foreign,
            manifest_digest=canonical_digest({"manifest": "foreign-v2"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_gapped_historical_three_m_profile() -> None:
    manifest = _reviewed_v2_manifest(3_000_000)
    stream = manifest.streams[0]
    continuity = stream.continuity.model_copy(
        update={
            "refill_count": 2,
            "segment_count": 2,
            "gap_count": 1,
            "missing_sample_count": 1,
            "last_source_sequence": 1,
            "observed_sample_count": stream.captured_sample_count - 1,
        }
    )
    gapped = stream.model_copy(
        update={
            "state": _Value("partial"),
            "captured_sample_count": stream.captured_sample_count - 1,
            "continuity": continuity,
            "error": "counter gap",
        }
    )
    degraded = manifest.model_copy(
        update={"state": _Value("degraded"), "streams": (gapped, manifest.streams[1])}
    )

    with pytest.raises(ValueError, match="does not permit gaps"):
        compile_standard_native_run_plan(
            degraded,
            manifest_digest=canonical_digest({"manifest": "gapped-3m-v2"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_historical_v2_unproven_counter_endpoint() -> None:
    manifest = _reviewed_v2_manifest(2_500_000)
    stream = manifest.streams[0]
    continuity = stream.continuity.model_copy(
        update={"last_device_sample_counter": stream.continuity.last_device_sample_counter - 1}
    )
    truncated = manifest.model_copy(
        update={
            "streams": (stream.model_copy(update={"continuity": continuity}), manifest.streams[1])
        }
    )

    with pytest.raises(ValueError, match="complete counter-proven span"):
        compile_standard_native_run_plan(
            truncated,
            manifest_digest=canonical_digest({"manifest": "unproven-counter-v2"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_historical_v2_applied_tuning_retarget() -> None:
    manifest = _reviewed_v2_manifest(5_000_000)
    stream = manifest.streams[0]
    assert stream.applied_settings is not None
    retargeted_settings = stream.applied_settings.model_copy(
        update={"center_frequency_hz": stream.requested_settings.center_frequency_hz + 10_000}
    )
    retargeted = manifest.model_copy(
        update={
            "streams": (
                stream.model_copy(update={"applied_settings": retargeted_settings}),
                manifest.streams[1],
            )
        }
    )

    with pytest.raises(ValueError, match="applied center exceeds tolerance"):
        compile_standard_native_run_plan(
            retargeted,
            manifest_digest=canonical_digest({"manifest": "retargeted-v2"}),
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

    assert len(plan.jobs) == 12


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
    with pytest.raises(ValueError, match="reviewed V2, V3, or V4"):
        compile_standard_native_run_plan(
            SimpleNamespace(session_id="old", streams=()),  # type: ignore[arg-type]
            manifest_digest=canonical_digest({"manifest": "old"}),
            pipeline_release_id=_RELEASE,
        )
