#!/usr/bin/env python3
"""Evaluate causal adaptive frame-CFO tracking on recent verified dwells.

The input is the immutable artifact from ``prototype_recent_frame_cfo_rate``.
Only even-Qin frame CFO points update the three trackers.  A future odd-Qin
point is scored after a predeclared forecast delay; it cannot affect tracker
state, history selection, target membership, or method availability.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402

from leo.analysis.research.adaptive_frame_cfo import (  # noqa: E402
    AdaptiveFrameCfoConfig,
    AdaptiveFrameCfoEstimate,
    AdaptiveFrameCfoPoint,
    AdaptiveFrameCfoTrack,
    track_adaptive_frame_cfo,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402

DEFAULT_INPUTS = Path("config/analysis/recent-adaptive-cfo-track-v1.json")
DEFAULT_UPSTREAM_ROOT = Path("reports/figures/2026_08_25_recent_frame_cfo_rate")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_recent_adaptive_cfo_track")

METHOD_ADAPTIVE = "adaptive_75_500ms"
METHOD_FIXED_125 = "fixed_125ms"
METHOD_FIXED_500 = "fixed_500ms"
METHODS = (METHOD_FIXED_125, METHOD_FIXED_500, METHOD_ADAPTIVE)
_COLORS = {
    METHOD_FIXED_125: "#6b7280",
    METHOD_FIXED_500: "#2563eb",
    METHOD_ADAPTIVE: "#d97706",
}
_LABELS = {
    METHOD_FIXED_125: "Fixed 125 ms",
    METHOD_FIXED_500: "Fixed 500 ms",
    METHOD_ADAPTIVE: "Adaptive 75–500 ms",
}
_LINESTYLES = {
    METHOD_FIXED_125: "-",
    METHOD_FIXED_500: "-",
    METHOD_ADAPTIVE: "--",
}
_INVENTORY_FIELDS = {
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
_UPSTREAM_SUMMARY_FIELDS = {
    "candidate_only",
    "carrier_phase_connected",
    "configuration",
    "continuity_policy",
    "dwells",
    "full_frozen_run",
    "implementation_sha256",
    "input_sha256",
    "known_pilots_only",
    "maximum_age_s",
    "method_summaries",
    "odd_qin_provenance",
    "schema",
    "selection_reference_utc",
    "track_visualization",
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--upstream-root", type=Path, default=DEFAULT_UPSTREAM_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
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


def _validate_config(document: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "upstream_artifact_manifest_sha256",
        "labels",
        "sample_rate_hz",
        "pilot_reference_offset_samples",
        "measurement_sigma_hz",
        "history_durations_ms",
        "fixed_history_durations_ms",
        "forecast_horizons_ms",
        "target_stride_frames",
        "aggregation_block_s",
        "maximum_gap_ms",
        "minimum_frames",
        "minimum_effective_frames",
        "minimum_history_coverage",
        "consistency_chi_square",
    }
    if set(document) != fields or document.get("schema") != (
        "org.leo.research.recent-adaptive-cfo-track-inputs/v1"
    ):
        raise ValueError("unsupported or non-closed adaptive CFO input")
    digest = document["upstream_artifact_manifest_sha256"]
    if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        raise ValueError("upstream artifact manifest digest is invalid")
    labels = document["labels"]
    if (
        not isinstance(labels, list)
        or len(labels) < 2
        or labels != sorted(set(labels))
        or any(not isinstance(label, str) or not label for label in labels)
    ):
        raise ValueError("labels must be sorted unique nonempty strings")
    sample_rate_hz = document["sample_rate_hz"]
    reference_offset = document["pilot_reference_offset_samples"]
    if (
        isinstance(sample_rate_hz, bool)
        or not isinstance(sample_rate_hz, int)
        or sample_rate_hz <= 0
        or isinstance(reference_offset, bool)
        or not isinstance(reference_offset, int)
        or reference_offset < 0
    ):
        raise ValueError("sample rate and pilot reference offset must be integer samples")

    def ordered_positive(name: str) -> tuple[float, ...]:
        raw = document[name]
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{name} must be one nonempty list")
        values = tuple(float(value) for value in raw)
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError(f"{name} must contain finite positive values")
        if values != tuple(sorted(set(values))):
            raise ValueError(f"{name} must be strictly increasing and unique")
        return values

    histories = ordered_positive("history_durations_ms")
    fixed = ordered_positive("fixed_history_durations_ms")
    horizons = ordered_positive("forecast_horizons_ms")
    if histories != (75.0, 125.0, 250.0, 500.0):
        raise ValueError("adaptive histories are frozen at 75/125/250/500 ms")
    if fixed != (125.0, 500.0) or any(value not in histories for value in fixed):
        raise ValueError("fixed histories must be the frozen 125/500 ms pair")
    if horizons != (125.0, 500.0, 1_000.0):
        raise ValueError("forecast horizons are frozen at 125/500/1000 ms")
    sample_scales_ms = (*histories, *fixed, *horizons)
    if any(
        not math.isclose(
            value * int(sample_rate_hz) / 1_000.0,
            round(value * int(sample_rate_hz) / 1_000.0),
            abs_tol=1e-9,
        )
        for value in sample_scales_ms
    ):
        raise ValueError("history and forecast durations must be exact in device samples")
    positive = (
        document["measurement_sigma_hz"],
        document["aggregation_block_s"],
        document["maximum_gap_ms"],
        document["minimum_history_coverage"],
        document["consistency_chi_square"],
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in positive
    ):
        raise ValueError("adaptive tracker scales must be finite and positive")
    if not 0.0 < float(document["minimum_history_coverage"]) <= 1.0:
        raise ValueError("minimum history coverage must lie in (0, 1]")
    integers = (
        document["target_stride_frames"],
        document["minimum_frames"],
        document["minimum_effective_frames"],
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integers
    ):
        raise ValueError("adaptive tracker counts must be positive integers")
    if int(document["minimum_frames"]) < 3 or not (
        2 < int(document["minimum_effective_frames"]) <= int(document["minimum_frames"])
    ):
        raise ValueError("adaptive fit support counts are invalid")
    return document


def _verify_artifact(root: Path, item: dict[str, Any]) -> Path:
    if set(item) != {"bytes", "path", "sha256"}:
        raise ValueError("upstream artifact entry is not closed")
    name = item["path"]
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("upstream artifact path must be one local filename")
    path = root / name
    if not path.is_file():
        raise ValueError(f"missing upstream artifact: {name}")
    if path.stat().st_size != item["bytes"] or _sha256(path) != item["sha256"]:
        raise ValueError(f"upstream artifact digest mismatch: {name}")
    return path


def _load_verified_upstream(
    root: Path,
    expected_manifest_sha256: str,
) -> tuple[dict[str, Any], tuple[dict[str, object], ...], dict[str, Any]]:
    manifest_path = root / "artifact-manifest.json"
    if _sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("upstream artifact manifest digest mismatch")
    manifest = _load_object(manifest_path)
    if set(manifest) != {"schema", "artifacts"} or manifest.get("schema") != (
        "org.leo.research.recent-frame-cfo-rate-artifacts/v1"
    ):
        raise ValueError("unsupported upstream artifact manifest")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or not {"summary", "frame_inventory"} <= set(artifacts):
        raise ValueError("upstream manifest lacks required artifacts")
    summary_path = _verify_artifact(root, artifacts["summary"])
    inventory_path = _verify_artifact(root, artifacts["frame_inventory"])
    summary = _load_object(summary_path)
    if set(summary) != _UPSTREAM_SUMMARY_FIELDS or summary.get("schema") != (
        "org.leo.research.recent-frame-cfo-rate-summary/v1"
    ):
        raise ValueError("unsupported upstream frame-CFO summary")
    if not summary.get("full_frozen_run") or float(summary.get("maximum_age_s", math.inf)) > 43_200:
        raise ValueError("upstream frame-CFO run is not a full <=12-hour selection")
    if summary.get("carrier_phase_connected") is not False:
        raise ValueError("upstream frame CFO must not connect carrier phase")
    raw_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(raw_inventory, list) or not raw_inventory:
        raise ValueError("upstream frame inventory must be one nonempty list")
    inventory: list[dict[str, object]] = []
    identities: set[tuple[str, int]] = set()
    for raw in raw_inventory:
        if not isinstance(raw, dict) or set(raw) != _INVENTORY_FIELDS:
            raise ValueError("upstream frame inventory row is not closed")
        label = raw["label"]
        frame_start = raw["frame_start_sample"]
        frame_index = raw["frame_index"]
        if (
            not isinstance(label, str)
            or not label
            or isinstance(frame_start, bool)
            or not isinstance(frame_start, int)
            or frame_start < 0
            or isinstance(frame_index, bool)
            or not isinstance(frame_index, int)
            or frame_index < 0
        ):
            raise ValueError("upstream frame identity is invalid")
        key = (label, frame_start)
        if key in identities:
            raise ValueError("upstream frame identities must be unique")
        identities.add(key)
        if not isinstance(raw["continuity_safe"], bool) or not isinstance(
            raw["training_supported"], bool
        ):
            raise ValueError("upstream frame support flags must be Boolean")
        if not isinstance(raw["rejection_reasons"], list) or any(
            not isinstance(reason, str) for reason in raw["rejection_reasons"]
        ):
            raise ValueError("upstream rejection reasons are invalid")
        numeric = (
            raw["reference_time_s"],
            raw["even_absolute_cfo_hz"],
            raw["odd_absolute_cfo_hz"],
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in numeric
        ):
            raise ValueError("upstream split-CFO values must be finite")
        inventory.append(raw)
    inventory.sort(key=lambda row: (str(row["label"]), float(row["reference_time_s"])))
    return summary, tuple(inventory), manifest


def _tracker_config(
    document: dict[str, Any], histories_ms: tuple[float, ...]
) -> AdaptiveFrameCfoConfig:
    return AdaptiveFrameCfoConfig(
        history_durations_s=tuple(value / 1_000.0 for value in histories_ms),
        minimum_history_coverage=float(document["minimum_history_coverage"]),
        minimum_frames=int(document["minimum_frames"]),
        minimum_effective_frames=float(document["minimum_effective_frames"]),
        maximum_gap_s=float(document["maximum_gap_ms"]) / 1_000.0,
        consistency_chi_square=float(document["consistency_chi_square"]),
    )


def _build_tracks(
    inventory: tuple[dict[str, object], ...],
    document: dict[str, Any],
) -> dict[str, dict[str, AdaptiveFrameCfoTrack]]:
    labels = tuple(str(value) for value in document["labels"])
    present = tuple(sorted({str(row["label"]) for row in inventory}))
    if present != labels:
        raise ValueError("upstream frame labels disagree with the frozen input labels")
    sigma_hz = float(document["measurement_sigma_hz"])
    histories = tuple(float(value) for value in document["history_durations_ms"])
    output: dict[str, dict[str, AdaptiveFrameCfoTrack]] = {}
    for label in labels:
        label_rows = tuple(row for row in inventory if row["label"] == label)
        selected: list[tuple[dict[str, object], int]] = []
        continuity_segment = 0
        unsafe_since_last_point = False
        for row in label_rows:
            if not bool(row["continuity_safe"]):
                unsafe_since_last_point = True
                continue
            if unsafe_since_last_point:
                continuity_segment += 1
                unsafe_since_last_point = False
            if bool(row["training_supported"]):
                selected.append((row, continuity_segment))
        if not selected:
            raise ValueError(f"no supported even-Qin frames for {label}")
        points = tuple(
            AdaptiveFrameCfoPoint(
                frame_start_sample=int(row["frame_start_sample"]),
                reference_time_s=float(row["reference_time_s"]),
                continuity_segment=segment,
                even_cfo_hz=float(row["even_absolute_cfo_hz"]),
                even_cfo_sigma_hz=sigma_hz,
            )
            for row, segment in selected
        )
        output[label] = {
            METHOD_FIXED_125: track_adaptive_frame_cfo(
                points,
                config=_tracker_config(document, (125.0,)),
            ),
            METHOD_FIXED_500: track_adaptive_frame_cfo(
                points,
                config=_tracker_config(document, (500.0,)),
            ),
            METHOD_ADAPTIVE: track_adaptive_frame_cfo(
                points,
                config=_tracker_config(document, histories),
            ),
        }
    return output


def _estimate_map(track: AdaptiveFrameCfoTrack) -> dict[int, AdaptiveFrameCfoEstimate]:
    return {estimate.frame_start_sample: estimate for estimate in track.estimates}


def _locklet_map(track: AdaptiveFrameCfoTrack) -> dict[int, int]:
    locklet = -1
    output = {}
    for estimate in track.estimates:
        if estimate.reset_reason.value != "none":
            locklet += 1
        output[estimate.frame_start_sample] = locklet
    return output


def _forecast_rows(
    inventory: tuple[dict[str, object], ...],
    tracks: dict[str, dict[str, AdaptiveFrameCfoTrack]],
    document: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    """Score future odd-Qin points on one paired, even-selected target mask."""

    horizons_s = tuple(float(value) / 1_000.0 for value in document["forecast_horizons_ms"])
    stride = int(document["target_stride_frames"])
    block_s = float(document["aggregation_block_s"])
    output: list[dict[str, object]] = []
    for label in tuple(str(value) for value in document["labels"]):
        label_rows = tuple(row for row in inventory if row["label"] == label)
        sample_rate_hz = int(document["sample_rate_hz"])
        reference_offset = int(document["pilot_reference_offset_samples"])
        training = tuple(
            row
            for row in label_rows
            if bool(row["continuity_safe"]) and bool(row["training_supported"])
        )
        training_reference_samples = [
            int(row["frame_start_sample"]) + reference_offset for row in training
        ]
        maps = {method: _estimate_map(tracks[label][method]) for method in METHODS}
        locklets = _locklet_map(tracks[label][METHOD_ADAPTIVE])
        targets = tuple(
            row
            for row in label_rows
            if bool(row["continuity_safe"])
            and bool(row["training_supported"])
            and int(row["frame_index"]) % stride == 0
        )
        for target in targets:
            target_time_s = float(target["reference_time_s"])
            target_odd_hz = float(target["odd_absolute_cfo_hz"])
            target_reference_sample = int(target["frame_start_sample"]) + reference_offset
            for horizon_s in horizons_s:
                horizon_samples = round(horizon_s * sample_rate_hz)
                requested_cutoff_sample = target_reference_sample - horizon_samples
                index = bisect.bisect_right(training_reference_samples, requested_cutoff_sample) - 1
                if index < 0:
                    continue
                cutoff = training[index]
                cutoff_frame_start_sample = int(cutoff["frame_start_sample"])
                training_stop_reference_sample = cutoff_frame_start_sample + reference_offset
                estimates = {method: maps[method][cutoff_frame_start_sample] for method in METHODS}
                target_frame_start_sample = int(target["frame_start_sample"])
                if locklets[cutoff_frame_start_sample] != locklets[target_frame_start_sample]:
                    continue
                if any(
                    estimate.cfo_hz is None
                    or estimate.rate_hz_s is None
                    or estimate.cfo_sigma_hz is None
                    or estimate.rate_sigma_hz_s is None
                    or estimate.cfo_rate_covariance_hz2_s is None
                    for estimate in estimates.values()
                ):
                    continue
                pair_id = f"{label}:{int(target['frame_start_sample'])}:{horizon_samples}samples"
                for method in METHODS:
                    estimate = estimates[method]
                    assert estimate.cfo_hz is not None
                    assert estimate.rate_hz_s is not None
                    assert estimate.cfo_sigma_hz is not None
                    assert estimate.rate_sigma_hz_s is not None
                    assert estimate.cfo_rate_covariance_hz2_s is not None
                    delta_s = (
                        target_reference_sample - training_stop_reference_sample
                    ) / sample_rate_hz
                    prediction_hz = estimate.cfo_hz + estimate.rate_hz_s * delta_s
                    variance_hz2 = (
                        estimate.cfo_sigma_hz**2
                        + delta_s**2 * estimate.rate_sigma_hz_s**2
                        + 2.0 * delta_s * estimate.cfo_rate_covariance_hz2_s
                    )
                    output.append(
                        {
                            "pair_id": pair_id,
                            "label": label,
                            "method": method,
                            "horizon_ms": horizon_s * 1_000.0,
                            "block_index": int(
                                math.floor(target_reference_sample / (sample_rate_hz * block_s))
                            ),
                            "target_frame_index": int(target["frame_index"]),
                            "target_frame_start_sample": target_frame_start_sample,
                            "target_reference_sample": target_reference_sample,
                            "target_time_s": target_time_s,
                            "target_odd_cfo_hz": target_odd_hz,
                            "cutoff_sample": requested_cutoff_sample,
                            "cutoff_time_s": requested_cutoff_sample / sample_rate_hz,
                            "training_cutoff_frame_start_sample": cutoff_frame_start_sample,
                            "training_stop_reference_sample": training_stop_reference_sample,
                            "training_stop_time_s": estimate.reference_time_s,
                            "last_training_age_ms": 1_000.0
                            * (requested_cutoff_sample - training_stop_reference_sample)
                            / sample_rate_hz,
                            "actual_forecast_s": delta_s,
                            "selected_history_ms": float(estimate.selected_history_s) * 1_000.0,
                            "cfo_hz_at_cutoff": estimate.cfo_hz,
                            "rate_hz_s": estimate.rate_hz_s,
                            "prediction_hz": prediction_hz,
                            "prediction_sigma_hz": math.sqrt(max(variance_hz2, 0.0)),
                            "odd_residual_hz": target_odd_hz - prediction_hz,
                        }
                    )
    output.sort(
        key=lambda row: (
            str(row["label"]),
            float(row["horizon_ms"]),
            int(row["target_frame_start_sample"]),
            METHODS.index(str(row["method"])),
        )
    )
    _validate_paired_rows(tuple(output))
    return tuple(output)


def _validate_paired_rows(rows: tuple[dict[str, object], ...]) -> None:
    methods_by_pair: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        methods_by_pair[str(row["pair_id"])].add(str(row["method"]))
        if int(row["training_stop_reference_sample"]) > int(row["cutoff_sample"]):
            raise ValueError("forecast training cutoff uses a future frame")
    if not methods_by_pair or any(methods != set(METHODS) for methods in methods_by_pair.values()):
        raise ValueError("forecast methods do not share one paired target mask")


def _metric(values: np.ndarray) -> tuple[float, float, float]:
    return (
        float(math.sqrt(float(np.mean(values**2)))),
        float(np.median(np.abs(values))),
        float(np.mean(values)),
    )


def _summaries(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    _validate_paired_rows(rows)
    grouped: dict[tuple[str, float, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["label"]), float(row["horizon_ms"]), str(row["method"]))].append(row)
    output: list[dict[str, object]] = []
    per_dwell_mse: dict[tuple[float, str], list[float]] = defaultdict(list)
    for (label, horizon_ms, method), selected in sorted(grouped.items()):
        residual = np.asarray([float(row["odd_residual_hz"]) for row in selected])
        rms, median_absolute, bias = _metric(residual)
        blocks: dict[int, list[float]] = defaultdict(list)
        for row in selected:
            blocks[int(row["block_index"])].append(float(row["odd_residual_hz"]) ** 2)
        block_equal_mse = float(np.mean([np.mean(values) for values in blocks.values()]))
        per_dwell_mse[(horizon_ms, method)].append(block_equal_mse)
        output.append(
            {
                "scope": "dwell",
                "label": label,
                "horizon_ms": horizon_ms,
                "method": method,
                "target_count": len(selected),
                "block_count": len(blocks),
                "odd_rms_hz": rms,
                "odd_block_equal_rms_hz": math.sqrt(block_equal_mse),
                "odd_median_absolute_hz": median_absolute,
                "odd_bias_hz": bias,
                "median_rate_hz_s": float(np.median([float(row["rate_hz_s"]) for row in selected])),
                "rate_mad_hz_s": float(
                    np.median(
                        np.abs(
                            np.asarray([float(row["rate_hz_s"]) for row in selected])
                            - np.median([float(row["rate_hz_s"]) for row in selected])
                        )
                    )
                ),
            }
        )
    aggregate: dict[tuple[float, str], dict[str, object]] = {}
    for (horizon_ms, method), dwell_mse in sorted(per_dwell_mse.items()):
        aggregate[(horizon_ms, method)] = {
            "scope": "equal_dwell",
            "label": "ALL",
            "horizon_ms": horizon_ms,
            "method": method,
            "dwell_count": len(dwell_mse),
            "odd_block_equal_rms_hz": math.sqrt(float(np.mean(dwell_mse))),
        }
    for horizon_ms in sorted({key[0] for key in aggregate}):
        baseline = float(aggregate[(horizon_ms, METHOD_FIXED_125)]["odd_block_equal_rms_hz"])
        for method in METHODS:
            row = aggregate[(horizon_ms, method)]
            candidate = float(row["odd_block_equal_rms_hz"])
            row["improvement_vs_fixed_125_percent"] = 100.0 * (1.0 - candidate / baseline)
            output.append(row)
    return tuple(output)


def _rate_trace_rows(
    tracks: dict[str, dict[str, AdaptiveFrameCfoTrack]],
    document: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    stride = int(document["target_stride_frames"])
    output = []
    for label in sorted(tracks):
        for method in METHODS:
            for index, estimate in enumerate(tracks[label][method].estimates):
                if index % stride or estimate.rate_hz_s is None:
                    continue
                output.append(
                    {
                        "label": label,
                        "method": method,
                        "frame_start_sample": estimate.frame_start_sample,
                        "reference_time_s": estimate.reference_time_s,
                        "selected_history_ms": float(estimate.selected_history_s) * 1_000.0,
                        "cfo_hz": estimate.cfo_hz,
                        "rate_hz_s": estimate.rate_hz_s,
                        "rate_sigma_hz_s": estimate.rate_sigma_hz_s,
                        "reset_reason": estimate.reset_reason.value,
                        "selection_reason": estimate.selection_reason.value,
                        "history_change_reason": estimate.history_change_reason.value,
                    }
                )
    return tuple(output)


def _summary_lookup(
    summaries: tuple[dict[str, object], ...], scope: str, label: str, horizon: float, method: str
) -> dict[str, object]:
    matches = [
        row
        for row in summaries
        if row["scope"] == scope
        and row["label"] == label
        and float(row["horizon_ms"]) == horizon
        and row["method"] == method
    ]
    if len(matches) != 1:
        raise ValueError("summary lookup is not unique")
    return matches[0]


def _comparison_effects(
    summaries: tuple[dict[str, object], ...],
    document: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    labels = tuple(str(value) for value in document["labels"])
    output = []
    for horizon in tuple(float(value) for value in document["forecast_horizons_ms"]):
        for candidate_method in (METHOD_FIXED_500, METHOD_ADAPTIVE):
            ratios = []
            per_dwell = {}
            for label in labels:
                baseline = float(
                    _summary_lookup(summaries, "dwell", label, horizon, METHOD_FIXED_125)[
                        "odd_block_equal_rms_hz"
                    ]
                )
                candidate = float(
                    _summary_lookup(summaries, "dwell", label, horizon, candidate_method)[
                        "odd_block_equal_rms_hz"
                    ]
                )
                ratio = candidate / baseline
                ratios.append(ratio)
                per_dwell[label] = ratio
            leave_one_out = [
                math.exp(float(np.mean(np.log(np.delete(np.asarray(ratios), index)))))
                for index in range(len(ratios))
            ]
            geometric_ratio = math.exp(float(np.mean(np.log(ratios))))
            aggregate_baseline = float(
                _summary_lookup(summaries, "equal_dwell", "ALL", horizon, METHOD_FIXED_125)[
                    "odd_block_equal_rms_hz"
                ]
            )
            aggregate_candidate = float(
                _summary_lookup(summaries, "equal_dwell", "ALL", horizon, candidate_method)[
                    "odd_block_equal_rms_hz"
                ]
            )
            aggregate_ratio = aggregate_candidate / aggregate_baseline
            output.append(
                {
                    "horizon_ms": horizon,
                    "candidate_method": candidate_method,
                    "baseline_method": METHOD_FIXED_125,
                    "equal_dwell_rms_ratio": aggregate_ratio,
                    "equal_dwell_rms_change_percent": 100.0 * (1.0 - aggregate_ratio),
                    "geometric_mean_per_dwell_rms_ratio": geometric_ratio,
                    "worst_dwell_ratio": max(ratios),
                    "per_dwell_ratio": per_dwell,
                    "leave_one_dwell_out_ratio_range": [
                        min(leave_one_out),
                        max(leave_one_out),
                    ],
                    "descriptive_gate_passes": aggregate_ratio <= 0.90 and max(ratios) <= 1.05,
                    "descriptive_only": True,
                }
            )
    return tuple(output)


def _coverage_summaries(
    inventory: tuple[dict[str, object], ...],
    forecasts: tuple[dict[str, object], ...],
    document: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    sample_rate_hz = int(document["sample_rate_hz"])
    reference_offset = int(document["pilot_reference_offset_samples"])
    stride = int(document["target_stride_frames"])
    longest_history_samples = round(
        max(float(value) for value in document["history_durations_ms"])
        * float(document["minimum_history_coverage"])
        * sample_rate_hz
        / 1_000.0
    )
    predicted = {
        (str(row["label"]), float(row["horizon_ms"]), int(row["target_frame_start_sample"]))
        for row in forecasts
    }
    output = []
    for label in tuple(str(value) for value in document["labels"]):
        supported = tuple(
            row
            for row in inventory
            if row["label"] == label
            and bool(row["continuity_safe"])
            and bool(row["training_supported"])
        )
        first_reference_sample = int(supported[0]["frame_start_sample"]) + reference_offset
        for horizon_ms in tuple(float(value) for value in document["forecast_horizons_ms"]):
            horizon_samples = round(horizon_ms * sample_rate_hz / 1_000.0)
            eligible = tuple(
                row
                for row in supported
                if int(row["frame_index"]) % stride == 0
                and int(row["frame_start_sample"])
                + reference_offset
                - horizon_samples
                - first_reference_sample
                >= longest_history_samples
            )
            predicted_count = sum(
                (label, horizon_ms, int(row["frame_start_sample"])) in predicted for row in eligible
            )
            output.append(
                {
                    "label": label,
                    "horizon_ms": horizon_ms,
                    "eligible_target_count": len(eligible),
                    "paired_prediction_count": predicted_count,
                    "paired_coverage": predicted_count / len(eligible) if eligible else 0.0,
                }
            )
    return tuple(output)


def _render_comparison(
    path: Path,
    summaries: tuple[dict[str, object], ...],
    trace_rows: tuple[dict[str, object], ...],
    document: dict[str, Any],
) -> None:
    horizons = tuple(float(value) for value in document["forecast_horizons_ms"])
    labels = tuple(str(value) for value in document["labels"])
    figure = Figure(figsize=(12.5, 9.0))
    figure.subplots_adjust(left=0.08, right=0.98, bottom=0.12, top=0.90, hspace=0.42, wspace=0.24)
    grid = figure.add_gridspec(2, 2)
    aggregate_axis = figure.add_subplot(grid[0, 0])
    dwell_axis = figure.add_subplot(grid[0, 1])
    history_axis = figure.add_subplot(grid[1, 0])
    rate_axis = figure.add_subplot(grid[1, 1])

    for method in METHODS:
        values = [
            float(
                _summary_lookup(summaries, "equal_dwell", "ALL", horizon, method)[
                    "odd_block_equal_rms_hz"
                ]
            )
            for horizon in horizons
        ]
        aggregate_axis.plot(
            horizons,
            values,
            marker="o",
            linewidth=2.0,
            color=_COLORS[method],
            linestyle=_LINESTYLES[method],
            label=_LABELS[method],
        )
    aggregate_axis.set_xscale("log")
    aggregate_axis.set_xticks(horizons, [f"{value:g}" for value in horizons])
    aggregate_axis.xaxis.set_minor_formatter(NullFormatter())
    aggregate_axis.set_xlabel("Forecast horizon (ms)")
    aggregate_axis.set_ylabel("Future odd-Qin CFO RMS (Hz)\nequal dwell / 1 s block")
    aggregate_axis.set_title("A. Causal future prediction · lower is better", loc="left")
    aggregate_axis.grid(alpha=0.22)
    aggregate_axis.legend(frameon=False, fontsize=8)

    final_horizon = horizons[-1]
    width = 0.24
    x = np.arange(len(labels), dtype=float)
    for index, method in enumerate(METHODS):
        values = [
            float(
                _summary_lookup(summaries, "dwell", label, final_horizon, method)[
                    "odd_block_equal_rms_hz"
                ]
            )
            for label in labels
        ]
        dwell_axis.bar(
            x + (index - 1) * width,
            values,
            width=width,
            color=_COLORS[method],
            label=_LABELS[method],
        )
    dwell_axis.set_xticks(x, labels)
    dwell_axis.set_ylabel(f"Odd-Qin CFO RMS at {final_horizon:g} ms (Hz)")
    dwell_axis.set_title("B. Long-horizon result by dwell", loc="left")
    dwell_axis.grid(axis="y", alpha=0.22)

    adaptive_rows = [row for row in trace_rows if row["method"] == METHOD_ADAPTIVE]
    histories = tuple(float(value) for value in document["history_durations_ms"])
    bottom = np.zeros(len(labels), dtype=float)
    history_colors = ("#fee2e2", "#fdba74", "#93c5fd", "#1d4ed8")
    for history, color in zip(histories, history_colors, strict=True):
        fractions = []
        for label in labels:
            selected = [row for row in adaptive_rows if row["label"] == label]
            fractions.append(
                100.0
                * sum(float(row["selected_history_ms"]) == history for row in selected)
                / len(selected)
            )
        history_axis.bar(labels, fractions, bottom=bottom, color=color, label=f"{history:g} ms")
        bottom += np.asarray(fractions)
    history_axis.set_ylim(0.0, 100.0)
    history_axis.set_ylabel("Adaptive outputs (%)")
    history_axis.set_title("C. History selected from even Qin only", loc="left")
    history_axis.legend(frameon=False, ncols=2, fontsize=8)

    focus = labels[-1]
    focus_rows = [row for row in trace_rows if row["label"] == focus]
    focus_origin = min(float(row["reference_time_s"]) for row in focus_rows)
    for method in METHODS:
        selected = [row for row in focus_rows if row["method"] == method]
        selected.sort(key=lambda row: float(row["reference_time_s"]))
        if not selected:
            continue
        rate_axis.plot(
            [(float(row["reference_time_s"]) - focus_origin) * 1_000.0 for row in selected],
            [float(row["rate_hz_s"]) / 1_000.0 for row in selected],
            color=_COLORS[method],
            linewidth=1.3,
            alpha=0.9,
            linestyle=_LINESTYLES[method],
            label=_LABELS[method],
        )
    rate_axis.set_xlabel(f"Time within {focus} trace (ms)")
    rate_axis.set_ylabel("Apparent CFO rate (kHz/s)")
    rate_axis.set_title(f"D. {focus} causal rate trace", loc="left")
    rate_axis.grid(alpha=0.22)

    figure.suptitle(
        "Recent counter-verified dwells: causal CFO-rate history comparison",
        fontsize=14,
    )
    figure.text(
        0.01,
        0.02,
        "Every method trains on past even-Qin frames and predicts future odd-Qin frames. "
        "GLRT remains authoritative for epoch/alias; carrier phase and timing are not connected.",
        fontsize=8,
        color="#374151",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _render_rate_tracks(path: Path, trace_rows: tuple[dict[str, object], ...]) -> None:
    labels = sorted({str(row["label"]) for row in trace_rows})
    figure = Figure(figsize=(12.0, 3.1 * len(labels)), constrained_layout=True)
    axes = figure.subplots(len(labels), 1, squeeze=False).ravel()
    for axis, label in zip(axes, labels, strict=True):
        label_rows = [row for row in trace_rows if row["label"] == label]
        origin_s = min(float(row["reference_time_s"]) for row in label_rows)
        for method in METHODS:
            selected = [row for row in label_rows if row["method"] == method]
            selected.sort(key=lambda row: float(row["reference_time_s"]))
            axis.plot(
                [(float(row["reference_time_s"]) - origin_s) for row in selected],
                [float(row["rate_hz_s"]) / 1_000.0 for row in selected],
                color=_COLORS[method],
                linewidth=1.25,
                linestyle=_LINESTYLES[method],
                label=_LABELS[method],
            )
        axis.set_ylabel(f"{label}\nrate (kHz/s)")
        axis.grid(alpha=0.22)
    axes[0].legend(frameon=False, ncols=3, fontsize=8)
    axes[-1].set_xlabel("Time within analyzed interval (s)")
    figure.suptitle("Causal apparent-CFO-rate estimates (frequency only)", fontsize=14)
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError("cannot write an empty forecast CSV")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(
    *,
    inputs_path: Path,
    upstream_root: Path,
    output_root: Path,
) -> dict[str, object]:
    document = _validate_config(_load_object(inputs_path))
    if output_root.resolve() == upstream_root.resolve():
        raise ValueError("adaptive output root must differ from its upstream artifact root")
    summary, inventory, upstream_manifest = _load_verified_upstream(
        upstream_root,
        str(document["upstream_artifact_manifest_sha256"]),
    )
    tracks = _build_tracks(inventory, document)
    forecasts = _forecast_rows(inventory, tracks, document)
    summaries = _summaries(forecasts)
    comparison_effects = _comparison_effects(summaries, document)
    coverage_summaries = _coverage_summaries(inventory, forecasts, document)
    trace_rows = _rate_trace_rows(tracks, document)
    output_root.mkdir(parents=True, exist_ok=True)
    forecast_path = output_root / "forecast-rows.csv"
    trace_path = output_root / "rate-tracks.json"
    comparison_path = output_root / "comparison.png"
    rate_plot_path = output_root / "rate-tracks.png"
    summary_path = output_root / "summary.json"
    manifest_path = output_root / "artifact-manifest.json"
    _write_csv(forecast_path, forecasts)
    trace_path.write_bytes(
        _json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-rate-tracks/v1",
                "rows": list(trace_rows),
            }
        )
    )
    _render_comparison(comparison_path, summaries, trace_rows, document)
    _render_rate_tracks(rate_plot_path, trace_rows)
    result: dict[str, object] = {
        "schema": "org.leo.research.recent-adaptive-cfo-track-summary/v1",
        "candidate_only": True,
        "promotion_ready": False,
        "promotion_blocker": (
            "development cohort has three captures; promotion requires at least ten"
        ),
        "measurement_name": "receiver-relative apparent CFO and CFO rate",
        "carrier_phase_connected": False,
        "receiver_relative_timing_used_for_doppler": False,
        "epoch_and_alias_authority": "upstream 20 ms GLRT trajectory",
        "training_symbols": "past even Qin only",
        "response_symbols": "future odd Qin; fit-withheld from every compared tracker",
        "target_membership": "continuity-safe frames qualified by even-Qin diagnostics only",
        "selection_reference_utc": summary["selection_reference_utc"],
        "maximum_age_s": summary["maximum_age_s"],
        "continuity_policy": summary["continuity_policy"],
        "input_sha256": {
            "configuration": _sha256(inputs_path),
            "upstream_artifact_manifest": str(document["upstream_artifact_manifest_sha256"]),
            "upstream_summary": upstream_manifest["artifacts"]["summary"]["sha256"],
            "upstream_frame_inventory": upstream_manifest["artifacts"]["frame_inventory"]["sha256"],
        },
        "implementation_sha256": {
            "tool": _sha256(Path(__file__)),
            "adaptive_tracker": _sha256(
                Path(__file__).parents[1] / "src/leo/analysis/research/adaptive_frame_cfo.py"
            ),
        },
        "configuration": {
            key: value
            for key, value in document.items()
            if key not in {"schema", "upstream_artifact_manifest_sha256", "labels"}
        },
        "labels": list(document["labels"]),
        "methods": list(METHODS),
        "method_semantics": {
            METHOD_FIXED_125: "causal robust line over the trailing 125 ms",
            METHOD_FIXED_500: "causal robust line over the trailing 500 ms",
            METHOD_ADAPTIVE: (
                "longest 75/125/250/500 ms robust line statistically consistent "
                "with all shorter fits"
            ),
        },
        "adaptive_tracker_contract": asdict(
            _tracker_config(document, tuple(float(v) for v in document["history_durations_ms"]))
        ),
        "forecast_row_count": len(forecasts),
        "paired_target_count": len(forecasts) // len(METHODS),
        "rate_trace_row_count": len(trace_rows),
        "history_selection_counts": {
            label: dict(
                sorted(
                    Counter(
                        f"{float(row['selected_history_ms']):g}ms"
                        for row in trace_rows
                        if row["label"] == label and row["method"] == METHOD_ADAPTIVE
                    ).items()
                )
            )
            for label in document["labels"]
        },
        "paired_comparison_effects": list(comparison_effects),
        "paired_coverage": list(coverage_summaries),
        "forecast_summaries": list(summaries),
    }
    summary_path.write_bytes(_json_bytes(result))
    artifacts = {
        name: {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for name, path in (
            ("summary", summary_path),
            ("forecast_rows", forecast_path),
            ("rate_tracks", trace_path),
            ("comparison_plot", comparison_path),
            ("rate_tracks_plot", rate_plot_path),
        )
    }
    manifest_path.write_bytes(
        _json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-track-artifacts/v1",
                "artifacts": artifacts,
            }
        )
    )
    return result


def main() -> int:
    arguments = _arguments()
    summary = run(
        inputs_path=arguments.inputs,
        upstream_root=arguments.upstream_root,
        output_root=arguments.output_root,
    )
    print(json.dumps(stable_measurement_floats(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
