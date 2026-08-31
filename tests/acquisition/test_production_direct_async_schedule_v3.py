from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.acquisition.coverage import project_capture_progress_coverage
from leo.acquisition.mixed_rate_schedule import (
    PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1,
    compile_production_dwell_intent_hold_rollout_v1,
    compile_production_dwell_intent_v3,
    production_cycle_classes_v3,
)
from leo.contracts.device_buffer import (
    DIRECT_ASYNC_EVIDENCE_KEY_V1,
    DirectAsyncEvidenceV1,
    DirectAsyncRequestV1,
)
from leo.contracts.gain_control import GainControllerMode
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClassV3,
    ProductionDwellIntentV3,
    ProductionTuningBranchV2,
)
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV6,
    parse_recording_manifest_json,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StreamState,
    SynchronizationMode,
)
from leo.domain.mixed_rate_capture import compile_production_capture_plan_v5
from leo.pipeline import standard_native as standard_native_pipeline
from leo.pipeline.standard_native import compile_standard_native_run_plan
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore

_RADIOS = ("radio-20", "radio-21")
_PROFILE_KEYS = (
    (2_500_000, (0, 1), True),
    *(
        (rate, (receiver,), True)
        for rate in (10_000_000, 15_000_000, 25_000_000)
        for receiver in (0, 1)
    ),
)
_AUTHORITY = {
    key: (
        f"direct-{key[0]}-rx{''.join(str(item) for item in key[1])}",
        f"sha256:{index:064x}",
        1_048_576,
    )
    for index, key in enumerate(_PROFILE_KEYS, start=1)
}


def _intent(ordinal: int) -> ProductionDwellIntentV3:
    return compile_production_dwell_intent_v3(
        operation_key=f"direct-async-dwell:{ordinal}",
        cadence_ordinal=ordinal,
        radio_ids=_RADIOS,
        profile_authority=_AUTHORITY,
        extra_tags=("direct-async-rc1", "scheduled"),
    )


def _revision(
    rate: int,
    receivers: tuple[int, ...],
    *,
    name: str,
    duration_seconds: Decimal = Decimal("0.0000004"),
    ordinary_refill_samples: int = 4,
    prime_refills: int = 1,
) -> CaptureProfileRevisionV2:
    direct = rate > 2_500_000
    return CaptureProfileRevisionV2.from_profile(
        CaptureProfileV2(
            name=name,
            center_frequency_hz=1_700_000_000,
            sample_rate_hz=rate,
            bandwidth_hz=rate,
            receivers=receivers,
            gain_mode=GainMode.MANUAL,
            gains=tuple(ReceiverGainV1(receiver_id=item, gain_db=30) for item in receivers),
            duration_seconds=duration_seconds,
            refill_samples=1_048_576 if direct else ordinary_refill_samples,
            prime_refills=prime_refills,
            kernel_buffers=15 if direct else 4,
            refill_queue_capacity=64 if direct else 32,
            continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
            synchronization_mode=SynchronizationMode.BEST_EFFORT,
            peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
            storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
            tags=(
                "CAPTURE_ONLY",
                "DEVICE_AXIS_ZERO_FILL",
                *(("DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1",) if direct else ()),
                "LIVE",
                "MIXED_RATE",
                "NATIVE_BANDWIDTH",
                "RANDOM_TUNING",
                *(("SINGLE_RX",) if direct else ()),
                "STANDARD_NATIVE",
                "TANDEM_CONTROLLER",
            ),
        )
    )


def test_v3_cycle_is_uniform_and_every_intent_is_same_target() -> None:
    expected = Counter(
        {
            ProductionDwellClassV3.MIXED_2P5_10: 2,
            ProductionDwellClassV3.MIXED_2P5_15: 2,
            ProductionDwellClassV3.MIXED_2P5_25: 2,
        }
    )
    for cycle_index in range(128):
        assert (
            Counter(production_cycle_classes_v3(cycle_index=cycle_index, radio_ids=_RADIOS))
            == expected
        )

    intents = tuple(_intent(ordinal) for ordinal in range(6 * 256))
    high_legs = tuple(
        next(leg for leg in item.radio_legs if leg.sample_rate_hz > 2_500_000) for item in intents
    )
    assert {leg.radio_id for leg in high_legs} == set(_RADIOS)
    assert {leg.receiver_ids for leg in high_legs} == {(0,), (1,)}
    assert {leg.gain_controller.mode for item in intents for leg in item.radio_legs} == {
        GainControllerMode.TANDEM_AUTO,
        GainControllerMode.TANDEM_HOLD,
    }
    assert all(item.tuning_branch is ProductionTuningBranchV2.SAME for item in intents)
    assert all(
        len({(leg.starlink_channel, leg.starlink_edge) for leg in item.radio_legs}) == 1
        for item in intents
    )


