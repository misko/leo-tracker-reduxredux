"""Production presentation-v1 repository backed by catalog and bulk storage."""

from __future__ import annotations

import math
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from leo.artifacts import AnalysisArtifactStore, ArtifactStoreError
from leo.catalog import (
    CatalogRepository,
    CatalogRunReadSnapshot,
    CatalogSessionReadSnapshot,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.recording import RecordingManifestV1, RecordingStreamV1
from leo.contracts.states import CaptureState, StreamState
from leo.operations.retention import (
    ADMISSION_STOP_WATERMARK,
    HIGH_WATERMARK,
    LOW_WATERMARK,
)
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
    RadioStreamV1,
    ReceiverQamSummaryV1,
    RecordingDetailV1,
    RecordingPathsV1,
    RecordingSearchResponseV1,
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
from leo.presentation.projectors import recording_summary_v1
from leo.storage import RecordingStore
from leo.storage.errors import RecordingStoreError

_PRODUCT_ID = re.compile(r"^ap-([1-9][0-9]*)$")
_PRESENTATION_KIND_MAP: dict[str, str] = {
    "quality.summary": "quality",
    "power.summary": "power",
    "waterfall.presentation": "waterfall",
    "detection.presentation": "detection",
    "qam.presentation": "qam",
    "doppler.presentation": "doppler",
    "controls.presentation": "controls",
    "overlays.presentation": "overlays",
    "provenance.presentation": "provenance",
}
_MAX_PRESENTATION_PRODUCT_BYTES = 16 * 1024 * 1024


class CatalogPresentationRepository:
    """Project one catalog current-run snapshot at each public read boundary."""

    def __init__(
        self,
        catalog: CatalogRepository,
        recordings: RecordingStore,
        artifacts: AnalysisArtifactStore,
        *,
        bulk_root: Path,
    ) -> None:
        root = bulk_root.resolve(strict=True)
        if not root.is_dir() or bulk_root.is_symlink():
            raise ValueError("bulk root must be a real directory")
        if recordings.root != root or artifacts.root != root:
            raise ValueError("catalog presentation stores must share the configured bulk root")
        self._catalog = catalog
        self._recordings = recordings
        self._artifacts = artifacts
        self._bulk_root = root

    def search_recordings(
        self,
        *,
        query: str | None,
        include_test: bool,
        analysis_state: AnalysisStateV1 | None,
        storage_state: StorageStateV1 | None,
        held: bool | None,
        tag: str | None,
        cursor: int,
        limit: int,
    ) -> RecordingSearchResponseV1:
        needle = query.casefold().strip() if query else None
        matches = []
        for snapshot in self._catalog.presentation_snapshots():
            if snapshot.source_type == "test" and not include_test:
                continue
            if held is not None and (snapshot.hold_reason is not None) is not held:
                continue
            if tag is not None and tag not in snapshot.tags:
                continue
            detail = self._detail(snapshot)
            if detail is None:
                continue
            if analysis_state is not None and detail.analysis.state is not analysis_state:
                continue
            if storage_state is not None and detail.storage_state is not storage_state:
                continue
            if (
                needle
                and needle
                not in " ".join(
                    (detail.session_id, detail.title, detail.profile.name, *detail.tags)
                ).casefold()
            ):
                continue
            matches.append(recording_summary_v1(detail))
        ordered = sorted(matches, key=lambda item: item.started_at, reverse=True)
        selected = tuple(ordered[cursor : cursor + limit])
        candidate_cursor = cursor + len(selected)
        return RecordingSearchResponseV1(
            items=selected,
            total=len(ordered),
            next_cursor=candidate_cursor if candidate_cursor < len(ordered) else None,
        )

    def recording_detail(self, session_id: str) -> RecordingDetailV1 | None:
        snapshot = self._catalog.presentation_snapshot(session_id)
        return None if snapshot is None else self._detail(snapshot)

    def product(self, product_id: str) -> AnalysisProductV1 | None:
        match = _PRODUCT_ID.fullmatch(product_id)
        if match is None:
            return None
        numeric_id = int(match.group(1))
        snapshot = self._catalog.presentation_snapshot_for_product(numeric_id)
        if snapshot is None:
            return None
        detail = self._detail(snapshot)
        if detail is None:
            return None
        return next((item for item in detail.products if item.product_id == product_id), None)

    def status(self) -> SystemStatusV1:
        filesystem = os.statvfs(self._bulk_root)
        total_bytes = filesystem.f_frsize * filesystem.f_blocks
        available_bytes = filesystem.f_frsize * filesystem.f_bavail
        used_bytes = total_bytes - available_bytes
        used_fraction = used_bytes / total_bytes
        if used_fraction >= ADMISSION_STOP_WATERMARK:
            admission_state: Literal["open", "warning", "stopped"] = "stopped"
        elif used_fraction >= HIGH_WATERMARK:
            admission_state = "warning"
        else:
            admission_state = "open"
        backlog = self._catalog.backlog_snapshot()
        return SystemStatusV1(
            generated_at=datetime.now(UTC),
            storage=StorageStatusV1(
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                used_fraction=used_fraction,
                retention_high_watermark=HIGH_WATERMARK,
                retention_low_watermark=LOW_WATERMARK,
                admission_state=admission_state,
            ),
            backlog=BacklogStatusV1(
                queued=backlog.queued,
                running=backlog.running,
                failed=backlog.failed,
                oldest_queued_seconds=backlog.oldest_queued_seconds,
            ),
        )

    def _detail(self, snapshot: CatalogSessionReadSnapshot) -> RecordingDetailV1 | None:
        manifest_and_root = self._manifest(snapshot)
        if manifest_and_root is None:
            return None
        manifest, recording_root = manifest_and_root
        profile = manifest.capture_plan.profile_revision.profile
        dwell_seconds = manifest.capture_plan.resolved_sample_count / profile.sample_rate_hz
        storage_state = (
            StorageStateV1.PURGED if snapshot.state == "purged" else StorageStateV1.AVAILABLE
        )
        analysis, coverage = _analysis_summary(snapshot.analysis, dwell_seconds)
        products = self._products(snapshot, dwell_seconds)
        documents = {
            product.product_id: self._read_product_document(snapshot.analysis, product.product_id)
            for product in products
        }
        quality = _quality_summary(snapshot.analysis, products, documents, manifest)
        power = _power_series(products, documents)
        whole_dwell = _whole_dwell(snapshot.analysis, products, documents)
        analysis_root = _analysis_root(snapshot.analysis, self._artifacts)
        return RecordingDetailV1(
            session_id=snapshot.session_id,
            title=profile.description or profile.name,
            started_at=datetime.fromtimestamp(manifest.created_utc_ns / 1_000_000_000, UTC),
            duration_seconds=dwell_seconds,
            source_type=SourceTypeV1(snapshot.source_type.upper()),
            tags=snapshot.tags,
            hold=HoldV1(
                held=snapshot.hold_reason is not None,
                reason=snapshot.hold_reason,
            ),
            capture_health=_capture_health(manifest),
            storage_state=storage_state,
            profile=CaptureProfileV1(
                profile_id=manifest.capture_plan.profile_revision.revision_digest,
                name=profile.name,
                revision=1,
                sample_rate_hz=profile.sample_rate_hz,
                bandwidth_hz=profile.bandwidth_hz,
                dwell_seconds=dwell_seconds,
                center_frequency_hz=(profile.rf_center_frequency_hz or profile.center_frequency_hz),
                receiver_count_per_radio=len(profile.receivers),
            ),
            radios=tuple(
                _radio_stream(stream, recording_root, storage_state) for stream in manifest.streams
            ),
            synchronization=_synchronization(manifest),
            paths=RecordingPathsV1(
                recording_root=str(recording_root),
                manifest_path=str(recording_root / "manifest.json"),
                analysis_root=None if analysis_root is None else str(analysis_root),
            ),
            analysis=analysis.model_copy(update={"product_count": len(products)}),
            quality=quality,
            power=power,
            detection=_detection(snapshot.analysis, snapshot.tags, products, documents),
            whole_dwell=whole_dwell,
            qam=_qam(snapshot.analysis, products, documents),
            doppler=_doppler(snapshot.analysis, products, documents),
            provenance=_provenance(snapshot, coverage, products, documents),
            products=products,
        )

    def _manifest(
        self, snapshot: CatalogSessionReadSnapshot
    ) -> tuple[RecordingManifestV1, Path] | None:
        if snapshot.bundle_uri is not None:
            try:
                bundle = self._recordings.inspect_uri(snapshot.bundle_uri)
            except (OSError, RecordingStoreError):
                bundle = None
            if bundle is not None:
                if bundle.session_id != snapshot.session_id or (
                    snapshot.manifest_digest is not None
                    and snapshot.manifest_digest != bundle.manifest_sha256
                ):
                    return None
                return bundle.manifest, bundle.path
        tombstone = snapshot.attributes.get("recording_manifest")
        recording_root = snapshot.attributes.get("recording_root")
        if not isinstance(tombstone, dict) or not isinstance(recording_root, str):
            return None
        try:
            path = Path(recording_root)
            if not path.is_absolute():
                return None
            path.resolve(strict=False).relative_to(self._bulk_root)
            return RecordingManifestV1.model_validate(tombstone), path
        except (ValueError, TypeError):
            return None

    def _products(
        self,
        snapshot: CatalogSessionReadSnapshot,
        dwell_seconds: float,
    ) -> tuple[AnalysisProductV1, ...]:
        run = snapshot.analysis
        if run is None or not run.is_current:
            return ()
        output = []
        expected_root = self._bulk_root / "analysis" / snapshot.session_id / run.run_id
        for product in run.products:
            kind = _PRESENTATION_KIND_MAP.get(product.kind)
            if (
                not product.available
                or kind is None
                or product.media_type != "application/json"
                or not 0 < product.byte_size <= _MAX_PRESENTATION_PRODUCT_BYTES
            ):
                continue
            try:
                path = self._artifacts.resolver.resolve(product.logical_uri, must_exist=True)
                path.relative_to(expected_root)
            except (OSError, ValueError):
                continue
            if not path.is_file() or path.stat().st_size != product.byte_size:
                continue
            digest = _bare_digest(product.digest)
            if digest is None:
                continue
            output.append(
                AnalysisProductV1(
                    product_id=f"ap-{product.product_id}",
                    session_id=snapshot.session_id,
                    analysis_run_id=run.run_id,
                    kind=cast(
                        Literal[
                            "quality",
                            "power",
                            "waterfall",
                            "detection",
                            "qam",
                            "doppler",
                            "controls",
                            "overlays",
                            "provenance",
                        ],
                        kind,
                    ),
                    status=_product_status(product.status),
                    content_type="application/json",
                    artifact_path=str(path),
                    byte_count=product.byte_size,
                    sha256=digest,
                    coverage=_coverage(product.coverage, dwell_seconds),
                    summary={
                        **product.summary,
                        "stage_key": product.stage_key,
                        "scope_key": product.scope_key,
                        "scientific_kind": product.kind,
                    },
                )
            )
        return tuple(output)

    def _read_product_document(
        self,
        run: CatalogRunReadSnapshot | None,
        product_id: str,
    ) -> dict[str, Any] | None:
        if run is None:
            return None
        numeric_id = int(product_id.removeprefix("ap-"))
        source = next((item for item in run.products if item.product_id == numeric_id), None)
        if source is None or not source.available:
            return None
        try:
            return self._artifacts.read_json(source.logical_uri, source.digest)
        except (OSError, ArtifactStoreError):
            return None


def _analysis_summary(
    run: CatalogRunReadSnapshot | None,
    dwell_seconds: float,
) -> tuple[AnalysisSummaryV1, CoverageV1 | None]:
    if run is None:
        return (
            AnalysisSummaryV1(
                state=AnalysisStateV1.NO_RESULT,
                current_run=None,
                no_result_reason="No analysis run has been created",
            ),
            None,
        )
    coverage_value = (
        run.summary.coverage
        if run.summary is not None
        else min(
            (item.coverage for item in run.products if item.coverage is not None),
            default=None,
        )
    )
    coverage = _coverage(coverage_value, dwell_seconds)
    outcomes = {item.outcome for item in run.jobs if item.outcome is not None}
    if not run.is_current:
        if run.state == "failed":
            return (
                AnalysisSummaryV1(
                    state=AnalysisStateV1.FAILED,
                    current_run=None,
                    failure_reason=run.failure or "Analysis run failed",
                ),
                coverage,
            )
        state = AnalysisStateV1.RUNNING if run.state == "running" else AnalysisStateV1.QUEUED
        return AnalysisSummaryV1(state=state, current_run=None, coverage=coverage), coverage
    if outcomes and outcomes <= {"no_result", "insufficient_data"}:
        return (
            AnalysisSummaryV1(
                state=AnalysisStateV1.NO_RESULT,
                current_run=CurrentRunV1(
                    run_id=run.run_id,
                    pipeline_release=run.pipeline_release_id,
                    state=AnalysisStateV1.NO_RESULT,
                    started_at=run.created_at,
                    finished_at=run.sealed_at,
                ),
                coverage=coverage,
                no_result_reason="The current pipeline produced no scientific result",
            ),
            coverage,
        )
    state = (
        AnalysisStateV1.PARTIAL
        if outcomes & {"partial_coverage", "insufficient_data"}
        else AnalysisStateV1.COMPLETE
    )
    return (
        AnalysisSummaryV1(
            state=state,
            current_run=CurrentRunV1(
                run_id=run.run_id,
                pipeline_release=run.pipeline_release_id,
                state=state,
                started_at=run.started_at or run.created_at,
                finished_at=run.sealed_at,
            ),
            coverage=coverage,
            product_count=len(run.products),
        ),
        coverage,
    )


def _coverage(value: float | None, dwell_seconds: float) -> CoverageV1 | None:
    if value is None or not 0.0 <= value <= 1.0:
        return None
    return CoverageV1(
        analyzed_fraction=value,
        analyzed_seconds=value * dwell_seconds,
        dwell_seconds=dwell_seconds,
        description=f"{value:.1%} of the declared recording dwell was analyzed",
    )


def _capture_health(manifest: RecordingManifestV1) -> CaptureHealthV1:
    if manifest.state is CaptureState.COMMITTED:
        return CaptureHealthV1.COMPLETE
    return CaptureHealthV1.PARTIAL


def _radio_stream(
    stream: RecordingStreamV1,
    recording_root: Path,
    storage_state: StorageStateV1,
) -> RadioStreamV1:
    settings = stream.applied_settings or stream.requested_settings
    gains = {item.receiver_id: item.gain_db for item in settings.gains}
    if stream.state is StreamState.COMPLETE:
        state = CaptureHealthV1.COMPLETE
    elif stream.state is StreamState.PARTIAL:
        state = CaptureHealthV1.PARTIAL
    else:
        state = CaptureHealthV1.FAILED
    raw_path = None
    if storage_state is StorageStateV1.AVAILABLE and stream.chunks:
        raw_path = str(recording_root / stream.chunks[0].relative_path)
    return RadioStreamV1(
        radio_id=stream.radio.radio_id,
        serial=stream.radio.serial,
        receiver_labels=tuple(f"rx{item}" for item in settings.receiver_ids),
        state=state,
        captured_samples=stream.captured_sample_count,
        sample_rate_hz=settings.sample_rate_hz,
        gain_db=tuple(gains.get(item, 0.0) for item in settings.receiver_ids),
        raw_path=raw_path,
        continuity_gaps=stream.continuity.gap_count,
        clipped_samples=stream.continuity.clipped_sample_count,
    )


def _synchronization(manifest: RecordingManifestV1) -> SynchronizationV1:
    summary = manifest.synchronization
    grade = {
        "not_requested": "not_requested",
        "best_effort_observed": "observed",
        "degraded": "degraded",
        "unavailable": "unavailable",
    }[summary.grade.value]
    methods = sorted(
        {
            stream.timing.first_sample.method.value
            for stream in manifest.streams
            if stream.timing is not None
        }
    )
    return SynchronizationV1(
        mode=summary.effective_mode.value,
        grade=cast(Literal["not_requested", "observed", "degraded", "unavailable"], grade),
        start_skew_ms=(
            None
            if summary.estimated_start_skew_ns is None
            else summary.estimated_start_skew_ns / 1e6
        ),
        skew_uncertainty_ms=(
            None
            if summary.start_skew_uncertainty_ns is None
            else summary.start_skew_uncertainty_ns / 1e6
        ),
        overlap_seconds=(
            None if summary.estimated_overlap_ns is None else summary.estimated_overlap_ns / 1e9
        ),
        overlap_fraction=summary.overlap_fraction,
        timing_basis=(", ".join(methods) if methods else "recording manifest timing unavailable"),
        phase_coherent=False,
    )


def _quality_summary(
    run: CatalogRunReadSnapshot | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
    manifest: RecordingManifestV1,
) -> QualitySummaryV1:
    product = next((item for item in products if item.kind == "quality"), None)
    if product is None:
        failed = run is not None and run.state == "failed"
        return QualitySummaryV1(
            state=ProductStatusV1.FAILED if failed else ProductStatusV1.NO_RESULT,
            clipped_fraction=None,
            constant_iq_refills=None,
            continuity_gaps=None,
            note="Quality analysis is unavailable",
        )
    document = documents.get(product.product_id)
    receivers = document.get("receivers") if document is not None else None
    fractions = []
    if isinstance(receivers, list):
        fractions = [
            float(item["clipped_complex_fraction"])
            for item in receivers
            if isinstance(item, dict)
            and isinstance(item.get("clipped_complex_fraction"), (int, float))
        ]
    return QualitySummaryV1(
        state=product.status,
        clipped_fraction=(sum(fractions) / len(fractions) if fractions else None),
        constant_iq_refills=sum(
            stream.continuity.constant_iq_refill_count for stream in manifest.streams
        ),
        continuity_gaps=sum(stream.continuity.gap_count for stream in manifest.streams),
        note=None if document is not None else "Quality artifact could not be verified",
    )


def _power_series(
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> tuple[SeriesV1, ...]:
    output = []
    for product in products:
        if product.kind != "power":
            continue
        document = documents.get(product.product_id)
        receivers = document.get("receivers") if document is not None else None
        if not isinstance(receivers, list):
            continue
        for receiver in receivers:
            if not isinstance(receiver, dict):
                continue
            receiver_id = receiver.get("receiver_id")
            value = receiver.get("mean_power_dbfs")
            if isinstance(receiver_id, int) and isinstance(value, (int, float)):
                output.append(
                    SeriesV1(
                        series_id=f"power-{product.product_id}-rx{receiver_id}",
                        label=f"{product.summary['scope_key']} RX{receiver_id} mean power",
                        unit="dBFS",
                        points=(SeriesPointV1(time_s=0.0, value=float(value)),),
                        source_point_count=1,
                        decimated=False,
                    )
                )
    return tuple(output)


def _detection(
    run: CatalogRunReadSnapshot | None,
    tags: tuple[str, ...],
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> DetectionSummaryV1:
    document = _current_document(run, products, documents, "detection")
    if document is not None:
        candidates = document.get("candidates")
        returned = candidates if isinstance(candidates, list) else []
        best = max(
            (item for item in returned if isinstance(item, dict)),
            key=lambda item: _number(item.get("margin")) or -math.inf,
            default=None,
        )
        candidate_count = _integer(document.get("candidate_count")) or 0
        return DetectionSummaryV1(
            state=DetectionStateV1.CANDIDATE if candidate_count else DetectionStateV1.NONE,
            known_pilot_candidate=bool(document.get("known_pilot_candidate")),
            calibrated_detection=bool(document.get("calibrated_detection")),
            qin_score=None if best is None else _number(best.get("verify_score")),
            control_score=None if best is None else _number(best.get("control_score")),
            reason=str(document.get("confidence_reason") or "Candidate evidence unavailable"),
        )
    fallback_count = None if run is None or run.summary is None else run.summary.candidate_count
    candidate = fallback_count is not None and fallback_count > 0
    return DetectionSummaryV1(
        state=DetectionStateV1.CANDIDATE if candidate else DetectionStateV1.NOT_RUN,
        known_pilot_candidate="KNOWN_PILOT_CANDIDATE" in tags,
        calibrated_detection=False,
        qin_score=None,
        control_score=None,
        reason=(
            f"Current analysis reports {fallback_count} candidate(s)"
            if candidate
            else "Starlink detection has not produced a candidate summary"
        ),
    )


def _whole_dwell(
    run: CatalogRunReadSnapshot | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> WholeDwellSummaryV1:
    detection = _current_document(run, products, documents, "detection")
    controls = _current_document(run, products, documents, "controls")
    if detection is None or controls is None or run is None:
        return _empty_whole_dwell()
    try:
        raw_candidates = detection.get("candidates")
        candidates = tuple(
            CandidateLineageV1.model_validate(item)
            for item in (raw_candidates if isinstance(raw_candidates, list) else [])[:256]
        )
        raw_coverage = detection.get("candidate_coverage")
        coverage = (
            CandidateCoverageV1.model_validate(raw_coverage)
            if isinstance(raw_coverage, dict)
            else None
        )
        reasons = controls.get("reasons")
        control = ControlSummaryV1(
            state=_product_status(str(controls.get("state", "failed"))),
            thresholds_calibrated=bool(controls.get("thresholds_calibrated")),
            specificity_claimed=bool(controls.get("specificity_claimed")),
            passed_candidate_count=_integer(controls.get("passed_candidate_count")) or 0,
            best_held_out_margin=_number(controls.get("best_held_out_margin")),
            best_surrogate_margin=_number(controls.get("best_surrogate_margin")),
            rejection_reasons=tuple(str(item) for item in reasons if isinstance(item, str))
            if isinstance(reasons, list)
            else (),
            reason=str(controls.get("reason") or "Control evidence unavailable"),
        )
        candidate_count = _integer(detection.get("candidate_count")) or 0
        returned_count = len(candidates)
        return WholeDwellSummaryV1(
            analysis_run_id=run.run_id,
            compute_tier=ComputeTierV1(str(detection.get("compute_tier"))),
            confidence=ScientificConfidenceV1(str(detection.get("confidence"))),
            confidence_reason=str(
                detection.get("confidence_reason") or "Scientific confidence unavailable"
            ),
            candidate_count=candidate_count,
            returned_candidate_count=returned_count,
            candidate_lineage_truncated=candidate_count > returned_count,
            candidate_coverage=coverage,
            candidates=candidates,
            controls=control,
        )
    except (TypeError, ValueError):
        return _empty_whole_dwell()


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


def _qam(
    run: CatalogRunReadSnapshot | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> QamSummaryV1:
    document = _current_document(run, products, documents, "qam")
    if document is not None:
        raw_receivers = document.get("receiver_metrics")
        try:
            receivers = tuple(
                ReceiverQamSummaryV1.model_validate(item)
                for item in (raw_receivers if isinstance(raw_receivers, list) else [])
            )
        except (TypeError, ValueError):
            receivers = ()
        combined_accuracy = _number(document.get("combined_accuracy"))
        combined_evm = _number(document.get("combined_rms_evm"))
        combined_frames = _integer(document.get("combined_frame_count"))
        return QamSummaryV1(
            state=_product_status(str(document.get("state", "failed"))),
            combined_accuracy=combined_accuracy,
            receiver_accuracy=tuple(item.accuracy for item in receivers),
            rms_evm=combined_evm,
            frame_count=combined_frames or max((item.frame_count for item in receivers), default=0),
            receiver_metrics=receivers,
        )
    accuracy = None if run is None or run.summary is None else run.summary.best_qam_accuracy
    return QamSummaryV1(
        state=ProductStatusV1.COMPLETE if accuracy is not None else ProductStatusV1.NO_RESULT,
        combined_accuracy=accuracy,
        receiver_accuracy=(),
        rms_evm=None,
        frame_count=0,
    )


def _doppler(
    run: CatalogRunReadSnapshot | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> DopplerSummaryV1:
    document = _current_document(run, products, documents, "doppler")
    if document is not None:
        tle = document.get("tle")
        tle_document = tle if isinstance(tle, dict) else {}
        association = str(tle_document.get("status", "unavailable"))
        if association not in {"candidate", "unavailable", "no_match", "failed"}:
            association = "failed"
        return DopplerSummaryV1(
            state=_product_status(str(document.get("state", "failed"))),
            slope_hz_per_s=_number(document.get("slope_hz_s")),
            baseband_cfo_at_reference_hz=_number(document.get("baseband_cfo_at_reference_hz")),
            receiver_tuned_center_hz=_number(document.get("receiver_tuned_center_hz")),
            tuned_signal_frequency_at_reference_hz=_number(
                document.get("tuned_signal_frequency_at_reference_hz")
            ),
            frequency_span_hz=_number(document.get("frequency_span_hz")),
            correlation=None,
            residual_rms_hz=_number(document.get("residual_rms_hz")),
            point_count=_integer(document.get("point_count")) or 0,
            motion_class=cast(
                Literal["dynamic", "stationary_confounder", "indeterminate"] | None,
                document.get("motion_class"),
            ),
            confidence=ScientificConfidenceV1(str(document.get("confidence", "unassessed"))),
            tle_candidate=(
                str(tle_document["object_id"])
                if isinstance(tle_document.get("object_id"), str)
                else None
            ),
            association_status=cast(
                Literal["not_run", "candidate", "unavailable", "no_match", "failed"],
                association,
            ),
        )
    slope = None if run is None or run.summary is None else run.summary.doppler_slope_hz_s
    return DopplerSummaryV1(
        state=ProductStatusV1.COMPLETE if slope is not None else ProductStatusV1.NO_RESULT,
        slope_hz_per_s=slope,
        frequency_span_hz=None,
        correlation=None,
        tle_candidate=None,
        association_status="not_run",
    )


def _provenance(
    snapshot: CatalogSessionReadSnapshot,
    coverage: CoverageV1 | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
) -> ProvenanceV1:
    run = snapshot.analysis
    recording_digest = _bare_digest(snapshot.manifest_digest or "") or "0" * 64
    limitations: list[str] = []
    if coverage is not None and coverage.analyzed_fraction < 1.0:
        limitations.append("partial-coverage")
    if run is not None:
        limitations.extend(
            sorted(
                {
                    item.outcome
                    for item in run.jobs
                    if item.outcome is not None and item.outcome != "complete"
                }
            )
        )
    document = _current_document(run, products, documents, "provenance")
    if document is not None:
        raw_limitations = document.get("limitation_codes")
        if isinstance(raw_limitations, list):
            limitations.extend(str(item) for item in raw_limitations if isinstance(item, str))
    return ProvenanceV1(
        analysis_run_id=None if run is None or not run.is_current else run.run_id,
        pipeline_release=None if run is None else run.pipeline_release_id,
        generated_at=None if run is None else run.sealed_at,
        config_digest=(
            (
                _bare_digest(str(document.get("pipeline_config_digest")))
                if document is not None
                else None
            )
            or (None if run is None else _bare_digest(canonical_digest(run.pipeline_configuration)))
        ),
        recording_digest=recording_digest,
        limitation_codes=tuple(dict.fromkeys(limitations)),
    )


def _current_document(
    run: CatalogRunReadSnapshot | None,
    products: tuple[AnalysisProductV1, ...],
    documents: dict[str, dict[str, Any] | None],
    kind: str,
) -> dict[str, Any] | None:
    if run is None or not run.is_current:
        return None
    product = next((item for item in products if item.kind == kind), None)
    if product is None or product.analysis_run_id != run.run_id:
        return None
    document = documents.get(product.product_id)
    if document is None or document.get("run_id") != run.run_id:
        return None
    return document


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _analysis_root(
    run: CatalogRunReadSnapshot | None,
    artifacts: AnalysisArtifactStore,
) -> Path | None:
    if run is None or not run.is_current or run.manifest_uri is None:
        return None
    try:
        return artifacts.resolver.resolve(run.manifest_uri, must_exist=True).parent
    except (OSError, ValueError):
        return None


def _product_status(value: str) -> ProductStatusV1:
    return {
        "complete": ProductStatusV1.COMPLETE,
        "partial": ProductStatusV1.PARTIAL,
        "partial_coverage": ProductStatusV1.PARTIAL,
        "insufficient_data": ProductStatusV1.PARTIAL,
        "insufficient": ProductStatusV1.PARTIAL,
        "failed": ProductStatusV1.FAILED,
        "no_result": ProductStatusV1.NO_RESULT,
    }.get(value, ProductStatusV1.FAILED)


def _bare_digest(value: str) -> str | None:
    candidate = value.removeprefix("sha256:")
    if len(candidate) != 64 or any(character not in "0123456789abcdef" for character in candidate):
        return None
    return candidate
