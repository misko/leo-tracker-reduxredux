#!/usr/bin/env python3
"""Prototype refill-safe contiguous Qin frame recovery on three pinned dwells.

This is an additive research runner, not a persisted product.  It reads one
predeclared 500 ms interval per dwell, treats every Pluto refill as a hard
state boundary, and selects one acquisition anchor independently inside each
refill-safe segment.  Frame membership and tracking use even Qin symbols;
odd Qin symbols remain held out for causal one-step scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.research.continuous_frame_recovery import (
    ContinuousFrameRecoveryResult,
    FrameOpportunityOutcome,
    FrameRecoveryAnchor,
    FrameRecoveryConfig,
    RecoveredFrame,
    recover_contiguous_frames,
)
from leo.analysis.starlink.templates import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_INPUTS = Path("config/analysis/continuous-frame-recovery-three-dwell-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_continuous_frame_recovery_prototype")
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
GLRT_PROBE_DURATION_S = 0.020
MINIMUM_ANCHOR_MARGIN = 0.05
_TOP_LEVEL_FIELDS = {
    "schema",
    "description",
    "selection_lock",
    "common_geometry",
    "continuity_policy",
    "dwells",
}
_SELECTION_FIELDS = {
    "outcome_blinded",
    "new_frame_cfo_outcomes_used",
    "source_plot_summary_path",
    "source_plot_summary_sha256",
    "interval_rule",
    "anchor_rule",
    "anchor_identity_rule",
}
_GEOMETRY_FIELDS = {
    "sample_rate_hz",
    "interval_duration_s",
    "interval_sample_count",
    "interval_semantics",
    "frame_rate_hz",
    "nominal_frame_period_samples",
    "nominal_frame_period_s",
    "nominal_frame_opportunities_per_interval",
    "full_frame_alignment_ambiguity_s",
    "full_frame_alignment_ambiguity_samples",
    "phase_policy",
}
_CONTINUITY_POLICY_FIELDS = {
    "required_segment_count",
    "require_counter_authoritative_sample_loss",
    "require_zero_gap_missing_overflow_clip_and_constant_iq_counts",
    "refill_interpretation",
}
_DWELL_FIELDS = {
    "label",
    "session_id",
    "run_id",
    "scope_sha256",
    "stream_id",
    "radio_id",
    "receiver_id",
    "channel",
    "edge",
    "rf_hz",
    "recording_root",
    "recording_manifest",
    "analysis_manifest",
    "pilot_scan",
    "sealed_seed_document",
    "interval",
    "prior_visible_gap",
    "initial_anchor",
    "continuity_evidence",
    "iq_chunks",
}
_CHUNK_FIELDS = {
    "path",
    "chunk_index",
    "sample_start",
    "sample_end",
    "compressed_sha256",
    "uncompressed_sha256",
}
_INTERVAL_FIELDS = {"sample_start", "sample_end", "time_start_s", "time_end_s"}
_PRIOR_GAP_FIELDS = {
    "plot_zoom_s",
    "sample_start",
    "sample_end",
    "time_start_s",
    "time_end_s",
    "duration_samples",
    "duration_s",
    "left_seed_bin_index",
    "left_replay_sample_start",
    "left_replay_sample_end",
    "right_seed_bin_index",
    "right_replay_sample_start",
    "basis",
}
_INITIAL_ANCHOR_FIELDS = {
    "role",
    "seed_bin_index",
    "source_detection_index",
    "probe_index",
    "candidate_rank",
    "source_identity",
    "alias_identity",
    "source_sample_start",
    "source_time_s",
    "observation_center_time_s",
    "epoch_sample",
    "absolute_epoch_sample",
    "tracking_cfo_hz",
    "glrt_exact_score",
    "glrt_control_score",
    "glrt_margin",
}
_CONTINUITY_EVIDENCE_FIELDS = {
    "gap_map_path",
    "gap_map_sha256",
    "gap_map_boundary_count",
    "timeline_path",
    "timeline_sha256",
    "segment_count",
    "sample_loss_observable",
    "observed_sample_count",
    "device_span_sample_count",
    "gap_count",
    "missing_sample_count",
    "overflow_count",
    "clipped_sample_count",
    "constant_iq_refill_count",
    "refill_count",
    "interval_timeline_record_count",
    "interval_first_source_sequence",
    "interval_last_source_sequence",
    "interval_records_all_counter_contiguous",
    "interval_records_all_missing_samples_before_zero",
    "interval_records_all_overflow_false",
    "interval_hard_refill_boundary_samples",
}
_SCAN_FIELDS = {
    "algorithm_version",
    "candidate_only",
    "coarse_window_samples",
    "detections",
    "frequency_coordinate",
    "frequency_reference",
    "maximum_scored_candidates_per_probe",
    "methods",
    "payload_decoded",
    "probe_samples",
    "probe_schedule_digest",
    "schema_version",
    "specificity_claimed",
    "subwindow_samples",
}


@dataclass(frozen=True, slots=True)
class GlrtAnchorCandidate:
    detection_sample_start: int
    candidate_rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class OwnedAnchor:
    anchor: FrameRecoveryAnchor
    segment_start_sample: int
    segment_stop_sample: int
    acquisition_start_sample: int
    acquisition_stop_sample: int
    candidate: GlrtAnchorCandidate


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--labels", nargs="*", help="optional exact dwell labels")
    return parser.parse_args()


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else _repository_root() / value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected one JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _verify_declared_file(value: dict[str, Any], *, label: str) -> Path:
    if set(value) != {"path", "sha256"}:
        raise ValueError(f"{label}: expected closed path/sha256 declaration")
    path = _resolve(str(value["path"]))
    if not path.is_file():
        raise ValueError(f"{label}: missing {path}")
    digest = _sha256(path)
    if digest != value["sha256"]:
        raise ValueError(f"{label}: SHA-256 mismatch for {path}")
    return path


def _verify_path_digest(path_value: str, digest_value: str, *, label: str) -> Path:
    path = _resolve(path_value)
    if not path.is_file() or _sha256(path) != digest_value:
        raise ValueError(f"{label}: path/digest mismatch")
    return path


def validate_inputs(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Fail closed on the predeclared three-dwell geometry."""

    if set(document) != _TOP_LEVEL_FIELDS:
        raise ValueError("continuous-frame-recovery top-level fields are not closed")
    if document.get("schema") != "org.leo.research.continuous-frame-recovery-inputs/v1":
        raise ValueError("unsupported continuous-frame-recovery input schema")
    selection = document.get("selection_lock")
    geometry = document.get("common_geometry")
    policy = document.get("continuity_policy")
    dwells = document.get("dwells")
    if not all(isinstance(value, dict) for value in (selection, geometry, policy)):
        raise ValueError("prototype selection, geometry, and continuity policy must be objects")
    assert isinstance(selection, dict) and isinstance(geometry, dict) and isinstance(policy, dict)
    if set(selection) != _SELECTION_FIELDS:
        raise ValueError("prototype selection-lock fields are not closed")
    if selection["outcome_blinded"] is not True or selection["new_frame_cfo_outcomes_used"]:
        raise ValueError("prototype interval selection must remain outcome blinded")
    _verify_path_digest(
        str(selection["source_plot_summary_path"]),
        str(selection["source_plot_summary_sha256"]),
        label="selection source plot",
    )
    if "independently" not in str(selection["anchor_rule"]):
        raise ValueError("prototype must independently anchor every refill segment")
    if set(geometry) != _GEOMETRY_FIELDS:
        raise ValueError("prototype geometry fields are not closed")
    if geometry.get("sample_rate_hz") != 2_500_000:
        raise ValueError("prototype is frozen at 2.5 MS/s")
    if geometry.get("interval_sample_count") != 1_250_000:
        raise ValueError("prototype is frozen at one 500 ms interval per dwell")
    if geometry.get("frame_rate_hz") != 750:
        raise ValueError("prototype is frozen to the 750 Hz frame lattice")
    if not math.isclose(
        float(geometry.get("full_frame_alignment_ambiguity_s", 0.0)),
        1 / 750,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("full-frame alignment ambiguity must be exactly one 750 Hz period")
    if "does not estimate phase" not in str(geometry.get("phase_policy", "")):
        raise ValueError("bounded recovery prototype must not claim unmeasured phase evidence")
    if set(policy) != _CONTINUITY_POLICY_FIELDS:
        raise ValueError("prototype continuity-policy fields are not closed")
    if "hard analysis" not in str(policy.get("refill_interpretation", "")):
        raise ValueError("prototype must treat every refill as a hard analysis boundary")
    if (
        policy["required_segment_count"] != 1
        or policy["require_counter_authoritative_sample_loss"] is not True
        or policy["require_zero_gap_missing_overflow_clip_and_constant_iq_counts"] is not True
    ):
        raise ValueError("prototype continuity preconditions changed")
    if not isinstance(dwells, list) or len(dwells) != 3:
        raise ValueError("prototype requires exactly three predeclared dwells")
    labels = [item.get("label") for item in dwells if isinstance(item, dict)]
    if labels != ["D1", "D2", "D6"]:
        raise ValueError("prototype dwell order must remain D1, D2, D6")
    for item in dwells:
        if set(item) != _DWELL_FIELDS:
            raise ValueError(f"{item.get('label')}: dwell fields are not closed")
        interval = item.get("interval")
        gap = item.get("prior_visible_gap")
        if not isinstance(interval, dict) or not isinstance(gap, dict):
            raise ValueError(f"{item['label']}: interval and prior gap must be objects")
        if set(interval) != _INTERVAL_FIELDS or set(gap) != _PRIOR_GAP_FIELDS:
            raise ValueError(f"{item['label']}: interval/prior-gap fields are not closed")
        start = interval.get("sample_start")
        stop = interval.get("sample_end")
        if not isinstance(start, int) or not isinstance(stop, int) or stop - start != 1_250_000:
            raise ValueError(f"{item['label']}: invalid frozen interval")
        if not (start <= gap.get("sample_start", -1) < gap.get("sample_end", -1) <= stop):
            raise ValueError(f"{item['label']}: prior gap lies outside frozen interval")
        if item.get("stream_id") != "stream-1" or item.get("receiver_id") != 1:
            raise ValueError(f"{item['label']}: unexpected stream/receiver binding")
        StarlinkEdge(item.get("edge"))
        for name in (
            "recording_manifest",
            "analysis_manifest",
            "pilot_scan",
            "sealed_seed_document",
        ):
            if not isinstance(item.get(name), dict) or set(item[name]) != {"path", "sha256"}:
                raise ValueError(f"{item['label']}: {name} declaration is not closed")
        chunks = item.get("iq_chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError(f"{item['label']}: no IQ chunks were pinned")
        if any(not isinstance(value, dict) or set(value) != _CHUNK_FIELDS for value in chunks):
            raise ValueError(f"{item['label']}: IQ chunk declaration is not closed")
        initial = item.get("initial_anchor")
        if (
            not isinstance(initial, dict)
            or set(initial) != _INITIAL_ANCHOR_FIELDS
            or initial.get("role") != "legacy_sealed_comparator_only"
            or initial.get("source_identity") != "unknown"
            or initial.get("alias_identity") != "unknown"
        ):
            raise ValueError(f"{item['label']}: initial anchor role/identity changed")
        evidence = item.get("continuity_evidence")
        if not isinstance(evidence, dict) or set(evidence) != _CONTINUITY_EVIDENCE_FIELDS:
            raise ValueError(f"{item['label']}: continuity-evidence fields are not closed")
    return tuple(dwells)


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [value for value in candidate.get("scores", ()) if value.get("method") == "glrt64"]
    if len(scores) != 1:
        raise ValueError("pilot candidate must contain exactly one GLRT64 score")
    return scores[0]


def glrt_candidates(scan: dict[str, Any]) -> tuple[GlrtAnchorCandidate, ...]:
    if set(scan) != _SCAN_FIELDS:
        raise ValueError("pilot-scan V3 fields are not closed")
    if (
        scan.get("schema_version") != 3
        or scan.get("algorithm_version") != "standard-pilot-scan-v3"
        or scan.get("candidate_only") is not True
        or scan.get("payload_decoded") is not False
        or scan.get("specificity_claimed") is not False
        or scan.get("probe_samples") != 50_000
        or scan.get("methods") != ["anchor8", "glrt64", "symbolwise"]
    ):
        raise ValueError("continuous recovery requires pilot-scan V3")
    output = []
    for detection in scan.get("detections", ()):
        if detection.get("status") != "complete":
            continue
        detection_start = int(detection["sample_start"])
        for candidate in detection.get("candidates", ()):
            score = _glrt_score(candidate)
            values = (
                float(score["tracking_cfo_hz"]),
                float(score["exact_score"]),
                float(score["control_score"]),
                float(score["margin"]),
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError("pilot scan contains a non-finite GLRT value")
            output.append(
                GlrtAnchorCandidate(
                    detection_sample_start=detection_start,
                    candidate_rank=int(candidate["rank"]),
                    local_epoch_sample=int(candidate["local_epoch_sample"]),
                    tracking_cfo_hz=values[0],
                    exact_score=values[1],
                    control_score=values[2],
                    margin=values[3],
                )
            )
    if not output:
        raise ValueError("pilot scan contains no GLRT candidates")
    return tuple(output)


def select_segment_anchor(
    candidates: tuple[GlrtAnchorCandidate, ...],
    *,
    segment_start_sample: int,
    segment_stop_sample: int,
    probe_sample_count: int,
) -> GlrtAnchorCandidate | None:
    """Select a deterministic strong acquisition wholly inside one segment."""

    eligible = [
        value
        for value in candidates
        if value.detection_sample_start >= segment_start_sample
        and value.detection_sample_start + probe_sample_count <= segment_stop_sample
        and value.margin >= MINIMUM_ANCHOR_MARGIN
        and value.exact_score >= 0.02
        and 0 <= value.local_epoch_sample < math.ceil(2_500_000 / 750)
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda value: (
            value.margin,
            value.exact_score,
            -value.candidate_rank,
            -abs(value.tracking_cfo_hz),
            -value.detection_sample_start,
            -value.local_epoch_sample,
        ),
    )


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return np.asarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15),
        dtype=np.complex128,
    )


def _merged_spans(spans: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[tuple[int, int]] = []
    for start, stop in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return tuple(merged)


def legacy_replay_coverage_samples(
    seed_document: dict[str, Any],
    *,
    interval_start_sample: int,
    interval_stop_sample: int,
    replay_sample_count: int,
) -> int:
    spans = []
    for item in seed_document.get("bins", ()):
        seed = item.get("seed")
        if item.get("status") != "selected" or not isinstance(seed, dict):
            continue
        start = max(interval_start_sample, int(seed["sample_start"]))
        stop = min(interval_stop_sample, int(seed["sample_start"]) + replay_sample_count)
        if start < stop:
            spans.append((start, stop))
    return sum(stop - start for start, stop in _merged_spans(spans))


def legacy_replay_spans(
    seed_document: dict[str, Any],
    *,
    interval_start_sample: int,
    interval_stop_sample: int,
    replay_sample_count: int,
) -> tuple[tuple[int, int], ...]:
    spans = []
    for item in seed_document.get("bins", ()):
        seed = item.get("seed")
        if item.get("status") != "selected" or not isinstance(seed, dict):
            continue
        start = max(interval_start_sample, int(seed["sample_start"]))
        stop = min(interval_stop_sample, int(seed["sample_start"]) + replay_sample_count)
        if start < stop:
            spans.append((start, stop))
    return _merged_spans(spans)


def _anchor_document(value: OwnedAnchor) -> dict[str, Any]:
    candidate = value.candidate
    return {
        "anchor_id": value.anchor.anchor_id,
        "segment_start_sample": value.segment_start_sample,
        "segment_stop_sample": value.segment_stop_sample,
        "acquisition_start_sample": value.acquisition_start_sample,
        "acquisition_stop_sample": value.acquisition_stop_sample,
        "epoch_sample": value.anchor.epoch_sample,
        "tracking_cfo_hz": candidate.tracking_cfo_hz,
        "candidate_rank": candidate.candidate_rank,
        "local_epoch_sample": candidate.local_epoch_sample,
        "exact_score": candidate.exact_score,
        "control_score": candidate.control_score,
        "margin": candidate.margin,
        "continuity_source_identity": None,
        "alias_identity": None,
    }


def _frame_document(
    label: str,
    frame: RecoveredFrame,
    anchor: OwnedAnchor,
    *,
    sample_rate_hz: int,
) -> dict[str, Any]:
    primary = frame.primary
    split = frame.split_validation
    acquisition_overlap = (
        frame.frame_start_sample < anchor.acquisition_stop_sample
        and frame.frame_start_sample + round(302 * sample_rate_hz * 4.4e-6)
        > anchor.acquisition_start_sample
    )
    anchor_causally_available = frame.frame_start_sample >= anchor.acquisition_stop_sample
    pre_acquisition_backprojection = not anchor_causally_available and not acquisition_overlap
    odd_boundary = bool(split is not None and split.odd_search_boundary)
    odd_scored = bool(
        frame.outcome is FrameOpportunityOutcome.SUPPORTED
        and frame.odd_prediction_error_hz is not None
        and not odd_boundary
        and not acquisition_overlap
        and anchor_causally_available
    )
    return {
        "label": label,
        "opportunity_index": frame.opportunity_index,
        "anchor_id": frame.anchor_id,
        "lattice_index": frame.lattice_index,
        "frame_start_sample": frame.frame_start_sample,
        "reference_sample": frame.reference_sample,
        "reference_time_s": frame.reference_sample / sample_rate_hz,
        "outcome": frame.outcome.value,
        "mode": frame.mode.value,
        "locklet_index": frame.locklet_index,
        "reacquired": frame.reacquired,
        "hard_split_before": frame.hard_split_before,
        "split_reason": None if frame.split_reason is None else frame.split_reason.value,
        "filter_accepted": frame.filter_accepted,
        "predicted_only": frame.predicted_only,
        "estimator_seed_cfo_hz": frame.estimator_seed_cfo_hz,
        "predicted_cfo_hz": frame.predicted_cfo_hz,
        "tracked_cfo_hz": frame.tracked_cfo_hz,
        "tracked_rate_hz_s": frame.tracked_rate_hz_s,
        "frequency_innovation_hz": frame.frequency_innovation_hz,
        "normalized_frequency_innovation": frame.normalized_frequency_innovation,
        "odd_prediction_error_hz": frame.odd_prediction_error_hz,
        "odd_scored": odd_scored,
        "odd_search_boundary": odd_boundary,
        "acquisition_overlap": acquisition_overlap,
        "anchor_causally_available": anchor_causally_available,
        "pre_acquisition_backprojection": pre_acquisition_backprojection,
        "rejection_reasons": list(frame.rejection_reasons),
        "primary_supported": None if primary is None else primary.measurement_supported,
        "primary_absolute_cfo_hz": None if primary is None else primary.absolute_cfo_hz,
        "primary_frequency_uncertainty_hz": (
            None if primary is None else primary.frequency_uncertainty_hz
        ),
        "primary_exact_coherence": None if primary is None else primary.exact_coherence,
        "primary_control_coherence": None if primary is None else primary.control_coherence,
        "primary_even_odd_disagreement_hz": (
            None if primary is None else primary.even_odd_disagreement_hz
        ),
        "primary_timing_spread_hz": None if primary is None else primary.timing_spread_hz,
        "primary_half_frame_difference_z": (
            None if primary is None else primary.half_frame_difference_z
        ),
        "primary_tone_deletion_spread_hz": (
            None if primary is None else primary.tone_deletion_spread_hz
        ),
        "primary_search_boundary": None if primary is None else primary.search_boundary,
        "even_absolute_cfo_hz": None if split is None else split.even_absolute_cfo_hz,
        "odd_absolute_cfo_hz": None if split is None else split.odd_absolute_cfo_hz,
        "even_frequency_uncertainty_hz": (
            None if split is None else split.even_frequency_uncertainty_hz
        ),
        "odd_frequency_uncertainty_hz": (
            None if split is None else split.odd_frequency_uncertainty_hz
        ),
    }


def _rms(values: list[float]) -> float | None:
    return None if not values else float(np.sqrt(np.mean(np.square(values))))


def _percentile_absolute(values: list[float], percentile: float) -> float | None:
    return None if not values else float(np.percentile(np.abs(values), percentile))


def _robust_weighted_line(
    time_s: np.ndarray,
    cfo_hz: np.ndarray,
    sigma_hz: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Fit the frozen causal trailing-line comparator."""

    reference = float(np.median(time_s))
    design = np.column_stack((np.ones(len(time_s)), time_s - reference))
    base = 1.0 / np.maximum(sigma_hz, 15.0) ** 2
    coefficients = np.linalg.lstsq(
        design * np.sqrt(base)[:, None],
        cfo_hz * np.sqrt(base),
        rcond=None,
    )[0]
    for _ in range(8):
        residual = cfo_hz - design @ coefficients
        scale = max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            15.0,
        )
        standardized = np.abs(residual) / scale
        robust = np.ones(len(residual))
        tail = standardized > 1.5
        robust[tail] = 1.5 / standardized[tail]
        weights = base * robust
        updated = np.linalg.lstsq(
            design * np.sqrt(weights)[:, None],
            cfo_hz * np.sqrt(weights),
            rcond=None,
        )[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    return reference, coefficients


def add_trailing_line_predictions(
    rows: list[dict[str, Any]],
    *,
    history_s: float = 0.020,
    minimum_history: int = 6,
) -> None:
    """Add causal baseline predictions without crossing one locklet boundary."""

    prior_by_locklet: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["trailing_20ms_prediction_hz"] = None
        row["trailing_20ms_odd_error_hz"] = None
        row["trailing_20ms_scored"] = False
        locklet = row["locklet_index"]
        time_s = float(row["reference_time_s"])
        if locklet is not None:
            prior = [
                value
                for value in prior_by_locklet[int(locklet)]
                if float(value["reference_time_s"]) >= time_s - history_s
            ]
            if len(prior) >= minimum_history:
                times = np.asarray([value["reference_time_s"] for value in prior], dtype=float)
                cfo = np.asarray([value["even_absolute_cfo_hz"] for value in prior], dtype=float)
                sigma = np.asarray(
                    [value["even_frequency_uncertainty_hz"] for value in prior],
                    dtype=float,
                )
                reference, coefficients = _robust_weighted_line(times, cfo, sigma)
                predicted = float(coefficients[0] + coefficients[1] * (time_s - reference))
                row["trailing_20ms_prediction_hz"] = predicted
                if row["odd_scored"]:
                    row["trailing_20ms_odd_error_hz"] = float(
                        row["odd_absolute_cfo_hz"] - predicted
                    )
                    row["trailing_20ms_scored"] = True
        if (
            locklet is not None
            and row["outcome"] == FrameOpportunityOutcome.SUPPORTED.value
            and row["even_absolute_cfo_hz"] is not None
            and row["even_frequency_uncertainty_hz"] is not None
        ):
            prior_by_locklet[int(locklet)].append(row)


def summarize_result(
    result: ContinuousFrameRecoveryResult,
    rows: list[dict[str, Any]],
    *,
    label: str,
    interval_start_sample: int,
    interval_stop_sample: int,
    prior_gap_start_sample: int,
    prior_gap_stop_sample: int,
    legacy_coverage_samples: int,
    legacy_spans: tuple[tuple[int, int], ...],
    owned_anchors: tuple[OwnedAnchor, ...],
    refill_boundaries: tuple[int, ...],
) -> dict[str, Any]:
    interval_samples = interval_stop_sample - interval_start_sample
    outcome_counts = Counter(str(value["outcome"]) for value in rows)
    mode_counts = Counter(str(value["mode"]) for value in rows)
    odd_errors = [float(value["odd_prediction_error_hz"]) for value in rows if value["odd_scored"]]
    common_rows = [value for value in rows if value["odd_scored"] and value["trailing_20ms_scored"]]
    common_filter_errors = [float(value["odd_prediction_error_hz"]) for value in common_rows]
    common_baseline_errors = [float(value["trailing_20ms_odd_error_hz"]) for value in common_rows]
    common_filter_rms = _rms(common_filter_errors)
    common_baseline_rms = _rms(common_baseline_errors)
    gap_rows = [
        value
        for value in rows
        if prior_gap_start_sample <= int(value["frame_start_sample"]) < prior_gap_stop_sample
    ]
    gap_outcomes = Counter(str(value["outcome"]) for value in gap_rows)
    primary_rows = [value for value in rows if value["primary_supported"] is not None]
    primary_supported = sum(bool(value["primary_supported"]) for value in primary_rows)
    acquisition_overlap_count = sum(bool(value["acquisition_overlap"]) for value in rows)
    backprojected_count = sum(bool(value["pre_acquisition_backprojection"]) for value in rows)
    even_training_supported_count = outcome_counts[FrameOpportunityOutcome.SUPPORTED.value]
    filter_accepted_count = sum(bool(value["filter_accepted"]) for value in rows)
    anchor_by_id = {value.anchor.anchor_id: value for value in owned_anchors}
    if set(anchor_by_id) != {str(value["anchor_id"]) for value in rows}:
        raise ValueError(f"{label}: frame rows do not bind exactly to selected anchors")
    return {
        "label": label,
        "interval_sample_start": interval_start_sample,
        "interval_sample_stop": interval_stop_sample,
        "interval_sample_count": interval_samples,
        "fixed_grid_raw_read_coverage_samples": interval_samples,
        "fixed_grid_raw_read_coverage_fraction": 1.0,
        "legacy_seed_started_replay_coverage_samples": legacy_coverage_samples,
        "legacy_seed_started_replay_coverage_fraction": legacy_coverage_samples / interval_samples,
        "legacy_seed_started_replay_spans": [
            {"sample_start": start, "sample_stop": stop} for start, stop in legacy_spans
        ],
        "structurally_newly_read_samples": interval_samples - legacy_coverage_samples,
        "structurally_newly_read_fraction": (interval_samples - legacy_coverage_samples)
        / interval_samples,
        "hard_refill_boundary_count": len(refill_boundaries),
        "hard_refill_boundary_samples": list(refill_boundaries),
        "refill_safe_segment_count": len(refill_boundaries) + 1,
        "selected_anchor_count": len(owned_anchors),
        "unanchored_segment_count": len(result.unanchored_spans),
        "unanchored_sample_count": sum(value.sample_count for value in result.unanchored_spans),
        "opportunity_count": len(rows),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "mode_counts": dict(sorted(mode_counts.items())),
        "supported_frame_count": even_training_supported_count,
        "even_training_supported_count": even_training_supported_count,
        "filter_accepted_count": filter_accepted_count,
        "primary_diagnostic_frame_count": len(primary_rows),
        "primary_diagnostic_supported_count": primary_supported,
        "primary_diagnostic_supported_fraction": (
            primary_supported / len(primary_rows) if primary_rows else None
        ),
        "prediction_only_coast_count": sum(bool(value["predicted_only"]) for value in rows),
        "locklet_count": len(result.locklets),
        "locklet_end_reason_counts": dict(
            sorted(Counter(value.ended_by.value for value in result.locklets).items())
        ),
        "acquisition_overlap_frame_count": acquisition_overlap_count,
        "pre_acquisition_backprojected_frame_count": backprojected_count,
        "conditional_odd_fold_scored_frame_count": len(odd_errors),
        "conditional_odd_fold_one_step_rms_hz": _rms(odd_errors),
        "conditional_odd_fold_one_step_median_absolute_hz": _percentile_absolute(odd_errors, 50),
        "conditional_odd_fold_one_step_p95_absolute_hz": _percentile_absolute(odd_errors, 95),
        "conditional_odd_fold_exclusion_policy": (
            "score only frames starting after the all-Qin anchor probe; exclude pre-anchor "
            "backprojection, acquisition-overlap, absent prediction, unsupported even-training, "
            "and odd search-boundary rows"
        ),
        "conditional_odd_fold_scope": (
            "delayed-causal frame-estimator validation after the all-Qin GLRT64 anchor probe; "
            "conditional on anchor selection and not end-to-end untouched validation"
        ),
        "common_mask_trailing_20ms": {
            "frame_count": len(common_rows),
            "recovery_filter_rms_hz": common_filter_rms,
            "causal_trailing_20ms_robust_line_rms_hz": common_baseline_rms,
            "recovery_filter_to_baseline_rms_ratio": (
                None
                if common_filter_rms is None
                or common_baseline_rms is None
                or common_baseline_rms == 0.0
                else common_filter_rms / common_baseline_rms
            ),
        },
        "occupancy_status": "unknown; this prototype has no independent occupancy fold",
        "estimator_retention_fraction": None,
        "prior_visible_gap": {
            "sample_start": prior_gap_start_sample,
            "sample_stop": prior_gap_stop_sample,
            "opportunity_count": len(gap_rows),
            "outcome_counts": dict(sorted(gap_outcomes.items())),
            "supported_frame_count": gap_outcomes[FrameOpportunityOutcome.SUPPORTED.value],
        },
        "anchors": [_anchor_document(value) for value in owned_anchors],
        "unanchored_spans": [
            {"sample_start": value.start_sample, "sample_stop": value.stop_sample}
            for value in result.unanchored_spans
        ],
    }


def _small_input_paths(item: dict[str, Any]) -> dict[str, Path]:
    output = {
        "recording_manifest": _verify_declared_file(
            item["recording_manifest"], label=f"{item['label']} recording manifest"
        ),
        "analysis_manifest": _verify_declared_file(
            item["analysis_manifest"], label=f"{item['label']} analysis manifest"
        ),
        "pilot_scan": _verify_declared_file(
            item["pilot_scan"], label=f"{item['label']} pilot scan"
        ),
        "sealed_seed_document": _verify_declared_file(
            item["sealed_seed_document"], label=f"{item['label']} seed document"
        ),
    }
    evidence = item["continuity_evidence"]
    for name in ("gap_map", "timeline"):
        path = Path(str(evidence[f"{name}_path"]))
        if not path.is_file() or _sha256(path) != evidence[f"{name}_sha256"]:
            raise ValueError(f"{item['label']}: {name} path/digest mismatch")
        output[name] = path
    return output


def _validate_seed_binding(
    seed: dict[str, Any],
    scan: dict[str, Any],
    item: dict[str, Any],
) -> None:
    if seed.get("schema") != "org.leo.research.sealed-standard-100ms-glrt64-seeds/v1":
        raise ValueError(f"{item['label']}: unsupported sealed-seed schema")
    for field in (
        "label",
        "session_id",
        "run_id",
        "scope_sha256",
        "stream_id",
        "radio_id",
        "receiver_id",
        "channel",
        "edge",
        "rf_hz",
    ):
        if seed.get(field) != item[field]:
            raise ValueError(f"{item['label']}: sealed seed identity mismatch for {field}")
    expected_hashes = {
        "recording_manifest_sha256": item["recording_manifest"]["sha256"],
        "analysis_manifest_sha256": item["analysis_manifest"]["sha256"],
        "pilot_scan_sha256": item["pilot_scan"]["sha256"],
    }
    if any(seed.get(field) != value for field, value in expected_hashes.items()):
        raise ValueError(f"{item['label']}: sealed seed source digest mismatch")
    if (
        seed.get("sample_rate_hz") != 2_500_000
        or seed.get("bin_count") != 600
        or seed.get("selected_bin_count") != 600
        or seed.get("missing_bin_count") != 0
        or seed.get("tle_or_track_used_in_selection") is not False
        or seed.get("pilot_probe_schedule_digest") != scan.get("probe_schedule_digest")
    ):
        raise ValueError(f"{item['label']}: sealed seed schedule/selection changed")


def _validate_manifests_and_chunks(
    recording_manifest: dict[str, Any],
    analysis_manifest: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    label = str(item["label"])
    if (
        analysis_manifest.get("session_id") != item["session_id"]
        or analysis_manifest.get("run_id") != item["run_id"]
        or analysis_manifest.get("pipeline_lane") != "standard"
    ):
        raise ValueError(f"{label}: analysis manifest identity/lane mismatch")
    products = [
        value
        for value in analysis_manifest.get("products", ())
        if value.get("kind") == "standard.pilot-scan"
        and value.get("scope_key") == item["scope_sha256"]
        and value.get("status") == "complete"
    ]
    if (
        len(products) != 1
        or str(products[0].get("digest", "")).removeprefix("sha256:")
        != item["pilot_scan"]["sha256"]
    ):
        raise ValueError(f"{label}: pilot scan is not bound to the declared analysis scope")
    streams = [
        value
        for value in recording_manifest.get("streams", ())
        if value.get("stream_id") == item["stream_id"]
    ]
    if len(streams) != 1:
        raise ValueError(f"{label}: recording stream binding is absent or duplicated")
    stream = streams[0]
    chunks_by_index = {int(value["chunk_index"]): value for value in stream.get("chunks", ())}
    interval_start = int(item["interval"]["sample_start"])
    interval_stop = int(item["interval"]["sample_end"])
    overlapping = {
        index
        for index, value in chunks_by_index.items()
        if int(value["sample_start"]) < interval_stop
        and int(value["sample_start"]) + int(value["sample_count"]) > interval_start
    }
    declared = {int(value["chunk_index"]) for value in item["iq_chunks"]}
    if declared != overlapping:
        raise ValueError(f"{label}: pinned IQ chunks do not exactly cover the interval")
    recording_root = Path(str(item["recording_root"])).resolve()
    for value in item["iq_chunks"]:
        source = chunks_by_index[int(value["chunk_index"])]
        expected_path = (recording_root / str(source["relative_path"])).resolve()
        if (
            Path(str(value["path"])).resolve() != expected_path
            or int(value["sample_start"]) != int(source["sample_start"])
            or int(value["sample_end"]) != int(source["sample_start"]) + int(source["sample_count"])
            or value["compressed_sha256"]
            != str(source["compressed_sha256"]).removeprefix("sha256:")
            or value["uncompressed_sha256"]
            != str(source["uncompressed_sha256"]).removeprefix("sha256:")
        ):
            raise ValueError(f"{label}: IQ chunk declaration disagrees with recording manifest")
    return stream


def _validate_continuity(
    *,
    stream: dict[str, Any],
    timeline: tuple[Any, ...],
    gap_map: Any,
    item: dict[str, Any],
    interval_start: int,
    interval_stop: int,
) -> tuple[int, ...]:
    label = str(item["label"])
    evidence = item["continuity_evidence"]
    continuity = stream.get("continuity")
    if not isinstance(continuity, dict):
        raise ValueError(f"{label}: recording has no continuity summary")
    for field in (
        "sample_loss_observable",
        "observed_sample_count",
        "device_span_sample_count",
        "segment_count",
        "gap_count",
        "missing_sample_count",
        "overflow_count",
        "clipped_sample_count",
        "constant_iq_refill_count",
        "refill_count",
    ):
        if continuity.get(field) != evidence[field]:
            raise ValueError(f"{label}: continuity mismatch for {field}")
    if (
        len(gap_map.boundaries) != evidence["gap_map_boundary_count"]
        or gap_map.observed_sample_count != evidence["observed_sample_count"]
        or gap_map.device_span_sample_count != evidence["device_span_sample_count"]
        or gap_map.segment_count != evidence["segment_count"]
    ):
        raise ValueError(f"{label}: verified gap map disagrees with predeclaration")
    overlapping = tuple(
        value
        for value in timeline
        if value.session_sample_start < interval_stop
        and value.session_sample_start + value.sample_count > interval_start
    )
    if (
        len(overlapping) != evidence["interval_timeline_record_count"]
        or overlapping[0].source_sequence != evidence["interval_first_source_sequence"]
        or overlapping[-1].source_sequence != evidence["interval_last_source_sequence"]
        or not all(value.missing_samples_before == 0 for value in overlapping)
        or not all(not value.overflow_observed for value in overlapping)
        or not all(value.continuity.value == "contiguous" for value in overlapping)
    ):
        raise ValueError(f"{label}: interval timeline evidence changed")
    boundaries = tuple(
        value.session_sample_start
        for value in timeline[1:]
        if interval_start < value.session_sample_start < interval_stop
    )
    declared = tuple(int(value) for value in evidence["interval_hard_refill_boundary_samples"])
    if boundaries != declared:
        raise ValueError(f"{label}: live refill boundaries disagree with predeclaration")
    return boundaries


def analyze_dwell(
    *,
    store: RecordingStore,
    item: dict[str, Any],
    recovery_config: FrameRecoveryConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    label = str(item["label"])
    paths = _small_input_paths(item)
    analysis_manifest = _read_json(paths["analysis_manifest"])
    recording_manifest = _read_json(paths["recording_manifest"])
    stream = _validate_manifests_and_chunks(recording_manifest, analysis_manifest, item)
    bundle = store.inspect(str(item["session_id"]))
    if bundle.manifest_sha256.removeprefix("sha256:") != item["recording_manifest"]["sha256"]:
        raise ValueError(f"{label}: recording-store manifest digest mismatch")
    reader = store.reader(bundle, str(item["stream_id"]), verify=True)
    sample_rate_hz = int(reader.sample_rate_hz)
    receiver_id = int(item["receiver_id"])
    if sample_rate_hz != 2_500_000 or receiver_id not in reader.receiver_ids:
        raise ValueError(f"{label}: recording geometry disagrees with frozen input")
    interval_start = int(item["interval"]["sample_start"])
    interval_stop = int(item["interval"]["sample_end"])
    if interval_stop > reader.sample_count:
        raise ValueError(f"{label}: frozen interval exceeds recording")
    timeline = tuple(reader.iter_timeline_metadata())
    boundaries = _validate_continuity(
        stream=stream,
        timeline=timeline,
        gap_map=reader.gap_map(),
        item=item,
        interval_start=interval_start,
        interval_stop=interval_stop,
    )

    scan = _read_json(paths["pilot_scan"])
    candidates = glrt_candidates(scan)
    seed_document = _read_json(paths["sealed_seed_document"])
    _validate_seed_binding(seed_document, scan, item)
    probe_samples = round(GLRT_PROBE_DURATION_S * sample_rate_hz)
    segment_edges = (interval_start, *boundaries, interval_stop)
    owned = []
    for segment_index, (start, stop) in enumerate(
        zip(segment_edges, segment_edges[1:], strict=False)
    ):
        candidate = select_segment_anchor(
            candidates,
            segment_start_sample=start,
            segment_stop_sample=stop,
            probe_sample_count=probe_samples,
        )
        if candidate is None:
            continue
        anchor_id = (
            f"{label.lower()}-segment-{segment_index:02d}-"
            f"sample-{candidate.detection_sample_start}-rank-{candidate.candidate_rank}"
        )
        anchor = FrameRecoveryAnchor(
            anchor_id=anchor_id,
            sample_source_id=(f"{item['session_id']}:{item['stream_id']}:receiver-{receiver_id}"),
            canonical_observation_id=None,
            source_observation_id=(
                f"sample-{candidate.detection_sample_start}:rank-{candidate.candidate_rank}:glrt64"
            ),
            continuity_source_id=None,
            edge=StarlinkEdge(item["edge"]),
            cfo_alias_index=None,
            epoch_sample=candidate.detection_sample_start + candidate.local_epoch_sample,
            acquisition_absolute_cfo_hz=candidate.tracking_cfo_hz,
            ownership_start_sample=start,
            ownership_stop_sample=stop,
        )
        owned.append(
            OwnedAnchor(
                anchor=anchor,
                segment_start_sample=start,
                segment_stop_sample=stop,
                acquisition_start_sample=candidate.detection_sample_start,
                acquisition_stop_sample=candidate.detection_sample_start + probe_samples,
                candidate=candidate,
            )
        )
    if not owned:
        raise ValueError(f"{label}: no refill-safe strong GLRT anchor was available")

    print(
        f"{label}: reading verified {interval_stop - interval_start:,}-sample interval",
        flush=True,
    )
    raw = reader.read(
        interval_start,
        interval_stop - interval_start,
        receiver_ids=(receiver_id,),
    )
    result = recover_contiguous_frames(
        _complex_receiver(raw),
        sample_start=interval_start,
        sample_rate_hz=sample_rate_hz,
        anchors=tuple(value.anchor for value in owned),
        refill_boundaries=boundaries,
        config=recovery_config,
    )
    owned_by_id = {value.anchor.anchor_id: value for value in owned}
    rows = [
        _frame_document(
            label,
            frame,
            owned_by_id[frame.anchor_id],
            sample_rate_hz=sample_rate_hz,
        )
        for frame in result.frames
    ]
    add_trailing_line_predictions(rows)
    legacy_coverage = legacy_replay_coverage_samples(
        seed_document,
        interval_start_sample=interval_start,
        interval_stop_sample=interval_stop,
        replay_sample_count=round(0.100 * sample_rate_hz),
    )
    legacy_spans = legacy_replay_spans(
        seed_document,
        interval_start_sample=interval_start,
        interval_stop_sample=interval_stop,
        replay_sample_count=round(0.100 * sample_rate_hz),
    )
    gap = item["prior_visible_gap"]
    summary = summarize_result(
        result,
        rows,
        label=label,
        interval_start_sample=interval_start,
        interval_stop_sample=interval_stop,
        prior_gap_start_sample=int(gap["sample_start"]),
        prior_gap_stop_sample=int(gap["sample_end"]),
        legacy_coverage_samples=legacy_coverage,
        legacy_spans=legacy_spans,
        owned_anchors=tuple(owned),
        refill_boundaries=boundaries,
    )
    summary.update(
        {
            "session_id": item["session_id"],
            "run_id": item["run_id"],
            "scope_sha256": item["scope_sha256"],
            "stream_id": item["stream_id"],
            "receiver_id": receiver_id,
            "edge": item["edge"],
            "sample_rate_hz": sample_rate_hz,
            "input_hashes": {name: _sha256(path) for name, path in sorted(paths.items())},
        }
    )
    return summary, rows


def _aggregate(per_dwell: list[dict[str, Any]]) -> dict[str, Any]:
    odd_squares = []
    common_filter_squares = []
    common_baseline_squares = []
    common_ratios = []
    for value in per_dwell:
        count = int(value["conditional_odd_fold_scored_frame_count"])
        rms = value["conditional_odd_fold_one_step_rms_hz"]
        if count and rms is not None:
            odd_squares.extend([float(rms) ** 2] * count)
        common = value["common_mask_trailing_20ms"]
        common_count = int(common["frame_count"])
        filter_rms = common["recovery_filter_rms_hz"]
        baseline_rms = common["causal_trailing_20ms_robust_line_rms_hz"]
        ratio = common["recovery_filter_to_baseline_rms_ratio"]
        if common_count and filter_rms is not None and baseline_rms is not None:
            common_filter_squares.extend([float(filter_rms) ** 2] * common_count)
            common_baseline_squares.extend([float(baseline_rms) ** 2] * common_count)
        if ratio is not None and ratio > 0.0:
            common_ratios.append(float(ratio))
    pooled_filter_rms = (
        None
        if not common_filter_squares
        else float(math.sqrt(sum(common_filter_squares) / len(common_filter_squares)))
    )
    pooled_baseline_rms = (
        None
        if not common_baseline_squares
        else float(math.sqrt(sum(common_baseline_squares) / len(common_baseline_squares)))
    )
    return {
        "dwell_count": len(per_dwell),
        "interval_duration_s": sum(value["interval_sample_count"] for value in per_dwell)
        / 2_500_000,
        "fixed_grid_raw_read_coverage_fraction": 1.0,
        "legacy_seed_started_replay_coverage_fraction": sum(
            value["legacy_seed_started_replay_coverage_samples"] for value in per_dwell
        )
        / sum(value["interval_sample_count"] for value in per_dwell),
        "structurally_newly_read_fraction": sum(
            value["structurally_newly_read_samples"] for value in per_dwell
        )
        / sum(value["interval_sample_count"] for value in per_dwell),
        "opportunity_count": sum(value["opportunity_count"] for value in per_dwell),
        "supported_frame_count": sum(value["supported_frame_count"] for value in per_dwell),
        "prior_visible_gap_supported_frame_count": sum(
            value["prior_visible_gap"]["supported_frame_count"] for value in per_dwell
        ),
        "conditional_odd_fold_scored_frame_count": sum(
            value["conditional_odd_fold_scored_frame_count"] for value in per_dwell
        ),
        "pooled_conditional_odd_fold_one_step_rms_hz": (
            None if not odd_squares else float(math.sqrt(sum(odd_squares) / len(odd_squares)))
        ),
        "common_mask_trailing_20ms": {
            "frame_count": len(common_filter_squares),
            "pooled_recovery_filter_rms_hz": pooled_filter_rms,
            "pooled_causal_trailing_20ms_robust_line_rms_hz": pooled_baseline_rms,
            "pooled_recovery_filter_to_baseline_rms_ratio": (
                None
                if pooled_filter_rms is None
                or pooled_baseline_rms is None
                or pooled_baseline_rms == 0.0
                else pooled_filter_rms / pooled_baseline_rms
            ),
            "equal_dwell_geometric_mean_rms_ratio": (
                None if not common_ratios else float(math.exp(np.mean(np.log(common_ratios))))
            ),
            "recovery_filter_win_count": sum(value < 1.0 for value in common_ratios),
            "estimable_dwell_count": len(common_ratios),
        },
        "conditional_odd_fold_scope": (
            "delayed-causal frame-estimator validation after and conditional on all-Qin "
            "GLRT64 anchor selection"
        ),
        "occupancy_status": "unknown; no independent occupancy fold",
        "promotion_status": "exploratory prototype only",
    }


def render_plot(
    per_dwell: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    """Render temporal coverage and reset-safe CFO evidence for each dwell."""

    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_label[str(row["label"])].append(row)
    figure, axes = plt.subplots(len(per_dwell), 2, figsize=(15.5, 3.6 * len(per_dwell)))
    if len(per_dwell) == 1:
        axes = np.asarray([axes])
    for row_index, summary in enumerate(per_dwell):
        label = str(summary["label"])
        sample_rate_hz = float(summary["sample_rate_hz"])
        start = int(summary["interval_sample_start"])
        stop = int(summary["interval_sample_stop"])
        start_s = start / sample_rate_hz
        stop_s = stop / sample_rate_hz
        gap = summary["prior_visible_gap"]
        gap_start_s = int(gap["sample_start"]) / sample_rate_hz
        gap_stop_s = int(gap["sample_stop"]) / sample_rate_hz
        coverage = axes[row_index, 0]
        coverage.axvspan(gap_start_s, gap_stop_s, color="#f3e7bc", alpha=0.65, zorder=0)
        coverage.plot([start_s, stop_s], [2, 2], color="#4d5963", linewidth=8)
        for span in summary["legacy_seed_started_replay_spans"]:
            coverage.plot(
                [span["sample_start"] / sample_rate_hz, span["sample_stop"] / sample_rate_hz],
                [1, 1],
                color="#d48806",
                linewidth=8,
                solid_capstyle="butt",
            )
        for span in summary["unanchored_spans"]:
            coverage.plot(
                [span["sample_start"] / sample_rate_hz, span["sample_stop"] / sample_rate_hz],
                [0, 0],
                color="#8f969c",
                linewidth=8,
                solid_capstyle="butt",
            )
        selected_rows = by_label[label]
        supported = [
            value
            for value in selected_rows
            if value["outcome"] == FrameOpportunityOutcome.SUPPORTED.value
        ]
        excluded = [value for value in selected_rows if value not in supported]
        coverage.scatter(
            [float(value["reference_time_s"]) for value in supported],
            np.zeros(len(supported)),
            s=7,
            color="#17824b",
            linewidths=0,
            zorder=3,
        )
        coverage.scatter(
            [float(value["reference_time_s"]) for value in excluded],
            np.zeros(len(excluded)),
            s=22,
            color="#b5473c",
            marker="x",
            linewidths=0.9,
            zorder=4,
        )
        for boundary in summary["hard_refill_boundary_samples"]:
            coverage.axvline(boundary / sample_rate_hz, color="#b8bec3", linewidth=0.7)
        coverage.set_yticks((0, 1, 2), ("recovered frames", "legacy replay", "fixed read"))
        coverage.set_xlim(start_s, stop_s)
        coverage.set_ylim(-0.55, 2.55)
        coverage.set_xlabel("Time from dwell start (s)")
        coverage.set_title(
            f"{label} coverage · +{100 * summary['structurally_newly_read_fraction']:.0f}% read"
        )
        coverage.grid(True, axis="x", color="#dce3e8", linewidth=0.6)

        cfo_axis = axes[row_index, 1]
        cfo_axis.axvspan(gap_start_s, gap_stop_s, color="#f3e7bc", alpha=0.65, zorder=0)
        anchor_cfo = {
            value["anchor_id"]: float(value["tracking_cfo_hz"]) for value in summary["anchors"]
        }
        residual_values = []
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for value in selected_rows:
            locklet = value["locklet_index"]
            if locklet is not None:
                grouped[(str(value["anchor_id"]), int(locklet))].append(value)
            reference = anchor_cfo[str(value["anchor_id"])]
            if value["even_absolute_cfo_hz"] is not None:
                residual = float(value["even_absolute_cfo_hz"]) - reference
                residual_values.append(residual)
                cfo_axis.scatter(
                    float(value["reference_time_s"]),
                    residual,
                    s=5,
                    color="#5aa6c8",
                    alpha=0.35,
                    linewidths=0,
                    zorder=1,
                )
            if value["odd_scored"]:
                odd_residual = float(value["odd_absolute_cfo_hz"]) - reference
                residual_values.append(odd_residual)
                cfo_axis.scatter(
                    float(value["reference_time_s"]),
                    odd_residual,
                    s=5,
                    color="#7256a8",
                    alpha=0.28,
                    linewidths=0,
                    zorder=1,
                )
        for (anchor_id, _locklet), values in grouped.items():
            ordered = sorted(values, key=lambda value: float(value["reference_time_s"]))
            reference = anchor_cfo[anchor_id]
            predicted = [
                value
                for value in ordered
                if value["predicted_cfo_hz"] is not None and value["anchor_causally_available"]
            ]
            if predicted:
                cfo_axis.plot(
                    [float(value["reference_time_s"]) for value in predicted],
                    [float(value["predicted_cfo_hz"]) - reference for value in predicted],
                    color="#17824b",
                    linewidth=1.0,
                    zorder=3,
                )
            baseline = [
                value
                for value in ordered
                if value["trailing_20ms_prediction_hz"] is not None
                and value["anchor_causally_available"]
            ]
            if baseline:
                cfo_axis.plot(
                    [float(value["reference_time_s"]) for value in baseline],
                    [float(value["trailing_20ms_prediction_hz"]) - reference for value in baseline],
                    color="#555c63",
                    linewidth=0.75,
                    alpha=0.8,
                    zorder=2,
                )
        for boundary in summary["hard_refill_boundary_samples"]:
            cfo_axis.axvline(boundary / sample_rate_hz, color="#b8bec3", linewidth=0.7)
        if residual_values:
            lower, upper = np.percentile(np.asarray(residual_values), (0.5, 99.5))
            padding = max(20.0, 0.08 * float(upper - lower))
            cfo_axis.set_ylim(float(lower - padding), float(upper + padding))
        cfo_axis.set_xlim(start_s, stop_s)
        cfo_axis.set_xlabel("Time from dwell start (s)")
        cfo_axis.set_ylabel("CFO minus local GLRT anchor (Hz)")
        common = summary["common_mask_trailing_20ms"]
        cfo_axis.set_title(
            f"{label} reset-safe locklets · filter / 20 ms line = "
            f"{common['recovery_filter_to_baseline_rms_ratio']:.3f}×"
        )
        cfo_axis.grid(True, color="#dce3e8", linewidth=0.6)
    handles = [
        Line2D([], [], color="#4d5963", linewidth=6, label="fixed 500 ms IQ read"),
        Line2D([], [], color="#d48806", linewidth=6, label="legacy seed-started replay union"),
        Line2D(
            [],
            [],
            color="#17824b",
            marker="o",
            linewidth=1,
            label="post-anchor causal prediction / support",
        ),
        Line2D([], [], color="#8f969c", linewidth=6, label="unanchored span"),
        Line2D([], [], color="#5aa6c8", marker="o", linewidth=0, label="even-Qin frame CFO"),
        Line2D([], [], color="#7256a8", marker="o", linewidth=0, label="conditional odd fold"),
        Line2D([], [], color="#555c63", linewidth=1, label="causal trailing-20 ms line"),
    ]
    figure.suptitle(
        "Continuous frame recovery prototype — every Pluto refill is a hard reset",
        fontsize=14,
        y=0.995,
    )
    figure.legend(
        handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.97), ncol=3, frameon=False
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190, bbox_inches="tight", metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> None:
    arguments = _arguments()
    inputs_path = _resolve(arguments.inputs)
    document = _read_json(inputs_path)
    items = validate_inputs(document)
    if arguments.labels:
        requested = set(arguments.labels)
        unknown = requested - {str(item["label"]) for item in items}
        if unknown:
            raise ValueError(f"unknown dwell labels: {sorted(unknown)}")
        items = tuple(item for item in items if item["label"] in requested)
    output_root = _resolve(arguments.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    capability = PinnedLocalRoot(arguments.bulk_root)
    store = RecordingStore.open_pinned(capability)
    capability.close()
    per_dwell = []
    all_rows = []
    try:
        for item in items:
            summary, rows = analyze_dwell(
                store=store,
                item=item,
                recovery_config=FrameRecoveryConfig(),
            )
            per_dwell.append(summary)
            all_rows.extend(rows)
            print(
                f"{item['label']}: {summary['supported_frame_count']}/"
                f"{summary['opportunity_count']} supported; "
                f"{summary['prior_visible_gap']['supported_frame_count']} recovered in prior gap",
                flush=True,
            )
    finally:
        store.close()
    evidence = {
        "schema": "org.leo.research.continuous-frame-recovery-evidence/v1",
        "candidate_only": True,
        "known_symbols_only": True,
        "phase_feedback_used": False,
        "input_path": str(arguments.inputs),
        "input_sha256": _sha256(inputs_path),
        "core_source_sha256": _sha256(
            _repository_root() / "src/leo/analysis/research/continuous_frame_recovery.py"
        ),
        "anchor_policy": (
            "strongest safe GLRT64 candidate independently inside each refill segment; "
            "source and alias identity unknown; no state transfer across refill"
        ),
        "per_dwell": per_dwell,
        "aggregate": _aggregate(per_dwell),
    }
    rows_path = output_root / "continuous-frame-recovery-rows.json"
    _write_json(rows_path, all_rows)
    evidence["rows_relative_path"] = rows_path.name
    evidence["rows_sha256"] = _sha256(rows_path)
    plot_path = output_root / "continuous-frame-recovery-three-dwell.png"
    render_plot(per_dwell, all_rows, plot_path)
    evidence["plot_relative_path"] = plot_path.name
    evidence["plot_sha256"] = _sha256(plot_path)
    summary_path = output_root / "continuous-frame-recovery-summary.json"
    _write_json(summary_path, evidence)
    print(summary_path)


if __name__ == "__main__":
    main()