def test_additive_hold_rollout_preserves_v3_contract_and_excludes_auto() -> None:
    intents = tuple(
        compile_production_dwell_intent_hold_rollout_v1(
            operation_key=f"hold-rollout:{ordinal}",
            cadence_ordinal=ordinal,
            radio_ids=_RADIOS,
            profile_authority=_AUTHORITY,
            rollout_policy_id=PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
            extra_tags=("production",),
        )
        for ordinal in range(6 * 32)
    )

    assert all(item.policy_id == "production-direct-async-2p5-10-15-25-6-v3" for item in intents)
    assert all(PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1 in item.extra_tags for item in intents)
    assert {leg.gain_controller.mode for intent in intents for leg in intent.radio_legs} == {
        GainControllerMode.TANDEM_HOLD
    }
    assert {leg.radio_id for intent in intents for leg in intent.radio_legs} == set(_RADIOS)
    assert {
        leg.receiver_ids
        for intent in intents
        for leg in intent.radio_legs
        if leg.sample_rate_hz > 2_500_000
    } == {(0,), (1,)}


def test_hold_rollout_rejects_an_unreviewed_selector() -> None:
    with pytest.raises(ValueError, match="HOLD rollout policy"):
        compile_production_dwell_intent_hold_rollout_v1(
            operation_key="hold-rollout:invalid",
            cadence_ordinal=0,
            radio_ids=_RADIOS,
            profile_authority=_AUTHORITY,
            rollout_policy_id="unreviewed",
        )


def test_v5_plan_and_v6_manifest_round_trip_through_a_real_capture(tmp_path) -> None:
    revisions_by_key = {
        key: _revision(
            key[0],
            key[1],
            name=f"direct-{key[0]}-rx{''.join(str(item) for item in key[1])}",
        )
        for key in _PROFILE_KEYS
    }
    authority = {
        key: (
            revision.profile.name,
            revision.revision_digest,
            revision.profile.refill_samples,
        )
        for key, revision in revisions_by_key.items()
    }
    intent = next(
        candidate
        for ordinal in range(6)
        for candidate in (
            compile_production_dwell_intent_v3(
                operation_key=f"direct-plan:{ordinal}",
                cadence_ordinal=ordinal,
                radio_ids=_RADIOS,
                profile_authority=authority,
            ),
        )
        if candidate.dwell_class is ProductionDwellClassV3.MIXED_2P5_25
    )
    plan = compile_production_capture_plan_v5(
        intent=intent,
        profile_revisions_by_radio={
            leg.radio_id: revisions_by_key[(leg.sample_rate_hz, leg.receiver_ids, True)]
            for leg in intent.radio_legs
        },
        source_type=SourceType.TEST,
    )
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=128 * 1024 * 1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )

    result = coordinator.capture_once(
        plan,
        {radio_id: FakeRadioSource(radio_id) for radio_id in _RADIOS},
        session_id="production-direct-async-v6",
    )

    assert result.state is CaptureState.COMMITTED
    assert type(result.manifest) is RecordingManifestV6
    assert result.manifest.capture_plan == plan
    assert parse_recording_manifest_json(result.manifest.model_dump_json()) == result.manifest
    assert {stream.applied_settings.sample_rate_hz for stream in result.manifest.streams} == {
        2_500_000,
        25_000_000,
    }


def test_bounded_live_2p5_x25_manifest_is_admitted_to_standard_analysis(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revisions_by_key = {
        key: _revision(
            key[0],
            key[1],
            name=f"direct-live-{key[0]}-rx{''.join(str(item) for item in key[1])}",
        )
        for key in _PROFILE_KEYS
    }
    authority = {
        key: (
            revision.profile.name,
            revision.revision_digest,
            revision.profile.refill_samples,
        )
        for key, revision in revisions_by_key.items()
    }
    intent = next(
        candidate
        for ordinal in range(6)
        for candidate in (
            compile_production_dwell_intent_v3(
                operation_key=f"direct-live-plan:{ordinal}",
                cadence_ordinal=ordinal,
                radio_ids=_RADIOS,
                profile_authority=authority,
            ),
        )
        if candidate.dwell_class is ProductionDwellClassV3.MIXED_2P5_25
    )
    selected = {
        leg.radio_id: revisions_by_key[(leg.sample_rate_hz, leg.receiver_ids, True)]
        for leg in intent.radio_legs
    }
    plan = compile_production_capture_plan_v5(
        intent=intent,
        profile_revisions_by_radio=selected,
        source_type=SourceType.LIVE,
    )
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=128 * 1024 * 1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {radio_id: FakeRadioSource(radio_id) for radio_id in _RADIOS},
        session_id="production-direct-async-live-v6",
    )
    assert type(result.manifest) is RecordingManifestV6
    manifest = result.manifest
    for revision in selected.values():
        profile = revision.profile
        if profile.sample_rate_hz == 2_500_000:
            monkeypatch.setitem(
                standard_native_pipeline.STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES,
                profile.name,
                (
                    profile.sample_rate_hz,
                    profile.receivers,
                    revision.revision_digest,
                    profile.refill_samples,
                ),
            )
        else:
            monkeypatch.setitem(
                standard_native_pipeline.STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES,
                profile.name,
                (profile.sample_rate_hz, profile.receivers, revision.revision_digest),
            )
    expanded = compile_standard_native_run_plan(
        manifest,
        manifest_digest="sha256:" + "a" * 64,
        pipeline_release_id="b" * 40,
    )
    assert Counter(item.stage_key for item in expanded.jobs) == Counter(
        {
            "path-standard-native": 3,
            "path-alternate-tracks-native": 3,
            "radio-scientific-report-native": 2,
            "paired-scientific-report-native": 1,
            "paired-presentation-native": 1,
        }
    )


