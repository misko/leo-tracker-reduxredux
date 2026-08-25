#!/usr/bin/env python3
"""Build the response-blind, exact-15 Doppler holdout feasibility manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.qam import (  # noqa: E402
    PilotFrameCfoConfig,
    estimate_edge_pilot_frame_cfo_even_evidence,
)
from leo.analysis.research.doppler_dataset_policy import (  # noqa: E402
    CaptureBinding,
    DopplerDatasetPolicy,
    authorize_capture,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from leo.analysis.research.doppler_holdout_manifest import (  # noqa: E402
    MANIFEST_SCHEMA,
    DerivedHoldoutEpisodeV1,
    DopplerHoldoutDerivedManifestV1,
    DopplerHoldoutFeasibilityProtocolV1,
    FrameMaskDispositionV1,
    HoldoutCaptureDispositionV1,
    InspectedProductV1,
    ScopeFeasibilityAuditV1,
    SelectedAliasTrajectoryV1,
    SelectedUpstreamSourceV1,
    SourceSupportPoint,
    SourceWindowAuditV1,
    best_source_supported_window,
    frame_opportunity_starts,
    load_holdout_protocol,
    maximum_contiguous_supported,
    validate_derived_holdout_manifest,
    validate_protocol_authority,
)
from leo.analysis.standard.codecs import decode_standard_product  # noqa: E402
from leo.analysis.standard.products import PILOT_SCAN_PRODUCT  # noqa: E402
from leo.artifacts import (  # noqa: E402
    AnalysisArtifactStore,
    AnalysisProductReceiptV1,
    AnalysisRunManifestV2,
    parse_analysis_run_manifest,
)
from leo.contracts.cfo_dealias import (  # noqa: E402
    CanonicalObservationV1,
    CfoAliasMapV2,
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV3,
    FinalTrajectoryV3,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.final_trajectory_reports import PathStandardReportV2  # noqa: E402
from leo.contracts.recording import RecordingManifestV1, RecordingStreamV2  # noqa: E402
from leo.contracts.states import StreamState, TimingMethod  # noqa: E402
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_POLICY = REPOSITORY_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
DEFAULT_PROTOCOL = REPOSITORY_ROOT / "config/analysis/doppler-holdout-feasibility-protocol-v1.json"
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "reports/figures/2026_08_25_doppler_holdout_feasibility"
SELECTOR_PATHS = (
    "config/analysis/doppler-holdout-feasibility-protocol-v1.json",
    "src/leo/analysis/qam/__init__.py",
    "src/leo/analysis/qam/pilot.py",
    "src/leo/analysis/research/doppler_holdout_manifest.py",
    "tools/build_doppler_holdout_feasibility.py",
)
EVEN_ESTIMATOR_PATH = REPOSITORY_ROOT / "src/leo/analysis/qam/pilot.py"
MANIFEST_CONTRACT_PATH = REPOSITORY_ROOT / "src/leo/analysis/research/doppler_holdout_manifest.py"
SYMBOL_ALIAS_SPACING_HZ = 1.0 / 4.4e-6


@dataclass(frozen=True, slots=True)
class InventoryRow:
    session_id: str
    recording_manifest_uri: str
    recording_manifest_digest: str
    analysis_run_id: str
    analysis_manifest_uri: str
    analysis_manifest_digest: str
    raw_integrity_attestation_id: str


@dataclass(frozen=True, slots=True)
class RawSource:
    source_id: str
    detection_time_s: float
    sample_start: int
    candidate_rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class CandidateEpisode:
    scope_key: str
    path_report: PathStandardReportV2
    stream: RecordingStreamV2
    edge: Literal["lower", "upper"]
    trajectory: FinalTrajectoryV3
    source_points: tuple[SourceSupportPoint, ...]
    sources: tuple[RawSource, ...]
    observation_by_source: dict[str, CanonicalObservationV1]
    median_source_margin: float
    audit: SourceWindowAuditV1


@dataclass(slots=True)
class CaptureWork:
    binding: CaptureBinding
    inventory: InventoryRow
    manifest: RecordingManifestV1
    analysis: AnalysisRunManifestV2
    bundle: PublishedBundle
    scopes: tuple[ScopeFeasibilityAuditV1, ...] = ()
    candidate: CandidateEpisode | None = None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _protocol_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if len(commit) != 40 or any(value not in "0123456789abcdef" for value in commit):
        raise ValueError("repository HEAD is not one exact Git commit")
    for relative in SELECTOR_PATHS:
        path = REPOSITORY_ROOT / relative
        frozen = subprocess.run(
            ("git", "show", f"HEAD:{relative}"),
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        if path.read_bytes() != frozen:
            raise ValueError(f"protocol implementation differs from HEAD: {relative}")
    return commit


def _load_inventory(
    path: Path,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> tuple[InventoryRow, ...]:
    with path.open(newline="", encoding="utf-8") as source:
        by_session = {row["capture_session_id"]: row for row in csv.DictReader(source)}
    rows = []
    for session_id in protocol.expected_capture_ids:
        row = by_session.get(session_id)
        if row is None:
            raise ValueError(f"holdout capture is absent from frozen inventory: {session_id}")
        rows.append(
            InventoryRow(
                session_id=session_id,
                recording_manifest_uri=row["recording_manifest_uri"],
                recording_manifest_digest=row["recording_manifest_digest"],
                analysis_run_id=row["analysis_run_id"],
                analysis_manifest_uri=row["analysis_manifest_uri"],
                analysis_manifest_digest=row["analysis_manifest_digest"],
                raw_integrity_attestation_id=row["raw_integrity_attestation_id"],
            )
        )
    return tuple(rows)


def _preflight(
    recording_store: RecordingStore,
    artifact_store: AnalysisArtifactStore,
    policy: DopplerDatasetPolicy,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
    inventory: tuple[InventoryRow, ...],
) -> tuple[CaptureWork, ...]:
    work = []
    for row in inventory:
        binding = policy.capture(row.session_id)
        bundle = recording_store.inspect_uri(row.recording_manifest_uri)
        if bundle.session_id != row.session_id or bundle.manifest_sha256 != (
            row.recording_manifest_digest
        ):
            raise ValueError(f"actual recording manifest disagrees: {row.session_id}")
        analysis_document, analysis_bytes = artifact_store.read_json_with_size(
            row.analysis_manifest_uri,
            row.analysis_manifest_digest,
        )
        analysis = parse_analysis_run_manifest(analysis_document)
        if not isinstance(analysis, AnalysisRunManifestV2):
            raise ValueError(f"holdout analysis manifest is not lane-explicit: {row.session_id}")
        if analysis_bytes <= 0 or (
            analysis.session_id,
            analysis.run_id,
            analysis.pipeline_lane,
            analysis.input_manifest_digest,
        ) != (
            row.session_id,
            row.analysis_run_id,
            "standard",
            row.recording_manifest_digest,
        ):
            raise ValueError(f"actual analysis manifest disagrees: {row.session_id}")
        authorize_capture(
            policy,
            experiment_role=protocol.experiment_role,
            session_id=row.session_id,
            recording_manifest_sha256=bundle.manifest_sha256,
            analysis_run_id=analysis.run_id,
            analysis_manifest_sha256=row.analysis_manifest_digest,
        )
        work.append(
            CaptureWork(
                binding=binding,
                inventory=row,
                manifest=bundle.manifest,
                analysis=analysis,
                bundle=bundle,
            )
        )
    return tuple(work)


def _product_map(
    analysis: AnalysisRunManifestV2,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> dict[str, dict[str, AnalysisProductReceiptV1]]:
    required = {
        (item.stage_key, item.kind, item.schema_version) for item in protocol.product_requirements
    }
    by_scope: dict[str, dict[str, AnalysisProductReceiptV1]] = {}
    for product in analysis.products:
        identity = (product.stage_key, product.kind, product.product_schema_version)
        if identity not in required:
            continue
        scope = by_scope.setdefault(product.scope_key, {})
        if product.kind in scope:
            raise ValueError("analysis manifest duplicates a required path product")
        scope[product.kind] = product
    expected_kinds = {item.kind for item in protocol.product_requirements}
    incomplete = {
        scope_key: tuple(sorted(expected_kinds - set(products)))
        for scope_key, products in by_scope.items()
        if set(products) != expected_kinds
    }
    if incomplete:
        raise ValueError(f"required path-product scope is incomplete: {incomplete}")
    if not by_scope:
        raise ValueError("analysis manifest has no scope with the complete frozen products")
    return by_scope


def _read_product(
    artifacts: AnalysisArtifactStore,
    receipt: AnalysisProductReceiptV1,
) -> tuple[dict[str, Any], InspectedProductV1]:
    document, byte_size = artifacts.read_json_with_size(receipt.logical_uri, receipt.digest)
    if byte_size != receipt.byte_size:
        raise ValueError("inspected product byte count disagrees with sealed receipt")
    if receipt.role != "scientific" or receipt.media_type != "application/json":
        raise ValueError("inspected product receipt weakens the frozen scientific JSON role")
    return document, InspectedProductV1(
        product_id=receipt.product_id,
        stage_key=receipt.stage_key,
        scope_key=receipt.scope_key,
        kind=receipt.kind,
        schema_version=receipt.product_schema_version,
        role="scientific",
        status=receipt.status,
        media_type="application/json",
        logical_uri=receipt.logical_uri,
        artifact_sha256=receipt.digest,
        artifact_bytes=receipt.byte_size,
        document_content_digest=canonical_digest(document),
    )


def _edge_for_stream(
    manifest: RecordingManifestV1,
    stream_id: str,
) -> Literal["lower", "upper"]:
    prefix = f"tuning:{stream_id}:"
    matches = [tag for tag in manifest.tags if tag.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("recording manifest lacks one exact stream tuning tag")
    parts = matches[0].split(":")
    if len(parts) != 4 or parts[3] not in {"lower", "upper"}:
        raise ValueError("recording stream tuning tag is malformed")
    return "lower" if parts[3] == "lower" else "upper"


def _lossless_stream(
    manifest: RecordingManifestV1,
    path: PathStandardReportV2,
    *,
    recording_manifest_digest: str,
) -> RecordingStreamV2:
    raw = path.raw_report
    streams = [item for item in manifest.streams if item.stream_id == raw.stream_id]
    if len(streams) != 1 or not isinstance(streams[0], RecordingStreamV2):
        raise ValueError("selected path lacks one V2 recording stream")
    stream = streams[0]
    continuity = stream.continuity
    if (
        stream.radio.radio_id != raw.radio_id
        or raw.manifest_digest != recording_manifest_digest
        or stream.state is not StreamState.COMPLETE
        or stream.timing is None
        or stream.timing.first_sample.method is not TimingMethod.DEVICE_COUNTER_ANCHORED
        or not continuity.sample_loss_observable
        or continuity.observed_sample_count != stream.captured_sample_count
        or continuity.device_span_sample_count != stream.captured_sample_count
        or continuity.segment_count != 1
        or continuity.gap_count != 0
        or continuity.missing_sample_count != 0
        or continuity.overflow_count != 0
        or continuity.enqueue_failure_count != 0
        or continuity.clipped_sample_count != 0
        or continuity.constant_iq_refill_count != 0
        or continuity.terminal_rejected_gap_count != 0
        or continuity.terminal_rejected_missing_sample_count != 0
        or continuity.terminal_rejected_overflow_count != 0
    ):
        raise ValueError("selected path is not one counter-authoritative lossless stream")
    return stream


def _raw_sources(scan: dict[str, Any]) -> dict[str, RawSource]:
    output = {}
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            matches = [score for score in candidate["scores"] if score["method"] == "glrt64"]
            if len(matches) != 1 or matches[0]["control_score"] is None:
                raise ValueError("pilot candidate lacks one exact GLRT64 source score")
            score = matches[0]
            source_id = canonical_digest(
                {
                    "sample_start": int(detection["sample_start"]),
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            output[source_id] = RawSource(
                source_id=source_id,
                detection_time_s=float(detection["time_s"]),
                sample_start=int(detection["sample_start"]),
                candidate_rank=int(candidate["rank"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                tracking_cfo_hz=float(score["tracking_cfo_hz"]),
                exact_score=float(score["exact_score"]),
                control_score=float(score["control_score"]),
                margin=float(score["margin"]),
            )
    return output


def _median(values: tuple[float, ...]) -> float:
    ordered = tuple(sorted(values))
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else 0.5 * (ordered[middle - 1] + ordered[middle])


def _scope_candidates(
    *,
    scope_key: str,
    path: PathStandardReportV2,
    stream: RecordingStreamV2,
    edge: Literal["lower", "upper"],
    scan: dict[str, Any],
    alias_map: CfoAliasMapV2,
    dealiased: DealiasedTrajectoryBankV4,
    final: FinalTrajectoryBankV3,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> tuple[tuple[SourceWindowAuditV1, ...], tuple[CandidateEpisode, ...]]:
    if (
        alias_map.pilot_scan_digest != canonical_digest(scan)
        or dealiased.alias_map_digest != alias_map.content_digest
        or final.dealiased_bank_digest != dealiased.content_digest
        or path.cfo_alias_map_digest != alias_map.content_digest
        or path.dealiased_trajectory_bank_digest != dealiased.content_digest
        or path.final_trajectory_bank_digest != final.content_digest
    ):
        raise ValueError("inspected Standard source/alias/final closure disagrees")
    sources = _raw_sources(scan)
    observations = {item.observation_id: item for item in dealiased.observations}
    branches = {item.branch_id: item for item in dealiased.branches}
    audits = []
    candidates: list[CandidateEpisode] = []
    for trajectory in final.trajectories:
        if not trajectory.automatic_correction_eligible:
            continue
        branch = branches.get(trajectory.branch_id)
        if branch is None or trajectory.observation_ids != branch.observation_ids:
            raise ValueError("final trajectory and dealiased branch membership disagree")
        selected_points = []
        selected_sources = []
        observation_by_source: dict[str, CanonicalObservationV1] = {}
        for observation_id in branch.observation_ids:
            observation = observations.get(observation_id)
            if observation is None or len(observation.source_observation_ids) != 1:
                raise ValueError("canonical observation lacks one exact raw source")
            source_id = observation.source_observation_ids[0]
            source = sources.get(source_id)
            if source is None or (
                observation.sample_start != source.sample_start
                or not math.isclose(
                    observation.raw_cfo_hz,
                    source.tracking_cfo_hz,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
            ):
                raise ValueError("canonical observation and raw GLRT source disagree")
            selected_points.append(
                SourceSupportPoint(
                    source_id=source_id,
                    observation_id=observation_id,
                    sample_start=source.sample_start,
                    margin=source.margin,
                )
            )
            selected_sources.append(source)
            observation_by_source[source_id] = observation
        window = best_source_supported_window(
            selected_points,
            sample_rate_hz=path.raw_report.sample_rate_hz,
            probe_samples=int(scan["probe_samples"]),
            selector=protocol.source_episode_selector,
        )
        points_for_audit = window or tuple(
            sorted(selected_points, key=lambda item: item.sample_start)
        )
        if not points_for_audit:
            continue
        start = points_for_audit[0].sample_start
        stop = points_for_audit[-1].sample_start + int(scan["probe_samples"])
        margins = tuple(item.margin for item in points_for_audit)
        candidate_id = canonical_digest(
            {
                "scope_key": scope_key,
                "trajectory_id": trajectory.trajectory_id,
                "branch_id": trajectory.branch_id,
                "source_ids": [item.source_id for item in points_for_audit],
                "source_start_sample": start,
                "source_stop_sample": stop,
            }
        )
        audit = SourceWindowAuditV1(
            candidate_id=candidate_id,
            trajectory_id=trajectory.trajectory_id,
            branch_id=trajectory.branch_id,
            source_start_sample=start,
            source_stop_sample=stop,
            source_observation_count=len(points_for_audit),
            source_inventory_digest=canonical_digest(
                [item.model_dump(mode="json") for item in points_for_audit]
            ),
            median_source_margin=_median(margins),
            evaluated_probe_count=trajectory.evaluated_probe_count,
            status="eligible" if window else "rejected",
            reason="source_supported_window" if window else "source_window_below_protocol_minimum",
        )
        audits.append(audit)
        if not window:
            continue
        chosen_ids = {item.source_id for item in window}
        chosen_sources = tuple(
            sorted(
                (item for item in selected_sources if item.source_id in chosen_ids),
                key=lambda item: item.sample_start,
            )
        )
        candidates.append(
            CandidateEpisode(
                scope_key=scope_key,
                path_report=path,
                stream=stream,
                edge=edge,
                trajectory=trajectory,
                source_points=window,
                sources=chosen_sources,
                observation_by_source=observation_by_source,
                median_source_margin=_median(tuple(item.margin for item in chosen_sources)),
                audit=audit,
            )
        )
    return tuple(audits), tuple(candidates)


def _inspect_capture_products(
    work: CaptureWork,
    artifacts: AnalysisArtifactStore,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> None:
    scopes: list[ScopeFeasibilityAuditV1] = []
    candidates: list[CandidateEpisode] = []
    required = tuple(item.kind for item in protocol.product_requirements)
    for scope_key, receipts in sorted(_product_map(work.analysis, protocol).items()):
        documents = {}
        inspected = []
        for kind in required:
            document, binding = _read_product(artifacts, receipts[kind])
            documents[kind] = document
            inspected.append(binding)
        path = PathStandardReportV2.model_validate(documents["standard.path-report"])
        decode_standard_product(PILOT_SCAN_PRODUCT, documents["standard.pilot-scan"])
        alias_map = CfoAliasMapV2.model_validate(documents["standard.cfo-alias-map"])
        dealiased = DealiasedTrajectoryBankV4.model_validate(
            documents["standard.dealiased-trajectory-bank"]
        )
        final = FinalTrajectoryBankV3.model_validate(documents["standard.final-trajectory-bank"])
        stream = _lossless_stream(
            work.manifest,
            path,
            recording_manifest_digest=work.bundle.manifest_sha256,
        )
        edge = _edge_for_stream(work.manifest, path.raw_report.stream_id)
        audits, scope_candidates = _scope_candidates(
            scope_key=scope_key,
            path=path,
            stream=stream,
            edge=edge,
            scan=documents["standard.pilot-scan"],
            alias_map=alias_map,
            dealiased=dealiased,
            final=final,
            protocol=protocol,
        )
        scopes.append(
            ScopeFeasibilityAuditV1(
                scope_key=scope_key,
                stream_id=path.raw_report.stream_id,
                radio_id=path.raw_report.radio_id,
                receiver_id=path.raw_report.receiver_id,
                edge=edge,
                sample_rate_hz=path.raw_report.sample_rate_hz,
                declared_sample_count=path.raw_report.declared_sample_count,
                products=tuple(inspected),
                source_windows=audits,
                status="eligible" if scope_candidates else "no_source_supported_episode",
                reason=(
                    "source_supported_episode_available"
                    if scope_candidates
                    else "no_source_window_meets_protocol"
                ),
            )
        )
        candidates.extend(scope_candidates)
    work.scopes = tuple(scopes)
    if candidates:
        work.candidate = min(candidates, key=_candidate_rank)


def _candidate_rank(value: CandidateEpisode) -> tuple[object, ...]:
    duration = value.audit.source_stop_sample - value.audit.source_start_sample
    return (
        -len(value.source_points),
        -duration,
        -value.median_source_margin,
        -value.trajectory.evaluated_probe_count,
        value.scope_key,
        value.trajectory.trajectory_id,
        value.audit.source_start_sample,
    )


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return np.asarray(
        (values[:, 0, 0].astype(float) + 1j * values[:, 0, 1].astype(float)) / (2**15),
        dtype=np.complex128,
    )


def _episode_from_even_evidence(
    work: CaptureWork,
    recording_store: RecordingStore,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> DerivedHoldoutEpisodeV1:
    candidate = work.candidate
    if candidate is None:
        raise ValueError("capture has no source-supported episode")
    path = candidate.path_report.raw_report
    sample_rate_hz = path.sample_rate_hz
    start_sample = candidate.audit.source_start_sample
    stop_sample = candidate.audit.source_stop_sample
    midpoint = 0.5 * (start_sample + stop_sample)
    source = min(
        candidate.sources,
        key=lambda item: (
            abs(item.sample_start - midpoint),
            -item.margin,
            -item.exact_score,
            item.source_id,
        ),
    )
    observation = candidate.observation_by_source[source.source_id]
    trajectory = candidate.trajectory
    source_bound_cfo_hz = (
        source.tracking_cfo_hz
        + (trajectory.alias_index - observation.alias_index) * SYMBOL_ALIAS_SPACING_HZ
    )
    model_at_source = float(
        np.polyval(
            trajectory.absolute_coefficients_hz,
            source.detection_time_s - trajectory.reference_time_s,
        )
    )
    if abs(source_bound_cfo_hz - model_at_source) > (
        protocol.even_qin_mask.residual_cfo_half_width_hz
    ):
        raise ValueError("selected source leaves the final trajectory CFO basin")
    epoch_sample = source.sample_start + source.local_epoch_sample
    frame_content = round(302 * sample_rate_hz * 4.4e-6)
    reference_offset_samples = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * 4.4e-6) * sample_rate_hz
    )
    starts = frame_opportunity_starts(
        epoch_sample=epoch_sample,
        sample_rate_hz=sample_rate_hz,
        device_sample_start=start_sample,
        device_sample_stop=stop_sample,
        frame_content_samples=frame_content,
    )
    if not starts:
        raise ValueError("source-supported episode has no complete frame opportunity")
    reader = recording_store.reader(work.bundle, path.stream_id, verify=True)
    if reader.sample_rate_hz != sample_rate_hz or path.receiver_id not in reader.receiver_ids:
        raise ValueError("digest-pinned IQ reader disagrees with selected Standard path")
    gap_map = reader.gap_map()
    if gap_map.segment_count != 1 or gap_map.missing_sample_count != 0:
        raise ValueError("digest-pinned IQ gap map is not one lossless segment")
    read_start = starts[0] - 1
    read_stop = starts[-1] + frame_content + 1
    device = reader.read_device_span(
        read_start,
        read_stop - read_start,
        receiver_ids=(path.receiver_id,),
    )
    samples = _complex_receiver(device.samples)
    settings = PilotFrameCfoConfig(
        residual_half_width_hz=protocol.even_qin_mask.residual_cfo_half_width_hz,
        minimum_exact_coherence=protocol.even_qin_mask.minimum_exact_coherence,
        minimum_coherence_margin=protocol.even_qin_mask.minimum_coherence_margin,
    )
    mask_rows = []
    for frame_start in starts:
        local = frame_start - read_start
        local_slice = slice(local - 1, local + frame_content + 1)
        valid = device.valid_samples[local_slice]
        segments = device.continuity_segment_ids[local_slice]
        continuity_safe = bool(np.all(valid) and len(set(segments.tolist())) == 1)
        reference_sample = float(frame_start + reference_offset_samples)
        if not continuity_safe:
            mask_rows.append(
                FrameMaskDispositionV1(
                    frame_start_sample=frame_start,
                    reference_sample=reference_sample,
                    continuity_segment_id=None,
                    status="unsupported",
                    rejection_reasons=("device_gap_or_segment_crossing",),
                    even_absolute_cfo_hz=None,
                    even_frequency_uncertainty_hz=None,
                    even_exact_coherence=None,
                    even_control_coherence=None,
                    even_coherence_margin=None,
                    even_search_boundary=False,
                )
            )
            continue
        reference_time_s = reference_sample / sample_rate_hz
        model_cfo_hz = float(
            source_bound_cfo_hz
            + np.polyval(
                trajectory.absolute_coefficients_hz,
                reference_time_s - trajectory.reference_time_s,
            )
            - model_at_source
        )
        evidence = estimate_edge_pilot_frame_cfo_even_evidence(
            samples[local_slice],
            sample_rate_hz,
            frame_start_sample=frame_start,
            acquisition_absolute_cfo_hz=model_cfo_hz,
            edge=candidate.edge,
            config=settings,
        )
        if evidence.odd_symbols_evaluated:
            raise AssertionError("even-only feasibility API opened a response fold")
        mask_rows.append(
            FrameMaskDispositionV1(
                frame_start_sample=frame_start,
                reference_sample=evidence.reference_sample,
                continuity_segment_id=int(segments[0]),
                status="supported" if evidence.training_supported else "unsupported",
                rejection_reasons=evidence.training_rejection_reasons,
                even_absolute_cfo_hz=evidence.absolute_cfo_hz,
                even_frequency_uncertainty_hz=evidence.frequency_uncertainty_hz,
                even_exact_coherence=evidence.exact_coherence,
                even_control_coherence=evidence.control_coherence,
                even_coherence_margin=evidence.coherence_margin,
                even_search_boundary=evidence.search_boundary,
            )
        )
    mask = tuple(mask_rows)
    supported = sum(item.status == "supported" for item in mask)
    support_fraction = supported / len(mask)
    contiguous = maximum_contiguous_supported(tuple(item.status == "supported" for item in mask))
    thresholds = protocol.even_qin_mask
    evaluable = (
        len(mask) >= thresholds.minimum_frame_opportunities
        and supported >= thresholds.minimum_supported_frames
        and support_fraction >= thresholds.minimum_support_fraction
        and contiguous >= thresholds.minimum_contiguous_supported_frames
    )
    selected_observation_ids = tuple(item.observation_id for item in candidate.source_points)
    selected_source_ids = tuple(item.source_id for item in candidate.source_points)
    source_binding = SelectedUpstreamSourceV1(
        source_id=source.source_id,
        detection_sample_start=source.sample_start,
        detection_time_s=source.detection_time_s,
        candidate_rank=source.candidate_rank,
        local_epoch_sample=source.local_epoch_sample,
        tracking_cfo_hz=source.tracking_cfo_hz,
        exact_score=source.exact_score,
        control_score=source.control_score,
        margin=source.margin,
        canonical_observation_id=observation.observation_id,
        observed_alias_index=observation.alias_index,
    )
    trajectory_binding = SelectedAliasTrajectoryV1(
        branch_id=trajectory.branch_id,
        trajectory_id=trajectory.trajectory_id,
        component_id=trajectory.component_id,
        final_alias_index=trajectory.alias_index,
        polynomial_degree=trajectory.polynomial_degree,
        reference_time_s=trajectory.reference_time_s,
        absolute_coefficients_hz=trajectory.absolute_coefficients_hz,
        trajectory_start_s=trajectory.start_s,
        trajectory_end_s=trajectory.end_s,
        source_observation_ids=selected_observation_ids,
        source_ids=selected_source_ids,
        source_support=candidate.source_points,
    )
    identity = {
        "scope_key": candidate.scope_key,
        "stream_id": path.stream_id,
        "radio_id": path.radio_id,
        "receiver_id": path.receiver_id,
        "edge": candidate.edge,
        "device_sample_start": start_sample,
        "device_sample_stop": stop_sample,
        "frame_epoch_sample": epoch_sample,
        "source": source_binding.model_dump(mode="json"),
        "alias_trajectory": trajectory_binding.model_dump(mode="json"),
    }
    return DerivedHoldoutEpisodeV1(
        episode_id=canonical_digest(identity),
        scope_key=candidate.scope_key,
        stream_id=path.stream_id,
        radio_id=path.radio_id,
        receiver_id=path.receiver_id,
        edge=candidate.edge,
        device_sample_start=start_sample,
        device_sample_stop=stop_sample,
        frame_epoch_sample=epoch_sample,
        source=source_binding,
        alias_trajectory=trajectory_binding,
        frame_opportunity_count=len(mask),
        supported_frame_count=supported,
        support_fraction=support_fraction,
        maximum_contiguous_supported_frames=contiguous,
        frame_mask_digest=canonical_digest([item.model_dump(mode="json") for item in mask]),
        frame_mask=mask,
        status="evaluable" if evaluable else "non_evaluable",
        reason="even_mask_meets_protocol" if evaluable else "even_mask_below_protocol_minimum",
    )


def _capture_disposition(
    work: CaptureWork,
    recording_store: RecordingStore,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
) -> HoldoutCaptureDispositionV1:
    if work.candidate is None:
        return HoldoutCaptureDispositionV1(
            session_id=work.binding.session_id,
            recording_manifest_sha256=work.binding.recording_manifest_sha256,
            analysis_run_id=work.binding.analysis_run_id,
            analysis_manifest_sha256=work.binding.analysis_manifest_sha256,
            recording_manifest_uri=work.inventory.recording_manifest_uri,
            analysis_manifest_uri=work.inventory.analysis_manifest_uri,
            raw_integrity_attestation_id=work.inventory.raw_integrity_attestation_id,
            scopes=work.scopes,
            episode=None,
            status="non_evaluable",
            failure_stage="source_selection",
            reason="no_source_supported_episode",
        )
    episode = _episode_from_even_evidence(work, recording_store, protocol)
    return HoldoutCaptureDispositionV1(
        session_id=work.binding.session_id,
        recording_manifest_sha256=work.binding.recording_manifest_sha256,
        analysis_run_id=work.binding.analysis_run_id,
        analysis_manifest_sha256=work.binding.analysis_manifest_sha256,
        recording_manifest_uri=work.inventory.recording_manifest_uri,
        analysis_manifest_uri=work.inventory.analysis_manifest_uri,
        raw_integrity_attestation_id=work.inventory.raw_integrity_attestation_id,
        scopes=work.scopes,
        episode=episode,
        status=episode.status,
        failure_stage="none" if episode.status == "evaluable" else "even_mask",
        reason=episode.reason,
    )


def _render_accounting(manifest: DopplerHoldoutDerivedManifestV1) -> bytes:
    labels = [item.session_id[-12:] for item in manifest.captures]
    opportunities = [
        item.episode.frame_opportunity_count if item.episode else 0 for item in manifest.captures
    ]
    supported = [
        item.episode.supported_frame_count if item.episode else 0 for item in manifest.captures
    ]
    figure = Figure(figsize=(13.5, 5.5), constrained_layout=True)
    axis = figure.subplots()
    positions = np.arange(len(labels))
    axis.bar(positions, opportunities, color="#cbd5e1", label="frame opportunities")
    colors = ["#16835d" if item.status == "evaluable" else "#c2413b" for item in manifest.captures]
    axis.bar(positions, supported, color=colors, label="even-Qin supported mask")
    axis.axhline(
        600,
        color="#4b5563",
        linestyle="--",
        linewidth=1.2,
        label="frozen minimum supported frames",
    )
    axis.set_xticks(positions, labels, rotation=45, ha="right")
    axis.set_ylabel("Frames")
    axis.set_title(
        f"Response-blind holdout feasibility: {manifest.evaluable_capture_count}/15 evaluable"
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="upper right")
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=170)
    return buffer.getvalue()


def _failure_ledger(manifest: DopplerHoldoutDerivedManifestV1) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "session_id",
            "status",
            "failure_stage",
            "reason",
            "scope_count",
            "frame_opportunity_count",
            "supported_frame_count",
            "support_fraction",
            "maximum_contiguous_supported_frames",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for item in manifest.captures:
        episode = item.episode
        writer.writerow(
            {
                "session_id": item.session_id,
                "status": item.status,
                "failure_stage": item.failure_stage,
                "reason": item.reason,
                "scope_count": len(item.scopes),
                "frame_opportunity_count": episode.frame_opportunity_count if episode else 0,
                "supported_frame_count": episode.supported_frame_count if episode else 0,
                "support_fraction": episode.support_fraction if episode else 0.0,
                "maximum_contiguous_supported_frames": (
                    episode.maximum_contiguous_supported_frames if episode else 0
                ),
            }
        )
    return buffer.getvalue().encode("utf-8")


def main() -> int:
    args = _arguments()
    started = time.monotonic()
    protocol_commit = _protocol_commit()
    policy_payload = args.policy.read_bytes()
    protocol_payload = args.protocol.read_bytes()
    policy = load_doppler_dataset_policy(args.policy)
    protocol = load_holdout_protocol(protocol_payload)
    policy_sha256 = _sha256_bytes(policy_payload)
    validate_protocol_authority(protocol, policy, policy_sha256=policy_sha256)
    inventory_path = verify_policy_inventory(policy, REPOSITORY_ROOT)
    inventory = _load_inventory(inventory_path, protocol)
    output = args.output_root.resolve()
    qnap = Path("/mnt/qnap01").resolve()
    if output == qnap or qnap in output.parents:
        raise ValueError("feasibility output cannot be written beneath read-only QNAP")

    pin = PinnedLocalRoot(args.bulk_root)
    recordings = RecordingStore.open_pinned(pin)
    artifacts = AnalysisArtifactStore.open_pinned(pin)
    try:
        work = _preflight(recordings, artifacts, policy, protocol, inventory)
        for item in work:
            _inspect_capture_products(item, artifacts, protocol)
        dispositions = tuple(_capture_disposition(item, recordings, protocol) for item in work)
    finally:
        artifacts.close()
        recordings.close()
        pin.close()

    evaluable = sum(item.status == "evaluable" for item in dispositions)
    values = {
        "schema": MANIFEST_SCHEMA,
        "phase": "feasibility_only",
        "protocol_repository_commit": protocol_commit,
        "dataset_policy_repository_commit": protocol.dataset_policy_repository_commit,
        "dataset_policy_sha256": protocol.dataset_policy_sha256,
        "protocol_configuration_sha256": _sha256_bytes(protocol_payload),
        "selector_implementation_sha256": _sha256(Path(__file__)),
        "even_estimator_implementation_sha256": _sha256(EVEN_ESTIMATOR_PATH),
        "manifest_contract_implementation_sha256": _sha256(MANIFEST_CONTRACT_PATH),
        "inventory_sha256": policy.inventory_sha256,
        "experiment_role": protocol.experiment_role,
        "future_odd_qin_outcomes_opened": False,
        "candidate_estimators_run": False,
        "upstream_source_and_epoch_conditioning": (protocol.upstream_source_and_epoch_conditioning),
        "guarded_full_frame_iq_loaded": True,
        "odd_qin_symbols_demodulated_or_scored": False,
        "capture_count": 15,
        "evaluable_capture_count": evaluable,
        "minimum_evaluable_capture_count": protocol.minimum_evaluable_capture_count,
        "launch_gate": (
            "pass" if evaluable >= protocol.minimum_evaluable_capture_count else "fail"
        ),
        "runtime_seconds": time.monotonic() - started,
        "captures": [item.model_dump(mode="json") for item in dispositions],
    }
    manifest = DopplerHoldoutDerivedManifestV1.model_validate(
        {**values, "manifest_digest": canonical_digest(values)}
    )
    validate_derived_holdout_manifest(manifest, protocol, policy)
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    ledger_bytes = _failure_ledger(manifest)
    png_bytes = _render_accounting(manifest)
    output.mkdir(parents=True, exist_ok=True)
    generated = {
        "derived_manifest": ("derived-manifest.json", manifest_bytes),
        "failure_ledger": ("failure-ledger.csv", ledger_bytes),
        "accounting_figure": ("feasibility-accounting.png", png_bytes),
    }
    for _, (name, payload) in generated.items():
        _atomic_write(output / name, payload)
    artifact_manifest = {
        "schema": "org.leo.research.doppler-holdout-feasibility-artifacts/v1",
        "phase": "feasibility_only",
        "future_odd_qin_outcomes_opened": False,
        "candidate_estimators_run": False,
        "upstream_source_and_epoch_conditioning": (protocol.upstream_source_and_epoch_conditioning),
        "guarded_full_frame_iq_loaded": True,
        "odd_qin_symbols_demodulated_or_scored": False,
        "artifacts": {
            key: {"path": name, "bytes": len(payload), "sha256": _sha256_bytes(payload)}
            for key, (name, payload) in generated.items()
        },
    }
    _atomic_write(output / "artifact-manifest.json", _json_bytes(artifact_manifest))
    print(
        json.dumps(
            {
                "protocol_commit": protocol_commit,
                "capture_count": 15,
                "evaluable_capture_count": evaluable,
                "launch_gate": manifest.launch_gate,
                "runtime_seconds": manifest.runtime_seconds,
                "output_root": str(output),
            },
            sort_keys=True,
        )
    )
    return 0 if manifest.launch_gate == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
