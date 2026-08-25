"""Manifest-authoritative planning for the evidence-only Research rate lane."""

from __future__ import annotations

from leo.contracts.profile import CaptureProfileV2
from leo.contracts.rate_analysis import (
    RateAnalysisCapabilityBindingV1,
    RateAnalysisCapabilityV1,
    RateAnalysisConfigurationV1,
)
from leo.contracts.recording import RecordingManifestV1, RecordingManifestV2
from leo.contracts.standard_pipeline import (
    ManifestStarlinkTuningIntent,
    resolve_manifest_starlink_tuning,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    SourceType,
    StarlinkEdge,
    StreamState,
)
from leo.pipeline.contracts import ResourceClass
from leo.pipeline.planning import ExpandedRunPlanV1, IqAccess, JobNodeV1
from leo.pipeline.topology import compile_scope_inventory

RATE_CONTINUITY_BASELINE_STAGE_KEY = "rate-continuity-baseline"

THREE_M_LOSSLESS_CAPABILITY_V1 = RateAnalysisCapabilityV1(
    capability_id="3m-lossless-committed-v1",
    profile_name="starlink-ch4-lower-3m-60s-capture-v2",
    profile_revision_digest=(
        "sha256:6dbcb80f92b605a20564bac17001ae6ce394e5961fda2d11c808cdff8a81a652"
    ),
    sample_rate_hz=3_000_000,
    capture_state="committed",
    profile_tags=("CAPTURE_ONLY", "LIVE", "RANDOM_TUNING"),
    continuity_requirement="lossless_device_span",
)

FIVE_M_GAP_AWARE_CAPABILITY_V1 = RateAnalysisCapabilityV1(
    capability_id="5m-gap-aware-degraded-v1",
    profile_name="starlink-ch4-lower-5m-60s-segmented-v2",
    profile_revision_digest=(
        "sha256:52a5fa028ae3d5975188e2221e7f00af850366ede0903645d952ba6ad4636640"
    ),
    sample_rate_hz=5_000_000,
    capture_state="degraded",
    profile_tags=("CAPTURE_ONLY", "EXPERIMENTAL", "LIVE", "RANDOM_TUNING"),
    continuity_requirement="gap_map_evidence",
)

RATE_ANALYSIS_CAPABILITIES_V1 = (
    THREE_M_LOSSLESS_CAPABILITY_V1,
    FIVE_M_GAP_AWARE_CAPABILITY_V1,
)

RATE_ANALYSIS_CONFIGURATION_V1 = RateAnalysisConfigurationV1(
    capabilities=tuple(
        RateAnalysisCapabilityBindingV1(
            capability=capability,
            capability_digest=capability.capability_digest,
        )
        for capability in RATE_ANALYSIS_CAPABILITIES_V1
    )
)


def rate_analysis_configuration_v1() -> dict[str, object]:
    """Return the exact reviewed stage configuration as JSON-compatible values."""

    return RATE_ANALYSIS_CONFIGURATION_V1.model_dump(mode="json")


