#!/usr/bin/env python3
"""Rank causal TLE candidates independently and jointly from PSS and GLRT evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.sky.doppler import doppler_shift_hz  # noqa: E402
from leo.sky.propagation import (  # noqa: E402
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid  # noqa: E402
from leo.sky.screening import observe_grid  # noqa: E402
from leo.sky.sites import resolve_preset  # noqa: E402

FRAME_PERIOD_S = 1.0 / 750.0
GLRT_ALIAS_SPACING_HZ = 2_500_000.0 / 11.0
SITE_NAME = "spinnaker-sausalito"
LIGHT_SPEED_M_S = 299_792_458.0
TRAIN_FRACTION = 0.60
COARSE_POINT_COUNT = 31
FINE_SPACING_S = 0.02


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--tle-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{nanoseconds:09d}Z"


def latest_causal_tle(directory: Path, first_utc_ns: int) -> Path:
    candidates = [
        path for path in directory.glob("*.tle") if path.stat().st_mtime_ns <= first_utc_ns
    ]
    if not candidates:
        raise ValueError(f"no causal TLE snapshot in {directory}")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def sampling_grid(first_utc_ns: int, relative_s: np.ndarray) -> SamplingGrid:
    instants = tuple(first_utc_ns + round(float(value) * 1e9) for value in relative_s)
    return SamplingGrid(
        utc_ns=instants,
        anchor_index=len(instants) // 2,
        spacing_s=float(np.median(np.diff(relative_s))),
    )


def design(times_s: np.ndarray, degree: int) -> np.ndarray:
    origin_s = float(np.mean(times_s))
    centered_s = times_s - origin_s
    return np.column_stack(tuple(centered_s**power for power in range(degree + 1)))


def fit_nuisance(
    observed: np.ndarray,
    predicted: np.ndarray,
    times_s: np.ndarray,
    *,
    degree: int,
    train_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    selected = np.ones(observed.size, dtype=bool) if train_mask is None else train_mask
    matrix = design(times_s, degree)
    coefficients = np.linalg.lstsq(
        matrix[selected],
        (observed - predicted)[selected],
        rcond=None,
    )[0]
    fitted = predicted + matrix @ coefficients
    return coefficients, fitted, observed - fitted


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def holdout(
    observed: np.ndarray,
    predicted: np.ndarray,
    times_s: np.ndarray,
    *,
    degree: int,
) -> dict[str, Any]:
    count = observed.size
    training_count = math.ceil(TRAIN_FRACTION * count)
    indexes = np.arange(count)
    folds: list[dict[str, Any]] = []
    for label, training, evaluation in (
        ("forward", indexes < training_count, indexes >= training_count),
        ("reverse", indexes >= count - training_count, indexes < count - training_count),
    ):
        coefficients, _, residuals = fit_nuisance(
            observed,
            predicted,
            times_s,
            degree=degree,
            train_mask=training,
        )
        folds.append(
            {
                "label": label,
                "training_count": int(np.count_nonzero(training)),
                "evaluation_count": int(np.count_nonzero(evaluation)),
                "nuisance_coefficients_ascending": coefficients.tolist(),
                "evaluation_rms": rms(residuals[evaluation]),
            }
        )
    return {
        "rms": float(np.sqrt(np.mean([item["evaluation_rms"] ** 2 for item in folds]))),
        "folds": folds,
    }


def null_model(observed: np.ndarray, times_s: np.ndarray, *, degree: int) -> dict[str, Any]:
    prediction = np.zeros_like(observed)
    coefficients, fitted, residuals = fit_nuisance(
        observed,
        prediction,
        times_s,
        degree=degree,
    )
    return {
        "full_nuisance_coefficients_ascending": coefficients.tolist(),
        "full_rms": rms(residuals),
        "bidirectional_holdout": holdout(
            observed,
            prediction,
            times_s,
            degree=degree,
        ),
        "_fitted": fitted,
    }


def load_pss_measurements(capture: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    track = capture["pss"]["independent_track"]
    if track is None:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    document = json.loads(Path(capture["pss_input"]["path"]).read_text(encoding="utf-8"))
    if sha256(Path(capture["pss_input"]["path"])) != capture["pss_input"]["sha256"]:
        raise ValueError("PSS replay changed after the cohort analysis")
    wanted = frozenset(track["mode_ids"])
    modes = sorted(
        (
            mode
            for block in document["blocks"]
            for mode in block["modes"]
            if mode["mode_id"] in wanted
        ),
        key=lambda mode: mode["center_time_s"],
    )
    if len(modes) != len(wanted):
        raise ValueError("selected PSS modes are missing from the replay")
    times_s = np.asarray([mode["center_time_s"] for mode in modes], dtype=float)
    phases_s = np.asarray([mode["median_frame_phase_s"] for mode in modes], dtype=float)
    unwrapped_s = np.unwrap(phases_s / FRAME_PERIOD_S * 2.0 * np.pi) * (
        FRAME_PERIOD_S / (2.0 * np.pi)
    )
    return times_s, unwrapped_s


def glrt_hough_track(product: dict[str, Any], label: str) -> dict[str, Any]:
    target = int(label.removeprefix("H"))
    index = 0
    for segment in product["segments"]:
        hough = segment.get("hough")
        if not hough:
            continue
        for track in hough["tracks"]:
            index += 1
            if index == target:
                return track
    raise ValueError(f"GLRT track {label} is missing")


def load_glrt_measurements(
    capture: dict[str, Any],
) -> dict[int, tuple[np.ndarray, np.ndarray, float]]:
    native_first = int(capture["native25"]["first_sample_timing"]["estimate_utc_ns"])
    rows: dict[int, tuple[np.ndarray, np.ndarray, float]] = {}
    for path in capture["glrt"]["paths"]:
        family = path["stitched_family"]
        if family is None:
            continue
        product_path = Path(path["path"])
        if sha256(product_path) != path["sha256"]:
            raise ValueError("GLRT product changed after the cohort analysis")
        product = json.loads(product_path.read_text(encoding="utf-8"))
        offset_s = (int(product["source"]["timing"]["first_estimate_utc_ns"]) - native_first) / 1e9
        aligned_rows: list[tuple[float, float]] = []
        for track_row in family["tracks"]:
            track = glrt_hough_track(product, track_row["track_label"])
            for observation in track["observations"]:
                canonical_cfo_hz = (
                    float(observation["raw_cfo_hz"])
                    - int(observation["alias_index"]) * GLRT_ALIAS_SPACING_HZ
                )
                aligned_rows.append(
                    (
                        float(observation["global_time_s"]) + offset_s,
                        canonical_cfo_hz
                        + int(track_row["integer_alias_shift"]) * GLRT_ALIAS_SPACING_HZ,
                    )
                )
        unique_rows = np.unique(np.asarray(aligned_rows, dtype=float), axis=0)
        order = np.argsort(unique_rows[:, 0])
        times_s = unique_rows[order, 0]
        canonical_cfo_hz = unique_rows[order, 1]
        rows[int(path["receiver_id"])] = (
            times_s,
            canonical_cfo_hz,
            float(path["rf_reference_hz"]),
        )
    return rows


def load_glrt_anchor_measurements(
    capture: dict[str, Any],
) -> dict[int, tuple[np.ndarray, np.ndarray, float, str]]:
    """Load each receiver's largest GLRT episode without global episode stitching."""
    native_first = int(capture["native25"]["first_sample_timing"]["estimate_utc_ns"])
    rows: dict[int, tuple[np.ndarray, np.ndarray, float, str]] = {}
    for path in capture["glrt"]["paths"]:
        family = path["stitched_family"]
        if family is None:
            continue
        product_path = Path(path["path"])
        if sha256(product_path) != path["sha256"]:
            raise ValueError("GLRT product changed after the cohort analysis")
        product = json.loads(product_path.read_text(encoding="utf-8"))
        offset_s = (int(product["source"]["timing"]["first_estimate_utc_ns"]) - native_first) / 1e9
        anchor_label = str(family["anchor_track_label"])
        track = glrt_hough_track(product, anchor_label)
        aligned_rows = np.asarray(
            [
                (
                    float(observation["global_time_s"]) + offset_s,
                    float(observation["raw_cfo_hz"])
                    - int(observation["alias_index"]) * GLRT_ALIAS_SPACING_HZ,
                )
                for observation in track["observations"]
            ],
            dtype=float,
        )
        unique_rows = np.unique(aligned_rows, axis=0)
        order = np.argsort(unique_rows[:, 0])
        rows[int(path["receiver_id"])] = (
            unique_rows[order, 0],
            unique_rows[order, 1],
            float(path["rf_reference_hz"]),
            anchor_label,
        )
    return rows


