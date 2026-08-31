"""Additive manifest-authoritative topology for Standard-native-v1."""

from __future__ import annotations

from dataclasses import dataclass

from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClass,
    ProductionDwellClassV2,
    ProductionDwellClassV3,
)
from leo.contracts.pipeline_lanes import PipelineDefinitionV1, PipelineLane
from leo.contracts.recording import (
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingManifestV5,
    RecordingManifestV6,
)
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.contracts.starlink_frequency import (
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import CaptureState, GainMode, SourceType, StarlinkEdge, StreamState
from leo.pipeline.contracts import ResourceClass
from leo.pipeline.planning import ExpandedRunPlanV1, IqAccess, JobDependencyRefV1, JobNodeV1
from leo.pipeline.scopes import ScopeIdentityV1
from leo.pipeline.topology import CompiledScopeInventory, compile_scope_inventory

STANDARD_NATIVE_SAMPLE_RATES_HZ = (
    2_500_000,
    3_000_000,
    5_000_000,
    10_000_000,
    15_000_000,
    20_000_000,
    25_000_000,
)
STANDARD_NATIVE_PROFILE_RATE_HZ = {
    "starlink-ch4-lower-2p5m-60s-device-axis-v3": 2_500_000,
    "starlink-ch4-lower-3m-60s-device-axis-v3": 3_000_000,
    "starlink-ch4-lower-5m-60s-device-axis-v3": 5_000_000,
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": 2_500_000,
    "starlink-ch4-lower-3m-60s-native-bandwidth-v4": 3_000_000,
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": 5_000_000,
    "starlink-ch4-lower-10m-60s-native-bandwidth-v4": 10_000_000,
}
STANDARD_NATIVE_PROFILE_REVISION_DIGESTS = {
    "starlink-ch4-lower-2p5m-60s-device-axis-v3": (
        "sha256:b30f80c13c8003ebf57f5530bcca73e3928102597f8fb6342618f4820ab91101"
    ),
    "starlink-ch4-lower-3m-60s-device-axis-v3": (
        "sha256:4533ac4a3348721e0bf7bda50c5701f505e47ef579ef9a47cbc7c38b9c9b4c3e"
    ),
    "starlink-ch4-lower-5m-60s-device-axis-v3": (
        "sha256:8851c20e4c6e79bc5d4cb92f8fd0e09eaf24e59b742239b92bc248fd4d09ba5d"
    ),
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": (
        "sha256:140d4f834fd27b94754ea9017f2be45da21af2662dfef8ec97c4487fbf15bc89"
    ),
    "starlink-ch4-lower-3m-60s-native-bandwidth-v4": (
        "sha256:523402d005564d97177ee139f1a616c01b6b65d9a6c4ad11a0564c074216865c"
    ),
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": (
        "sha256:6f8ec4a5dec0f6b18d09c0f464c22c143ac363f2088242db830b0757a6316294"
    ),
    "starlink-ch4-lower-10m-60s-native-bandwidth-v4": (
        "sha256:3b4a970db3c891f4327a2c5713e5deaf1161429d5a9ce5c2f0d597e7808205ce"
    ),
}
STANDARD_NATIVE_MIXED_PROFILE_REVISION_DIGESTS = {
    2_500_000: "sha256:e5f088ba153a893eb5f5324c6c411ebe189acc9de5bfa68211a841edc9bbdb44",
    5_000_000: "sha256:e5d593c1711ddb65be6adeb2f3fe620afe99948aed2881dabc142b5737e81afc",
    10_000_000: "sha256:c3062bf57769d14682206855c8d4b8ec011aa1a005e411252ea4234291216d63",
}
STANDARD_NATIVE_MIXED_REFILL_SAMPLES = 1_048_576
STANDARD_NATIVE_MIXED_KERNEL_BUFFERS = 4
STANDARD_NATIVE_MIXED_QUEUE_CAPACITY = 32
STANDARD_NATIVE_MIXED_PROFILE_NAMES = {
    2_500_000: "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
    5_000_000: "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
    10_000_000: "starlink-ch4-lower-10m-60s-mixed-device-axis-v4",
}
STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES = {
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": (
        2_500_000,
        (0, 1),
        "sha256:140d4f834fd27b94754ea9017f2be45da21af2662dfef8ec97c4487fbf15bc89",
        1_048_576,
    ),
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": (
        5_000_000,
        (0, 1),
        "sha256:6f8ec4a5dec0f6b18d09c0f464c22c143ac363f2088242db830b0757a6316294",
        1_048_576,
    ),
    "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4": (
        2_500_000,
        (0, 1),
        "sha256:e5f088ba153a893eb5f5324c6c411ebe189acc9de5bfa68211a841edc9bbdb44",
        1_048_576,
    ),
    "starlink-ch4-lower-5m-60s-mixed-device-axis-v4": (
        5_000_000,
        (0, 1),
        "sha256:e5d593c1711ddb65be6adeb2f3fe620afe99948aed2881dabc142b5737e81afc",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx0-production-v5": (
        10_000_000,
        (0,),
        "sha256:5f58b6a4afaf77649f389eaf2e167af53d61e851ca294c5d7622b495fa24bf0e",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx1-production-v5": (
        10_000_000,
        (1,),
        "sha256:446a7d5637f3e1bc8a8fe62ecb8f7b4ad6eeac2ece367d9e022ae0b4cc12ba1f",
        1_048_576,
    ),
    "starlink-ch4-lower-15m-60s-rx0-production-v5": (
        15_000_000,
        (0,),
        "sha256:9336da0d5cc00d006a80e35180812d7ad8cf09ca7f590f0b03b7786b259583ba",
        1_048_576,
    ),
    "starlink-ch4-lower-15m-60s-rx1-production-v5": (
        15_000_000,
        (1,),
        "sha256:b69997f7ad37b484d22dd21dab95c31ea74af67e7909142a21c94cbf1df174e8",
        1_048_576,
    ),
    "starlink-ch4-lower-20m-60s-rx0-production-v5": (
        20_000_000,
        (0,),
        "sha256:9c9b4e34515f536bcb01751650a7e8c396d2f03f4ae979f6451f6b9d9fe1f0a1",
        1_048_576,
    ),
    "starlink-ch4-lower-20m-60s-rx1-production-v5": (
        20_000_000,
        (1,),
        "sha256:5fad84a88fe487a812598fd3de2697aef443ee14b8b64eefc253256dd9006410",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx0-ddr-ring-v6": (
        10_000_000,
        (0,),
        "sha256:4c9fcc3fe27af3a6f9341c0ac42beb9f6e135731541114f9a7cb15b95d9e71f4",
        1_000_000,
    ),
    "starlink-ch4-lower-10m-60s-rx1-ddr-ring-v6": (
        10_000_000,
        (1,),
        "sha256:9fce2e136b1f1e002282520d7ce4f2df60afd9e2dcff8db0586a388b976f0b43",
        1_000_000,
    ),
    "starlink-ch4-lower-15m-60s-rx0-ddr-ring-v6": (
        15_000_000,
        (0,),
        "sha256:2dab9044d0b11f4f3af57882e90d248bbafcda684a68182f00fef686aa58cb63",
        1_000_000,
    ),
    "starlink-ch4-lower-15m-60s-rx1-ddr-ring-v6": (
        15_000_000,
        (1,),
        "sha256:17335b014966a45505d46e94bb754ce13f11f52498fa0a2ddfabed07f41ec320",
        1_000_000,
    ),
    "starlink-ch4-lower-20m-60s-rx0-ddr-ring-v6": (
        20_000_000,
        (0,),
        "sha256:3131e4776d9dd6bc9a986adbdce35d6cb431dcfb31178fff1ef9aa285c11cc5a",
        1_000_000,
    ),
    "starlink-ch4-lower-20m-60s-rx1-ddr-ring-v6": (
        20_000_000,
        (1,),
        "sha256:baf767d6a04a183283b606874042138969939d3064e7840b773b1394be7df88a",
        1_000_000,
    ),
}
STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES = {
    "starlink-ch4-lower-10m-60s-rx0-direct-async-v7": (
        10_000_000,
        (0,),
        "sha256:22172543ea6139b98eed978a2c994f8384932a2f88dc3135e6ef7e560074aa59",
    ),
    "starlink-ch4-lower-10m-60s-rx1-direct-async-v7": (
        10_000_000,
        (1,),
        "sha256:34dd3ea083b62305ecdbc8a9a3563b91bef0e0d37cf598e4168a9217098cef83",
    ),
    "starlink-ch4-lower-15m-60s-rx0-direct-async-v7": (
        15_000_000,
        (0,),
        "sha256:7786970fe19bc5f75da2f3bf61219716d306fe69d3e3403b89fa080b2eb07bfd",
    ),
    "starlink-ch4-lower-15m-60s-rx1-direct-async-v7": (
        15_000_000,
        (1,),
        "sha256:cdb3734d0bdab0e741e9d855998ee6c5c735fbc1d4b7034b5b4e81340ad33cc2",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-v7": (
        25_000_000,
        (0,),
        "sha256:17794a88d89b35149fe6976b1de8344b5c58d0e52393c69e027d6759b9ee369e",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-v7": (
        25_000_000,
        (1,),
        "sha256:6675fbf3d6e6899a2c0fec29b078181a7f843df1cb8941906ab11ac3c7f7adb9",
    ),
}