def rate_analysis_capability(manifest: RecordingManifestV1) -> RateAnalysisCapabilityV1:
    """Fail closed unless a verified manifest matches one reviewed rate capability."""

    if not isinstance(manifest, RecordingManifestV2):
        raise ValueError("rate baseline requires a V2 recording manifest")
    if manifest.source_type is not SourceType.LIVE:
        raise ValueError("rate baseline requires a live recording")

    revision = manifest.capture_plan.profile_revision
    profile = revision.profile
    identity = (
        profile.name,
        revision.revision_digest,
        profile.sample_rate_hz,
        manifest.state.value,
    )
    matches = tuple(
        capability
        for capability in RATE_ANALYSIS_CAPABILITIES_V1
        if identity
        == (
            capability.profile_name,
            capability.profile_revision_digest,
            capability.sample_rate_hz,
            capability.capture_state,
        )
    )
    if len(matches) != 1:
        raise ValueError("recording does not match an exact reviewed rate-analysis capability")
    capability = matches[0]

    if not isinstance(profile, CaptureProfileV2):
        raise ValueError("rate baseline requires the exact V2 capture profile")
    expected_sample_count = capability.sample_rate_hz * 60
    if (
        profile.tags != capability.profile_tags
        or profile.bandwidth_hz != 2_500_000
        or profile.receivers != (0, 1)
        or profile.continuity_policy is not ContinuityPolicy.ALLOW_SEGMENTS
        or not profile.require_device_metadata
        or manifest.capture_plan.resolved_sample_count != expected_sample_count
        or len(manifest.capture_plan.radio_ids) != 2
        or len(manifest.streams) != 2
    ):
        raise ValueError("recording capture plan differs from the reviewed rate capability")

    tuning_by_stream = _validated_runtime_tuning(manifest, capability)

    for stream in manifest.streams:
        applied = stream.applied_settings
        continuity = stream.continuity
        if (
            stream.requested_sample_count != expected_sample_count
            or stream.captured_sample_count <= 0
            or not stream.chunks
            or stream.timeline_relative_path is None
            or stream.timeline_sha256 is None
            or stream.gap_map_relative_path is None
            or stream.gap_map_sha256 is None
            or stream.timing is None
            or applied is None
        ):
            raise ValueError("rate baseline requires persisted IQ, timing, and gap-map evidence")
        tuning, gain_mode = tuning_by_stream[stream.stream_id]
        expected_center = _starlink_if_center_frequency_hz(tuning.channel, tuning.edge)
        requested = stream.requested_settings
        if requested.center_frequency_hz != expected_center:
            raise ValueError("rate stream requested center disagrees with tuning tags")
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
            raise ValueError("rate stream settings disagree with runtime tuning evidence")
        center_tolerance = max(1, round(requested.center_frequency_hz * 1e-6))
        if abs(applied.center_frequency_hz - requested.center_frequency_hz) > center_tolerance:
            raise ValueError("rate stream applied center exceeds readback tolerance")
        if (
            not continuity.sample_loss_observable
            or continuity.metadata_abi_version != 1
            or continuity.validated_stream_generation is None
            or continuity.observed_sample_count != stream.captured_sample_count
            or continuity.device_span_sample_count > expected_sample_count
            or continuity.kernel_buffers != profile.kernel_buffers
            or continuity.queue_capacity_refills != profile.refill_queue_capacity
            or continuity.refill_count <= 0
            or continuity.segment_count <= 0
        ):
            raise ValueError("rate stream lacks closed device-counter continuity evidence")

        if capability.capture_state == "committed":
            if (
                manifest.state is not CaptureState.COMMITTED
                or stream.state is not StreamState.COMPLETE
                or stream.captured_sample_count != expected_sample_count
                or continuity.device_span_sample_count != expected_sample_count
                or continuity.total_observed_gap_count != 0
                or continuity.total_observed_missing_sample_count != 0
                or continuity.total_observed_overflow_count != 0
                or continuity.enqueue_failure_count != 0
            ):
                raise ValueError("3 MS/s rate baseline requires a lossless committed device span")
        elif (
            continuity.device_span_sample_count != expected_sample_count
            or continuity.total_observed_overflow_count != 0
            or continuity.enqueue_failure_count != 0
            or continuity.terminal_enqueue_failure is not None
            or continuity.terminal_rejected_gap_count != 0
            or continuity.terminal_rejected_missing_sample_count != 0
            or continuity.terminal_rejected_overflow_count != 0
        ):
            raise ValueError("5 MS/s rate baseline requires full-span gap-only continuity evidence")
        elif stream.state is StreamState.COMPLETE:
            if (
                stream.captured_sample_count != expected_sample_count
                or continuity.gap_count != 0
                or continuity.missing_sample_count != 0
            ):
                raise ValueError("complete 5 MS/s stream must have lossless full-span closure")
        elif stream.state is StreamState.PARTIAL:
            if continuity.gap_count <= 0 or continuity.missing_sample_count <= 0:
                raise ValueError("partial 5 MS/s stream requires positive gap evidence")
        else:
            raise ValueError("5 MS/s rate baseline requires preserved IQ on every stream")

    if capability.capture_state == "degraded" and (
        manifest.state is not CaptureState.DEGRADED
        or not any(stream.state is StreamState.PARTIAL for stream in manifest.streams)
    ):
        raise ValueError("5 MS/s rate baseline requires an explicitly degraded capture")
    return capability