def candidate_specificity(
    ranked: list[dict[str, Any]],
    score_path: tuple[str, ...],
) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> float:
        value: Any = row
        for key in score_path:
            value = value[key]
        return float(value)

    if not ranked:
        return {"candidate_count": 0, "specific": False}
    best = score(ranked[0])
    second = score(ranked[1]) if len(ranked) > 1 else None
    near_tie_count = sum(score(row) <= best * 1.05 for row in ranked)
    return {
        "candidate_count": len(ranked),
        "best_score": best,
        "second_score": second,
        "second_to_best_ratio": (second / best if second is not None and best > 0.0 else None),
        "within_five_percent_of_best_count": near_tie_count,
        "specific": second is not None and second > best * 1.20,
    }


def rank_rows(
    candidates: list[dict[str, Any]],
    key_path: tuple[str, ...],
    rank_key: str,
) -> list[dict[str, Any]]:
    def value(row: dict[str, Any]) -> float:
        target: Any = row
        for key in key_path:
            target = target[key]
        return float(target)

    ranked = sorted(candidates, key=value)
    for rank, row in enumerate(ranked, start=1):
        row[rank_key] = rank
    return ranked


def candidate_label(row: dict[str, Any]) -> str:
    return f"{row['object_name']} / {row['norad_id']}"


