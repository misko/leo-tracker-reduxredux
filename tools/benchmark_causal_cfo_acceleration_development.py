#!/usr/bin/env python3
"""Benchmark the frozen causal CFO/rate/acceleration development protocol.

Only the 16 captures in the exact ``rate_development`` policy role are admitted.
The tool consumes digest-pinned serialized parity-split products and never reads
raw IQ.  Even Qin defines training, masks, state, and modes; odd Qin is read only
after an identical four-method forecast opportunity is fixed.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.causal_cfo_acceleration import (  # noqa: E402
    CausalCfoAccelerationConfig,
    CausalCfoAccelerationEstimate,
    CausalCfoPoint,
    CausalPolynomialFit,
    track_causal_cfo_acceleration,
)
from leo.analysis.research.doppler_dataset_policy import (  # noqa: E402
    CaptureDisposition,
    authorize_capture,
    finalize_capture_dispositions,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402

DEFAULT_CONFIG = Path("config/analysis/causal-cfo-acceleration-development-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_causal_cfo_acceleration_development")
SCHEMA = "org.leo.research.causal-cfo-acceleration-development-evidence/v1"
METHOD_CANDIDATE = "causal_hysteretic_quadratic_state"
METHOD_FIXED_20 = "fixed_20ms"
METHOD_FIXED_125 = "fixed_125ms"
METHOD_FIXED_500 = "fixed_500ms"
METHODS = (METHOD_CANDIDATE, METHOD_FIXED_20, METHOD_FIXED_125, METHOD_FIXED_500)
BASELINE_METHOD_BY_HISTORY = {
    0.020: METHOD_FIXED_20,
    0.125: METHOD_FIXED_125,
    0.500: METHOD_FIXED_500,
}
COLORS = {
    METHOD_CANDIDATE: "#d97706",
    METHOD_FIXED_20: "#9ca3af",
    METHOD_FIXED_125: "#4b5563",
    METHOD_FIXED_500: "#2563eb",
}
LABELS = {
    METHOD_CANDIDATE: "Hysteretic quadratic",
    METHOD_FIXED_20: "Fixed 20 ms line",
    METHOD_FIXED_125: "Fixed 125 ms line",
    METHOD_FIXED_500: "Fixed 500 ms line",
}
FRAME_FIELDS = {
    "continuity_safe",
    "even_absolute_cfo_hz",
    "frame_index",
    "frame_start_sample",
    "label",
    "odd_absolute_cfo_hz",
    "reference_time_s",
    "rejection_reasons",
    "training_supported",
}


@dataclass(frozen=True, slots=True)
class FrameRow:
    """One serialized parity-split frame, before response access."""

    capture_label: str
    session_id: str
    locklet_id: str
    frame_ordinal: int
    frame_start_sample: int
    reference_time_s: float
    continuity_safe: bool
    training_supported: bool
    even_cfo_hz: float
    odd_cfo_hz: float


@dataclass(frozen=True, slots=True)
class Locklet:
    """One hard causal segment source; internal supported gaps may split it again."""

    capture_label: str
    session_id: str
    locklet_id: str
    source_name: str
    rows: tuple[FrameRow, ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _load_array(path: Path) -> list[Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"expected one JSON array: {path}")
    return value


def _resolve(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"protocol path must be repository-relative: {relative}")
    resolved = (root / path).resolve()
    resolved.relative_to(root.resolve())
    return resolved


def _verify_digest(path: Path, expected: str) -> None:
    observed = _sha256(path)
    if observed != expected:
        raise ValueError(f"digest mismatch for {path}: {observed} != {expected}")


def _validate_and_bind_protocol(
    root: Path,
    config_path: Path,
) -> tuple[dict[str, Any], Any, dict[str, dict[str, Any]]]:
    config = _load_object(config_path)
    if config.get("schema") != "org.leo.research.causal-cfo-acceleration-development/v1":
        raise ValueError("unsupported causal CFO acceleration protocol")
    basis = config.get("protocol_basis")
    if not isinstance(basis, dict):
        raise ValueError("protocol_basis must be an object")
    if basis.get("response_outcomes_aggregated_before_freeze") is not False:
        raise ValueError("protocol does not attest a pre-outcome freeze")
    if basis.get("raw_iq_reextraction_authorized") is not False:
        raise ValueError("raw IQ rescue is forbidden by this protocol")

    policy_config = config.get("dataset_policy")
    if not isinstance(policy_config, dict):
        raise ValueError("dataset_policy must be an object")
    if policy_config.get("experiment_role") != "rate_development":
        raise ValueError("only the rate_development role is authorized")
    policy_path = _resolve(root, str(policy_config["path"]))
    _verify_digest(policy_path, str(policy_config["sha256"]))
    policy = load_doppler_dataset_policy(policy_path)
    verify_policy_inventory(policy, root)
    expected_ids = tuple(str(value) for value in policy_config["expected_capture_ids"])
    role = policy.role("rate_development")
    if expected_ids != role.capture_ids:
        raise ValueError("protocol capture order/binding differs from the exact policy role")
    if set(expected_ids) & set(policy.role("holdout_foundation").capture_ids):
        raise ValueError("holdout_foundation capture leakage")
    for session_id in expected_ids:
        binding = policy.capture(session_id)
        authorize_capture(
            policy,
            experiment_role="rate_development",
            session_id=session_id,
            recording_manifest_sha256=binding.recording_manifest_sha256,
            analysis_run_id=binding.analysis_run_id,
            analysis_manifest_sha256=binding.analysis_manifest_sha256,
        )

    sources = config.get("serialized_sources")
    if not isinstance(sources, list) or len(sources) != 2:
        raise ValueError("protocol must bind exactly two serialized sources")
    sources_by_name: dict[str, dict[str, Any]] = {}
    covered: set[str] = set()
    for raw_source in sources:
        if not isinstance(raw_source, dict):
            raise ValueError("serialized source must be an object")
        source = dict(raw_source)
        name = str(source["source_name"])
        if name in sources_by_name:
            raise ValueError(f"duplicate serialized source: {name}")
        manifest_path = _resolve(root, str(source["artifact_manifest_path"]))
        payload_path = _resolve(root, str(source["payload_path"]))
        _verify_digest(manifest_path, str(source["artifact_manifest_sha256"]))
        _verify_digest(payload_path, str(source["payload_sha256"]))
        manifest = _load_object(manifest_path)
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError(f"source manifest has no artifact ledger: {name}")
        matching = [
            item
            for item in artifacts.values()
            if isinstance(item, dict) and item.get("sha256") == source["payload_sha256"]
        ]
        if len(matching) != 1 or matching[0].get("path") != payload_path.name:
            raise ValueError(f"payload is not exactly bound by source manifest: {name}")
        if "failure_ledger_path" in source:
            failure_path = _resolve(root, str(source["failure_ledger_path"]))
            _verify_digest(failure_path, str(source["failure_ledger_sha256"]))
            checkpoint = artifacts.get("checkpoint_index")
            if (
                not isinstance(checkpoint, dict)
                or checkpoint.get("sha256") != source["failure_ledger_sha256"]
            ):
                raise ValueError("failure ledger is not bound by the source manifest")
        labels = source.get("capture_labels")
        if not isinstance(labels, dict) or not labels:
            raise ValueError(f"source labels are missing: {name}")
        for session_id in labels.values():
            session = str(session_id)
            if session in covered or session not in expected_ids:
                raise ValueError(f"source capture is duplicate or unauthorized: {session}")
            covered.add(session)
        source["_manifest"] = manifest
        source["_manifest_path"] = manifest_path
        source["_payload_path"] = payload_path
        sources_by_name[name] = source

    unavailable = config.get("non_evaluable_sources")
    if not isinstance(unavailable, list):
        raise ValueError("non_evaluable_sources must be a list")
    unavailable_ids = {str(item["session_id"]) for item in unavailable if isinstance(item, dict)}
    if len(unavailable_ids) != len(unavailable):
        raise ValueError("non-evaluable source ledger has duplicates")
    if covered & unavailable_ids or covered | unavailable_ids != set(expected_ids):
        raise ValueError("serialized and non-evaluable ledgers do not partition the policy role")
    return config, policy, sources_by_name


def _validated_frame(
    raw: object,
    *,
    capture_label: str,
    session_id: str,
    locklet_id: str,
    frame_ordinal: int,
) -> FrameRow:
    if not isinstance(raw, dict) or set(raw) != FRAME_FIELDS:
        raise ValueError(f"unsupported frame inventory row in {locklet_id}")
    if str(raw["label"]) != locklet_id and str(raw["label"]) != capture_label:
        raise ValueError(f"frame label mismatch in {locklet_id}")
    continuity_safe = raw["continuity_safe"]
    supported = raw["training_supported"]
    if not isinstance(continuity_safe, bool) or not isinstance(supported, bool):
        raise ValueError("frame support fields must be boolean")
    frame_sample = raw["frame_start_sample"]
    if isinstance(frame_sample, bool) or not isinstance(frame_sample, int) or frame_sample < 0:
        raise ValueError("frame_start_sample must be a non-negative integer")
    values = (
        float(raw["reference_time_s"]),
        float(raw["even_absolute_cfo_hz"]),
        float(raw["odd_absolute_cfo_hz"]),
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"frame CFO values must be finite in {locklet_id}")
    return FrameRow(
        capture_label=capture_label,
        session_id=session_id,
        locklet_id=locklet_id,
        frame_ordinal=frame_ordinal,
        frame_start_sample=frame_sample,
        reference_time_s=values[0],
        continuity_safe=continuity_safe,
        training_supported=supported,
        even_cfo_hz=values[1],
        odd_cfo_hz=values[2],
    )


def _load_locklets(
    root: Path,
    sources: dict[str, dict[str, Any]],
) -> tuple[tuple[Locklet, ...], list[dict[str, Any]]]:
    locklets: list[Locklet] = []
    recent = sources["recent_frame_inventory"]
    recent_rows = _load_array(recent["_payload_path"])
    by_label: dict[str, list[object]] = defaultdict(list)
    for raw in recent_rows:
        if not isinstance(raw, dict) or not isinstance(raw.get("label"), str):
            raise ValueError("recent frame row has no label")
        by_label[raw["label"]].append(raw)
    for label, session_id in recent["capture_labels"].items():
        raw_rows = by_label.get(label)
        if not raw_rows:
            raise ValueError(f"recent source has no frozen label: {label}")
        rows = tuple(
            _validated_frame(
                raw,
                capture_label=label,
                session_id=session_id,
                locklet_id=label,
                frame_ordinal=index,
            )
            for index, raw in enumerate(raw_rows)
        )
        locklets.append(
            Locklet(
                capture_label=label,
                session_id=session_id,
                locklet_id=label,
                source_name="recent_frame_inventory",
                rows=rows,
            )
        )

    opened = sources["opened_holdout_tile_inventory"]
    with gzip.open(opened["_payload_path"], "rt", encoding="utf-8") as source:
        replay_document = json.load(source)
    if not isinstance(replay_document, dict) or not isinstance(
        replay_document.get("tile_replays"), list
    ):
        raise ValueError("unsupported opened tile replay product")
    seen_tiles: set[str] = set()
    for replay in replay_document["tile_replays"]:
        if not isinstance(replay, dict) or not isinstance(replay.get("tile"), dict):
            raise ValueError("malformed tile replay")
        tile = replay["tile"]
        label = str(tile["capture_label"])
        tile_id = str(tile["tile_id"])
        if label not in opened["capture_labels"] or tile_id in seen_tiles:
            raise ValueError(f"unknown or duplicate opened tile: {tile_id}")
        seen_tiles.add(tile_id)
        raw_rows = replay.get("frame_inventory")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError(f"opened tile has no frame inventory: {tile_id}")
        session_id = opened["capture_labels"][label]
        rows = tuple(
            _validated_frame(
                raw,
                capture_label=label,
                session_id=session_id,
                locklet_id=tile_id,
                frame_ordinal=index,
            )
            for index, raw in enumerate(raw_rows)
        )
        locklets.append(
            Locklet(
                capture_label=label,
                session_id=session_id,
                locklet_id=tile_id,
                source_name="opened_holdout_tile_inventory",
                rows=rows,
            )
        )

    manifest = opened["_manifest"]
    summary_entry = manifest["artifacts"].get("summary")
    if not isinstance(summary_entry, dict):
        raise ValueError("opened tile manifest does not bind its failure summary")
    summary_path = opened["_manifest_path"].parent / str(summary_entry["path"])
    _verify_digest(summary_path, str(summary_entry["sha256"]))
    summary = _load_object(summary_path)
    failures = summary.get("tile_failures")
    if not isinstance(failures, list):
        raise ValueError("opened tile summary has no failure ledger")
    planned = int(summary.get("planned_tile_count", -1))
    if planned != len(seen_tiles) + len(failures):
        raise ValueError("successful and failed tile ledgers do not cover the frozen plan")
    return tuple(locklets), list(failures)


def _config_from_protocol(config: dict[str, Any]) -> CausalCfoAccelerationConfig:
    fit = config["robust_fit"]
    state = config["candidate_state"]
    enter = state["enter_change_mode"]
    leave = state["leave_change_mode"]
    frame = config["frame_contract"]
    baselines = config["baselines"]
    return CausalCfoAccelerationConfig(
        stable_history_s=float(state["stable_history_ms"]) / 1000.0,
        change_history_s=float(state["change_history_ms"]) / 1000.0,
        baseline_histories_s=tuple(
            float(value) / 1000.0 for value in baselines["history_durations_ms"]
        ),
        maximum_supported_point_gap_s=float(frame["maximum_supported_point_gap_ms"]) / 1000.0,
        minimum_history_coverage=float(fit["minimum_history_coverage"]),
        minimum_frames=int(fit["minimum_frames"]),
        minimum_effective_frames=float(fit["minimum_effective_frames"]),
        huber_tuning=float(fit["huber_tuning"]),
        maximum_iterations=int(fit["maximum_iterations"]),
        prediction_convergence_hz=float(fit["prediction_convergence_hz"]),
        standardized_scale_floor=float(fit["standardized_scale_floor"]),
        maximum_normal_condition=float(fit["maximum_normal_condition"]),
        acceleration_zero_prior_sigma_hz_s2=float(state["acceleration_zero_prior_sigma_hz_s2"]),
        enter_residual_hz=float(enter["long_state_one_step_absolute_residual_min_hz"]),
        enter_rate_disagreement_hz_s=float(enter["short_minus_long_absolute_rate_min_hz_s"]),
        enter_consecutive_points=int(enter["consecutive_points"]),
        enter_minimum_span_s=float(enter["minimum_evidence_span_ms"]) / 1000.0,
        leave_residual_hz=float(leave["long_state_one_step_absolute_residual_max_hz"]),
        leave_rate_disagreement_hz_s=float(leave["short_minus_long_absolute_rate_max_hz_s"]),
        leave_minimum_calm_points=int(leave["minimum_calm_points"]),
        leave_minimum_calm_span_s=float(leave["minimum_calm_span_ms"]) / 1000.0,
        minimum_change_hold_s=float(leave["minimum_change_mode_hold_ms"]) / 1000.0,
    )


def _training_points(
    locklet: Locklet,
    *,
    measurement_sigma_hz: float,
    maximum_gap_s: float,
) -> tuple[tuple[CausalCfoPoint, ...], dict[int, int]]:
    points: list[CausalCfoPoint] = []
    segment_by_sample: dict[int, int] = {}
    segment = 0
    previous_time_s: float | None = None
    previous_sample: int | None = None
    for row in locklet.rows:
        if not row.continuity_safe or not row.training_supported:
            continue
        if previous_time_s is not None and (
            row.reference_time_s - previous_time_s > maximum_gap_s + 1e-12
            or (previous_sample is not None and row.frame_start_sample <= previous_sample)
        ):
            segment += 1
        points.append(
            CausalCfoPoint(
                frame_start_sample=row.frame_start_sample,
                reference_time_s=row.reference_time_s,
                continuity_segment=segment,
                even_cfo_hz=row.even_cfo_hz,
                even_cfo_sigma_hz=measurement_sigma_hz,
            )
        )
        segment_by_sample[row.frame_start_sample] = segment
        previous_time_s = row.reference_time_s
        previous_sample = row.frame_start_sample
    return tuple(points), segment_by_sample


def _baseline_by_method(
    estimate: CausalCfoAccelerationEstimate,
) -> dict[str, Any]:
    output = {}
    for fit in estimate.baseline_fits:
        method = BASELINE_METHOD_BY_HISTORY.get(round(fit.requested_history_s, 3))
        if method is not None:
            output[method] = fit
    return output


def _all_method_fits(
    estimate: CausalCfoAccelerationEstimate,
) -> dict[str, Any] | None:
    if estimate.selected_fit is None:
        return None
    output = _baseline_by_method(estimate)
    if set(output) != {METHOD_FIXED_20, METHOD_FIXED_125, METHOD_FIXED_500}:
        return None
    output[METHOD_CANDIDATE] = estimate.selected_fit
    return output


def _stratum(estimate: CausalCfoAccelerationEstimate) -> str:
    fit = estimate.stable_fit
    if fit is not None and fit.weighted_rms_hz <= 50.0 and fit.downweighted_fraction <= 0.10:
        return "strong"
    return "weak_or_ambiguous"


def _state_row(
    locklet: Locklet,
    estimate: CausalCfoAccelerationEstimate,
    fits: dict[str, CausalPolynomialFit],
) -> dict[str, Any]:
    candidate = fits[METHOD_CANDIDATE]
    fixed20 = fits[METHOD_FIXED_20]
    fixed125 = fits[METHOD_FIXED_125]
    fixed500 = fits[METHOD_FIXED_500]
    if estimate.stable_fit is None:
        raise ValueError("identical-mask state row requires a stable fit")
    return {
        "capture_label": locklet.capture_label,
        "session_id": locklet.session_id,
        "locklet_id": locklet.locklet_id,
        "continuity_segment": estimate.continuity_segment,
        "frame_start_sample": estimate.frame_start_sample,
        "reference_time_s": estimate.reference_time_s,
        "stratum": _stratum(estimate),
        "candidate_mode": estimate.mode.value,
        "transition": estimate.transition.value,
        "long_one_step_residual_hz": estimate.long_one_step_residual_hz,
        "short_minus_long_rate_hz_s": estimate.short_minus_long_rate_hz_s,
        "candidate_cfo_hz": candidate.cfo_hz,
        "candidate_rate_hz_s": candidate.rate_hz_s,
        "candidate_acceleration_hz_s2": candidate.acceleration_hz_s2,
        "candidate_weighted_rms_hz": candidate.weighted_rms_hz,
        "stable_weighted_rms_hz": estimate.stable_fit.weighted_rms_hz,
        "stable_downweighted_fraction": estimate.stable_fit.downweighted_fraction,
        "fixed_20ms_cfo_hz": fixed20.cfo_hz,
        "fixed_20ms_rate_hz_s": fixed20.rate_hz_s,
        "fixed_125ms_cfo_hz": fixed125.cfo_hz,
        "fixed_125ms_rate_hz_s": fixed125.rate_hz_s,
        "fixed_500ms_cfo_hz": fixed500.cfo_hz,
        "fixed_500ms_rate_hz_s": fixed500.rate_hz_s,
        "candidate_minus_fixed_20ms_rate_hz_s": candidate.rate_hz_s - fixed20.rate_hz_s,
        "candidate_minus_fixed_125ms_rate_hz_s": candidate.rate_hz_s - fixed125.rate_hz_s,
        "candidate_minus_fixed_500ms_rate_hz_s": candidate.rate_hz_s - fixed500.rate_hz_s,
    }


def _forecast_rows_for_locklet(
    locklet: Locklet,
    estimates: tuple[CausalCfoAccelerationEstimate, ...],
    segment_by_sample: dict[int, int],
    *,
    horizons_s: tuple[float, ...],
    target_stride_frames: int,
    sample_rate_hz: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_segment: dict[int, list[CausalCfoAccelerationEstimate]] = defaultdict(list)
    for estimate in estimates:
        if _all_method_fits(estimate) is not None:
            by_segment[estimate.continuity_segment].append(estimate)
    times_by_segment = {
        segment: [item.reference_time_s for item in values]
        for segment, values in by_segment.items()
    }
    output: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for row in locklet.rows:
        if row.frame_ordinal % target_stride_frames != 0:
            continue
        counters["stride_targets"] += 1
        if not row.continuity_safe or not row.training_supported:
            counters["response_blind_ineligible_targets"] += 1
            continue
        counters["response_blind_eligible_targets"] += 1
        segment = segment_by_sample.get(row.frame_start_sample)
        if segment is None:
            raise ValueError("eligible target has no even-Qin continuity segment")
        estimates_in_segment = by_segment.get(segment, [])
        times = times_by_segment.get(segment, [])
        for requested_horizon_s in horizons_s:
            counters["eligible_target_horizons"] += 1
            cutoff_limit_s = row.reference_time_s - requested_horizon_s
            cutoff_index = bisect.bisect_right(times, cutoff_limit_s + 1e-12) - 1
            if cutoff_index < 0:
                counters["method_unavailable_target_horizons"] += 1
                continue
            estimate = estimates_in_segment[cutoff_index]
            fits = _all_method_fits(estimate)
            assert fits is not None
            counters["paired_target_horizons"] += 1
            if not math.isfinite(row.odd_cfo_hz):
                counters["missing_odd_response_target_horizons"] += 1
                continue
            actual_horizon_s = row.reference_time_s - estimate.reference_time_s
            for method in METHODS:
                fit = fits[method]
                prediction_hz = fit.predict_cfo(row.reference_time_s)
                error_hz = prediction_hz - row.odd_cfo_hz
                output.append(
                    {
                        "capture_label": locklet.capture_label,
                        "session_id": locklet.session_id,
                        "locklet_id": locklet.locklet_id,
                        "continuity_segment": segment,
                        "target_frame_start_sample": row.frame_start_sample,
                        "target_reference_time_s": row.reference_time_s,
                        "cutoff_frame_start_sample": estimate.frame_start_sample,
                        "cutoff_reference_time_s": estimate.reference_time_s,
                        "requested_horizon_ms": requested_horizon_s * 1000.0,
                        "actual_horizon_ms": actual_horizon_s * 1000.0,
                        "recording_block_index": row.frame_start_sample // sample_rate_hz,
                        "stratum": _stratum(estimate),
                        "candidate_mode": estimate.mode.value,
                        "method": method,
                        "cutoff_cfo_hz": fit.cfo_hz,
                        "cutoff_rate_hz_s": fit.rate_hz_s,
                        "cutoff_acceleration_hz_s2": fit.acceleration_hz_s2,
                        "predicted_odd_cfo_hz": prediction_hz,
                        "measured_odd_cfo_hz": row.odd_cfo_hz,
                        "prediction_error_hz": error_hz,
                        "squared_error_hz2": error_hz**2,
                    }
                )
    return output, dict(counters)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(
            sink,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(stable_measurement_floats(rows))


def _rms_by_equal_blocks(rows: list[dict[str, Any]]) -> float:
    by_block: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in rows:
        by_block[(str(row["locklet_id"]), int(row["recording_block_index"]))].append(
            float(row["squared_error_hz2"])
        )
    block_mse = [float(np.mean(values)) for values in by_block.values()]
    return float(math.sqrt(float(np.mean(block_mse))))


def _median(values: list[float]) -> float | None:
    return None if not values else float(np.median(np.asarray(values, dtype=float)))


def _mad(values: list[float]) -> float | None:
    if not values:
        return None
    data = np.asarray(values, dtype=float)
    return float(np.median(np.abs(data - np.median(data))))


def _capture_forecast_metrics(forecast_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in forecast_rows:
        groups[
            (
                str(row["session_id"]),
                str(row["method"]),
                float(row["requested_horizon_ms"]),
            )
        ].append(row)
    output = []
    for (session_id, method, horizon_ms), rows in sorted(groups.items()):
        blocks = {(str(row["locklet_id"]), int(row["recording_block_index"])) for row in rows}
        output.append(
            {
                "capture_label": rows[0]["capture_label"],
                "session_id": session_id,
                "method": method,
                "requested_horizon_ms": horizon_ms,
                "paired_target_count": len(rows),
                "block_count": len(blocks),
                "future_odd_cfo_rms_hz": _rms_by_equal_blocks(rows),
                "median_cutoff_rate_hz_s": _median(
                    [float(row["cutoff_rate_hz_s"]) for row in rows]
                ),
                "rate_mad_hz_s": _mad([float(row["cutoff_rate_hz_s"]) for row in rows]),
                "median_cutoff_acceleration_hz_s2": _median(
                    [float(row["cutoff_acceleration_hz_s2"]) for row in rows]
                ),
                "acceleration_mad_hz_s2": _mad(
                    [float(row["cutoff_acceleration_hz_s2"]) for row in rows]
                ),
            }
        )
    by_key = {
        (row["session_id"], row["method"], row["requested_horizon_ms"]): row for row in output
    }
    for row in output:
        baseline = by_key.get((row["session_id"], METHOD_FIXED_500, row["requested_horizon_ms"]))
        row["rms_ratio_to_fixed_500"] = (
            None
            if baseline is None or baseline["future_odd_cfo_rms_hz"] <= 0.0
            else row["future_odd_cfo_rms_hz"] / baseline["future_odd_cfo_rms_hz"]
        )
    return output


def _aggregate_forecast_metrics(
    capture_metrics: list[dict[str, Any]],
    forecast_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    for horizon_ms in sorted({float(row["requested_horizon_ms"]) for row in capture_metrics}):
        for method in METHODS:
            cells = [
                row
                for row in capture_metrics
                if row["method"] == method and row["requested_horizon_ms"] == horizon_ms
            ]
            if not cells:
                continue
            equal_capture_rms = float(
                math.sqrt(
                    float(np.mean([float(row["future_odd_cfo_rms_hz"]) ** 2 for row in cells]))
                )
            )
            matching_rows = [
                row
                for row in forecast_rows
                if row["method"] == method and row["requested_horizon_ms"] == horizon_ms
            ]
            output.append(
                {
                    "method": method,
                    "requested_horizon_ms": horizon_ms,
                    "capture_count": len(cells),
                    "paired_target_count": len(matching_rows),
                    "equal_capture_future_odd_cfo_rms_hz": equal_capture_rms,
                }
            )
    by_key = {(row["method"], row["requested_horizon_ms"]): row for row in output}
    for row in output:
        baseline = by_key.get((METHOD_FIXED_500, row["requested_horizon_ms"]))
        baseline_rms = (
            None
            if baseline is None
            else cast(float, baseline["equal_capture_future_odd_cfo_rms_hz"])
        )
        row["rms_ratio_to_fixed_500"] = (
            None
            if baseline_rms is None or baseline_rms <= 0.0
            else cast(float, row["equal_capture_future_odd_cfo_rms_hz"]) / baseline_rms
        )
    return output


def _stratum_metrics(forecast_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    groups: dict[tuple[str, float, str], list[dict[str, Any]]] = defaultdict(list)
    for row in forecast_rows:
        groups[
            (str(row["stratum"]), float(row["requested_horizon_ms"]), str(row["method"]))
        ].append(row)
    for (stratum, horizon_ms, method), rows in sorted(groups.items()):
        by_capture: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_capture[str(row["session_id"])].append(row)
        capture_rms = [_rms_by_equal_blocks(values) for values in by_capture.values()]
        output.append(
            {
                "stratum": stratum,
                "requested_horizon_ms": horizon_ms,
                "method": method,
                "capture_count": len(by_capture),
                "paired_target_count": len(rows),
                "equal_capture_future_odd_cfo_rms_hz": float(
                    math.sqrt(float(np.mean(np.square(capture_rms))))
                ),
            }
        )
    return output


def _state_metrics(state_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    by_capture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in state_rows:
        by_capture[str(row["session_id"])].append(row)
    method_fields = {
        METHOD_CANDIDATE: ("candidate_rate_hz_s", "candidate_acceleration_hz_s2"),
        METHOD_FIXED_20: ("fixed_20ms_rate_hz_s", None),
        METHOD_FIXED_125: ("fixed_125ms_rate_hz_s", None),
        METHOD_FIXED_500: ("fixed_500ms_rate_hz_s", None),
    }
    for session_id, rows in sorted(by_capture.items()):
        for method, (rate_field, acceleration_field) in method_fields.items():
            rates = [float(row[rate_field]) for row in rows]
            rate_changes = []
            acceleration_changes = []
            accelerations = (
                []
                if acceleration_field is None
                else [float(row[acceleration_field]) for row in rows]
            )
            by_locklet_segment: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                by_locklet_segment[(str(row["locklet_id"]), int(row["continuity_segment"]))].append(
                    row
                )
            for sequence in by_locklet_segment.values():
                sequence.sort(key=lambda item: int(item["frame_start_sample"]))
                for previous, current in zip(sequence, sequence[1:], strict=False):
                    rate_changes.append(
                        abs(float(current[rate_field]) - float(previous[rate_field]))
                    )
                    if acceleration_field is not None:
                        acceleration_changes.append(
                            abs(
                                float(current[acceleration_field])
                                - float(previous[acceleration_field])
                            )
                        )
            output.append(
                {
                    "capture_label": rows[0]["capture_label"],
                    "session_id": session_id,
                    "method": method,
                    "state_count": len(rows),
                    "median_rate_hz_s": _median(rates),
                    "rate_mad_hz_s": _mad(rates),
                    "median_absolute_successive_rate_change_hz_s": _median(rate_changes),
                    "median_acceleration_hz_s2": _median(accelerations),
                    "acceleration_mad_hz_s2": _mad(accelerations),
                    "median_absolute_successive_acceleration_change_hz_s2": _median(
                        acceleration_changes
                    ),
                }
            )
        candidate_disagreements = {}
        for label in ("20ms", "125ms", "500ms"):
            values = [abs(float(row[f"candidate_minus_fixed_{label}_rate_hz_s"])) for row in rows]
            candidate_disagreements[label] = {
                "median_absolute_hz_s": _median(values),
                "p90_absolute_hz_s": float(np.percentile(values, 90.0)),
            }
        candidate_row = next(
            item
            for item in output
            if item["session_id"] == session_id and item["method"] == METHOD_CANDIDATE
        )
        candidate_row["rate_disagreement_to_baselines"] = candidate_disagreements
        modes = Counter(str(row["candidate_mode"]) for row in rows)
        transitions = Counter(str(row["transition"]) for row in rows)
        candidate_row["mode_counts"] = dict(sorted(modes.items()))
        candidate_row["mode_occupancy"] = {
            key: count / len(rows) for key, count in sorted(modes.items())
        }
        candidate_row["transition_counts"] = dict(sorted(transitions.items()))
    return output


def _development_verdict(
    capture_metrics: list[dict[str, Any]],
    aggregate_metrics: list[dict[str, Any]],
    horizons_ms: tuple[float, ...],
) -> dict[str, Any]:
    qualifying = [
        row
        for row in capture_metrics
        if row["method"] == METHOD_CANDIDATE
        and int(row["paired_target_count"]) >= 50
        and int(row["block_count"]) >= 3
    ]
    support_by_horizon = {
        horizon: sum(row["requested_horizon_ms"] == horizon for row in qualifying)
        for horizon in horizons_ms
    }
    support_pass = all(count >= 7 for count in support_by_horizon.values())
    aggregate_candidate = {
        row["requested_horizon_ms"]: row
        for row in aggregate_metrics
        if row["method"] == METHOD_CANDIDATE
    }
    aggregate_ratios = {
        horizon: (
            None
            if horizon not in aggregate_candidate
            else aggregate_candidate[horizon]["rms_ratio_to_fixed_500"]
        )
        for horizon in horizons_ms
    }
    aggregate_effect_pass = all(
        ratio is not None and float(ratio) <= 0.95 for ratio in aggregate_ratios.values()
    )
    worst_capture_ratio = max(
        (float(row["rms_ratio_to_fixed_500"]) for row in qualifying),
        default=math.inf,
    )
    per_capture_effect_pass = worst_capture_ratio <= 1.10
    if not support_pass:
        verdict = "inconclusive"
        reason = "frozen minimum capture/target/block support was not met at every horizon"
    elif aggregate_effect_pass and per_capture_effect_pass:
        verdict = "promising"
        reason = "all frozen development support and effect conditions passed"
    else:
        verdict = "not_promising"
        reason = "support passed but one or more frozen effect conditions failed"
    return {
        "status": verdict,
        "reason": reason,
        "supporting_capture_count_by_horizon": support_by_horizon,
        "aggregate_candidate_to_fixed_500_rms_ratio": aggregate_ratios,
        "worst_qualifying_capture_horizon_ratio": (
            None if not math.isfinite(worst_capture_ratio) else worst_capture_ratio
        ),
        "support_pass": support_pass,
        "aggregate_effect_pass": aggregate_effect_pass,
        "per_capture_effect_pass": per_capture_effect_pass,
        "development_only": True,
        "holdout_claim": False,
        "known_truth_rate_claim": False,
    }


def _plot_forecast_rms(
    path: Path,
    aggregate_metrics: list[dict[str, Any]],
) -> None:
    horizons = sorted({float(row["requested_horizon_ms"]) for row in aggregate_metrics})
    figure = Figure(figsize=(9.0, 5.5), constrained_layout=True)
    axis = figure.subplots()
    x = np.arange(len(horizons), dtype=float)
    width = 0.19
    for index, method in enumerate(METHODS):
        values_by_horizon = {
            float(row["requested_horizon_ms"]): float(row["equal_capture_future_odd_cfo_rms_hz"])
            for row in aggregate_metrics
            if row["method"] == method
        }
        values = [values_by_horizon.get(value, math.nan) for value in horizons]
        axis.bar(
            x + (index - 1.5) * width,
            values,
            width=width,
            color=COLORS[method],
            label=LABELS[method],
        )
    axis.set_xticks(x, [f"{value:.0f} ms" for value in horizons])
    axis.set_ylabel("Equal-capture future odd-Qin CFO RMS (Hz)")
    axis.set_xlabel("Forecast horizon")
    axis.set_title("Frozen identical-mask causal forecast comparison")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncols=2)
    figure.savefig(path, dpi=160)


def _plot_state_stability(path: Path, state_metrics: list[dict[str, Any]]) -> None:
    captures = sorted(
        {str(row["capture_label"]) for row in state_metrics},
        key=lambda value: (value[0], int(value[1:])),
    )
    figure = Figure(figsize=(11.0, 7.0), constrained_layout=True)
    rate_axis, acceleration_axis = figure.subplots(2, 1)
    x = np.arange(len(captures), dtype=float)
    for method in METHODS:
        by_capture = {
            str(row["capture_label"]): row for row in state_metrics if row["method"] == method
        }
        values = [
            float(by_capture[label]["rate_mad_hz_s"]) if label in by_capture else math.nan
            for label in captures
        ]
        rate_axis.plot(x, values, marker="o", color=COLORS[method], label=LABELS[method])
    candidate = {
        str(row["capture_label"]): row for row in state_metrics if row["method"] == METHOD_CANDIDATE
    }
    acceleration_axis.bar(
        x,
        [
            float(candidate[label]["acceleration_mad_hz_s2"]) if label in candidate else math.nan
            for label in captures
        ],
        color=COLORS[METHOD_CANDIDATE],
    )
    rate_axis.set_ylabel("Rate MAD (Hz/s)")
    rate_axis.set_title("Causal rate-state stability")
    rate_axis.grid(axis="y", alpha=0.25)
    rate_axis.legend(frameon=False, ncols=2)
    acceleration_axis.set_ylabel("Candidate acceleration MAD (Hz/s²)")
    acceleration_axis.set_xlabel("Development capture")
    acceleration_axis.set_xticks(x, captures)
    acceleration_axis.grid(axis="y", alpha=0.25)
    figure.savefig(path, dpi=160)


def _plot_yield_and_mode(
    path: Path,
    capture_metrics: list[dict[str, Any]],
    state_metrics: list[dict[str, Any]],
) -> None:
    candidate_cells = [row for row in capture_metrics if row["method"] == METHOD_CANDIDATE]
    captures = sorted(
        {str(row["capture_label"]) for row in candidate_cells},
        key=lambda value: (value[0], int(value[1:])),
    )
    horizons = sorted({float(row["requested_horizon_ms"]) for row in candidate_cells})
    figure = Figure(figsize=(11.0, 7.0), constrained_layout=True)
    yield_axis, mode_axis = figure.subplots(2, 1)
    x = np.arange(len(captures), dtype=float)
    for horizon in horizons:
        by_capture = {
            str(row["capture_label"]): int(row["paired_target_count"])
            for row in candidate_cells
            if row["requested_horizon_ms"] == horizon
        }
        yield_axis.plot(
            x,
            [by_capture.get(label, 0) for label in captures],
            marker="o",
            label=f"{horizon:.0f} ms",
        )
    candidate_states = {
        str(row["capture_label"]): row for row in state_metrics if row["method"] == METHOD_CANDIDATE
    }
    change_occupancy = [
        float(candidate_states[label].get("mode_occupancy", {}).get("change_125ms", 0.0))
        if label in candidate_states
        else 0.0
        for label in captures
    ]
    mode_axis.bar(x, np.asarray(change_occupancy) * 100.0, color=COLORS[METHOD_CANDIDATE])
    yield_axis.set_ylabel("Paired targets")
    yield_axis.set_title("Identical-mask support")
    yield_axis.set_xticks(x, captures)
    yield_axis.grid(axis="y", alpha=0.25)
    yield_axis.legend(frameon=False, ncols=3)
    mode_axis.set_ylabel("125 ms change mode (%)")
    mode_axis.set_xlabel("Development capture")
    mode_axis.set_xticks(x, captures)
    mode_axis.set_ylim(0.0, max(1.0, 1.1 * max(change_occupancy, default=0.0) * 100.0))
    if not any(change_occupancy):
        mode_axis.text(
            0.5,
            0.5,
            "No change-mode transitions observed",
            ha="center",
            va="center",
            transform=mode_axis.transAxes,
        )
    mode_axis.grid(axis="y", alpha=0.25)
    figure.savefig(path, dpi=160)


def main() -> None:
    args = _arguments()
    root = args.repository_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    output_root = args.output_root if args.output_root.is_absolute() else root / args.output_root
    started = time.perf_counter()
    config, policy, sources = _validate_and_bind_protocol(root, config_path)
    tracker_config = _config_from_protocol(config)
    locklets, frozen_tile_failures = _load_locklets(root, sources)
    load_elapsed_s = time.perf_counter() - started

    frame_contract = config["frame_contract"]
    paired_mask = config["paired_mask"]
    measurement_sigma_hz = float(frame_contract["measurement_sigma_hz"])
    sample_rate_hz = int(frame_contract["sample_rate_hz"])
    horizons_s = tuple(float(value) / 1000.0 for value in paired_mask["forecast_horizons_ms"])
    target_stride = int(paired_mask["target_stride_frames"])
    state_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    locklet_runtime_rows: list[dict[str, Any]] = []
    locklet_counters: dict[str, dict[str, int]] = {}
    locklet_output_counts: Counter[str] = Counter()

    benchmark_started = time.perf_counter()
    for locklet in locklets:
        locklet_started = time.perf_counter()
        points, segment_by_sample = _training_points(
            locklet,
            measurement_sigma_hz=measurement_sigma_hz,
            maximum_gap_s=tracker_config.maximum_supported_point_gap_s,
        )
        track = track_causal_cfo_acceleration(points, config=tracker_config)
        for estimate in track.estimates:
            fits = _all_method_fits(estimate)
            if fits is None:
                continue
            state_rows.append(_state_row(locklet, estimate, fits))
            locklet_output_counts[locklet.locklet_id] += 1
        rows, counters = _forecast_rows_for_locklet(
            locklet,
            track.estimates,
            segment_by_sample,
            horizons_s=horizons_s,
            target_stride_frames=target_stride,
            sample_rate_hz=sample_rate_hz,
        )
        forecast_rows.extend(rows)
        locklet_counters[locklet.locklet_id] = counters
        elapsed_s = time.perf_counter() - locklet_started
        locklet_runtime_rows.append(
            {
                "capture_label": locklet.capture_label,
                "session_id": locklet.session_id,
                "locklet_id": locklet.locklet_id,
                "source_name": locklet.source_name,
                "frame_count": len(locklet.rows),
                "supported_training_point_count": len(points),
                "identical_mask_state_count": locklet_output_counts[locklet.locklet_id],
                "wall_clock_s": elapsed_s,
                "supported_points_per_s": (len(points) / elapsed_s if elapsed_s > 0.0 else None),
                **counters,
            }
        )
    benchmark_elapsed_s = time.perf_counter() - benchmark_started

    capture_metrics = _capture_forecast_metrics(forecast_rows)
    aggregate_metrics = _aggregate_forecast_metrics(capture_metrics, forecast_rows)
    stratum_metrics = _stratum_metrics(forecast_rows)
    state_metrics = _state_metrics(state_rows)
    verdict = _development_verdict(
        capture_metrics,
        aggregate_metrics,
        tuple(value * 1000.0 for value in horizons_s),
    )

    policy_role = policy.role("rate_development")
    numeric_capture_ids = {str(row["session_id"]) for row in forecast_rows}
    fixed_unavailable = {
        str(item["session_id"]): str(item["reason"]) for item in config["non_evaluable_sources"]
    }
    dispositions = []
    disposition_rows = []
    for session_id in policy_role.capture_ids:
        if session_id in numeric_capture_ids:
            status = "evaluable"
            reason = "digest-closed parity-split source produced identical-mask forecasts"
        else:
            status = "non_evaluable"
            reason = fixed_unavailable.get(
                session_id,
                "serialized source produced no identical-mask forecast rows",
            )
        disposition = CaptureDisposition(
            capture=policy.capture(session_id), status=status, reason=reason
        )
        dispositions.append(disposition)
        disposition_rows.append(
            {
                "session_id": session_id,
                "status": status,
                "reason": reason,
                "recording_manifest_sha256": disposition.capture.recording_manifest_sha256,
                "analysis_run_id": disposition.capture.analysis_run_id,
                "analysis_manifest_sha256": disposition.capture.analysis_manifest_sha256,
            }
        )
    finalize_capture_dispositions(
        policy,
        experiment_role="rate_development",
        dispositions=tuple(dispositions),
    )

    tile_disposition_rows = []
    for locklet in locklets:
        tile_disposition_rows.append(
            {
                "capture_label": locklet.capture_label,
                "session_id": locklet.session_id,
                "locklet_id": locklet.locklet_id,
                "source_name": locklet.source_name,
                "status": (
                    "evaluable"
                    if locklet_output_counts[locklet.locklet_id] > 0
                    else "non_evaluable"
                ),
                "reason": (
                    "identical-mask state rows available"
                    if locklet_output_counts[locklet.locklet_id] > 0
                    else "no identical-mask state rows after frozen causal support gates"
                ),
                "state_count": locklet_output_counts[locklet.locklet_id],
            }
        )
    opened_labels = sources["opened_holdout_tile_inventory"]["capture_labels"]
    for failure in frozen_tile_failures:
        tile = failure["tile"]
        label = str(tile["capture_label"])
        tile_disposition_rows.append(
            {
                "capture_label": label,
                "session_id": opened_labels[label],
                "locklet_id": str(tile["tile_id"]),
                "source_name": "opened_holdout_tile_inventory",
                "status": "source_failure",
                "reason": str(failure["reason"]),
                "state_count": 0,
            }
        )
    tile_disposition_rows.sort(key=lambda row: (row["capture_label"], row["locklet_id"]))

    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "state-rows.csv"
    forecast_path = output_root / "forecast-rows.csv"
    capture_disposition_path = output_root / "capture-dispositions.csv"
    tile_disposition_path = output_root / "tile-dispositions.csv"
    runtime_path = output_root / "runtime-rows.csv"
    _write_csv(state_path, state_rows, list(state_rows[0]) if state_rows else [])
    _write_csv(forecast_path, forecast_rows, list(forecast_rows[0]) if forecast_rows else [])
    _write_csv(
        capture_disposition_path,
        disposition_rows,
        list(disposition_rows[0]),
    )
    _write_csv(
        tile_disposition_path,
        tile_disposition_rows,
        list(tile_disposition_rows[0]),
    )
    _write_csv(runtime_path, locklet_runtime_rows, list(locklet_runtime_rows[0]))

    forecast_plot = output_root / "forecast-rms.png"
    stability_plot = output_root / "rate-acceleration-stability.png"
    yield_plot = output_root / "yield-and-mode.png"
    _plot_forecast_rms(forecast_plot, aggregate_metrics)
    _plot_state_stability(stability_plot, state_metrics)
    _plot_yield_and_mode(yield_plot, capture_metrics, state_metrics)

    implementation_paths = {
        "tracker": root / "src/leo/analysis/research/causal_cfo_acceleration.py",
        "benchmark": root / "tools/benchmark_causal_cfo_acceleration_development.py",
    }
    total_elapsed_s = time.perf_counter() - started
    evidence = {
        "schema": SCHEMA,
        "protocol": {
            "path": str(config_path.relative_to(root)),
            "sha256": _sha256(config_path),
            "basis_repository_commit": config["protocol_basis"]["repository_commit"],
            "experiment_role": "rate_development",
            "development_only": True,
        },
        "policy": {
            "path": config["dataset_policy"]["path"],
            "sha256": config["dataset_policy"]["sha256"],
            "inventory_path": policy.inventory_path,
            "inventory_sha256": policy.inventory_sha256,
            "exact_role_capture_count": len(policy_role.capture_ids),
            "holdout_foundation_consumed": False,
        },
        "serialized_sources": [
            {key: source[key] for key in source if not key.startswith("_")}
            for source in sources.values()
        ],
        "implementation_sha256": {key: _sha256(path) for key, path in implementation_paths.items()},
        "scope": {
            "capture_count": len(policy_role.capture_ids),
            "evaluable_capture_count": len(numeric_capture_ids),
            "fixed_non_evaluable_capture_count": len(fixed_unavailable),
            "hard_locklet_count": len(locklets),
            "frozen_source_failure_count": len(frozen_tile_failures),
            "frame_count": sum(len(locklet.rows) for locklet in locklets),
            "supported_training_point_count": sum(
                int(row["supported_training_point_count"]) for row in locklet_runtime_rows
            ),
            "identical_mask_state_count": len(state_rows),
            "forecast_method_row_count": len(forecast_rows),
            "paired_target_horizon_count": len(forecast_rows) // len(METHODS),
        },
        "capture_dispositions": disposition_rows,
        "tile_failure_ledger": frozen_tile_failures,
        "likelihood_gate": {
            **config["likelihood_gate"],
            "real_data_invocation_count": None,
            "real_data_compute_or_accuracy_result": None,
            "unit_test_only": True,
        },
        "forecast_metrics_by_capture": capture_metrics,
        "forecast_metrics_equal_capture": aggregate_metrics,
        "forecast_metrics_by_stratum": stratum_metrics,
        "state_metrics_by_capture": state_metrics,
        "development_verdict": verdict,
        "compute": {
            "source_load_and_verification_s": load_elapsed_s,
            "benchmark_wall_clock_s": benchmark_elapsed_s,
            "total_wall_clock_s_before_evidence_write": total_elapsed_s,
            "supported_state_input_points_per_s": (
                sum(int(row["supported_training_point_count"]) for row in locklet_runtime_rows)
                / benchmark_elapsed_s
                if benchmark_elapsed_s > 0.0
                else None
            ),
            "runtime_rows": locklet_runtime_rows,
        },
        "uncertainty": {
            "covariance_claimed": False,
            "nis_reported": False,
            "coverage_68_95_reported": False,
            "reason": "robust local-polynomial covariance was not calibrated or claimed",
        },
        "interpretation_limits": [
            "development-only opened captures; not a holdout",
            "future odd-Qin CFO error is prediction error, not known Doppler-rate truth error",
            "upstream frozen source/epoch/alias membership was not end-to-end odd-Qin-independent",
            "receiver-relative CFO includes unmeasured receiver, LNB, and clock drift",
            "six policy captures lack a serialized parity-split source",
            "the full-likelihood gate has no real-data result because required surfaces are absent",
        ],
    }
    evidence_path = output_root / "evidence.json"
    evidence_path.write_bytes(_json_bytes(evidence))

    artifact_paths = (
        evidence_path,
        state_path,
        forecast_path,
        capture_disposition_path,
        tile_disposition_path,
        runtime_path,
        forecast_plot,
        stability_plot,
        yield_plot,
    )
    artifact_manifest = {
        "schema": "org.leo.research.causal-cfo-acceleration-development-artifacts/v1",
        "protocol_sha256": _sha256(config_path),
        "artifacts": {
            path.name: {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in artifact_paths
        },
    }
    manifest_path = output_root / "artifact-manifest.json"
    manifest_path.write_bytes(_json_bytes(artifact_manifest))
    print(
        json.dumps(
            stable_measurement_floats(
                {
                    "verdict": verdict,
                    "scope": evidence["scope"],
                    "compute": evidence["compute"],
                    "evidence": str(evidence_path),
                    "artifact_manifest": str(manifest_path),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
