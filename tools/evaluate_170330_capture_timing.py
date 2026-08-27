#!/usr/bin/env python3
"""Reproduce the receiver-relative timing comparison for capture 170330.

The replay is intentionally exploratory and post-hoc branch-conditioned.  It
compares timing repeatability, not absolute TOA accuracy, transmit time, or
pseudorange.  Every raw chunk used by the replay is verified against both its
compressed and uncompressed manifest digest before analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd

from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    DEFAULT_VERIFY_SYMBOLS,
    _folded_anchor_scores,
    normalized_frame_score,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame

FS_HZ = 5_000_000.0
FRAME_PERIOD_SAMPLES = FS_HZ / 750.0
WINDOW_STOP_S = 4.14
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_OUTPUT = Path(
    "reports/figures/2026_08_27_170330_capture_quality/timing-evaluation-results.json"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def case_configs(bulk_root: Path) -> dict[str, dict[str, Any]]:
    """Return the two frozen capture/product bindings used by the report."""

    return {
        "old_20260826": {
            "capture_root": bulk_root / "recordings/2026/08/26/cap-20260826T182310-f2c5b2a92b71",
            "analysis_root": bulk_root / "analysis/cap-20260826T182310-f2c5b2a92b71",
            "phase_range_samples": (1500.0, 2500.0),
        },
        "new_20260827": {
            "capture_root": bulk_root / "recordings/2026/08/27/cap-20260827T170330-a555a5cf5306",
            "analysis_root": bulk_root / "analysis/cap-20260827T170330-a555a5cf5306",
            "phase_range_samples": (2100.0, 2500.0),
        },
    }


def sha256(data: bytes) -> str:
    """Return the repository's canonical SHA-256 label for bytes."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_for_json(value: Any) -> Any:
    """Normalize floats so receipts are stable across numerical libraries."""

    if isinstance(value, dict):
        return {key: normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_for_json(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("published JSON cannot contain a non-finite float")
        return float(f"{value:.15g}")
    return value


def strongest_lower_rx1_glrt(analysis_root: Path) -> Path:
    """Resolve the one persisted lower-edge RX1 GLRT product."""

    matches = []
    for path in analysis_root.glob("**/standard.full-capture-glrt20ms.v1.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        source = document["source"]
        if (
            source["stream_id"] == "stream-1"
            and source["receiver_id"] == 1
            and document["starlink_edge"] == "lower"
        ):
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(f"expected one lower RX1 GLRT product, found {matches}")
    return matches[0]


def quadratic_metrics(times: np.ndarray, phases: np.ndarray) -> dict[str, object]:
    """Summarize residual repeatability after the declared quadratic trend."""

    if times.size != phases.size or times.size < 3:
        raise ValueError("quadratic metrics require at least three paired values")
    coefficients = np.polyfit(times, phases, 2)
    residual = phases - np.polyval(coefficients, times)
    absolute_ns = np.abs(residual) * 1e9 / FS_HZ
    return {
        "count": int(times.size),
        "quadratic_coefficients_samples": [float(value) for value in coefficients],
        "rms_ns": float(np.sqrt(np.mean(residual**2)) * 1e9 / FS_HZ),
        "median_absolute_ns": float(np.median(absolute_ns)),
        "p90_absolute_ns": float(np.quantile(absolute_ns, 0.90)),
        "maximum_absolute_ns": float(np.max(absolute_ns)),
    }


def parabolic_peak(scores: np.ndarray, offsets: np.ndarray) -> tuple[float, float]:
    """Refine a discrete peak by at most half a sample on either side."""

    if scores.ndim != 1 or offsets.ndim != 1 or scores.size != offsets.size:
        raise ValueError("scores and offsets must be equal one-dimensional arrays")
    if scores.size < 3:
        raise ValueError("at least three peak samples are required")
    index = int(np.argmax(scores))
    integer_offset = float(offsets[index])
    fractional_offset = 0.0
    if 0 < index < len(scores) - 1:
        denominator = scores[index - 1] - 2.0 * scores[index] + scores[index + 1]
        if denominator < 0.0:
            fractional_offset = float(
                np.clip(
                    0.5 * (scores[index - 1] - scores[index + 1]) / denominator,
                    -0.5,
                    0.5,
                )
            )
    return integer_offset + fractional_offset, float(scores[index])


def lobe_width_ns(scores: np.ndarray, offsets: np.ndarray) -> float:
    """Return the interpolated half-prominence width of a bracketed peak."""

    if scores.ndim != 1 or offsets.ndim != 1 or scores.size != offsets.size:
        raise ValueError("scores and offsets must be equal one-dimensional arrays")
    peak = int(np.argmax(scores))
    baseline = float(np.median(scores))
    threshold = baseline + 0.5 * (float(scores[peak]) - baseline)
    left = peak
    while left > 0 and scores[left] >= threshold:
        left -= 1
    right = peak
    while right + 1 < len(scores) and scores[right + 1] >= threshold:
        right += 1
    if left == peak or right + 1 >= len(scores):
        raise RuntimeError("local score grid does not bracket the half-prominence lobe")

    def crossing(first: int, second: int) -> float:
        return float(
            offsets[first]
            + (threshold - scores[first])
            * (offsets[second] - offsets[first])
            / (scores[second] - scores[first])
        )

    left_crossing = crossing(left, left + 1)
    right_crossing = crossing(right, right + 1)
    return (right_crossing - left_crossing) * 1e9 / FS_HZ


def _verified_chunk_values(capture_root: Path, chunk: dict[str, Any]) -> np.ndarray:
    path = capture_root / str(chunk["relative_path"])
    compressed = path.read_bytes()
    if sha256(compressed) != chunk["compressed_sha256"]:
        raise RuntimeError(f"compressed digest mismatch: {chunk['relative_path']}")
    raw = zstd.ZstdDecompressor().decompress(
        compressed,
        max_output_size=int(chunk["uncompressed_bytes"]),
    )
    if sha256(raw) != chunk["uncompressed_sha256"]:
        raise RuntimeError(f"uncompressed digest mismatch: {chunk['relative_path']}")
    return np.frombuffer(raw, dtype="<i2").reshape(int(chunk["sample_count"]), 2, 2)


def evaluate_case(
    config: dict[str, Any],
) -> tuple[dict[str, object], dict[int, dict[str, float]]]:
    """Evaluate one frozen capture over its first 4.14 seconds."""

    capture_root = Path(config["capture_root"])
    manifest_path = capture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["stream_id"] == "stream-1")
    if stream["applied_settings"]["sample_rate_hz"] != int(FS_HZ):
        raise RuntimeError("comparison requires 5 MS/s")
    if stream["applied_settings"]["receiver_ids"] != [0, 1]:
        raise RuntimeError("comparison expects receiver 1 in dual-receiver ci16 layout")

    glrt_path = strongest_lower_rx1_glrt(Path(config["analysis_root"]))
    glrt = json.loads(glrt_path.read_text(encoding="utf-8"))
    segment_windows = glrt["segments"][0]["windows"]
    scheduled = [row for row in segment_windows if row["global_center_time_s"] <= WINDOW_STOP_S]
    passed = [row for row in scheduled if row["passed_margin_gate"]]
    phase_min, phase_max = config["phase_range_samples"]
    branch = [
        row
        for row in passed
        if phase_min <= row["global_epoch_device_sample"] % FRAME_PERIOD_SAMPLES <= phase_max
    ]

    template = np.asarray(qin_edge_pilot_frame(FS_HZ, "lower"), dtype=np.complex128)
    symbol_groups = {
        "acquire_even": DEFAULT_ACQUIRE_SYMBOLS,
        "verify_odd": DEFAULT_VERIFY_SYMBOLS,
        "all_300": tuple(range(2, 302)),
    }
    local_offsets = np.arange(-3, 4, dtype=int)
    observations: dict[int, dict[str, float]] = {}
    verified_chunks = []
    first_window_iq: np.ndarray | None = None
    first_window = branch[0]

    for chunk in stream["chunks"][:2]:
        chunk_start = int(chunk["device_sample_start"])
        chunk_stop = chunk_start + int(chunk["sample_count"])
        selected_windows = [
            row
            for row in branch
            if int(row["global_device_sample_start"]) >= chunk_start
            and int(row["global_device_sample_stop"]) <= chunk_stop
        ]
        if not selected_windows:
            continue
        values = _verified_chunk_values(capture_root, chunk)
        verified_chunks.append(str(chunk["relative_path"]))
        for row in selected_windows:
            sample_start = int(row["global_device_sample_start"])
            sample_stop = int(row["global_device_sample_stop"])
            local = values[sample_start - chunk_start : sample_stop - chunk_start, 1, :]
            iq = local[:, 0].astype(np.float64) + 1j * local[:, 1].astype(np.float64)
            local_epoch = int(row["global_epoch_device_sample"]) - sample_start
            estimates = {}
            peak_scores = {}
            for group_name, symbols in symbol_groups.items():
                scores = np.asarray(
                    [
                        normalized_frame_score(
                            iq,
                            template,
                            FS_HZ,
                            local_epoch + int(offset),
                            float(row["acquired_cfo_hz"]),
                            symbols,
                        )[0]
                        for offset in local_offsets
                    ]
                )
                offset, peak_score = parabolic_peak(scores, local_offsets)
                estimates[group_name] = float(row["global_epoch_device_sample"] + offset)
                peak_scores[group_name] = peak_score
            opportunity = int(row["opportunity_index"])
            observations[opportunity] = {
                "time_s": float(row["global_center_time_s"]),
                **{f"epoch_{key}": value for key, value in estimates.items()},
                **{f"peak_{key}": value for key, value in peak_scores.items()},
            }
            if row is first_window:
                first_window_iq = iq
        del values

    if first_window_iq is None:
        raise RuntimeError("the first selected window was not fully stored in a verified chunk")

    ordered = [observations[index] for index in sorted(observations)]
    times = np.asarray([row["time_s"] for row in ordered])
    metrics: dict[str, dict[str, object]] = {}
    for group_name in symbol_groups:
        phases = np.mod(
            [row[f"epoch_{group_name}"] for row in ordered],
            FRAME_PERIOD_SAMPLES,
        )
        metrics[group_name] = quadratic_metrics(times, np.asarray(phases))
        metrics[group_name]["median_peak_score"] = float(
            np.median([row[f"peak_{group_name}"] for row in ordered])
        )

    acquire_phase = np.mod([row["epoch_acquire_even"] for row in ordered], FRAME_PERIOD_SAMPLES)
    verify_phase = np.mod([row["epoch_verify_odd"] for row in ordered], FRAME_PERIOD_SAMPLES)
    split_difference = acquire_phase - verify_phase
    split_difference -= np.polyval(np.polyfit(times, split_difference, 2), times)

    lobe_offsets = np.arange(-12, 13, dtype=int)
    first_local_epoch = int(first_window["global_epoch_device_sample"]) - int(
        first_window["global_device_sample_start"]
    )
    lobe_scores = np.asarray(
        [
            normalized_frame_score(
                first_window_iq,
                template,
                FS_HZ,
                first_local_epoch + int(offset),
                float(first_window["acquired_cfo_hz"]),
                tuple(range(2, 302)),
            )[0]
            for offset in lobe_offsets
        ]
    )
    anchor_scores = _folded_anchor_scores(
        first_window_iq,
        template,
        FS_HZ,
        float(first_window["acquired_cfo_hz"]),
        DEFAULT_ANCHOR_SYMBOLS,
        math.ceil(FRAME_PERIOD_SAMPLES),
    )
    best = int(np.argmax(anchor_scores))
    indexes = np.arange(anchor_scores.size)
    circular_distance = np.minimum(
        np.mod(indexes - best, anchor_scores.size),
        np.mod(best - indexes, anchor_scores.size),
    )
    far_scores = np.where(circular_distance >= 20, anchor_scores, -np.inf)
    far = int(np.argmax(far_scores))

    integer_times = np.asarray([row["global_center_time_s"] for row in branch])
    integer_phases = np.mod(
        [row["global_epoch_device_sample"] for row in branch], FRAME_PERIOD_SAMPLES
    )
    result: dict[str, object] = {
        "capture_id": manifest["session_id"],
        "capture_manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path.read_bytes()),
        "glrt_product": str(glrt_path),
        "glrt_product_sha256": sha256(glrt_path.read_bytes()),
        "stream_settings": stream["applied_settings"],
        "continuity": stream["continuity"],
        "evaluation_interval": {
            "first_center_time_s": float(min(row["global_center_time_s"] for row in scheduled)),
            "last_center_time_s": float(max(row["global_center_time_s"] for row in scheduled)),
            "window_samples": int(glrt["window_samples"]),
            "stride_samples": int(glrt["stride_samples"]),
        },
        "scheduled_window_count": len(scheduled),
        "passing_window_count": len(passed),
        "branch_condition": {
            "folded_epoch_min_samples": float(phase_min),
            "folded_epoch_max_samples": float(phase_max),
            "post_hoc": True,
        },
        "branch_window_count": len(branch),
        "refined_window_count": len(observations),
        "chunk_boundary_excluded_count": len(branch) - len(observations),
        "verified_chunks": verified_chunks,
        "integer_epoch_quadratic": quadratic_metrics(integer_times, integer_phases),
        "subsample_quadratic": metrics,
        "disjoint_pilot_half_difference": {
            "detrended_standard_deviation_ns": float(np.std(split_difference) * 1e9 / FS_HZ),
            "p90_absolute_ns": float(np.quantile(np.abs(split_difference), 0.9) * 1e9 / FS_HZ),
        },
        "first_window_lobe": {
            "half_prominence_width_ns": lobe_width_ns(lobe_scores, lobe_offsets),
            "all_pilot_peak_score": float(np.max(lobe_scores)),
        },
        "first_window_epoch_specificity": {
            "best_anchor_epoch_sample": best,
            "best_anchor_score": float(anchor_scores[best]),
            "best_far_epoch_sample": far,
            "best_far_score": float(anchor_scores[far]),
            "best_to_far_score_ratio": float(anchor_scores[best] / anchor_scores[far]),
            "minimum_far_separation_samples": 20,
        },
    }
    return result, observations


def evaluate(bulk_root: Path) -> dict[str, object]:
    """Run both frozen cases and construct the matched-support comparison."""

    results = {}
    observations = {}
    for name, config in case_configs(bulk_root).items():
        results[name], observations[name] = evaluate_case(config)

    common = sorted(set(observations["old_20260826"]) & set(observations["new_20260827"]))
    common_metrics = {}
    for name in ("old_20260826", "new_20260827"):
        rows = [observations[name][index] for index in common]
        times = np.asarray([row["time_s"] for row in rows])
        phases = np.mod([row["epoch_all_300"] for row in rows], FRAME_PERIOD_SAMPLES)
        common_metrics[name] = quadratic_metrics(times, np.asarray(phases))

    old_rms = float(common_metrics["old_20260826"]["rms_ns"])
    new_rms = float(common_metrics["new_20260827"]["rms_ns"])
    return {
        "schema": "org.leo.research.capture-170330-relative-timing/v1",
        "claim_boundary": {
            "receiver_relative_repeatability_only": True,
            "absolute_toa_accuracy_measured": False,
            "pseudorange_measured": False,
            "blind_end_to_end": False,
            "windows_overlap_fraction": 0.5,
            "same_channel_capture_pair": False,
        },
        "method": {
            "sample_rate_hz": FS_HZ,
            "known_pilot_symbol_count": 300,
            "known_pilot_tone_count": 8,
            "known_pilot_span_hz": 1_640_625.0,
            "search_offsets_samples": [-3, -2, -1, 0, 1, 2, 3],
            "subsample_refinement": "three-point parabolic peak",
            "track_model": "degree-two folded frame epoch versus elapsed time",
            "branch_selection": "post-hoc folded-epoch interval",
        },
        "cases": results,
        "matched_opportunity_comparison": {
            "opportunity_count": len(common),
            "opportunity_indexes": common,
            "metrics": common_metrics,
            "old_to_new_rms_ratio": old_rms / new_rms,
            "identical_method_window_and_elapsed_time_support": True,
        },
    }


def main() -> None:
    arguments = _arguments()
    document = normalize_for_json(evaluate(arguments.bulk_root))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