@dataclass(frozen=True, slots=True)
class HistoricalV2NativeAdmission:
    """One exact packed-IQ profile admitted only to manual native evidence."""

    revision_digest: str
    sample_rate_hz: int
    expected_sample_count: int
    counter_gaps_allowed: bool


STANDARD_NATIVE_V2_PROFILE_ADMISSIONS = {
    "starlink-ch4-lower-2p5m-60s-continuity-v2": HistoricalV2NativeAdmission(
        revision_digest=("sha256:8b4b47a1c5abcc5cb8b5bb41796fd08a6221a862aceb7139c5cd43819e79820f"),
        sample_rate_hz=2_500_000,
        expected_sample_count=150_000_000,
        counter_gaps_allowed=True,
    ),
    "starlink-ch4-lower-3m-60s-capture-v2": HistoricalV2NativeAdmission(
        revision_digest=("sha256:6dbcb80f92b605a20564bac17001ae6ce394e5961fda2d11c808cdff8a81a652"),
        sample_rate_hz=3_000_000,
        expected_sample_count=180_000_000,
        counter_gaps_allowed=False,
    ),
    "starlink-ch4-lower-5m-60s-segmented-v2": HistoricalV2NativeAdmission(
        revision_digest=("sha256:52a5fa028ae3d5975188e2221e7f00af850366ede0903645d952ba6ad4636640"),
        sample_rate_hz=5_000_000,
        expected_sample_count=300_000_000,
        counter_gaps_allowed=True,
    ),
}
STANDARD_NATIVE_STAGE_KEYS = (
    "path-standard-native",
    "path-alternate-tracks-native",
    "radio-scientific-report-native",
    "paired-scientific-report-native",
    "paired-presentation-native",
)


