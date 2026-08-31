"""Representative presentation fixtures for API/UI development and E2E."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from leo.presentation.models import (
    AnalysisProductV1,
    AnalysisStateV1,
    AnalysisSummaryV1,
    BacklogStatusV1,
    CandidateCoverageV1,
    CandidateLineageV1,
    CaptureHealthV1,
    CaptureProfileV1,
    ComputeTierV1,
    ControlSummaryV1,
    CoverageV1,
    CurrentRunV1,
    DetectionStateV1,
    DetectionSummaryV1,
    DopplerSummaryV1,
    HoldV1,
    ProductStatusV1,
    ProvenanceV1,
    QamSummaryV1,
    QualitySummaryV1,
    RadioCoverageV1,
    RadioStreamV1,
    ReceiverQamSummaryV1,
    RecordingDetailV1,
    RecordingPathsV1,
    ScientificConfidenceV1,
    SeriesPointV1,
    SeriesV1,
    SourceTypeV1,
    StorageStateV1,
    StorageStatusV1,
    SynchronizationV1,
    SystemStatusV1,
    WholeDwellSummaryV1,
)
from leo.presentation.repository import FixturePresentationRepository

_DIGEST_A = "a80c3b0d94b95548d9ae0ab5d8243fee8cf6c760ccb6fa4ca4efeb6351176e50"
_DIGEST_B = "ae6b124fff2668fa80fba1af9da98e7ffcb2df9cd3b6e196c8d761f4b25ba031"
_CONFIG_DIGEST = "b" * 64


def fixture_product_payloads() -> dict[str, bytes]:
    points = [
        {
            "x": round(index * 0.02, 6),
            "y": float(-1_000_000 + (index % 32) * 62_500),
            "value": round(((index * 17) % 101) / 100, 3),
        }
        for index in range(320)
    ]
    document = {
        "schema_version": 1,
        "kind": "waterfall",
        "metadata": {
            "run_id": "run-retro-v1",
            "time_unit": "s",
            "frequency_unit": "Hz",
            "value_unit": "normalized power",
            "coverage": "bounded TEST fixture",
        },
        "points": points,
    }
    overlay = {
        "schema_version": 1,
        "kind": "overlays",
        "metadata": {
            "run_id": "run-retro-v1",
            "time_unit": "s",
            "frequency_unit": "Hz",
            "frequency_axis": "baseband_cfo_hz",
            "value_unit": "held-out margin",
        },
        "points": [
            {"x": 0.002, "y": 225_000.0, "value": 0.3705},
            {"x": 0.008, "y": 200_500.0, "value": 0.351},
        ],
    }
    compact = {
        "detection": {
            "schema_version": 1,
            "run_id": "run-retro-v1",
            "compute_tier": "standard",
            "confidence": "candidate",
            "confidence_reason": "Candidate passed research gates; specificity is uncalibrated",
            "known_pilot_candidate": True,
            "calibrated_detection": False,
            "candidate_count": 1,
            "returned_candidate_count": 1,
            "candidate_lineage_truncated": False,
            "candidate_coverage": {
                "scheduled_windows": 10,
                "complete_windows": 10,
                "searched_receiver_windows": 20,
                "searched_samples": 25000,
                "searched_time_fraction": 0.1,
                "residual_cfo_min_hz": -400000.0,
                "residual_cfo_max_hz": 400000.0,
                "survey_config_digest": _CONFIG_DIGEST,
            },
            "candidates": [
                {
                    "candidate_id": "cand-retro-1",
                    "receiver_key": "0",
                    "time_s": 0.002,
                    "absolute_epoch_sample": 5000,
                    "search_residual_cfo_hz": 225000.0,
                    "baseband_cfo_hz": 225000.0,
                    "receiver_tuned_center_hz": 1709687500.0,
                    "tuned_signal_frequency_hz": 1709912500.0,
                    "verify_score": 0.385697,
                    "control_score": 0.015197,
                    "margin": 0.3705,
                    "rank_within_search": 0,
                    "track_id": "track-retro-1",
                    "calibration_digest": "d" * 64,
                    "parent_survey_config_digest": _CONFIG_DIGEST,
                }
            ],
        },
        "qam": {
            "schema_version": 1,
            "run_id": "run-retro-v1",
            "state": "complete",
            "known_symbols_only": True,
            "candidate_only": True,
            "combined_accuracy": 0.88375,
            "combined_rms_evm": 0.638002,
            "combined_frame_count": 6,
            "receiver_metrics": [
                {
                    "receiver_key": "0",
                    "candidate_epoch_sample": 2063,
                    "baseband_cfo_hz": 364150.85,
                    "residual_cfo_refinement_hz": 5.79,
                    "receiver_tuned_center_hz": 1709687500.0,
                    "tuned_signal_frequency_hz": 1710051650.85,
                    "accuracy": 0.748333,
                    "rms_evm": 0.712,
                    "frame_count": 6,
                    "noise_variance": 0.021,
                },
                {
                    "receiver_key": "1",
                    "candidate_epoch_sample": 2063,
                    "baseband_cfo_hz": -194343.87,
                    "residual_cfo_refinement_hz": 1.29,
                    "receiver_tuned_center_hz": 1709687500.0,
                    "tuned_signal_frequency_hz": 1709493156.13,
                    "accuracy": 0.799167,
                    "rms_evm": 0.681,
                    "frame_count": 6,
                    "noise_variance": 0.018,
                },
            ],
            "reason": "Known-pilot QAM evidence; payload was not decoded",
        },
        "doppler": {
            "schema_version": 1,
            "run_id": "run-retro-v1",
            "state": "complete",
            "confidence": "candidate",
            "motion_class": "dynamic",
            "baseband_cfo_at_reference_hz": 212750.0,
            "receiver_tuned_center_hz": 1709687500.0,
            "tuned_signal_frequency_at_reference_hz": 1709900250.0,
            "slope_hz_s": -4012.0,
            "acceleration_hz_s2": 0.0,
            "residual_rms_hz": 312.5,
            "point_count": 7,
            "time_coverage_s": 0.006,
            "tle": {
                "status": "unavailable",
                "object_id": None,
                "candidate_only": True,
                "reason": "TLE predictions were not supplied",
            },
            "reason": "Dynamic CFO track; association remains candidate-only",
        },
        "controls": {
            "schema_version": 1,
            "run_id": "run-retro-v1",
            "state": "complete",
            "confidence": "candidate",
            "thresholds_calibrated": False,
            "specificity_claimed": False,
            "passed_candidate_count": 1,
            "best_held_out_margin": 0.3705,
            "best_surrogate_margin": 0.345,
            "reasons": ["specificity thresholds are not calibrated"],
            "reason": "Candidate passed research gates; specificity is not calibrated",
        },
        "provenance": {
            "schema_version": 1,
            "run_id": "run-retro-v1",
            "recording_digest": _DIGEST_A,
            "pipeline_config_digest": _CONFIG_DIGEST,
            "compute_tier": "standard",
            "config_digests": [_CONFIG_DIGEST],
            "algorithm_versions": ["bounded-waterfall-v1", "sparse-whole-dwell-survey-v1"],
            "limitation_codes": ["candidate-only", "known-symbols-not-payload"],
        },
    }
    documents = {"waterfall": document, "overlays": overlay, **compact}
    return {
        f"prod-retro-{kind}": (
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        for kind, value in documents.items()
    }


def write_fixture_artifacts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for product_id, payload in fixture_product_payloads().items():
        path = root / f"{product_id}.json"
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError(f"fixture artifact conflicts: {path}")
            continue
        path.write_bytes(payload)


def build_fixture_repository(artifact_root: Path) -> FixturePresentationRepository:
    payloads = fixture_product_payloads()
    coverage = CoverageV1(
        analyzed_fraction=0.1,
        analyzed_seconds=0.001,
        dwell_seconds=0.01,
        description="10% sparse exact Qin replay coverage; power coverage is complete",
    )
    products = tuple(
        AnalysisProductV1(
            product_id=product_id,
            session_id="retro-positive-68p7",
            analysis_run_id="run-retro-v1",
            kind=kind,  # type: ignore[arg-type]
            status=ProductStatusV1.COMPLETE,
            content_type="application/json",
            artifact_path=str((artifact_root / f"{product_id}.json").resolve()),
            byte_count=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            coverage=coverage,
            summary={"current_run_id": "run-retro-v1"},
        )
        for product_id, payload in payloads.items()
        for kind in (product_id.removeprefix("prod-retro-"),)
    )
    retro = _retro_detail(products, coverage)
    partial = _partial_detail()
    purged = _purged_detail()
    failed = _failed_detail()
    status = SystemStatusV1(
        generated_at=datetime(2026, 8, 19, 2, 10, tzinfo=UTC),
        storage=StorageStatusV1(
            total_bytes=47_300_000_000_000,
            used_bytes=12_300_000_000_000,
            used_fraction=0.26,
            retention_high_watermark=0.70,
            retention_low_watermark=0.65,
            admission_state="open",
        ),
        backlog=BacklogStatusV1(
            queued=3,
            running=2,
            failed=1,
            oldest_queued_seconds=82.4,
        ),
    )
    return FixturePresentationRepository((partial, retro, purged, failed), status)


def _retro_detail(
    products: tuple[AnalysisProductV1, ...], coverage: CoverageV1
) -> RecordingDetailV1:
    analysis = AnalysisSummaryV1(
        state=AnalysisStateV1.COMPLETE,
        current_run=CurrentRunV1(
            run_id="run-retro-v1",
            pipeline_release="analysis-2026.08.19.1",
            state=AnalysisStateV1.COMPLETE,
            started_at=datetime(2026, 8, 19, 1, 35, tzinfo=UTC),
            finished_at=datetime(2026, 8, 19, 1, 36, tzinfo=UTC),
        ),
        coverage=coverage,
        product_count=len(products),
    )
    return RecordingDetailV1(
        session_id="retro-positive-68p7",
        title="RETRO CH4 lower-edge pilot window",
        started_at=datetime(2026, 8, 13, 21, 11, 22, tzinfo=UTC),
        duration_seconds=0.01,
        source_type=SourceTypeV1.TEST,
        tags=("TEST", "RETRO", "KNOWN_PILOT_CANDIDATE"),
        hold=HoldV1(held=True, reason="Protected TEST corpus fixture"),
        capture_health=CaptureHealthV1.COMPLETE,
        storage_state=StorageStateV1.AVAILABLE,
        profile=_profile("profile-retro", "CH4 lower · 2.5 MS/s · 10 ms", 0.01),
        radios=(
            _radio(
                "radio-pluto-5d4d",
                "10400056f695001322002d0010ad1715d4d",
                ("lnb-a", "lnb-b"),
                "/srv/bulk/leo/test-corpus/retro-positive-68p7/recording.ci16",
                25_000,
            ),
        ),
        synchronization=SynchronizationV1(
            mode="none",
            grade="not_requested",
            timing_basis="imported evidence-bundle timestamp",
        ),
        paths=RecordingPathsV1(
            recording_root="/srv/bulk/leo/test-corpus/retro-positive-68p7",
            manifest_path=("/srv/bulk/leo/test-corpus/retro-positive-68p7/fixture-manifest.json"),
            analysis_root="/srv/bulk/leo/analysis/retro-positive-68p7/run-retro-v1",
        ),
        analysis=analysis,
        quality=QualitySummaryV1(
            state=ProductStatusV1.COMPLETE,
            clipped_fraction=0.00002,
            constant_iq_refills=0,
            continuity_gaps=0,
            note="Contiguous selected real-IQ window",
        ),
        power=(
            _series("rx0-power", "RX0 mean power", "dBFS", -31.0),
            _series("rx1-power", "RX1 mean power", "dBFS", -29.5),
        ),
        detection=DetectionSummaryV1(
            state=DetectionStateV1.CANDIDATE,
            known_pilot_candidate=True,
            calibrated_detection=False,
            qin_score=0.385697,
            control_score=0.015197,
            reason="Known synchronization-pilot candidate; no calibrated detection claim",
        ),
        whole_dwell=_retro_whole_dwell(),
        qam=QamSummaryV1(
            state=ProductStatusV1.COMPLETE,
            combined_accuracy=0.88375,
            receiver_accuracy=(0.748333, 0.799167),
            rms_evm=0.638002,
            frame_count=6,
            receiver_metrics=(
                ReceiverQamSummaryV1(
                    receiver_key="0",
                    candidate_epoch_sample=2063,
                    baseband_cfo_hz=364_150.85,
                    residual_cfo_refinement_hz=5.79,
                    receiver_tuned_center_hz=1_709_687_500.0,
                    tuned_signal_frequency_hz=1_710_051_650.85,
                    accuracy=0.748333,
                    rms_evm=0.712,
                    frame_count=6,
                    noise_variance=0.021,
                ),
                ReceiverQamSummaryV1(
                    receiver_key="1",
                    candidate_epoch_sample=2063,
                    baseband_cfo_hz=-194_343.87,
                    residual_cfo_refinement_hz=1.29,
                    receiver_tuned_center_hz=1_709_687_500.0,
                    tuned_signal_frequency_hz=1_709_493_156.13,
                    accuracy=0.799167,
                    rms_evm=0.681,
                    frame_count=6,
                    noise_variance=0.018,
                ),
            ),
        ),
        doppler=DopplerSummaryV1(
            state=ProductStatusV1.PARTIAL,
            slope_hz_per_s=-4012.0,
            baseband_cfo_at_reference_hz=212_750.0,
            receiver_tuned_center_hz=1_709_687_500.0,
            tuned_signal_frequency_at_reference_hz=1_709_900_250.0,
            frequency_span_hz=86_600.0,
            correlation=0.9997,
            residual_rms_hz=312.5,
            point_count=7,
            motion_class="dynamic",
            confidence=ScientificConfidenceV1.CANDIDATE,
            tle_candidate=None,
            association_status="unavailable",
        ),
        provenance=ProvenanceV1(
            analysis_run_id="run-retro-v1",
            pipeline_release="analysis-2026.08.19.1",
            generated_at=datetime(2026, 8, 19, 1, 36, tzinfo=UTC),
            config_digest=_CONFIG_DIGEST,
            recording_digest=_DIGEST_A,
            limitation_codes=(
                "candidate-only",
                "known-symbols-not-payload",
                "sparse-exact-coverage",
            ),
        ),
        products=products,
    )


def _partial_detail() -> RecordingDetailV1:
    coverage = CoverageV1(
        analyzed_fraction=0.64,
        analyzed_seconds=38.4,
        dwell_seconds=60.0,
        description="Power complete; Starlink candidate refinement still running",
    )
    run = CurrentRunV1(
        run_id="run-live-072-v3",
        pipeline_release="analysis-2026.08.19.1",
        state=AnalysisStateV1.PARTIAL,
        started_at=datetime(2026, 8, 19, 2, 1, tzinfo=UTC),
    )
    return RecordingDetailV1(
        session_id="session-live-072",
        title="CH4 lower · coordinated 60 s dwell",
        started_at=datetime(2026, 8, 19, 2, 0, tzinfo=UTC),
        duration_seconds=60.0,
        source_type=SourceTypeV1.LIVE,
        tags=("campaign-nightly", "ch4-lower"),
        hold=HoldV1(held=False),
        capture_health=CaptureHealthV1.PARTIAL,
        storage_state=StorageStateV1.AVAILABLE,
        profile=_profile("profile-ch4-60", "CH4 lower · 2.5 MS/s · 60 s", 60.0),
        radios=(
            _radio(
                "radio-pluto-19f2",
                "10400056f695001322002d0010ad1719f2",
                ("lnb-c", "lnb-d"),
                "/srv/bulk/leo/recordings/2026/08/19/session-live-072/radio-19f2/iq.ci16.zst",
                150_000_000,
            ),
            _radio(
                "radio-pluto-5d4d",
                "10400056f695001322002d0010ad1715d4d",
                ("lnb-a", "lnb-b"),
                "/srv/bulk/leo/recordings/2026/08/19/session-live-072/radio-5d4d/iq.ci16.zst",
                149_800_000,
                state=CaptureHealthV1.PARTIAL,
                gaps=1,
            ),
        ),
        synchronization=SynchronizationV1(
            mode="best_effort",
            grade="degraded",
            start_skew_ms=2.8,
            skew_uncertainty_ms=1.1,
            overlap_seconds=59.91,
            overlap_fraction=0.9985,
            timing_basis="host barrier and first-refill bracketing",
        ),
        paths=RecordingPathsV1(
            recording_root="/srv/bulk/leo/recordings/2026/08/19/session-live-072",
            manifest_path=("/srv/bulk/leo/recordings/2026/08/19/session-live-072/manifest.json"),
            analysis_root="/srv/bulk/leo/analysis/session-live-072/run-live-072-v3",
        ),
        analysis=AnalysisSummaryV1(
            state=AnalysisStateV1.PARTIAL,
            current_run=run,
            coverage=coverage,
            product_count=3,
        ),
        quality=QualitySummaryV1(
            state=ProductStatusV1.PARTIAL,
            clipped_fraction=0.0004,
            constant_iq_refills=0,
            continuity_gaps=1,
            note="One stream ended 80 ms early",
        ),
        power=(_series("live-power", "Combined mean power", "dBFS", -35.0, 60),),
        detection=DetectionSummaryV1(
            state=DetectionStateV1.NOT_RUN,
            known_pilot_candidate=False,
            calibrated_detection=False,
            qin_score=None,
            control_score=None,
            reason="Dense acquisition is queued behind the power survey",
        ),
        whole_dwell=_empty_whole_dwell(),
        qam=QamSummaryV1(
            state=ProductStatusV1.NO_RESULT,
            combined_accuracy=None,
            receiver_accuracy=(),
            rms_evm=None,
            frame_count=0,
        ),
        doppler=DopplerSummaryV1(
            state=ProductStatusV1.NO_RESULT,
            slope_hz_per_s=None,
            frequency_span_hz=None,
            correlation=None,
            tle_candidate=None,
            association_status="not_run",
        ),
        provenance=ProvenanceV1(
            pipeline_release="analysis-2026.08.19.1",
            generated_at=None,
            config_digest=_CONFIG_DIGEST,
            recording_digest="c" * 64,
            limitation_codes=("analysis-in-progress",),
        ),
        products=(),
    )


def _purged_detail() -> RecordingDetailV1:
    return _terminal_detail(
        session_id="session-purged-014",
        title="CH2 upper · purged raw IQ",
        storage_state=StorageStateV1.PURGED,
        analysis=AnalysisSummaryV1(
            state=AnalysisStateV1.NO_RESULT,
            current_run=None,
            no_result_reason="Raw IQ was purged before this pipeline release",
        ),
        capture_health=CaptureHealthV1.COMPLETE,
        raw_path=None,
    )


def _failed_detail() -> RecordingDetailV1:
    return _terminal_detail(
        session_id="session-failed-009",
        title="Research 5 MS/s dwell · analysis failed",
        storage_state=StorageStateV1.AVAILABLE,
        analysis=AnalysisSummaryV1(
            state=AnalysisStateV1.FAILED,
            current_run=CurrentRunV1(
                run_id="run-failed-009",
                pipeline_release="analysis-2026.08.19.1",
                state=AnalysisStateV1.FAILED,
                started_at=datetime(2026, 8, 18, 23, 45, tzinfo=UTC),
                finished_at=datetime(2026, 8, 18, 23, 46, tzinfo=UTC),
            ),
            failure_reason="Waterfall artifact failed checksum verification",
            product_count=2,
        ),
        capture_health=CaptureHealthV1.FAILED,
        raw_path=("/srv/bulk/leo/recordings/2026/08/18/session-failed-009/radio-19f2/iq.ci16.zst"),
    )


def _terminal_detail(
    *,
    session_id: str,
    title: str,
    storage_state: StorageStateV1,
    analysis: AnalysisSummaryV1,
    capture_health: CaptureHealthV1,
    raw_path: str | None,
) -> RecordingDetailV1:
    root = f"/srv/bulk/leo/recordings/2026/08/18/{session_id}"
    return RecordingDetailV1(
        session_id=session_id,
        title=title,
        started_at=datetime(2026, 8, 18, 23, 40, tzinfo=UTC),
        duration_seconds=20.0,
        source_type=SourceTypeV1.IMPORT,
        tags=("historical",),
        hold=HoldV1(held=False),
        capture_health=capture_health,
        storage_state=storage_state,
        profile=_profile("profile-historical", "Historical import", 20.0),
        radios=(
            _radio(
                "radio-imported",
                "imported-serial",
                ("rx0", "rx1"),
                raw_path,
                0 if raw_path is None else 50_000_000,
                state=capture_health,
            ),
        ),
        synchronization=SynchronizationV1(
            mode="none", grade="not_requested", timing_basis="imported manifest"
        ),
        paths=RecordingPathsV1(
            recording_root=root,
            manifest_path=f"{root}/manifest.json",
            analysis_root=None,
        ),
        analysis=analysis,
        quality=QualitySummaryV1(
            state=(
                ProductStatusV1.FAILED
                if analysis.state is AnalysisStateV1.FAILED
                else ProductStatusV1.NO_RESULT
            ),
            clipped_fraction=None,
            constant_iq_refills=None,
            continuity_gaps=None,
            note="Metadata retained after terminal state",
        ),
        power=(),
        detection=DetectionSummaryV1(
            state=(
                DetectionStateV1.FAILED
                if analysis.state is AnalysisStateV1.FAILED
                else DetectionStateV1.NOT_RUN
            ),
            known_pilot_candidate=False,
            calibrated_detection=False,
            qin_score=None,
            control_score=None,
            reason=analysis.failure_reason or analysis.no_result_reason or "Unavailable",
        ),
        whole_dwell=_empty_whole_dwell(),
        qam=QamSummaryV1(
            state=ProductStatusV1.NO_RESULT,
            combined_accuracy=None,
            receiver_accuracy=(),
            rms_evm=None,
            frame_count=0,
        ),
        doppler=DopplerSummaryV1(
            state=ProductStatusV1.NO_RESULT,
            slope_hz_per_s=None,
            frequency_span_hz=None,
            correlation=None,
            tle_candidate=None,
            association_status="not_run",
        ),
        provenance=ProvenanceV1(
            pipeline_release=(
                analysis.current_run.pipeline_release if analysis.current_run else None
            ),
            generated_at=None,
            config_digest=None,
            recording_digest=_DIGEST_B,
            limitation_codes=(analysis.state.value,),
        ),
        products=(),
    )


def _retro_whole_dwell() -> WholeDwellSummaryV1:
    return WholeDwellSummaryV1(
        analysis_run_id="run-retro-v1",
        compute_tier=ComputeTierV1.STANDARD,
        confidence=ScientificConfidenceV1.CANDIDATE,
        confidence_reason="Candidate passed research gates; specificity is uncalibrated",
        candidate_count=1,
        returned_candidate_count=1,
        candidate_lineage_truncated=False,
        candidate_coverage=CandidateCoverageV1(
            scheduled_windows=10,
            complete_windows=10,
            searched_receiver_windows=20,
            searched_samples=25_000,
            searched_time_fraction=0.1,
            residual_cfo_min_hz=-400_000.0,
            residual_cfo_max_hz=400_000.0,
            survey_config_digest=_CONFIG_DIGEST,
        ),
        candidates=(
            CandidateLineageV1(
                candidate_id="cand-retro-1",
                receiver_key="0",
                time_s=0.002,
                absolute_epoch_sample=5000,
                search_residual_cfo_hz=225_000.0,
                baseband_cfo_hz=225_000.0,
                receiver_tuned_center_hz=1_709_687_500.0,
                tuned_signal_frequency_hz=1_709_912_500.0,
                verify_score=0.385697,
                control_score=0.015197,
                margin=0.3705,
                rank_within_search=0,
                track_id="track-retro-1",
                calibration_digest="d" * 64,
                parent_survey_config_digest=_CONFIG_DIGEST,
            ),
        ),
        controls=ControlSummaryV1(
            state=ProductStatusV1.COMPLETE,
            thresholds_calibrated=False,
            specificity_claimed=False,
            passed_candidate_count=1,
            best_held_out_margin=0.3705,
            best_surrogate_margin=0.345,
            rejection_reasons=("specificity thresholds are not calibrated",),
            reason="Candidate passed research gates; specificity is not calibrated",
        ),
    )


def _empty_whole_dwell() -> WholeDwellSummaryV1:
    return WholeDwellSummaryV1(
        analysis_run_id=None,
        compute_tier=ComputeTierV1.NOT_RUN,
        confidence=ScientificConfidenceV1.UNASSESSED,
        confidence_reason="Whole-dwell scientific presentation is unavailable",
        candidate_count=0,
        returned_candidate_count=0,
        candidate_lineage_truncated=False,
        candidate_coverage=None,
        candidates=(),
        controls=ControlSummaryV1(
            state=ProductStatusV1.NO_RESULT,
            thresholds_calibrated=False,
            specificity_claimed=False,
            passed_candidate_count=0,
            best_held_out_margin=None,
            best_surrogate_margin=None,
            rejection_reasons=(),
            reason="Control evidence is unavailable",
        ),
    )


def _profile(profile_id: str, name: str, dwell: float) -> CaptureProfileV1:
    return CaptureProfileV1(
        profile_id=profile_id,
        name=name,
        revision=1,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        dwell_seconds=dwell,
        center_frequency_hz=1_709_687_500,
        receiver_count_per_radio=2,
    )


def _radio(
    radio_id: str,
    serial: str,
    labels: tuple[str, ...],
    path: str | None,
    samples: int,
    *,
    state: CaptureHealthV1 = CaptureHealthV1.COMPLETE,
    gaps: int = 0,
) -> RadioStreamV1:
    observed_samples = samples if state is CaptureHealthV1.COMPLETE else max(1, samples - gaps)
    requested_samples = max(1, samples)
    return RadioStreamV1(
        radio_id=radio_id,
        serial=serial,
        receiver_labels=labels,
        state=state,
        captured_samples=samples,
        coverage=RadioCoverageV1(
            delivery_unit="device_samples",
            delivered_units=samples,
            requested_units=requested_samples,
            delivery_coverage_pct=100.0 * samples / requested_samples,
            observed_samples=observed_samples,
            logical_samples=samples,
            observed_density_pct=(None if samples == 0 else 100.0 * observed_samples / samples),
        ),
        sample_rate_hz=2_500_000,
        gain_db=tuple(44.0 for _ in labels),
        raw_path=path,
        continuity_gaps=gaps,
        clipped_samples=12 if state is CaptureHealthV1.PARTIAL else 0,
    )


def _series(series_id: str, label: str, unit: str, baseline: float, count: int = 20) -> SeriesV1:
    points = tuple(
        SeriesPointV1(time_s=index * 0.5, value=baseline + ((index * 7) % 9) * 0.18)
        for index in range(count)
    )
    return SeriesV1(
        series_id=series_id,
        label=label,
        unit=unit,
        points=points,
        source_point_count=len(points),
        decimated=False,
    )