def fitted_curve(
    observed: np.ndarray,
    predicted: np.ndarray,
    times_s: np.ndarray,
    coefficients: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    fitted = predicted + design(times_s, len(coefficients) - 1) @ np.asarray(
        coefficients,
        dtype=float,
    )
    return fitted, observed - fitted


def evaluate_capture(capture: dict[str, Any], tle_path: Path) -> dict[str, Any]:
    first_utc_ns = int(capture["native25"]["first_sample_timing"]["estimate_utc_ns"])
    pss_times_s, pss_observed_s = load_pss_measurements(capture)
    has_pss = pss_times_s.size >= 6
    glrt = load_glrt_measurements(capture)
    if not glrt:
        raise ValueError(f"{capture['capture_id']} has no usable GLRT Hough track")
    glrt_anchor = load_glrt_anchor_measurements(capture)
    if set(glrt_anchor) != set(glrt):
        raise ValueError("GLRT anchor sensitivity does not cover every stitched receiver")
    stop_values = [float(times.max()) for times, _, _ in glrt.values()]
    if has_pss:
        stop_values.append(float(pss_times_s.max()))
    analysis_stop_s = max(stop_values)
    catalogue = parse_element_sets(tle_path.read_text(encoding="ascii"))
    element_epoch_ns = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)
    coarse_times_s = np.linspace(0.0, analysis_stop_s, COARSE_POINT_COUNT)
    coarse_grid = sampling_grid(first_utc_ns, coarse_times_s)
    coarse_tracks = observe_grid(
        propagate_grid(catalogue, coarse_grid),
        resolve_preset(SITE_NAME),
        coarse_grid,
    )
    horizon_margin_deg = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    causal = element_epoch_ns <= first_utc_ns
    plausible = (
        coarse_tracks.usable
        & causal
        & (np.min(coarse_tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    )
    coarse_indices = np.flatnonzero(
        plausible & (np.max(coarse_tracks.elevation_deg, axis=1) > -horizon_margin_deg)
    )
    fine_stop_s = analysis_stop_s + 2.0 * FINE_SPACING_S
    fine_count = int(math.ceil(fine_stop_s / FINE_SPACING_S)) + 1
    fine_times_s = np.linspace(0.0, fine_stop_s, fine_count)
    fine_grid = sampling_grid(first_utc_ns, fine_times_s)
    fine_tracks = observe_grid(
        propagate_grid(catalogue, fine_grid, coarse_indices.tolist()),
        resolve_preset(SITE_NAME),
        fine_grid,
    )
    actual = fine_times_s <= analysis_stop_s
    visible_rows = np.flatnonzero(
        fine_tracks.usable
        & (np.min(fine_tracks.altitude_km[:, actual], axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
        & (np.max(fine_tracks.elevation_deg[:, actual], axis=1) > 0.0)
    )
    visible_indices = coarse_indices[visible_rows]
    if visible_indices.size == 0:
        raise ValueError(f"{capture['capture_id']} has no causal horizon-visible TLE candidates")
    fine_row_by_catalogue_index = {
        int(catalogue_index): int(track_row)
        for track_row, catalogue_index in zip(
            visible_rows,
            visible_indices,
            strict=True,
        )
    }

    pss_null = null_model(pss_observed_s, pss_times_s, degree=1) if has_pss else None
    glrt_nulls = {
        receiver_id: null_model(values_hz, times_s, degree=0)
        for receiver_id, (times_s, values_hz, _) in glrt.items()
    }
    glrt_anchor_nulls = {
        receiver_id: null_model(values_hz, times_s, degree=0)
        for receiver_id, (times_s, values_hz, _, _) in glrt_anchor.items()
    }
    candidates: list[dict[str, Any]] = []
    for track_row, catalogue_index in zip(visible_rows, visible_indices, strict=True):
        pss_results: dict[str, Any] | None = None
        if has_pss:
            assert pss_null is not None
            range_delay_s = fine_tracks.range_km[track_row] * 1000.0 / LIGHT_SPEED_M_S
            pss_physical = np.interp(pss_times_s, fine_times_s, range_delay_s)
            pss_mirrored = -pss_physical
            pss_results = {}
            for label, prediction in (
                ("physical_arrival_delay", pss_physical),
                ("mirrored_sign_control", pss_mirrored),
            ):
                coefficients, _, residuals = fit_nuisance(
                    pss_observed_s,
                    prediction,
                    pss_times_s,
                    degree=1,
                )
                holdout_result = holdout(
                    pss_observed_s,
                    prediction,
                    pss_times_s,
                    degree=1,
                )
                null_rms = float(pss_null["bidirectional_holdout"]["rms"])
                pss_results[label] = {
                    "full_nuisance_coefficients_ascending_s": coefficients.tolist(),
                    "full_rms_us": rms(residuals) * 1e6,
                    "bidirectional_holdout_rms_us": float(holdout_result["rms"]) * 1e6,
                    "holdout_rms_ratio_to_affine_null": float(holdout_result["rms"]) / null_rms,
                    "holdout_mse_improvement_over_affine_null": 1.0
                    - (float(holdout_result["rms"]) / null_rms) ** 2,
                    "bidirectional_holdout": holdout_result,
                }
        glrt_results: dict[str, Any] = {}
        for receiver_id, (times_s, observed_hz, rf_hz) in glrt.items():
            physical_full = np.asarray(
                doppler_shift_hz(rf_hz, fine_tracks.range_rate_km_s[track_row]),
                dtype=float,
            )
            physical = np.interp(times_s, fine_times_s, physical_full)
            receiver_results: dict[str, Any] = {}
            for label, prediction in (
                ("physical_iq_sign", physical),
                ("opposite_iq_sign_control", -physical),
            ):
                coefficients, _, residuals = fit_nuisance(
                    observed_hz,
                    prediction,
                    times_s,
                    degree=0,
                )
                holdout_result = holdout(
                    observed_hz,
                    prediction,
                    times_s,
                    degree=0,
                )
                null_rms = float(glrt_nulls[receiver_id]["bidirectional_holdout"]["rms"])
                receiver_results[label] = {
                    "full_constant_cfo_offset_hz": float(coefficients[0]),
                    "full_rms_hz": rms(residuals),
                    "bidirectional_holdout_rms_hz": float(holdout_result["rms"]),
                    "holdout_rms_ratio_to_constant_null": float(holdout_result["rms"]) / null_rms,
                    "holdout_mse_improvement_over_constant_null": 1.0
                    - (float(holdout_result["rms"]) / null_rms) ** 2,
                    "bidirectional_holdout": holdout_result,
                }
            glrt_results[str(receiver_id)] = receiver_results
        glrt_anchor_results: dict[str, Any] = {}
        for receiver_id, (times_s, observed_hz, rf_hz, anchor_label) in glrt_anchor.items():
            physical_full = np.asarray(
                doppler_shift_hz(rf_hz, fine_tracks.range_rate_km_s[track_row]),
                dtype=float,
            )
            physical = np.interp(times_s, fine_times_s, physical_full)
            coefficients, _, residuals = fit_nuisance(
                observed_hz,
                physical,
                times_s,
                degree=0,
            )
            holdout_result = holdout(
                observed_hz,
                physical,
                times_s,
                degree=0,
            )
            null_rms = float(glrt_anchor_nulls[receiver_id]["bidirectional_holdout"]["rms"])
            glrt_anchor_results[str(receiver_id)] = {
                "anchor_track_label": anchor_label,
                "full_constant_cfo_offset_hz": float(coefficients[0]),
                "full_rms_hz": rms(residuals),
                "bidirectional_holdout_rms_hz": float(holdout_result["rms"]),
                "holdout_rms_ratio_to_constant_null": float(holdout_result["rms"]) / null_rms,
                "holdout_mse_improvement_over_constant_null": 1.0
                - (float(holdout_result["rms"]) / null_rms) ** 2,
                "bidirectional_holdout": holdout_result,
            }
        midpoint = int(np.argmin(np.abs(fine_times_s - analysis_stop_s / 2.0)))
        candidates.append(
            {
                "norad_id": int(catalogue.satellite_numbers[int(catalogue_index)]),
                "object_name": catalogue.names[int(catalogue_index)],
                "catalogue_index": int(catalogue_index),
                "element_epoch_utc_ns": int(element_epoch_ns[int(catalogue_index)]),
                "element_epoch_utc": iso_utc(int(element_epoch_ns[int(catalogue_index)])),
                "element_age_at_capture_h": float(
                    (first_utc_ns - element_epoch_ns[int(catalogue_index)]) / 3.6e12
                ),
                "minimum_elevation_deg": float(
                    np.min(fine_tracks.elevation_deg[track_row, actual])
                ),
                "maximum_elevation_deg": float(
                    np.max(fine_tracks.elevation_deg[track_row, actual])
                ),
                "midpoint_azimuth_deg": float(fine_tracks.azimuth_deg[track_row, midpoint]),
                "midpoint_elevation_deg": float(fine_tracks.elevation_deg[track_row, midpoint]),
                "midpoint_range_km": float(fine_tracks.range_km[track_row, midpoint]),
                "midpoint_range_rate_km_s": float(fine_tracks.range_rate_km_s[track_row, midpoint]),
                "pss": pss_results,
                "glrt": glrt_results,
                "glrt_anchor_sensitivity": glrt_anchor_results,
            }
        )

    pss_physical = (
        rank_rows(
            candidates,
            ("pss", "physical_arrival_delay", "holdout_rms_ratio_to_affine_null"),
            "pss_physical_rank",
        )
        if has_pss
        else []
    )
    pss_mirrored = (
        rank_rows(
            candidates,
            ("pss", "mirrored_sign_control", "holdout_rms_ratio_to_affine_null"),
            "pss_mirrored_rank",
        )
        if has_pss
        else []
    )
    glrt_rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for receiver_id in sorted(glrt):
        receiver = str(receiver_id)
        glrt_rankings[receiver] = {
            "physical": rank_rows(
                candidates,
                ("glrt", receiver, "physical_iq_sign", "holdout_rms_ratio_to_constant_null"),
                f"glrt_rx{receiver}_physical_rank",
            ),
            "opposite": rank_rows(
                candidates,
                (
                    "glrt",
                    receiver,
                    "opposite_iq_sign_control",
                    "holdout_rms_ratio_to_constant_null",
                ),
                f"glrt_rx{receiver}_opposite_rank",
            ),
        }
    for row in candidates:
        physical_ratios = np.asarray(
            [
                row["glrt"][receiver]["physical_iq_sign"]["holdout_rms_ratio_to_constant_null"]
                for receiver in glrt_rankings
            ],
            dtype=float,
        )
        opposite_ratios = np.asarray(
            [
                row["glrt"][receiver]["opposite_iq_sign_control"][
                    "holdout_rms_ratio_to_constant_null"
                ]
                for receiver in glrt_rankings
            ],
            dtype=float,
        )
        row["glrt_all_receiver_physical_score"] = float(np.mean(np.square(physical_ratios)))
        row["glrt_all_receiver_opposite_control_score"] = float(np.mean(np.square(opposite_ratios)))
    glrt_all_receiver_physical = rank_rows(
        candidates,
        ("glrt_all_receiver_physical_score",),
        "glrt_all_receiver_physical_rank",
    )
    glrt_all_receiver_opposite = rank_rows(
        candidates,
        ("glrt_all_receiver_opposite_control_score",),
        "glrt_all_receiver_opposite_control_rank",
    )
    glrt_anchor_rankings = {
        str(receiver_id): rank_rows(
            candidates,
            (
                "glrt_anchor_sensitivity",
                str(receiver_id),
                "holdout_rms_ratio_to_constant_null",
            ),
            f"glrt_rx{receiver_id}_anchor_sensitivity_rank",
        )
        for receiver_id in sorted(glrt_anchor)
    }
    for row in candidates:
        anchor_ratios = np.asarray(
            [
                row["glrt_anchor_sensitivity"][receiver]["holdout_rms_ratio_to_constant_null"]
                for receiver in glrt_anchor_rankings
            ],
            dtype=float,
        )
        row["glrt_all_receiver_anchor_sensitivity_score"] = float(np.mean(np.square(anchor_ratios)))
    glrt_all_receiver_anchor = rank_rows(
        candidates,
        ("glrt_all_receiver_anchor_sensitivity_score",),
        "glrt_all_receiver_anchor_sensitivity_rank",
    )
    best_receiver = str(capture["glrt"]["best_receiver_id_from_cohort_selection"])
    if has_pss:
        for row in candidates:
            assert row["pss"] is not None
            pss_ratio = float(
                row["pss"]["physical_arrival_delay"]["holdout_rms_ratio_to_affine_null"]
            )
            glrt_ratio = float(
                row["glrt"][best_receiver]["physical_iq_sign"]["holdout_rms_ratio_to_constant_null"]
            )
            opposite_ratio = float(
                row["glrt"][best_receiver]["opposite_iq_sign_control"][
                    "holdout_rms_ratio_to_constant_null"
                ]
            )
            mirrored_ratio = float(
                row["pss"]["mirrored_sign_control"]["holdout_rms_ratio_to_affine_null"]
            )
            row["joint_physical_score"] = pss_ratio**2 + glrt_ratio**2
            row["joint_pss_physical_glrt_opposite_score"] = pss_ratio**2 + opposite_ratio**2
            row["joint_mirrored_pss_glrt_physical_score"] = mirrored_ratio**2 + glrt_ratio**2
            row["joint_pss_physical_all_receiver_glrt_score"] = (
                pss_ratio**2 + row["glrt_all_receiver_physical_score"]
            )
            row["joint_pss_physical_all_receiver_glrt_opposite_control_score"] = (
                pss_ratio**2 + row["glrt_all_receiver_opposite_control_score"]
            )
            row["joint_mirrored_pss_all_receiver_glrt_physical_score"] = (
                mirrored_ratio**2 + row["glrt_all_receiver_physical_score"]
            )
        joint_physical = rank_rows(
            candidates,
            ("joint_physical_score",),
            "joint_physical_rank",
        )
        joint_glrt_opposite = rank_rows(
            candidates,
            ("joint_pss_physical_glrt_opposite_score",),
            "joint_pss_physical_glrt_opposite_rank",
        )
        joint_pss_mirrored = rank_rows(
            candidates,
            ("joint_mirrored_pss_glrt_physical_score",),
            "joint_mirrored_pss_glrt_physical_rank",
        )
        joint_all_receiver_physical = rank_rows(
            candidates,
            ("joint_pss_physical_all_receiver_glrt_score",),
            "joint_pss_physical_all_receiver_glrt_rank",
        )
        joint_all_receiver_glrt_opposite = rank_rows(
            candidates,
            ("joint_pss_physical_all_receiver_glrt_opposite_control_score",),
            "joint_pss_physical_all_receiver_glrt_opposite_control_rank",
        )
        joint_all_receiver_pss_mirrored = rank_rows(
            candidates,
            ("joint_mirrored_pss_all_receiver_glrt_physical_score",),
            "joint_mirrored_pss_all_receiver_glrt_physical_rank",
        )
    else:
        joint_physical = []
        joint_glrt_opposite = []
        joint_pss_mirrored = []
        joint_all_receiver_physical = []
        joint_all_receiver_glrt_opposite = []
        joint_all_receiver_pss_mirrored = []
    specificity = {
        "pss_physical": candidate_specificity(
            pss_physical,
            ("pss", "physical_arrival_delay", "holdout_rms_ratio_to_affine_null"),
        ),
        "pss_mirrored_control": candidate_specificity(
            pss_mirrored,
            ("pss", "mirrored_sign_control", "holdout_rms_ratio_to_affine_null"),
        ),
        "joint_physical": candidate_specificity(
            joint_physical,
            ("joint_physical_score",),
        ),
        "joint_glrt_opposite_control": candidate_specificity(
            joint_glrt_opposite,
            ("joint_pss_physical_glrt_opposite_score",),
        ),
        "joint_pss_mirrored_control": candidate_specificity(
            joint_pss_mirrored,
            ("joint_mirrored_pss_glrt_physical_score",),
        ),
        "glrt_all_receiver_physical": candidate_specificity(
            glrt_all_receiver_physical,
            ("glrt_all_receiver_physical_score",),
        ),
        "glrt_all_receiver_opposite_control": candidate_specificity(
            glrt_all_receiver_opposite,
            ("glrt_all_receiver_opposite_control_score",),
        ),
        "glrt_all_receiver_anchor_sensitivity": candidate_specificity(
            glrt_all_receiver_anchor,
            ("glrt_all_receiver_anchor_sensitivity_score",),
        ),
        "joint_all_receiver_physical": candidate_specificity(
            joint_all_receiver_physical,
            ("joint_pss_physical_all_receiver_glrt_score",),
        ),
        "joint_all_receiver_glrt_opposite_control": candidate_specificity(
            joint_all_receiver_glrt_opposite,
            ("joint_pss_physical_all_receiver_glrt_opposite_control_score",),
        ),
        "joint_all_receiver_pss_mirrored_control": candidate_specificity(
            joint_all_receiver_pss_mirrored,
            ("joint_mirrored_pss_all_receiver_glrt_physical_score",),
        ),
        "glrt": {
            receiver: {
                "physical": candidate_specificity(
                    rankings["physical"],
                    (
                        "glrt",
                        receiver,
                        "physical_iq_sign",
                        "holdout_rms_ratio_to_constant_null",
                    ),
                ),
                "opposite_control": candidate_specificity(
                    rankings["opposite"],
                    (
                        "glrt",
                        receiver,
                        "opposite_iq_sign_control",
                        "holdout_rms_ratio_to_constant_null",
                    ),
                ),
            }
            for receiver, rankings in glrt_rankings.items()
        },
        "glrt_anchor_sensitivity": {
            receiver: candidate_specificity(
                rankings,
                (
                    "glrt_anchor_sensitivity",
                    receiver,
                    "holdout_rms_ratio_to_constant_null",
                ),
            )
            for receiver, rankings in glrt_anchor_rankings.items()
        },
    }

    def pss_diagnostic(
        row: dict[str, Any],
        *,
        ranking_kind: str,
        model_label: str,
    ) -> dict[str, Any]:
        assert row["pss"] is not None
        track_row = fine_row_by_catalogue_index[int(row["catalogue_index"])]
        geometric_delay_s = fine_tracks.range_km[track_row] * 1000.0 / LIGHT_SPEED_M_S
        predicted_s = np.interp(pss_times_s, fine_times_s, geometric_delay_s)
        if model_label == "mirrored_sign_control":
            predicted_s = -predicted_s
        model = row["pss"][model_label]
        fitted_s, residual_s = fitted_curve(
            pss_observed_s,
            predicted_s,
            pss_times_s,
            model["full_nuisance_coefficients_ascending_s"],
        )
        return {
            "ranking_kind": ranking_kind,
            "candidate": candidate_label(row),
            "times_s": pss_times_s.tolist(),
            "fitted": (fitted_s * 1e6).tolist(),
            "residual": (residual_s * 1e6).tolist(),
            "holdout_score": model["holdout_rms_ratio_to_affine_null"],
        }

    def glrt_diagnostic(
        row: dict[str, Any],
        *,
        receiver: str,
        ranking_kind: str,
    ) -> dict[str, Any]:
        track_row = fine_row_by_catalogue_index[int(row["catalogue_index"])]
        times_s, observed_hz, rf_hz = glrt[int(receiver)]
        physical_full_hz = np.asarray(
            doppler_shift_hz(rf_hz, fine_tracks.range_rate_km_s[track_row]),
            dtype=float,
        )
        predicted_hz = np.interp(times_s, fine_times_s, physical_full_hz)
        model = row["glrt"][receiver]["physical_iq_sign"]
        fitted_hz, residual_hz = fitted_curve(
            observed_hz,
            predicted_hz,
            times_s,
            [model["full_constant_cfo_offset_hz"]],
        )
        return {
            "ranking_kind": ranking_kind,
            "candidate": candidate_label(row),
            "times_s": times_s.tolist(),
            "fitted": fitted_hz.tolist(),
            "residual": residual_hz.tolist(),
            "holdout_score": model["holdout_rms_ratio_to_constant_null"],
        }

    diagnostic_series: list[dict[str, Any]] = []
    if has_pss:
        pss_curves = [
            pss_diagnostic(
                pss_physical[0],
                ranking_kind="independent physical",
                model_label="physical_arrival_delay",
            ),
            pss_diagnostic(
                pss_mirrored[0],
                ranking_kind="mirrored-sign control",
                model_label="mirrored_sign_control",
            ),
        ]
        primary_joint = joint_all_receiver_physical[0]
        if primary_joint["norad_id"] != pss_physical[0]["norad_id"]:
            pss_curves.append(
                pss_diagnostic(
                    primary_joint,
                    ranking_kind="joint physical (dual GLRT)",
                    model_label="physical_arrival_delay",
                )
            )
        diagnostic_series.append(
            {
                "sensor": "native 25 MS/s PSS timing",
                "unit": "µs",
                "times_s": pss_times_s.tolist(),
                "observed": (pss_observed_s * 1e6).tolist(),
                "curves": pss_curves,
            }
        )
    diagnostic_receivers = [best_receiver] if has_pss else sorted(glrt_rankings, key=int)[:2]
    for receiver in diagnostic_receivers:
        independent = glrt_rankings[receiver]["physical"][0]
        glrt_curves = [
            glrt_diagnostic(
                independent,
                receiver=receiver,
                ranking_kind="independent",
            )
        ]
        if has_pss and primary_joint["norad_id"] != independent["norad_id"]:
            glrt_curves.append(
                glrt_diagnostic(
                    primary_joint,
                    receiver=receiver,
                    ranking_kind="joint physical (dual GLRT)",
                )
            )
        times_s, observed_hz, _ = glrt[int(receiver)]
        diagnostic_series.append(
            {
                "sensor": f"paired 2.5 MS/s GLRT RX{receiver}",
                "unit": "Hz",
                "times_s": times_s.tolist(),
                "observed": observed_hz.tolist(),
                "curves": glrt_curves,
            }
        )
    tle_stat = tle_path.stat()
    return {
        "capture_id": capture["capture_id"],
        "first_sample_estimate_utc_ns": first_utc_ns,
        "first_sample_estimate_utc": iso_utc(first_utc_ns),
        "tle": {
            "path": str(tle_path),
            "sha256": sha256(tle_path),
            "collection_time_authority": "legacy raw source filesystem mtime",
            "collection_utc_ns": tle_stat.st_mtime_ns,
            "collection_utc": iso_utc(tle_stat.st_mtime_ns),
            "collection_age_at_capture_s": (first_utc_ns - tle_stat.st_mtime_ns) / 1e9,
        },
        "accounting": {
            "catalogue_element_count": len(catalogue),
            "future_element_epoch_excluded_count": int(np.count_nonzero(~causal)),
            "coarse_candidate_count": int(coarse_indices.size),
            "horizon_visible_candidate_count": len(candidates),
            "pss_block_median_count": int(pss_times_s.size),
            "glrt_hough_observation_count_by_receiver": {
                str(receiver): int(values[0].size) for receiver, values in glrt.items()
            },
            "glrt_anchor_observation_count_by_receiver": {
                str(receiver): int(values[0].size) for receiver, values in glrt_anchor.items()
            },
        },
        "nulls": {
            "pss_affine": (
                {key: value for key, value in pss_null.items() if not key.startswith("_")}
                if pss_null is not None
                else None
            ),
            "glrt_constant": {
                str(receiver): {
                    key: value for key, value in result.items() if not key.startswith("_")
                }
                for receiver, result in glrt_nulls.items()
            },
        },
        "primary_best_receiver_id": int(best_receiver),
        "headline": {
            "pss_physical_best": pss_physical[0] if pss_physical else None,
            "pss_mirrored_control_best": pss_mirrored[0] if pss_mirrored else None,
            "glrt_physical_best_by_receiver": {
                receiver: rankings["physical"][0] for receiver, rankings in glrt_rankings.items()
            },
            "glrt_opposite_control_best_by_receiver": {
                receiver: rankings["opposite"][0] for receiver, rankings in glrt_rankings.items()
            },
            "glrt_all_receiver_physical_best": glrt_all_receiver_physical[0],
            "glrt_all_receiver_opposite_control_best": glrt_all_receiver_opposite[0],
            "glrt_all_receiver_anchor_sensitivity_best": (glrt_all_receiver_anchor[0]),
            "glrt_anchor_sensitivity_best_by_receiver": {
                receiver: rankings[0] for receiver, rankings in glrt_anchor_rankings.items()
            },
            "joint_physical_best": joint_physical[0] if joint_physical else None,
            "joint_glrt_opposite_control_best": (
                joint_glrt_opposite[0] if joint_glrt_opposite else None
            ),
            "joint_pss_mirrored_control_best": (
                joint_pss_mirrored[0] if joint_pss_mirrored else None
            ),
            "joint_all_receiver_physical_best": (
                joint_all_receiver_physical[0] if joint_all_receiver_physical else None
            ),
            "joint_all_receiver_glrt_opposite_control_best": (
                joint_all_receiver_glrt_opposite[0] if joint_all_receiver_glrt_opposite else None
            ),
            "joint_all_receiver_pss_mirrored_control_best": (
                joint_all_receiver_pss_mirrored[0] if joint_all_receiver_pss_mirrored else None
            ),
            "cross_ranks": (
                {
                    "pss_physical_best_primary_glrt_physical_rank": pss_physical[0][
                        f"glrt_rx{best_receiver}_physical_rank"
                    ],
                    "primary_glrt_physical_best_pss_physical_rank": glrt_rankings[best_receiver][
                        "physical"
                    ][0]["pss_physical_rank"],
                    "pss_physical_best_all_receiver_glrt_physical_rank": pss_physical[0][
                        "glrt_all_receiver_physical_rank"
                    ],
                    "all_receiver_glrt_physical_best_pss_physical_rank": (
                        glrt_all_receiver_physical[0]["pss_physical_rank"]
                    ),
                }
                if has_pss
                else None
            ),
        },
        "specificity": specificity,
        "candidates": sorted(
            candidates,
            key=(
                (lambda row: row["joint_pss_physical_all_receiver_glrt_rank"])
                if has_pss
                else (lambda row: row["glrt_all_receiver_physical_rank"])
            ),
        ),
        "_fit_diagnostic_series": diagnostic_series,
    }


def top_rows(
    result: dict[str, Any],
    metric: tuple[str, ...],
    *,
    count: int = 12,
) -> list[dict[str, Any]]:
    def value(row: dict[str, Any]) -> float:
        target: Any = row
        for key in metric:
            target = target[key]
        return float(target)

    return sorted(result["candidates"], key=value)[:count]


def render_ranking(result: dict[str, Any], path: Path) -> None:
    receiver = str(result["primary_best_receiver_id"])
    if result["headline"]["pss_physical_best"] is not None:
        panels = (
            (
                "PSS physical arrival delay",
                ("pss", "physical_arrival_delay", "holdout_rms_ratio_to_affine_null"),
                "#ea580c",
            ),
            (
                "PSS mirrored-sign control",
                ("pss", "mirrored_sign_control", "holdout_rms_ratio_to_affine_null"),
                "#f59e0b",
            ),
            (
                f"GLRT RX{receiver} physical IQ sign",
                (
                    "glrt",
                    receiver,
                    "physical_iq_sign",
                    "holdout_rms_ratio_to_constant_null",
                ),
                "#2563eb",
            ),
            (
                f"GLRT RX{receiver} opposite IQ sign (control)",
                (
                    "glrt",
                    receiver,
                    "opposite_iq_sign_control",
                    "holdout_rms_ratio_to_constant_null",
                ),
                "#7c3aed",
            ),
            (
                "Joint physical score (PSS + equal-weight dual GLRT)",
                ("joint_pss_physical_all_receiver_glrt_score",),
                "#16a34a",
            ),
            (
                "Joint mirrored-PSS control + equal-weight dual GLRT",
                ("joint_mirrored_pss_all_receiver_glrt_physical_score",),
                "#0d9488",
            ),
        )
        subplot_shape = (2, 3)
        figure_size = (22, 11)
    else:
        receiver_ids = sorted(result["headline"]["glrt_physical_best_by_receiver"])
        panels = tuple(
            panel
            for receiver_id in receiver_ids
            for panel in (
                (
                    f"GLRT RX{receiver_id} physical IQ sign",
                    (
                        "glrt",
                        receiver_id,
                        "physical_iq_sign",
                        "holdout_rms_ratio_to_constant_null",
                    ),
                    "#2563eb",
                ),
                (
                    f"GLRT RX{receiver_id} opposite IQ sign (control)",
                    (
                        "glrt",
                        receiver_id,
                        "opposite_iq_sign_control",
                        "holdout_rms_ratio_to_constant_null",
                    ),
                    "#7c3aed",
                ),
            )
        )[:4]
        subplot_shape = (2, 2)
        figure_size = (16, 11)
    figure, axes = plt.subplots(
        *subplot_shape,
        figsize=figure_size,
        constrained_layout=True,
    )
    for axis, (title, metric, color) in zip(axes.flat, panels, strict=True):
        rows = top_rows(result, metric)
        values: list[float] = []
        for row in rows:
            value: Any = row
            for key in metric:
                value = value[key]
            values.append(float(value))
        labels = [f"{row['object_name']} / {row['norad_id']}" for row in rows]
        positions = np.arange(len(rows))
        axis.barh(positions, values, color=color, alpha=0.78)
        axis.set_yticks(positions, labels, fontsize=8)
        axis.invert_yaxis()
        axis.set_xlabel("Normalized holdout score (lower is better)")
        axis.set_title(title, loc="left")
        axis.grid(axis="x", alpha=0.25)
    figure.suptitle(
        f"{result['capture_id']} — fixed-time causal-TLE candidate ranking\n"
        "opposite-sign panels are diagnostic controls, not silent sign choices",
        fontsize=15,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def render_fit_diagnostic(result: dict[str, Any], path: Path) -> None:
    series = result["_fit_diagnostic_series"]
    figure, axes = plt.subplots(
        len(series),
        2,
        figsize=(17, 4.8 * len(series)),
        squeeze=False,
        constrained_layout=True,
    )
    colors = ("#2563eb", "#ea580c", "#16a34a")
    for row_index, sensor in enumerate(series):
        fit_axis, residual_axis = axes[row_index]
        times_s = np.asarray(sensor["times_s"], dtype=float)
        observed = np.asarray(sensor["observed"], dtype=float)
        fit_axis.scatter(
            times_s,
            observed,
            s=5,
            color="#111827",
            alpha=0.35,
            label="observed",
            rasterized=True,
        )
        for color, curve in zip(colors, sensor["curves"], strict=False):
            curve_times_s = np.asarray(curve["times_s"], dtype=float)
            fitted = np.asarray(curve["fitted"], dtype=float)
            residual = np.asarray(curve["residual"], dtype=float)
            label = (
                f"{curve['ranking_kind']}: {curve['candidate']} "
                f"(holdout/null {curve['holdout_score']:.4g})"
            )
            fit_axis.plot(curve_times_s, fitted, color=color, linewidth=1.6, label=label)
            residual_axis.scatter(
                curve_times_s,
                residual,
                s=5,
                color=color,
                alpha=0.55,
                label=label,
                rasterized=True,
            )
        fit_axis.set_ylabel(sensor["unit"])
        fit_axis.set_title(f"{sensor['sensor']} — TLE fitted trajectory", loc="left")
        fit_axis.grid(alpha=0.25)
        fit_axis.legend(fontsize=8)
        residual_axis.axhline(0.0, color="black", linewidth=0.8)
        residual_axis.set_ylabel(f"Residual ({sensor['unit']})")
        residual_axis.set_title("Fit residual", loc="left")
        residual_axis.grid(alpha=0.25)
        residual_axis.legend(fontsize=8)
        if row_index == len(series) - 1:
            fit_axis.set_xlabel("Seconds from native 25 MS/s first-sample estimate")
            residual_axis.set_xlabel("Seconds from native 25 MS/s first-sample estimate")
    figure.suptitle(
        f"{result['capture_id']} — causal-TLE fitted trajectories and residuals\n"
        "nuisance is affine for PSS and constant-only for GLRT; ranking uses held-out data",
        fontsize=15,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def render_cohort_summary(results: list[dict[str, Any]], path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(16, 7), constrained_layout=True)
    labels = [result["capture_id"].split("-")[-1] for result in results]
    pss_ratios = [
        (
            result["headline"]["pss_physical_best"]["pss"]["physical_arrival_delay"][
                "holdout_rms_ratio_to_affine_null"
            ]
            if result["headline"]["pss_physical_best"] is not None
            else math.nan
        )
        for result in results
    ]
    pss_mirrored_ratios = [
        (
            result["headline"]["pss_mirrored_control_best"]["pss"]["mirrored_sign_control"][
                "holdout_rms_ratio_to_affine_null"
            ]
            if result["headline"]["pss_mirrored_control_best"] is not None
            else math.nan
        )
        for result in results
    ]
    glrt_ratios = []
    joint_scores = []
    joint_mirrored_scores = []
    for result in results:
        glrt_ratios.append(
            math.sqrt(
                result["headline"]["glrt_all_receiver_physical_best"][
                    "glrt_all_receiver_physical_score"
                ]
            )
        )
        joint = result["headline"]["joint_all_receiver_physical_best"]
        joint_scores.append(
            joint["joint_pss_physical_all_receiver_glrt_score"] if joint is not None else math.nan
        )
        joint_mirrored = result["headline"]["joint_all_receiver_pss_mirrored_control_best"]
        joint_mirrored_scores.append(
            joint_mirrored["joint_mirrored_pss_all_receiver_glrt_physical_score"]
            if joint_mirrored is not None
            else math.nan
        )
    positions = np.arange(len(results))
    axes[0].scatter(
        positions - 0.18,
        pss_ratios,
        marker="D",
        s=80,
        label="PSS physical best/null",
    )
    axes[0].scatter(
        positions,
        pss_mirrored_ratios,
        marker="s",
        s=70,
        label="PSS mirrored control best/null",
    )
    axes[0].scatter(
        positions + 0.18,
        glrt_ratios,
        marker="o",
        s=80,
        label="dual-GLRT physical RMS consensus",
    )
    axes[0].axhline(1.0, color="black", linewidth=0.8, linestyle="--")
    axes[0].set_xticks(positions, labels, rotation=25)
    axes[0].set_ylabel("Holdout RMS ratio to nuisance-only null")
    axes[0].set_title("Independent TLE evidence strength")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend()
    axes[1].scatter(
        positions - 0.08,
        joint_scores,
        s=90,
        color="#16a34a",
        label="joint physical",
    )
    axes[1].scatter(
        positions + 0.08,
        joint_mirrored_scores,
        marker="s",
        s=75,
        color="#0d9488",
        label="joint mirrored-PSS control",
    )
    axes[1].set_xticks(positions, labels, rotation=25)
    axes[1].set_ylabel("Joint normalized squared score")
    axes[1].set_title("Joint candidate scores and PSS-sign control")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=9)
    for position, result in zip(positions, results, strict=True):
        best = result["headline"]["joint_all_receiver_physical_best"]
        if best is None:
            axes[1].annotate(
                "no independent PSS track",
                (position, 0.0),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )
            continue
        axes[1].annotate(
            f"{best['object_name']}\n{best['norad_id']}",
            (position - 0.08, best["joint_pss_physical_all_receiver_glrt_score"]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    figure.suptitle("Five-capture causal-TLE association summary")
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = arguments()
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for capture in analysis["captures"]:
        first_utc_ns = int(capture["native25"]["first_sample_timing"]["estimate_utc_ns"])
        tle_path = latest_causal_tle(args.tle_dir, first_utc_ns)
        result = evaluate_capture(capture, tle_path)
        figure_name = f"{capture['capture_id']}-tle-ranking.png"
        figure_path = args.output_dir / figure_name
        render_ranking(result, figure_path)
        result["figure"] = {"path": figure_name, "sha256": sha256(figure_path)}
        fit_figure_name = f"{capture['capture_id']}-tle-fit-diagnostic.png"
        fit_figure_path = args.output_dir / fit_figure_name
        render_fit_diagnostic(result, fit_figure_path)
        result["fit_figure"] = {
            "path": fit_figure_name,
            "sha256": sha256(fit_figure_path),
        }
        del result["_fit_diagnostic_series"]
        results.append(result)
    summary_figure = args.output_dir / "cohort-tle-association-summary.png"
    render_cohort_summary(results, summary_figure)
    evidence = {
        "schema_version": 1,
        "analysis_kind": "five-capture-independent-and-joint-pss-glrt-causal-tle-ranking",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__)),
        },
        "input": {"path": str(args.analysis), "sha256": sha256(args.analysis)},
        "observer": {
            **resolve_preset(SITE_NAME).model_dump(mode="json"),
            "capture_bound": False,
            "antenna_boresight_known": False,
        },
        "method": {
            "fixed_capture_time": True,
            "time_shift_fitted": False,
            "doppler_scale_fitted": False,
            "slope_or_curvature_fitted_to_tle": False,
            "catalogue_filter": (
                "latest raw TLE snapshot collected before capture; element epoch no later "
                "than first sample; usable, plausible altitude, above geometric horizon"
            ),
            "pss_model": (
                "observed unwrapped arrival phase = geometric range/c + constant clock "
                "offset + constant clock drift*time"
            ),
            "glrt_model": (
                "GLRT-only integer-alias-stitched canonical CFO = physical TLE Doppler + "
                "constant receiver/LNB CFO offset"
            ),
            "glrt_dual_receiver_consensus": (
                "primary GLRT consensus is the equal-weight mean of squared per-receiver "
                "normalized holdout RMS ratios; per-receiver rankings remain explicit"
            ),
            "primary_joint_score": (
                "squared normalized PSS holdout RMS ratio plus the equal-weight mean of "
                "squared physical-sign GLRT ratios across both receivers"
            ),
            "glrt_anchor_sensitivity": (
                "repeat each receiver ranking on its single largest Hough episode, without "
                "global episode stitching; integer alias class is absorbed only by the "
                "declared constant CFO nuisance"
            ),
            "holdout": (
                "fit nuisance on first 60% and predict last 40%, then reverse; ranking uses "
                "quadratic mean of the two RMS values"
            ),
            "fine_propagation_spacing_s": FINE_SPACING_S,
            "coarse_point_count": COARSE_POINT_COUNT,
        },
        "captures": results,
        "artifacts": {
            "cohort_summary": {
                "path": summary_figure.name,
                "sha256": sha256(summary_figure),
            }
        },
        "limitations": [
            "Rankings are candidate associations, not satellite identifications.",
            "The site preset is reviewed but not capture-bound GPS authority.",
            "Antenna boresight and gain pattern are unknown.",
            "PSS and GLRT may observe different simultaneous transmitters or beams.",
            (
                "PSS absolute UTC frame cycle is unresolved when start-time uncertainty "
                "exceeds one frame."
            ),
            (
                "GLRT physical IQ/mixer sign is not independently calibrated; opposite-sign "
                "results are controls."
            ),
            "No SSS, payload, known-pilot, or beam schedule evidence is used.",
        ],
    }
    output = args.output_dir / "cohort-tle-association.json"
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "capture_count": len(results),
                "output": str(output),
                "joint_all_receiver_physical_best": [
                    (
                        {
                            "capture_id": result["capture_id"],
                            "norad_id": result["headline"]["joint_all_receiver_physical_best"][
                                "norad_id"
                            ],
                            "object_name": result["headline"]["joint_all_receiver_physical_best"][
                                "object_name"
                            ],
                            "specific": result["specificity"]["joint_all_receiver_physical"][
                                "specific"
                            ],
                        }
                        if result["headline"]["joint_all_receiver_physical_best"] is not None
                        else {
                            "capture_id": result["capture_id"],
                            "norad_id": None,
                            "object_name": None,
                            "specific": False,
                        }
                    )
                    for result in results
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