def standard_native_pipeline_definition_v1(
    *,
    executable_git_sha: str,
    graph_digest: str,
    configuration_digest: str,
) -> PipelineDefinitionV1:
    """Build the pure promotable definition for the reviewed native graph.

    The release authority supplies the immutable executable, graph, and
    configuration identities.  The expanded run plan independently binds the
    manifest-derived topology for one capture.
    """

    values = {
        "schema_version": 1,
        "lane": PipelineLane.STANDARD,
        "executable_git_sha": executable_git_sha,
        "graph_digest": graph_digest,
        "configuration_digest": configuration_digest,
        "product_namespace": "standard",
        "automatic_eligible": True,
        "promotion_allowed": True,
    }
    return PipelineDefinitionV1(
        lane=PipelineLane.STANDARD,
        executable_git_sha=executable_git_sha,
        graph_digest=graph_digest,
        configuration_digest=configuration_digest,
        product_namespace="standard",
        automatic_eligible=True,
        promotion_allowed=True,
        definition_id=canonical_digest(values),
    )


def compile_standard_native_run_plan(
    manifest: (
        RecordingManifestV2
        | RecordingManifestV3
        | RecordingManifestV4
        | RecordingManifestV5
        | RecordingManifestV6
    ),
    *,
    manifest_digest: str,
    pipeline_release_id: str,
) -> ExpandedRunPlanV1:
    """Expand the disjoint Standard-native graph without changing Standard-v2.

    This pure compiler closes reviewed native-rate/profile geometry and
    produces a stage inventory that cannot be mistaken for the frozen Standard
    graph. Promotion policy remains the run coordinator's responsibility.
    """

    _require_reviewed_native_geometry(manifest)
    topology = compile_standard_native_scope_inventory(manifest)
    jobs: list[JobNodeV1] = []
    edges: list[JobDependencyRefV1] = []
    path_terminals: dict[str, list[str]] = {}

    for path_ordinal, scope in enumerate(topology.receiver_paths):
        assert scope.stream_id is not None
        path_node_id = f"path-{path_ordinal:02d}-standard-native"
        jobs.append(
            JobNodeV1(
                node_id=path_node_id,
                stage_key="path-standard-native",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class=ResourceClass.HEAVY,
            )
        )
        alternate_node_id = f"path-{path_ordinal:02d}-alternate-tracks-native"
        jobs.append(
            JobNodeV1(
                node_id=alternate_node_id,
                stage_key="path-alternate-tracks-native",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.append(
            JobDependencyRefV1(
                job_node_id=alternate_node_id,
                depends_on_job_node_id=path_node_id,
            )
        )
        path_terminals.setdefault(scope.stream_id, []).append(path_node_id)

    radio_nodes: list[str] = []
    for radio_ordinal, scope in enumerate(topology.radios):
        assert scope.stream_id is not None
        node_id = f"radio-{radio_ordinal:02d}-reduce-native"
        jobs.append(
            JobNodeV1(
                node_id=node_id,
                stage_key="radio-scientific-report-native",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(job_node_id=node_id, depends_on_job_node_id=dependency)
            for dependency in sorted(path_terminals[scope.stream_id])
        )
        radio_nodes.append(node_id)

    if topology.paired is not None:
        paired_node_id = "paired-00-reduce-native"
        jobs.append(
            JobNodeV1(
                node_id=paired_node_id,
                stage_key="paired-scientific-report-native",
                scope=topology.paired,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(
                job_node_id=paired_node_id,
                depends_on_job_node_id=dependency,
            )
            for dependency in sorted(radio_nodes)
        )

        presentation_node_id = "paired-00-presentation-native"
        jobs.append(
            JobNodeV1(
                node_id=presentation_node_id,
                stage_key="paired-presentation-native",
                scope=topology.paired,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        # The paired presentation consumes every sealed path plot source plus
        # the paired report's exact common-valid UTC authority.
        edges.extend(
            JobDependencyRefV1(
                job_node_id=presentation_node_id,
                depends_on_job_node_id=node.node_id,
            )
            for node in jobs
            if node.stage_key == "path-standard-native"
        )
        edges.append(
            JobDependencyRefV1(
                job_node_id=presentation_node_id,
                depends_on_job_node_id=paired_node_id,
            )
        )

    return ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        jobs=tuple(jobs),
        edges=tuple(edges),
    )


def compile_standard_native_scope_inventory(
    manifest: (
        RecordingManifestV2
        | RecordingManifestV3
        | RecordingManifestV4
        | RecordingManifestV5
        | RecordingManifestV6
    ),
) -> CompiledScopeInventory:
    """Build native scopes while preserving historical V2 synchronization identity."""

    if isinstance(manifest, RecordingManifestV2):
        return compile_scope_inventory(manifest)
    if not isinstance(
        manifest,
        (RecordingManifestV3, RecordingManifestV4, RecordingManifestV5, RecordingManifestV6),
    ):
        raise ValueError(
            "Standard-native scope inventory requires a reviewed V2, V3, or V4 recording"
        )
    ordered = tuple(
        sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id))
    )
    identities = tuple((item.stream_id, item.radio.radio_id) for item in ordered)
    if (
        len(set(identities)) != len(identities)
        or len({item.stream_id for item in ordered}) != len(ordered)
        or len({item.radio.radio_id for item in ordered}) != len(ordered)
    ):
        raise ValueError("Standard-native manifest repeats a stream/radio topology identity")
    synchronization_inventory_digest = canonical_digest(
        [
            {
                "ordinal": ordinal,
                "stream_id": stream.stream_id,
                "radio": {
                    "radio_id": stream.radio.radio_id,
                    "serial": stream.radio.serial,
                    "uri": stream.radio.uri,
                    "transport": stream.radio.transport.value,
                },
                "receiver_ids": list(stream.applied_settings.receiver_ids),
                "sample_rate_hz": stream.applied_settings.sample_rate_hz,
                "logical_sample_count": stream.logical_sample_count,
                "observed_sample_count": stream.observed_sample_count,
                "timing": stream.timing.model_dump(mode="json"),
                "state": stream.state.value,
            }
            for ordinal, stream in enumerate(ordered)
        ]
    )
    receiver_paths = tuple(
        ScopeIdentityV1.receiver_path(
            session_id=manifest.session_id,
            stream_id=stream.stream_id,
            receiver_id=receiver_id,
        )
        for stream in ordered
        for receiver_id in stream.applied_settings.receiver_ids
    )
    radios = tuple(
        ScopeIdentityV1.radio(
            session_id=manifest.session_id,
            stream_id=stream.stream_id,
            radio_id=stream.radio.radio_id,
        )
        for stream in ordered
    )
    return CompiledScopeInventory(
        receiver_paths=receiver_paths,
        radios=radios,
        paired=(
            None
            if len(ordered) != 2
            else ScopeIdentityV1.paired(
                session_id=manifest.session_id,
                synchronization_inventory_digest=synchronization_inventory_digest,
            )
        ),
        synchronization_inventory_digest=synchronization_inventory_digest,
    )


def _require_reviewed_native_geometry(
    manifest: (
        RecordingManifestV2
        | RecordingManifestV3
        | RecordingManifestV4
        | RecordingManifestV5
        | RecordingManifestV6
    ),
) -> None:
    if isinstance(manifest, RecordingManifestV2):
        _require_reviewed_historical_v2_geometry(manifest)
        return
    if type(manifest) is RecordingManifestV6:
        _require_reviewed_direct_async_v6_geometry(manifest)
        return
    if type(manifest) is RecordingManifestV5:
        _require_reviewed_production_v5_geometry(manifest)
        return
    if isinstance(manifest, RecordingManifestV4):
        _require_reviewed_mixed_v4_geometry(manifest)
        return
    if not isinstance(manifest, RecordingManifestV3):
        raise ValueError("Standard-native expanded runs require a reviewed V2, V3, or V4 recording")
    if not manifest.streams:
        raise ValueError("Standard-native requires at least one recorded stream")
    revision = manifest.capture_plan.profile_revision
    profile = revision.profile
    expected_rate = STANDARD_NATIVE_PROFILE_RATE_HZ.get(profile.name)
    expected_revision = STANDARD_NATIVE_PROFILE_REVISION_DIGESTS.get(profile.name)
    if expected_rate is None or revision.revision_digest != expected_revision:
        raise ValueError("Standard-native capture profile identity is not reviewed")
    required_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
    }
    if (
        profile.schema_version != 2
        or profile.sample_rate_hz != expected_rate
        or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
        or profile.continuity_policy.value != "allow_segments"
        or profile.peer_failure_policy.value != "fail_session"
        or not required_tags.issubset(profile.tags)
        or not required_tags.issubset(manifest.tags)
    ):
        raise ValueError("Standard-native capture profile capability is incomplete")
    if "NATIVE_BANDWIDTH" in profile.tags and (
        profile.bandwidth_hz != profile.sample_rate_hz
        or profile.refill_samples != STANDARD_NATIVE_MIXED_REFILL_SAMPLES
        or profile.kernel_buffers != STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
        or profile.refill_queue_capacity != STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
    ):
        raise ValueError("Standard-native native-bandwidth capture geometry is incomplete")
    rates = {
        (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in manifest.streams
    }
    if len(rates) != 1 or next(iter(rates)) != expected_rate:
        raise ValueError("Standard-native requires one reviewed common native sample rate")
    expected_samples = manifest.capture_plan.resolved_sample_count
    if any(
        stream.requested_sample_count != expected_samples
        or stream.logical_sample_count != expected_samples
        or stream.requested_settings.sample_rate_hz != profile.sample_rate_hz
        or stream.requested_settings.bandwidth_hz != profile.bandwidth_hz
        or stream.applied_settings.sample_rate_hz != profile.sample_rate_hz
        or stream.applied_settings.bandwidth_hz != profile.bandwidth_hz
        or abs(
            stream.applied_settings.center_frequency_hz
            - stream.requested_settings.center_frequency_hz
        )
        > max(1, round(stream.requested_settings.center_frequency_hz * 1e-6))
        for stream in manifest.streams
    ):
        raise ValueError("Standard-native stream geometry differs from the reviewed capture plan")
    if any(
        tuple((stream.applied_settings or stream.requested_settings).receiver_ids) != (0, 1)
        for stream in manifest.streams
    ):
        raise ValueError("Standard-native requires the reviewed dual-receiver geometry")
    tuning_by_stream = resolve_manifest_starlink_tuning(manifest)
    if "NATIVE_BANDWIDTH" in profile.tags:
        for stream in manifest.streams:
            tuning = tuning_by_stream[stream.stream_id]
            expected_center_hz = starlink_maximum_coverage_if_center_frequency_hz(
                tuning.channel,
                tuning.edge,
                bandwidth_hz=profile.bandwidth_hz,
            )
            if (
                stream.requested_settings.center_frequency_hz != expected_center_hz
                or stream.applied_settings.center_frequency_hz != expected_center_hz
            ):
                raise ValueError("Standard-native RF center does not maximize in-channel coverage")


def _require_reviewed_mixed_v4_geometry(manifest: RecordingManifestV4) -> None:
    """Admit only exact reviewed unequal-rate V4 capabilities."""

    plan = manifest.capture_plan
    if plan.dwell_class not in {
        ProductionDwellClass.MIXED_2P5_5,
        ProductionDwellClass.MIXED_2P5_10,
    }:
        raise ValueError("Standard-native mixed 2.5/15 remains disabled by hardware qualification")
    if manifest.source_type is not SourceType.LIVE or len(manifest.streams) != 2:
        raise ValueError("Standard-native mixed capture requires exactly two LIVE streams")
    expected_rates = {
        ProductionDwellClass.MIXED_2P5_5: {2_500_000, 5_000_000},
        ProductionDwellClass.MIXED_2P5_10: {2_500_000, 10_000_000},
    }[plan.dwell_class]
    if {item.requested_settings.sample_rate_hz for item in plan.radio_plans} != expected_rates:
        raise ValueError("Standard-native mixed capture rates disagree with the reviewed class")
    required_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "MIXED_RATE",
        "NATIVE_BANDWIDTH",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
    }
    if not required_tags.issubset(manifest.tags):
        raise ValueError("Standard-native mixed manifest capability is incomplete")

    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        profile = leg.profile_revision.profile
        rate = leg.requested_settings.sample_rate_hz
        if (
            profile.name != STANDARD_NATIVE_MIXED_PROFILE_NAMES.get(rate)
            or leg.profile_revision.revision_digest
            != STANDARD_NATIVE_MIXED_PROFILE_REVISION_DIGESTS.get(rate)
            or profile.sample_rate_hz != rate
            or profile.bandwidth_hz != rate
            or profile.duration_seconds != plan.duration_seconds
            or profile.refill_samples != STANDARD_NATIVE_MIXED_REFILL_SAMPLES
            or profile.kernel_buffers != STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
            or profile.refill_queue_capacity != STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
            or profile.peer_failure_policy.value != "fail_session"
            or tuple(profile.receivers) != (0, 1)
            or not required_tags.issubset(profile.tags)
        ):
            raise ValueError("Standard-native mixed profile identity or capability is not reviewed")
        settings = stream.applied_settings
        if (
            stream.radio.radio_id != leg.radio_id
            or stream.requested_sample_count != leg.resolved_sample_count
            or stream.logical_sample_count != leg.resolved_sample_count
            or stream.requested_settings != leg.requested_settings
            or settings.sample_rate_hz != rate
            or settings.bandwidth_hz != profile.bandwidth_hz
            or tuple(settings.receiver_ids) != (0, 1)
            or settings.center_frequency_hz != leg.requested_settings.center_frequency_hz
        ):
            raise ValueError("Standard-native mixed stream geometry differs from its plan leg")
    resolve_manifest_starlink_tuning(manifest)


def _require_reviewed_production_v5_geometry(manifest: RecordingManifestV5) -> None:
    """Admit exact V2-policy captures, including one-path high-rate radio legs."""

    plan = manifest.capture_plan
    if manifest.source_type is not SourceType.LIVE or len(manifest.streams) != 2:
        raise ValueError("Standard-native production capture requires exactly two LIVE streams")
    expected_rates = {
        ProductionDwellClassV2.BOTH_2P5: (2_500_000, 2_500_000),
        ProductionDwellClassV2.BOTH_5: (5_000_000, 5_000_000),
        ProductionDwellClassV2.MIXED_2P5_5: (2_500_000, 5_000_000),
        ProductionDwellClassV2.MIXED_2P5_10: (2_500_000, 10_000_000),
        ProductionDwellClassV2.MIXED_2P5_15: (2_500_000, 15_000_000),
        ProductionDwellClassV2.MIXED_2P5_20: (2_500_000, 20_000_000),
    }[plan.dwell_class]
    if sorted(item.requested_settings.sample_rate_hz for item in plan.radio_plans) != sorted(
        expected_rates
    ):
        raise ValueError("Standard-native production rates disagree with dwell class")
    required_manifest_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "NATIVE_BANDWIDTH",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
        "PRODUCTION_NATIVE_RATES_V2",
    }
    if not required_manifest_tags.issubset(manifest.tags):
        raise ValueError("Standard-native production manifest capability is incomplete")
    is_mixed = plan.dwell_class.value.startswith("mixed_")
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        profile = leg.profile_revision.profile
        identity = STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES.get(profile.name)
        if identity is None:
            raise ValueError("Standard-native production profile identity is not reviewed")
        expected_rate, expected_receivers, expected_digest, expected_refill_samples = identity
        rate = leg.requested_settings.sample_rate_hz
        required_receiver_count = 1 if is_mixed and rate > 5_000_000 else 2
        settings = stream.applied_settings
        if (
            leg.profile_revision.revision_digest != expected_digest
            or profile.sample_rate_hz != expected_rate
            or profile.bandwidth_hz != expected_rate
            or profile.receivers != expected_receivers
            or len(profile.receivers) != required_receiver_count
            or profile.duration_seconds != plan.duration_seconds
            or profile.refill_samples != expected_refill_samples
            or profile.kernel_buffers != STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
            or profile.refill_queue_capacity != STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
            or profile.peer_failure_policy.value != "fail_session"
            or stream.radio.radio_id != leg.radio_id
            or stream.requested_sample_count != leg.resolved_sample_count
            or stream.logical_sample_count != leg.resolved_sample_count
            or stream.requested_settings != leg.requested_settings
            or settings.sample_rate_hz != rate
            or settings.bandwidth_hz != rate
            or settings.receiver_ids != profile.receivers
            or settings.center_frequency_hz != leg.requested_settings.center_frequency_hz
            or settings.gain_mode is not GainMode.MANUAL
            or stream.continuity.metadata_abi_version != 3
            or not stream.continuity.sample_loss_observable
        ):
            raise ValueError(
                "Standard-native production profile, stream, or metadata geometry is not reviewed"
            )
    tuning = resolve_manifest_starlink_tuning(manifest)
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        resolved = tuning[stream.stream_id]
        if resolved.channel != leg.starlink_channel or resolved.edge is not leg.starlink_edge:
            raise ValueError("Standard-native production tuning tags disagree with capture plan")


def _require_reviewed_direct_async_v6_geometry(manifest: RecordingManifestV6) -> None:
    """Admit exact same-target 2.5 x 10/15/25 MS/s direct-async captures."""

    plan = manifest.capture_plan
    if manifest.source_type is not SourceType.LIVE or len(manifest.streams) != 2:
        raise ValueError("Standard-native direct-async capture requires two LIVE streams")
    high_rate = {
        ProductionDwellClassV3.MIXED_2P5_10: 10_000_000,
        ProductionDwellClassV3.MIXED_2P5_15: 15_000_000,
        ProductionDwellClassV3.MIXED_2P5_25: 25_000_000,
    }[plan.dwell_class]
    if sorted(item.requested_settings.sample_rate_hz for item in plan.radio_plans) != [
        2_500_000,
        high_rate,
    ]:
        raise ValueError("Standard-native direct-async rates disagree with dwell class")
    required_manifest_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "MIXED_RATE",
        "NATIVE_BANDWIDTH",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
        "PRODUCTION_DIRECT_ASYNC_RATES_V3",
    }
    if not required_manifest_tags.issubset(manifest.tags):
        raise ValueError("Standard-native direct-async manifest capability is incomplete")
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        profile = leg.profile_revision.profile
        rate = leg.requested_settings.sample_rate_hz
        high_leg = rate != 2_500_000
        if high_leg:
            identity = STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES.get(profile.name)
            if identity is None:
                raise ValueError("Standard-native direct-async profile identity is not reviewed")
            expected_rate, direct_receivers, expected_digest = identity
            expected_receivers: tuple[int, ...] = direct_receivers
            expected_refill_samples = 1_048_576
            expected_kernel_buffers = 15
            expected_queue_capacity = 64
            required_profile_tags = {"DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1", "SINGLE_RX"}
        else:
            production_identity = STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES.get(profile.name)
            if production_identity is None:
                raise ValueError("Standard-native 2.5 MS/s profile identity is not reviewed")
            (
                expected_rate,
                production_receivers,
                expected_digest,
                expected_refill_samples,
            ) = production_identity
            expected_receivers = production_receivers
            expected_kernel_buffers = STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
            expected_queue_capacity = STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
            required_profile_tags = set()
        settings = stream.applied_settings
        if (
            leg.profile_revision.revision_digest != expected_digest
            or profile.sample_rate_hz != expected_rate
            or profile.bandwidth_hz != expected_rate
            or profile.receivers != expected_receivers
            or len(profile.receivers) != (1 if high_leg else 2)
            or profile.duration_seconds != plan.duration_seconds
            or profile.refill_samples != expected_refill_samples
            or profile.kernel_buffers != expected_kernel_buffers
            or profile.refill_queue_capacity != expected_queue_capacity
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
            or profile.peer_failure_policy.value != "fail_session"
            or not required_profile_tags.issubset(profile.tags)
            or stream.radio.radio_id != leg.radio_id
            or stream.requested_sample_count != leg.resolved_sample_count
            or stream.logical_sample_count != leg.resolved_sample_count
            or stream.requested_settings != leg.requested_settings
            or settings.sample_rate_hz != rate
            or settings.bandwidth_hz != rate
            or settings.receiver_ids != profile.receivers
            or settings.center_frequency_hz != leg.requested_settings.center_frequency_hz
            or settings.gain_mode is not GainMode.MANUAL
            or stream.continuity.metadata_abi_version != 3
            or not stream.continuity.sample_loss_observable
        ):
            raise ValueError(
                "Standard-native direct-async profile, stream, or metadata geometry is not reviewed"
            )
    tuning = resolve_manifest_starlink_tuning(manifest)
    targets = set()
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        resolved = tuning[stream.stream_id]
        targets.add((resolved.channel, resolved.edge))
        if resolved.channel != leg.starlink_channel or resolved.edge is not leg.starlink_edge:
            raise ValueError("Standard-native direct-async tuning tags disagree with capture plan")
    if len(targets) != 1:
        raise ValueError("Standard-native direct-async capture requires one common RF target")