def _validated_runtime_tuning(
    manifest: RecordingManifestV2,
    capability: RateAnalysisCapabilityV1,
) -> dict[str, tuple[ManifestStarlinkTuningIntent, GainMode]]:
    """Bind the bounded random-tuning tag inventory to each stream's settings."""

    tuning_tags = tuple(tag for tag in manifest.tags if tag.startswith("tuning:"))
    policy_tags = tuple(tag for tag in manifest.tags if tag.startswith("tuning_policy:"))
    gain_tags = tuple(tag for tag in manifest.tags if tag.startswith("gain_mode:"))
    runtime_tags = set(tuning_tags + policy_tags + gain_tags)
    if (
        len(tuning_tags) != 2
        or len(policy_tags) != 1
        or len(gain_tags) != 2
        or set(manifest.tags) != set(capability.profile_tags) | runtime_tags
    ):
        raise ValueError("rate manifest has an unexpected runtime tag inventory")
    policy = policy_tags[0].removeprefix("tuning_policy:")
    if policy not in {"same", "same_channel_opposite_edge", "independent"}:
        raise ValueError("rate manifest has an invalid random-tuning policy tag")

    resolved = resolve_manifest_starlink_tuning(manifest)
    if any(item.channel not in {1, 2, 3, 4} for item in resolved.values()):
        raise ValueError("rate manifest tuning falls outside the enabled capture channels")
    ordered = tuple(resolved[stream.stream_id] for stream in manifest.streams)
    if policy == "same" and ordered[0] != ordered[1]:
        raise ValueError("same tuning policy disagrees with per-stream tuning tags")
    if policy == "same_channel_opposite_edge" and not (
        ordered[0].channel == ordered[1].channel and ordered[0].edge is not ordered[1].edge
    ):
        raise ValueError("opposite-edge policy disagrees with per-stream tuning tags")

    gain_by_stream: dict[str, GainMode] = {}
    stream_ids = {stream.stream_id for stream in manifest.streams}
    for tag in gain_tags:
        parts = tag.split(":")
        if len(parts) != 3 or parts[1] not in stream_ids or parts[1] in gain_by_stream:
            raise ValueError("rate manifest has an invalid per-stream gain-mode tag")
        try:
            gain_mode = GainMode(parts[2])
        except ValueError as error:
            raise ValueError("rate manifest has an invalid per-stream gain mode") from error
        if gain_mode not in {GainMode.MANUAL, GainMode.SLOW_ATTACK}:
            raise ValueError("rate manifest gain mode is outside the reviewed random policy")
        gain_by_stream[parts[1]] = gain_mode
    if set(gain_by_stream) != stream_ids:
        raise ValueError("rate manifest gain-mode tags do not cover every stream")
    return {
        stream.stream_id: (resolved[stream.stream_id], gain_by_stream[stream.stream_id])
        for stream in manifest.streams
    }


def _starlink_if_center_frequency_hz(channel: int, edge: StarlinkEdge) -> int:
    first = 959_687_500 if edge is StarlinkEdge.LOWER else 1_190_312_500
    return first + (channel - 1) * 250_000_000


def compile_rate_baseline_run_plan(
    manifest: RecordingManifestV1, *, manifest_digest: str, pipeline_release_id: str
) -> ExpandedRunPlanV1:
    """Compile one independent continuity-only job per verified receiver path."""

    rate_analysis_capability(manifest)
    topology = compile_scope_inventory(manifest)
    jobs = tuple(
        JobNodeV1(
            node_id=f"rate-path-{ordinal:02d}-baseline",
            stage_key=RATE_CONTINUITY_BASELINE_STAGE_KEY,
            scope=scope,
            iq_access=IqAccess.RECEIVER_PATH,
            resource_class=ResourceClass.STREAMING,
        )
        for ordinal, scope in enumerate(topology.receiver_paths)
    )
    return ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        jobs=jobs,
        edges=(),
    )