def test_gapped_2p5_x25_pair_publishes_with_complete_delivery_and_truthful_density(
    tmp_path,
) -> None:
    duration = Decimal("0.05")
    revisions_by_key = {
        key: _revision(
            key[0],
            key[1],
            name=f"coverage-{key[0]}-rx{''.join(str(item) for item in key[1])}",
            duration_seconds=duration,
            ordinary_refill_samples=131_072,
            prime_refills=0,
        )
        for key in _PROFILE_KEYS
    }
    authority = {
        key: (
            revision.profile.name,
            revision.revision_digest,
            revision.profile.refill_samples,
        )
        for key, revision in revisions_by_key.items()
    }
    intent = next(
        candidate
        for ordinal in range(6)
        for candidate in (
            compile_production_dwell_intent_v3(
                operation_key=f"coverage-plan:{ordinal}",
                cadence_ordinal=ordinal,
                radio_ids=_RADIOS,
                profile_authority=authority,
            ),
        )
        if candidate.dwell_class is ProductionDwellClassV3.MIXED_2P5_25
    )
    selected = {
        leg.radio_id: revisions_by_key[(leg.sample_rate_hz, leg.receiver_ids, True)]
        for leg in intent.radio_legs
    }
    plan = compile_production_capture_plan_v5(
        intent=intent,
        profile_revisions_by_radio=selected,
        source_type=SourceType.TEST,
    )
    high_leg = next(leg for leg in intent.radio_legs if leg.sample_rate_hz == 25_000_000)
    sources = {radio_id: FakeRadioSource(radio_id) for radio_id in _RADIOS}
    sources[high_leg.radio_id] = FakeRadioSource(
        high_leg.radio_id,
        gaps_before_blocks={1: 1_048_576},
    )
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=128 * 1024 * 1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )

    result = coordinator.capture_once(plan, sources, session_id="gapped-pair-coverage")

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV6)
    high_stream = next(
        stream for stream in result.manifest.streams if stream.radio.radio_id == high_leg.radio_id
    )
    assert high_stream.state is StreamState.PARTIAL
    assert high_stream.logical_sample_count == high_stream.requested_sample_count == 1_250_000
    assert high_stream.observed_sample_count == 1_048_576
    high_coverage = next(
        item for item in result.stream_coverage if item.radio_id == high_leg.radio_id
    )
    low_coverage = next(
        item for item in result.stream_coverage if item.radio_id != high_leg.radio_id
    )
    assert high_coverage.delivery_unit == "frames"
    assert (high_coverage.delivered_units, high_coverage.requested_units) == (2, 2)
    assert high_coverage.delivery_coverage_pct == 100.0
    assert high_coverage.observed_density_pct == pytest.approx(83.88608)
    assert high_coverage.in_segment_density_pct == pytest.approx(200 / 3)
    assert high_coverage.transport_density_pct == pytest.approx(200 / 3)
    assert low_coverage.delivery_coverage_pct == 100.0
    assert low_coverage.observed_density_pct == 100.0
    first = next(
        coordinator.store.reader(result.bundle, high_stream.stream_id).iter_timeline_metadata()
    )
    evidence = DirectAsyncEvidenceV1.model_validate(
        first.hardware_metadata[DIRECT_ASYNC_EVIDENCE_KEY_V1]
    )
    assert evidence.returned_frames == evidence.request.target_frames == 2
    assert evidence.counter_missing_sample_count == 1_048_576


@pytest.mark.parametrize("returned_frames", [0, 6, 7, 63, 64, 1430])
def test_failed_direct_async_progress_reports_exact_frame_delivery(returned_frames) -> None:
    request = DirectAsyncRequestV1(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )

    coverage = project_capture_progress_coverage(
        radio_id="radio-21",
        stream_id="stream-1",
        requested_samples=request.requested_device_samples,
        observed_samples=returned_frames * request.frame_samples,
        covered_device_samples=returned_frames * request.frame_samples,
        direct_async_request=request,
        returned_frames=returned_frames,
    )

    assert coverage.delivery_coverage_pct == pytest.approx(100 * returned_frames / 1431)