def _require_reviewed_historical_v2_geometry(manifest: RecordingManifestV2) -> None:
    """Admit only exact full-span counter-proven historical packed-IQ captures."""

    revision = manifest.capture_plan.profile_revision
    profile = revision.profile
    admission = STANDARD_NATIVE_V2_PROFILE_ADMISSIONS.get(profile.name)
    if admission is None or revision.revision_digest != admission.revision_digest:
        raise ValueError("Standard-native historical V2 capture profile identity is not reviewed")
    if (
        manifest.source_type is not SourceType.LIVE
        or profile.schema_version != 2
        or profile.sample_rate_hz != admission.sample_rate_hz
        or manifest.capture_plan.resolved_sample_count != admission.expected_sample_count
        or profile.storage_policy != "zstd-128m-v1"
        or profile.continuity_policy.value != "allow_segments"
        or not profile.require_device_metadata
        or tuple(profile.receivers) != (0, 1)
        or not {"LIVE", "RANDOM_TUNING"}.issubset(profile.tags)
    ):
        raise ValueError("Standard-native historical V2 profile capability is incomplete")
    if len(manifest.streams) != 2:
        raise ValueError("Standard-native historical V2 requires exactly two preserved streams")
    _require_historical_v2_runtime_settings(manifest)

    any_gaps = False
    for stream in manifest.streams:
        settings = stream.applied_settings
        continuity = stream.continuity
        missing = continuity.missing_sample_count
        any_gaps = any_gaps or bool(missing)
        if (
            settings is None
            or stream.timing is None
            or stream.timeline_relative_path is None
            or stream.timeline_sha256 is None
            or stream.gap_map_relative_path is None
            or stream.gap_map_sha256 is None
            or not stream.chunks
            or stream.requested_sample_count != admission.expected_sample_count
            or stream.captured_sample_count != continuity.observed_sample_count
            or continuity.device_span_sample_count != admission.expected_sample_count
            or continuity.observed_sample_count + missing != admission.expected_sample_count
            or not continuity.sample_loss_observable
            or continuity.first_device_sample_counter is None
            or continuity.last_device_sample_counter is None
            or continuity.last_device_sample_counter - continuity.first_device_sample_counter + 1
            != admission.expected_sample_count
            or continuity.validated_stream_generation is None
            or continuity.metadata_abi_version != 1
            or continuity.kernel_buffers != profile.kernel_buffers
            or continuity.queue_capacity_refills != profile.refill_queue_capacity
            or continuity.refill_count <= 0
            or continuity.segment_count != continuity.gap_count + 1
            or continuity.overflow_count != 0
            or continuity.enqueue_failure_count != 0
            or continuity.terminal_enqueue_failure is not None
            or continuity.terminal_rejected_gap_count != 0
            or continuity.terminal_rejected_missing_sample_count != 0
            or continuity.terminal_rejected_overflow_count != 0
            or stream.requested_settings.sample_rate_hz != admission.sample_rate_hz
            or settings.sample_rate_hz != admission.sample_rate_hz
            or settings.bandwidth_hz != profile.bandwidth_hz
            or stream.requested_settings.bandwidth_hz != profile.bandwidth_hz
            or tuple(settings.receiver_ids) != (0, 1)
            or tuple(stream.requested_settings.receiver_ids) != (0, 1)
        ):
            raise ValueError(
                "Standard-native historical V2 stream lacks a complete counter-proven span"
            )
        if missing:
            if not admission.counter_gaps_allowed or stream.state is not StreamState.PARTIAL:
                raise ValueError("Standard-native historical V2 profile does not permit gaps")
        elif stream.state is not StreamState.COMPLETE:
            raise ValueError("Standard-native historical V2 lossless stream is not complete")

    expected_state = CaptureState.DEGRADED if any_gaps else CaptureState.COMMITTED
    if manifest.state is not expected_state:
        raise ValueError("Standard-native historical V2 capture state disagrees with gap evidence")
    synchronization = manifest.synchronization
    if any(
        value is None
        for value in (
            synchronization.estimated_start_skew_ns,
            synchronization.start_skew_uncertainty_ns,
            synchronization.estimated_overlap_start_utc_ns,
            synchronization.estimated_overlap_end_utc_ns,
            synchronization.guaranteed_overlap_ns,
        )
    ):
        raise ValueError("Standard-native historical V2 lacks paired timing evidence")


