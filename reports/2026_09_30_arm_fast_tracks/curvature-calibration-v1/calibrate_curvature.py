#!/usr/bin/env python3
"""Empirical curvature calibration on the independent 3cfdaa DS9 scan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


WINDOW_WIDTHS_S = (8.0, 12.0, 16.0, 20.0)
PRIMARY_WIDTH_S = 12.0
MINIMUM_WINDOW_POINTS = 9
MINIMUM_WINDOW_SPAN_FRACTION = 0.65
MINIMUM_TRACK_POINTS = 20
MINIMUM_TRACK_SPAN_S = 12.0
MINIMUM_TRACK_WEIGHTED_SUPPORT = 20.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("empty distribution")
    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(np.min(array)),
        "p01": float(np.quantile(array, 0.01)),
        "p05": float(np.quantile(array, 0.05)),
        "p10": float(np.quantile(array, 0.10)),
        "p25": float(np.quantile(array, 0.25)),
        "median": float(np.quantile(array, 0.50)),
        "p75": float(np.quantile(array, 0.75)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
        "maximum": float(np.max(array)),
    }


def weighted_fit(
    points: list[tuple[int, float, float]], *, robust: bool
) -> tuple[float, float, float]:
    time_ns = np.asarray([item[0] for item in points], dtype=np.int64)
    times = (time_ns - int(np.median(time_ns))) * 1e-9
    values = np.asarray([item[1] for item in points], dtype=np.float64)
    base_weights = np.asarray([item[2] for item in points], dtype=np.float64)
    design = np.column_stack((np.ones(len(times)), times, 0.5 * times * times))
    weights = base_weights.copy()
    coefficient = np.linalg.lstsq(
        design * np.sqrt(weights[:, None]), values * np.sqrt(weights), rcond=None
    )[0]
    scale = 0.0
    if robust:
        for _ in range(8):
            residual = values - design @ coefficient
            centered = residual - np.median(residual)
            scale = max(1.4826 * float(np.median(np.abs(centered))), 1e-6)
            ratio = np.abs(centered) / (1.5 * scale)
            huber = np.ones(len(ratio))
            huber[ratio > 1.0] = 1.0 / ratio[ratio > 1.0]
            weights = base_weights * huber
            updated = np.linalg.lstsq(
                design * np.sqrt(weights[:, None]),
                values * np.sqrt(weights),
                rcond=None,
            )[0]
            if float(np.max(np.abs(updated - coefficient))) < 1e-9:
                coefficient = updated
                break
            coefficient = updated
    residual = values - design @ coefficient
    centered = residual - np.median(residual)
    scale = max(1.4826 * float(np.median(np.abs(centered))), 1e-6)
    return float(coefficient[2]), scale, float(np.ptp(times))


def load(candidates_path: Path, tracks_path: Path):
    candidates = {}
    with candidates_path.open(newline="", encoding="ascii") as source:
        rows = csv.DictReader(source, delimiter="\t")
        for row in rows:
            candidate = row["candidate_id"]
            if candidate in candidates:
                raise ValueError("duplicate candidate")
            numeric = (
                float(row["support_center_utc_ns"]),
                float(row["control_score"]),
                float(row["margin"]),
            )
            if not all(math.isfinite(value) for value in numeric):
                raise ValueError("nonfinite candidate")
            candidates[candidate] = row
    tracks: dict[int, dict[str, object]] = {}
    with tracks_path.open(newline="", encoding="ascii") as source:
        for line, row in enumerate(csv.reader(source, delimiter="\t"), 1):
            if not row:
                raise ValueError(f"empty track row {line}")
            if row[0] in ("SUMMARY", "CONFIG"):
                continue
            if row[0] == "TRACK":
                if len(row) != 17:
                    raise ValueError("invalid TRACK row")
                index = int(row[1])
                tracks[index] = {
                    "track_index": index,
                    "tracklet_id": row[3],
                    "start_ns": int(row[8]),
                    "end_ns": int(row[9]),
                    "weighted_support": float(row[15]),
                    "declared_points": int(row[16]),
                    "points": [],
                }
            elif row[0] == "POINT":
                if len(row) != 7:
                    raise ValueError("invalid POINT row")
                index = int(row[1])
                candidate = candidates.get(row[2])
                if index not in tracks or candidate is None:
                    raise ValueError("POINT authority differs")
                control = float(candidate["control_score"])
                margin = float(candidate["margin"])
                evidence_weight = min(max(margin, 0.0) / max(control, 0.02), 16.0)
                point = (
                    int(candidate["support_center_utc_ns"]),
                    float(row[6]),
                    evidence_weight,
                )
                if not all(math.isfinite(value) for value in point):
                    raise ValueError("nonfinite track point")
                tracks[index]["points"].append(point)
            else:
                raise ValueError("unknown tracking row")
    if len(candidates) != 11_747 or len(tracks) != 64:
        raise ValueError("independent fixture size differs")
    if any(len(track["points"]) != track["declared_points"] for track in tracks.values()):
        raise ValueError("track point count differs")
    if sum(len(track["points"]) for track in tracks.values()) != 3_372:
        raise ValueError("track point total differs")
    return candidates, tracks


def window_estimates(track: dict[str, object], width_s: float):
    points = sorted(track["points"])
    robust_rows = []
    ordinary_rows = []
    half_ns = round(width_s * 1e9 / 2.0)
    for center, _value, _weight in points:
        window = [point for point in points if abs(point[0] - center) <= half_ns]
        span = (window[-1][0] - window[0][0]) * 1e-9 if window else 0.0
        if len(window) < MINIMUM_WINDOW_POINTS or span < width_s * MINIMUM_WINDOW_SPAN_FRACTION:
            continue
        robust_rows.append(weighted_fit(window, robust=True))
        ordinary_rows.append(weighted_fit(window, robust=False))
    return robust_rows, ordinary_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--fixture-report", type=Path, required=True)
    parser.add_argument("--reference-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _candidates, tracks = load(args.candidates, args.tracks)
    selected = []
    excluded = []
    for index in sorted(tracks):
        track = tracks[index]
        span_s = (track["end_ns"] - track["start_ns"]) * 1e-9
        reasons = []
        if track["declared_points"] < MINIMUM_TRACK_POINTS:
            reasons.append("points")
        if span_s < MINIMUM_TRACK_SPAN_S:
            reasons.append("span")
        if track["weighted_support"] < MINIMUM_TRACK_WEIGHTED_SUPPORT:
            reasons.append("weighted_support")
        if reasons:
            excluded.append(
                {
                    "track_index": index,
                    "point_count": track["declared_points"],
                    "span_s": span_s,
                    "weighted_support": track["weighted_support"],
                    "reasons": reasons,
                }
            )
        else:
            selected.append(track)
    if len(selected) != 60:
        raise ValueError("long/strong track selection differs")

    width_results = {}
    primary_tracks = []
    for width in WINDOW_WIDTHS_S:
        accelerations = []
        absolute_accelerations = []
        residual_scales = []
        robust_minus_ordinary = []
        per_track_medians = []
        tracks_with_windows = 0
        for track in selected:
            robust, ordinary = window_estimates(track, width)
            if not robust:
                continue
            tracks_with_windows += 1
            values = [item[0] for item in robust]
            accelerations.extend(values)
            absolute_accelerations.extend(abs(value) for value in values)
            residual_scales.extend(item[1] for item in robust)
            robust_minus_ordinary.extend(
                abs(left[0] - right[0]) for left, right in zip(robust, ordinary, strict=True)
            )
            per_track_medians.append(float(np.median(values)))
            if width == PRIMARY_WIDTH_S:
                primary_tracks.append(
                    {
                        "track_index": track["track_index"],
                        "tracklet_id": track["tracklet_id"],
                        "point_count": track["declared_points"],
                        "span_s": (track["end_ns"] - track["start_ns"]) * 1e-9,
                        "weighted_support": track["weighted_support"],
                        "window_count": len(values),
                        "signed_acceleration_hz_per_s2": quantiles(values),
                        "absolute_acceleration_hz_per_s2": quantiles(
                            [abs(value) for value in values]
                        ),
                        "median_residual_mad_scale_hz": float(
                            np.median([item[1] for item in robust])
                        ),
                    }
                )
        width_results[str(int(width))] = {
            "window_width_s": width,
            "window_count": len(accelerations),
            "tracks_with_windows": tracks_with_windows,
            "signed_acceleration_hz_per_s2": quantiles(accelerations),
            "absolute_acceleration_hz_per_s2": quantiles(absolute_accelerations),
            "absolute_track_median_acceleration_hz_per_s2": quantiles(
                [abs(value) for value in per_track_medians]
            ),
            "robust_residual_mad_scale_hz": quantiles(residual_scales),
            "absolute_robust_minus_weighted_least_squares_hz_per_s2": quantiles(
                robust_minus_ordinary
            ),
            "absolute_acceleration_exceedance_counts": {
                "125": sum(value > 125.0 for value in absolute_accelerations),
                "250": sum(value > 250.0 for value in absolute_accelerations),
                "500": sum(value > 500.0 for value in absolute_accelerations),
            },
        }

    primary = width_results[str(int(PRIMARY_WIDTH_S))]
    recommendation = {
        "sensitivity_sweep_absolute_acceleration_hz_per_s2": [125.0, 250.0, 500.0],
        "primary_value_hz_per_s2": 250.0,
        "basis": (
            "This independent measured-CFO audit is a compatibility/noise check for the "
            "separately frozen orbit-derived 125/250/500 sweep; it did not set those values. "
            "The 12-second robust-window p99 is near 100 Hz/s^2, while rare short-window "
            "tails rise above 500 and are strongly window-width sensitive."
        ),
        "interpretation": {
            "125": "lower sensitivity case, above approximately p99 of primary measured windows",
            "250": "primary independently selected orbit-envelope control; above almost all primary measured windows",
            "500": "upper sensitivity case that also covers nearly all short-window noise-sensitive tails",
        },
        "target_scan_used_for_calibration": False,
        "parameter_authority": "separate independent orbit-envelope artifact; measured CFO did not tune the values",
    }
    report = {
        "schema": "leo-independent-ds9-curvature-calibration/v1",
        "status": "empirical_calibration_only",
        "scope": {
            "session_id": "scan-fw-3cfdaa6d75762cad",
            "independent_of_target": "scan-fw-f363c7f29141d0b1 was not read or used",
            "claim_limit": (
                "These are robust local polynomial estimates from tracker-selected noisy CFO "
                "points over one 300-second lower-edge recording. They are neither a physical "
                "orbital acceleration bound nor evidence that curvature caused target misses."
            ),
            "selection_bias": (
                "The source track memberships survived the existing linear residual gate, so "
                "the distribution can under-represent arcs whose curvature already prevented "
                "linear reconstruction. It is a compatibility/noise audit, not an unbiased "
                "population estimate."
            ),
        },
        "inputs": {
            "candidates_tsv": {"path": str(args.candidates), "sha256": sha256(args.candidates)},
            "tracks_tsv": {"path": str(args.tracks), "sha256": sha256(args.tracks)},
            "fixture_report": {
                "path": str(args.fixture_report),
                "sha256": sha256(args.fixture_report),
            },
            "reference_comparison": {
                "path": str(args.reference_comparison),
                "sha256": sha256(args.reference_comparison),
            },
            "script_sha256": sha256(Path(__file__)),
        },
        "selection": {
            "input_track_count": len(tracks),
            "selected_track_count": len(selected),
            "minimum_points": MINIMUM_TRACK_POINTS,
            "minimum_span_s": MINIMUM_TRACK_SPAN_S,
            "minimum_weighted_support": MINIMUM_TRACK_WEIGHTED_SUPPORT,
            "excluded_tracks": excluded,
        },
        "method": {
            "response": "normalized dealiased CFO from each frozen track POINT row",
            "base_weight": "min(max(margin,0)/max(control_score,0.02),16)",
            "model": "cfo = intercept + rate*t + 0.5*acceleration*t^2",
            "robust_fit": "eight-iteration Huber IRLS at 1.5 residual MAD scales",
            "window_widths_s": list(WINDOW_WIDTHS_S),
            "primary_window_width_s": PRIMARY_WIDTH_S,
            "minimum_window_points": MINIMUM_WINDOW_POINTS,
            "minimum_window_span_fraction": MINIMUM_WINDOW_SPAN_FRACTION,
            "overlap_warning": "Adjacent local windows overlap heavily and are not independent samples.",
        },
        "distributions_by_window_width_s": width_results,
        "primary_track_distributions": sorted(
            primary_tracks, key=lambda item: item["track_index"]
        ),
        "recommended_sensitivity": recommendation,
        "summary": {
            "primary_windows": primary["window_count"],
            "primary_tracks": primary["tracks_with_windows"],
            "primary_absolute_acceleration_hz_per_s2": primary[
                "absolute_acceleration_hz_per_s2"
            ],
            "noise_sensitivity": (
                "The 8-second maximum is much larger than the 16/20-second maxima, while "
                "p95 and per-track medians are comparatively stable. Treat isolated short-window "
                "tails as measurement/selection-sensitive rather than a physical envelope."
            ),
        },
    }
    temporary = args.output.with_name("." + args.output.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