def _require_historical_v2_runtime_settings(manifest: RecordingManifestV2) -> None:
    """Bind random tuning/gain tags to requested settings and exact readback evidence."""

    profile = manifest.capture_plan.profile_revision.profile
    tuning_tags = tuple(tag for tag in manifest.tags if tag.startswith("tuning:"))
    policy_tags = tuple(tag for tag in manifest.tags if tag.startswith("tuning_policy:"))
    gain_tags = tuple(tag for tag in manifest.tags if tag.startswith("gain_mode:"))
    runtime_tags = set(tuning_tags + policy_tags + gain_tags)
    if (
        len(tuning_tags) != 2
        or len(policy_tags) != 1
        or len(gain_tags) != 2
        or set(manifest.tags) != set(profile.tags) | runtime_tags
    ):
        raise ValueError("Standard-native historical V2 runtime tag inventory is invalid")
    policy = policy_tags[0].removeprefix("tuning_policy:")
    if policy not in {"same", "same_channel_opposite_edge", "independent"}:
        raise ValueError("Standard-native historical V2 tuning policy is invalid")

    tuning_by_stream = resolve_manifest_starlink_tuning(manifest)
    if any(item.channel not in {1, 2, 3, 4} for item in tuning_by_stream.values()):
        raise ValueError("Standard-native historical V2 tuning is outside enabled channels")
    ordered_tuning = tuple(tuning_by_stream[stream.stream_id] for stream in manifest.streams)
    if policy == "same" and ordered_tuning[0] != ordered_tuning[1]:
        raise ValueError("Standard-native historical V2 same-tuning policy disagrees with tags")
    if policy == "same_channel_opposite_edge" and not (
        ordered_tuning[0].channel == ordered_tuning[1].channel
        and ordered_tuning[0].edge is not ordered_tuning[1].edge
    ):
        raise ValueError("Standard-native historical V2 opposite-edge policy disagrees with tags")

    stream_ids = {stream.stream_id for stream in manifest.streams}
    gain_by_stream: dict[str, GainMode] = {}
    for tag in gain_tags:
        parts = tag.split(":")
        if len(parts) != 3 or parts[1] not in stream_ids or parts[1] in gain_by_stream:
            raise ValueError("Standard-native historical V2 gain-mode tag is invalid")
        try:
            gain_mode = GainMode(parts[2])
        except ValueError as error:
            raise ValueError("Standard-native historical V2 gain mode is invalid") from error
        if gain_mode not in {GainMode.MANUAL, GainMode.SLOW_ATTACK}:
            raise ValueError("Standard-native historical V2 gain mode is not reviewed")
        gain_by_stream[parts[1]] = gain_mode
    if set(gain_by_stream) != stream_ids:
        raise ValueError("Standard-native historical V2 gain tags do not cover every stream")

    for stream in manifest.streams:
        applied = stream.applied_settings
        if applied is None:
            raise ValueError("Standard-native historical V2 lacks applied settings")
        tuning = tuning_by_stream[stream.stream_id]
        first_center = 959_687_500 if tuning.edge is StarlinkEdge.LOWER else 1_190_312_500
        expected_center = first_center + (tuning.channel - 1) * 250_000_000
        requested = stream.requested_settings
        gain_mode = gain_by_stream[stream.stream_id]
        if requested.center_frequency_hz != expected_center:
            raise ValueError("Standard-native historical V2 requested center disagrees with tags")
        if any(
            settings.sample_rate_hz != profile.sample_rate_hz
            or settings.bandwidth_hz != profile.bandwidth_hz
            or settings.receiver_ids != profile.receivers
            or settings.gain_mode is not gain_mode
            or (
                settings.gains != profile.gains
                if gain_mode is GainMode.MANUAL
                else bool(settings.gains)
            )
            for settings in (requested, applied)
        ):
            raise ValueError("Standard-native historical V2 settings disagree with tuning tags")
        center_tolerance = max(1, round(requested.center_frequency_hz * 1e-6))
        if abs(applied.center_frequency_hz - requested.center_frequency_hz) > center_tolerance:
            raise ValueError("Standard-native historical V2 applied center exceeds tolerance")
