#!/usr/bin/env python3
# ruff: noqa: E501
"""Evaluate robust CFO and explicit locklet prototypes on the D3 pilot replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.research.pilot_locklet_prototypes import (
    PiecewiseLockletConfig,
    PilotFrameObservation,
    RobustBlockConfig,
    compare_radio_only_polynomials,
    robust_blockwise_cfo_rate,
    track_piecewise_locklets,
)

FRAME_RATE_HZ = 750.0
PHASE_ARC_MINIMUM_FRAMES = 20
PHASE_ARC_GATE_RAD = 0.50
CAPTURE_MANIFEST_SHA256 = "145c55e56c3e7f1f76b1b769ae3779edc90186a2a2a91ecb05338212c724b2db"
CAPTURE_RELEASE_SHA = "058576ec74b7dae9ae3ad2a9798679fcf2c934c3"


@dataclass(frozen=True, slots=True)
class PredictionSeries:
    name: str
    residual_by_key: dict[tuple[int, int], float]
    prediction_by_key: dict[tuple[int, int], float]
    normalized_by_key: dict[tuple[int, int], float]


@dataclass(frozen=True, slots=True)
class WindowRows:
    index: int
    center_time_s: float
    raw_disjoint: bool
    frame_index: np.ndarray
    absolute_time_s: np.ndarray
    cfo_hz: np.ndarray
    sigma_hz: np.ndarray
    supported: np.ndarray
    exact_coherence: np.ndarray
    control_coherence: np.ndarray
    frequency_innovation_hz: np.ndarray
    tracked_cfo_hz: np.ndarray
    tracked_rate_hz_s: np.ndarray
    tracked_rate_sigma_hz_s: np.ndarray
    phase_innovation_rad: np.ndarray
    phase_update: np.ndarray
    reacquired: np.ndarray

    def key(self, offset: int) -> tuple[int, int]:
        return self.index, int(self.frame_index[offset])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-npz",
        type=Path,
        default=Path(
            "reports/figures/2026_08_25_d3_pilot_filter_prototypes/source/"
            "d3-radio1-rx1-filter-benchmark.npz"
        ),
    )
    parser.add_argument(
        "--source-summary",
        type=Path,
        default=Path(
            "reports/figures/2026_08_25_d3_pilot_filter_prototypes/source/"
            "d3-radio1-rx1-filter-benchmark-summary.json"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_25_d3_pilot_filter_prototypes"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_25_d3_pilot_filter_prototypes.md"),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_windows(path: Path) -> tuple[WindowRows, ...]:
    with np.load(path) as source:
        output = []
        for index in sorted(int(value) for value in np.unique(source["window_index"])):
            mask = source["window_index"] == index
            if not np.any(mask):
                continue
            output.append(
                WindowRows(
                    index=index,
                    center_time_s=float(source["window_center_time_s"][mask][0]),
                    raw_disjoint=bool(source["window_raw_disjoint"][mask][0]),
                    frame_index=np.asarray(source["frame_index"][mask], dtype=int),
                    absolute_time_s=np.asarray(source["absolute_time_s"][mask], dtype=float),
                    cfo_hz=np.asarray(source["absolute_cfo_measurement_hz"][mask], dtype=float),
                    sigma_hz=np.asarray(source["measurement_sigma_hz"][mask], dtype=float),
                    supported=np.asarray(source["measurement_supported"][mask], dtype=bool),
                    exact_coherence=np.asarray(source["exact_coherence"][mask], dtype=float),
                    control_coherence=np.asarray(source["control_coherence"][mask], dtype=float),
                    frequency_innovation_hz=np.asarray(
                        source["frequency_innovation_hz"][mask], dtype=float
                    ),
                    tracked_cfo_hz=np.asarray(source["tracked_absolute_cfo_hz"][mask], dtype=float),
                    tracked_rate_hz_s=np.asarray(source["tracked_rate_hz_s"][mask], dtype=float),
                    tracked_rate_sigma_hz_s=np.asarray(
                        source["tracked_rate_sigma_hz_s"][mask], dtype=float
                    ),
                    phase_innovation_rad=np.asarray(
                        source["phase_innovation_rad"][mask], dtype=float
                    ),
                    phase_update=np.asarray(source["phase_update"][mask], dtype=bool),
                    reacquired=np.asarray(source["reacquired"][mask], dtype=bool),
                )
            )
    return tuple(output)


def _observations(
    window: WindowRows, *, phase_gated: bool = False
) -> tuple[PilotFrameObservation, ...]:
    result = []
    for offset in range(len(window.absolute_time_s)):
        support = bool(window.supported[offset])
        if phase_gated:
            support = bool(
                support
                and window.phase_update[offset]
                and not window.reacquired[offset]
                and abs(window.phase_innovation_rad[offset]) <= PHASE_ARC_GATE_RAD
            )
        result.append(
            PilotFrameObservation(
                time_s=float(window.absolute_time_s[offset]),
                cfo_hz=float(window.cfo_hz[offset]),
                cfo_sigma_hz=max(float(window.sigma_hz[offset]), 1.0),
                support=1.0 if support else 0.0,
            )
        )
    return tuple(result)


def _robust_weighted_line(
    time_s: np.ndarray,
    cfo_hz: np.ndarray,
    sigma_hz: np.ndarray,
) -> tuple[float, np.ndarray]:
    reference = float(np.median(time_s))
    design = np.column_stack((np.ones(len(time_s)), time_s - reference))
    base = 1.0 / np.maximum(sigma_hz, 15.0) ** 2
    coefficients = np.linalg.lstsq(
        design * np.sqrt(base)[:, None], cfo_hz * np.sqrt(base), rcond=None
    )[0]
    for _ in range(8):
        residual = cfo_hz - design @ coefficients
        scale = max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            15.0,
        )
        standardized = np.abs(residual) / scale
        robust = np.ones(len(residual))
        mask = standardized > 1.5
        robust[mask] = 1.5 / standardized[mask]
        weights = base * robust
        updated = np.linalg.lstsq(
            design * np.sqrt(weights)[:, None],
            cfo_hz * np.sqrt(weights),
            rcond=None,
        )[0]
        if np.max(np.abs(updated - coefficients)) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    return reference, coefficients


def trailing_line_predictions(
    window: WindowRows,
    *,
    history_s: float,
    minimum_history: int = 6,
) -> PredictionSeries:
    residual: dict[tuple[int, int], float] = {}
    prediction: dict[tuple[int, int], float] = {}
    supported_offsets = np.flatnonzero(window.supported)
    for position, offset in enumerate(supported_offsets):
        current_time = window.absolute_time_s[offset]
        prior = supported_offsets[:position]
        prior = prior[window.absolute_time_s[prior] >= current_time - history_s]
        if len(prior) < minimum_history:
            continue
        reference, coefficients = _robust_weighted_line(
            window.absolute_time_s[prior],
            window.cfo_hz[prior],
            window.sigma_hz[prior],
        )
        predicted = float(coefficients[0] + coefficients[1] * (current_time - reference))
        key = window.key(int(offset))
        prediction[key] = predicted
        residual[key] = float(window.cfo_hz[offset] - predicted)
    return PredictionSeries(
        name=f"trailing-{history_s * 1_000:.0f}ms-line",
        residual_by_key=residual,
        prediction_by_key=prediction,
        normalized_by_key={},
    )


def v2_predictions(window: WindowRows) -> PredictionSeries:
    residual: dict[tuple[int, int], float] = {}
    prediction: dict[tuple[int, int], float] = {}
    supported = np.flatnonzero(window.supported)
    for offset in supported[12:]:
        key = window.key(int(offset))
        value = float(window.frequency_innovation_hz[offset])
        residual[key] = value
        prediction[key] = float(window.cfo_hz[offset] - value)
    return PredictionSeries("current-v2", residual, prediction, {})


def jump_filter_predictions(
    window: WindowRows,
    *,
    phase_gated: bool = False,
) -> tuple[PredictionSeries, Any]:
    observations = _observations(window, phase_gated=phase_gated)
    result = track_piecewise_locklets(
        observations,
        config=PiecewiseLockletConfig(),
    )
    residual: dict[tuple[int, int], float] = {}
    prediction: dict[tuple[int, int], float] = {}
    normalized: dict[tuple[int, int], float] = {}
    for offset, decision in enumerate(result.decisions):
        if decision.predicted_cfo_hz is None or not window.supported[offset]:
            continue
        key = window.key(offset)
        value = float(window.cfo_hz[offset] - decision.predicted_cfo_hz)
        residual[key] = value
        prediction[key] = float(decision.predicted_cfo_hz)
        if decision.normalized_frequency_innovation is not None:
            normalized[key] = float(decision.normalized_frequency_innovation)
    label = "phase-gated-jump-filter" if phase_gated else "robust-jump-filter"
    return PredictionSeries(label, residual, prediction, normalized), result


def frozen_block_holdout(window: WindowRows) -> PredictionSeries:
    supported = np.flatnonzero(window.supported)
    if len(supported) < 20:
        return PredictionSeries("60/40-block-holdout", {}, {}, {})
    cutoff = float(window.absolute_time_s[supported[0]] + 0.060)
    observations = _observations(window)
    train = tuple(item for item in observations if item.support > 0.0 and item.time_s < cutoff)
    test_offsets = [int(offset) for offset in supported if window.absolute_time_s[offset] >= cutoff]
    try:
        fit = robust_blockwise_cfo_rate(
            train,
            degree=1,
            config=RobustBlockConfig(
                block_duration_s=0.015,
                minimum_observations_per_block=4,
            ),
        )
    except ValueError:
        return PredictionSeries("60/40-block-holdout", {}, {}, {})
    residual = {}
    prediction = {}
    for offset in test_offsets:
        predicted = float(fit.predict((window.absolute_time_s[offset],))[0])
        key = window.key(offset)
        prediction[key] = predicted
        residual[key] = float(window.cfo_hz[offset] - predicted)
    return PredictionSeries("60/40-block-holdout", residual, prediction, {})


def offline_block_smoother(window: WindowRows) -> tuple[PredictionSeries, int | None]:
    observations = tuple(item for item in _observations(window) if item.support > 0.0)
    if len(observations) < 20:
        return PredictionSeries("offline-block-smoother", {}, {}, {}), None
    try:
        comparison = compare_radio_only_polynomials(
            observations,
            degrees=(1, 2, 3),
            config=RobustBlockConfig(
                block_duration_s=0.015,
                minimum_observations_per_block=4,
            ),
        )
    except ValueError:
        return PredictionSeries("offline-block-smoother", {}, {}, {}), None
    row = next(
        item for item in comparison.rows if item.degree == comparison.preferred_degree_by_bic
    )
    residual = {}
    prediction = {}
    for offset in np.flatnonzero(window.supported):
        predicted = float(row.fit.predict((window.absolute_time_s[offset],))[0])
        key = window.key(int(offset))
        prediction[key] = predicted
        residual[key] = float(window.cfo_hz[offset] - predicted)
    return (
        PredictionSeries("offline-block-smoother", residual, prediction, {}),
        comparison.preferred_degree_by_bic,
    )


def phase_arcs(window: WindowRows) -> tuple[tuple[int, int], ...]:
    good = (
        window.supported
        & window.phase_update
        & ~window.reacquired
        & (np.abs(window.phase_innovation_rad) <= PHASE_ARC_GATE_RAD)
    )
    arcs: list[tuple[int, int]] = []
    start: int | None = None
    previous: int | None = None
    for offset, accepted in enumerate(good):
        consecutive = bool(
            previous is not None
            and window.absolute_time_s[offset] - window.absolute_time_s[previous]
            <= 1.6 / FRAME_RATE_HZ
        )
        if accepted and (start is None or consecutive):
            if start is None:
                start = offset
            previous = offset
        elif accepted:
            if start is not None and previous is not None:
                arcs.append((start, previous))
            start = offset
            previous = offset
        else:
            if start is not None and previous is not None:
                arcs.append((start, previous))
            start = None
            previous = None
    if start is not None and previous is not None:
        arcs.append((start, previous))
    return tuple(arcs)


def _merge_series(parts: Iterable[PredictionSeries], name: str) -> PredictionSeries:
    residual: dict[tuple[int, int], float] = {}
    prediction: dict[tuple[int, int], float] = {}
    normalized: dict[tuple[int, int], float] = {}
    for part in parts:
        residual.update(part.residual_by_key)
        prediction.update(part.prediction_by_key)
        normalized.update(part.normalized_by_key)
    return PredictionSeries(name, residual, prediction, normalized)


def _basic_statistics(values: Iterable[float]) -> dict[str, float | int | None]:
    array = np.asarray(tuple(values), dtype=float)
    if not len(array):
        return {"count": 0, "rms_hz": None, "mae_hz": None, "p95_abs_hz": None}
    return {
        "count": len(array),
        "rms_hz": float(np.sqrt(np.mean(array**2))),
        "mae_hz": float(np.mean(np.abs(array))),
        "p95_abs_hz": float(np.quantile(np.abs(array), 0.95)),
    }


def _lag_one(values_by_window: dict[int, list[float]]) -> float | None:
    left = []
    right = []
    for values in values_by_window.values():
        if len(values) >= 2:
            left.extend(values[:-1])
            right.extend(values[1:])
    if len(left) < 3 or np.std(left) <= 0.0 or np.std(right) <= 0.0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _series_statistics(
    series: PredictionSeries,
    key_time_s: dict[tuple[int, int], float],
    *,
    denominator: int,
) -> dict[str, Any]:
    result = _basic_statistics(series.residual_by_key.values())
    result["prediction_coverage_fraction"] = len(series.residual_by_key) / denominator
    by_window: dict[int, list[float]] = {}
    for key in sorted(series.residual_by_key, key=lambda item: key_time_s[item]):
        by_window.setdefault(key[0], []).append(series.residual_by_key[key])
    result["lag1_residual_correlation"] = _lag_one(by_window)
    normalized = np.asarray(tuple(series.normalized_by_key.values()), dtype=float)
    result["standardized_count"] = len(normalized)
    result["one_sigma_coverage"] = (
        float(np.mean(np.abs(normalized) <= 1.0)) if len(normalized) else None
    )
    result["two_sigma_coverage"] = (
        float(np.mean(np.abs(normalized) <= 2.0)) if len(normalized) else None
    )
    result["three_sigma_coverage"] = (
        float(np.mean(np.abs(normalized) <= 3.0)) if len(normalized) else None
    )
    return result


def paired_block_bootstrap_improvement(
    candidate: PredictionSeries,
    baseline: PredictionSeries,
    key_time_s: dict[tuple[int, int], float],
    *,
    seed: int = 20260825,
    draws: int = 5_000,
    moving_block_length: int = 3,
) -> dict[str, float | int | str]:
    keys = sorted(
        set(candidate.residual_by_key) & set(baseline.residual_by_key),
        key=lambda item: key_time_s[item],
    )
    if not keys:
        raise ValueError("paired comparison has no common prediction frames")
    blocks: dict[int, list[tuple[float, float]]] = {}
    for key in keys:
        block = int(math.floor(key_time_s[key]))
        blocks.setdefault(block, []).append(
            (candidate.residual_by_key[key], baseline.residual_by_key[key])
        )
    block_ids = sorted(blocks)
    candidate_mse = np.asarray(
        [np.mean([pair[0] ** 2 for pair in blocks[block]]) for block in block_ids]
    )
    baseline_mse = np.asarray(
        [np.mean([pair[1] ** 2 for pair in blocks[block]]) for block in block_ids]
    )
    candidate_rms = math.sqrt(float(np.mean(candidate_mse)))
    baseline_rms = math.sqrt(float(np.mean(baseline_mse)))
    if baseline_rms <= 0.0:
        raise ValueError("paired comparison baseline RMS must be positive")
    observed = 1.0 - candidate_rms / baseline_rms
    rng = np.random.default_rng(seed)
    used_length = min(moving_block_length, len(block_ids))
    draw_block_count = math.ceil(len(block_ids) / used_length)
    starts = rng.integers(0, len(block_ids), size=(draws, draw_block_count))
    sampled = (starts[:, :, None] + np.arange(used_length, dtype=int)[None, None, :]) % len(
        block_ids
    )
    sampled = sampled.reshape(draws, -1)[:, : len(block_ids)]
    values = 1.0 - np.sqrt(np.mean(candidate_mse[sampled], axis=1)) / np.sqrt(
        np.mean(baseline_mse[sampled], axis=1)
    )
    low = float(np.quantile(values, 0.025))
    high = float(np.quantile(values, 0.975))
    return {
        "common_frame_count": len(keys),
        "block_count": len(block_ids),
        "bootstrap_method": "circular moving block over one-second bins",
        "moving_block_length_seconds": used_length,
        "candidate_block_equal_rms_hz": candidate_rms,
        "baseline_block_equal_rms_hz": baseline_rms,
        "fractional_rms_improvement": observed,
        "descriptive_resampling_95_low": low,
        "descriptive_resampling_95_high": high,
        "bootstrap_95_low": low,
        "bootstrap_95_high": high,
    }


def synthetic_benchmark(*, repetitions: int = 100) -> dict[str, Any]:
    scenarios = {}
    for jump_hz in (0.0, 800.0):
        errors: dict[str, list[float]] = {
            "trailing_20ms": [],
            "robust_jump_filter": [],
            "offline_quadratic": [],
        }
        change_points = []
        locklet_counts = []
        for seed in range(repetitions):
            rng = np.random.default_rng(seed)
            time_s = np.arange(0.0, 0.2, 1.0 / FRAME_RATE_HZ)
            truth = 20_000.0 - 3_500.0 * time_s + 1_200.0 * time_s**2
            truth = truth + (time_s >= 0.1) * jump_hz
            noise = rng.standard_t(4, len(time_s)) * 18.0
            outlier = rng.random(len(time_s)) < 0.04
            noise[outlier] += rng.normal(0.0, 250.0, int(np.count_nonzero(outlier)))
            supported = rng.random(len(time_s)) > 0.10
            measured = truth + noise
            observations = tuple(
                PilotFrameObservation(
                    float(time),
                    float(cfo),
                    20.0,
                    1.0 if support else 0.0,
                )
                for time, cfo, support in zip(time_s, measured, supported, strict=True)
            )
            trailing_prediction: dict[int, float] = {}
            for index, current in enumerate(time_s):
                prior = np.flatnonzero(supported[:index] & (time_s[:index] >= current - 0.020))
                if len(prior) < 6:
                    continue
                reference, coefficients = _robust_weighted_line(
                    time_s[prior], measured[prior], np.full(len(prior), 20.0)
                )
                predicted = coefficients[0] + coefficients[1] * (current - reference)
                trailing_prediction[index] = float(predicted)
            jump = track_piecewise_locklets(observations)
            jump_prediction = {
                index: float(decision.predicted_cfo_hz)
                for index, decision in enumerate(jump.decisions)
                if decision.predicted_cfo_hz is not None
            }
            smooth = robust_blockwise_cfo_rate(
                observations,
                degree=2,
                config=RobustBlockConfig(
                    block_duration_s=0.025,
                    minimum_observations_per_block=6,
                ),
            )
            offline_prediction = smooth.predict(time_s)
            scoring_start_s = 0.11 if jump_hz else 0.02
            common = sorted(
                index
                for index in set(trailing_prediction) & set(jump_prediction)
                if time_s[index] >= scoring_start_s
            )
            for index in common:
                errors["trailing_20ms"].append(trailing_prediction[index] - truth[index])
                errors["robust_jump_filter"].append(jump_prediction[index] - truth[index])
                errors["offline_quadratic"].append(float(offline_prediction[index] - truth[index]))
            change_points.append(jump.change_point_count)
            locklet_counts.append(len(jump.locklets))
        label = "jump_800hz" if jump_hz else "smooth_ramp"
        scenarios[label] = {
            "repetitions": repetitions,
            "common_scored_prediction_count": len(errors["trailing_20ms"]),
            "scoring": (
                "common method-available indices at t>=0.020s"
                if not jump_hz
                else "common method-available indices at t>=0.110s; 10ms transition excluded"
            ),
            "rmse_hz": {
                name: float(np.sqrt(np.mean(np.asarray(values) ** 2)))
                for name, values in errors.items()
            },
            "mean_change_point_count": float(np.mean(change_points)),
            "mean_locklet_count": float(np.mean(locklet_counts)),
        }
    return scenarios


def evaluate(
    windows: tuple[WindowRows, ...],
    summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = tuple(window for window in windows if window.raw_disjoint)
    key_time_s = {
        window.key(offset): float(window.absolute_time_s[offset])
        for window in selected
        for offset in range(len(window.absolute_time_s))
    }
    denominator = sum(int(np.count_nonzero(window.supported)) for window in selected)
    parts: dict[str, list[PredictionSeries]] = {
        "trailing_20ms": [],
        "trailing_50ms": [],
        "current_v2": [],
        "robust_jump_filter": [],
        "phase_gated_jump_filter": [],
        "block_60_40_holdout": [],
        "offline_block_smoother": [],
    }
    jump_results = []
    phase_jump_results = []
    degrees = []
    for window in selected:
        parts["trailing_20ms"].append(trailing_line_predictions(window, history_s=0.020))
        parts["trailing_50ms"].append(trailing_line_predictions(window, history_s=0.050))
        parts["current_v2"].append(v2_predictions(window))
        jump, result = jump_filter_predictions(window)
        parts["robust_jump_filter"].append(jump)
        jump_results.append(result)
        phase_jump, phase_result = jump_filter_predictions(window, phase_gated=True)
        parts["phase_gated_jump_filter"].append(phase_jump)
        phase_jump_results.append(phase_result)
        parts["block_60_40_holdout"].append(frozen_block_holdout(window))
        offline, degree = offline_block_smoother(window)
        parts["offline_block_smoother"].append(offline)
        if degree is not None:
            degrees.append(degree)
    series = {name: _merge_series(rows, name) for name, rows in parts.items()}
    statistics = {
        name: _series_statistics(value, key_time_s, denominator=denominator)
        for name, value in series.items()
    }
    statistics["current_v2"]["rate_bound_hit_count"] = sum(
        int(np.count_nonzero(np.abs(window.tracked_rate_hz_s) >= 14_999.0)) for window in selected
    )
    for name, results in (
        ("robust_jump_filter", jump_results),
        ("phase_gated_jump_filter", phase_jump_results),
    ):
        locklets = [locklet for result in results for locklet in result.locklets]
        durations = np.asarray(
            [locklet.end_s - locklet.start_s + 1.0 / FRAME_RATE_HZ for locklet in locklets]
        )
        statistics[name]["locklet_count"] = len(locklets)
        statistics[name]["median_locklet_duration_ms"] = (
            float(np.median(durations) * 1_000.0) if len(durations) else None
        )
        statistics[name]["maximum_locklet_duration_ms"] = (
            float(np.max(durations) * 1_000.0) if len(durations) else None
        )
        statistics[name]["reacquisition_count"] = sum(
            result.reacquisition_count for result in results
        )
        statistics[name]["change_point_count"] = sum(
            result.change_point_count for result in results
        )
    all_arcs = [
        (window, arc)
        for window in windows
        for arc in phase_arcs(window)
        if arc[1] - arc[0] + 1 >= PHASE_ARC_MINIMUM_FRAMES
    ]
    phase_arc_windows = {window.index for window, _ in all_arcs}
    phase_arc_durations = [(arc[1] - arc[0] + 1) / FRAME_RATE_HZ for _, arc in all_arcs]
    phase_arc_blocks = {int(math.floor(window.absolute_time_s[arc[0]])) for window, arc in all_arcs}
    qualified_times = sorted(
        float(row["center_time_s"]) for row in summary["exact_windows"] if row["qualified"]
    )
    qualified_interval_components = 0
    previous_qualified: float | None = None
    for time_s in qualified_times:
        if previous_qualified is None or time_s - previous_qualified >= 0.1:
            qualified_interval_components += 1
        previous_qualified = time_s
    comparisons = {
        "robust_jump_vs_current_v2": paired_block_bootstrap_improvement(
            series["robust_jump_filter"], series["current_v2"], key_time_s
        ),
        "robust_jump_vs_trailing_20ms": paired_block_bootstrap_improvement(
            series["robust_jump_filter"], series["trailing_20ms"], key_time_s
        ),
        "phase_jump_vs_current_v2": paired_block_bootstrap_improvement(
            series["phase_gated_jump_filter"], series["current_v2"], key_time_s
        ),
        "phase_jump_vs_trailing_20ms": paired_block_bootstrap_improvement(
            series["phase_gated_jump_filter"], series["trailing_20ms"], key_time_s
        ),
    }
    evidence = {
        "schema": "org.leo.research.d3-pilot-filter-prototypes/v1",
        "status": "retrospective_development_benchmark_not_satellite_identification",
        "session_id": summary["session_id"],
        "stream_id": summary["stream_id"],
        "receiver_id": summary["receiver_id"],
        "selection": summary["selection"],
        "corpus": {
            "seed_window_count": summary["window_count"],
            "raw_disjoint_planned_window_count": summary["raw_disjoint_window_count"],
            "raw_disjoint_windows_with_frames": len(selected),
            "raw_disjoint_supported_frame_count": denominator,
            "all_replay_frame_count": summary["frame_count"],
            "adjacent_overlapping_window_pairs": 287,
            "inference_unit": "one-second time block",
            "capture_continuity": "device-counter anchored; zero gaps/missing/overflow",
            "filter_initialization_scope": "independent restart in each 100ms seed window",
        },
        "fixed_configuration": {
            "trailing_histories_ms": [20.0, 50.0],
            "block_duration_ms": 15.0,
            "phase_arc_gate_rad": PHASE_ARC_GATE_RAD,
            "phase_arc_minimum_frames": PHASE_ARC_MINIMUM_FRAMES,
            "phase_arc_minimum_duration_ms": PHASE_ARC_MINIMUM_FRAMES / 0.75,
            "phase_arc_requires_no_reacquisition": True,
            "prototype_hyperparameters_were_not_cross_validated": True,
        },
        "models": statistics,
        "paired_one_second_block_bootstrap": comparisons,
        "phase_lock": {
            "current_v2_qualified_windows": summary["exact"]["qualified_count"],
            "current_v2_qualified_window_interval_component_count": (qualified_interval_components),
            "rolled_qin_qualified_windows": summary["rolled"]["qualified_count"],
            "rolled_qin_supported_frames": summary["rolled"]["supported_frames"],
            "explicit_no_reacquisition_phase_arc_count": len(all_arcs),
            "explicit_phase_arc_window_count": len(phase_arc_windows),
            "explicit_phase_arc_one_second_block_count": len(phase_arc_blocks),
            "explicit_phase_arc_total_duration_ms": float(sum(phase_arc_durations) * 1_000.0),
            "explicit_phase_arc_median_duration_ms": (
                float(np.median(phase_arc_durations) * 1_000.0) if phase_arc_durations else None
            ),
            "explicit_phase_arc_maximum_duration_ms": (
                float(np.max(phase_arc_durations) * 1_000.0) if phase_arc_durations else None
            ),
            "interpretation": (
                "local modulo-pi consistency only; no absolute carrier phase, code phase, "
                "pseudorange, or cross-window phase continuity"
            ),
        },
        "offline_model_degree_counts": {str(degree): degrees.count(degree) for degree in (1, 2, 3)},
        "synthetic_known_truth": synthetic_benchmark(),
        "limitations": [
            "D3 and its seed selection were already inspected; this is development evidence.",
            "Seed windows are strongest-GLRT-per-100ms and are source conditioned.",
            "Current replay exposes pre-update CFO residuals but not a valid pre-gate V2 covariance.",
            "The phase-gated jump filter reuses V2 phase-update evidence; it is a lifecycle wrapper, not an independent phase discriminator.",
            "Rolled Qin tests pilot specificity on the same selected RF windows, not universal false alarm.",
            "Offline smoother residuals use future data and are not compared as causal forecasts.",
            "All reported locklet durations are capped by independent 100ms window initialization.",
            "Moving-block intervals are descriptive because the source-conditioned time series remains serially dependent.",
            "Errors are innovations against a noisy extracted frame-CFO estimate; true CFO is unknown.",
            "Causal scores begin after a whole-capture-frozen GLRT seed/epoch/CFO selection, not an end-to-end online detector.",
            "Fifty-six planned raw-disjoint windows emitted no frame rows and are absent from prediction denominators.",
        ],
    }
    plotting = {
        "series": series,
        "key_time_s": key_time_s,
        "selected_windows": selected,
        "all_windows": windows,
        "phase_arcs": all_arcs,
        "v2_qualified_times_s": [
            float(row["center_time_s"]) for row in summary["exact_windows"] if row["qualified"]
        ],
    }
    return evidence, plotting


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _qin_confidence(
    exact: np.ndarray,
    control: np.ndarray,
    *,
    exact_scale: float | None = None,
    margin_scale: float | None = None,
) -> tuple[np.ndarray, float, float]:
    positive_margin = np.maximum(exact - control, 0.0)
    used_exact_scale = max(
        float(np.quantile(exact, 0.95)) if exact_scale is None else exact_scale,
        1e-12,
    )
    used_margin_scale = max(
        float(np.quantile(positive_margin, 0.95)) if margin_scale is None else margin_scale,
        1e-12,
    )
    confidence = np.sqrt(
        np.clip(exact / used_exact_scale, 0.0, 1.0)
        * np.clip(positive_margin / used_margin_scale, 0.0, 1.0)
    )
    return confidence, used_exact_scale, used_margin_scale


def _plot_causal_timeline(output: Path, plotting: dict[str, Any]) -> None:
    windows: tuple[WindowRows, ...] = plotting["selected_windows"]
    series: dict[str, PredictionSeries] = plotting["series"]
    key_time_s: dict[tuple[int, int], float] = plotting["key_time_s"]
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    time = np.concatenate([window.absolute_time_s for window in windows])
    cfo = np.concatenate([window.cfo_hz for window in windows]) / 1_000.0
    exact = np.concatenate([window.exact_coherence for window in windows])
    control = np.concatenate([window.control_coherence for window in windows])
    confidence, _, _ = _qin_confidence(exact, control)
    colors = np.zeros((len(time), 4))
    colors[:, :3] = (0.16, 0.46, 0.70)
    colors[:, 3] = 0.025 + 0.50 * confidence**1.25
    top.scatter(
        time,
        cfo,
        s=4,
        c=colors,
        linewidths=0,
        rasterized=True,
        label="frame CFO; opacity ∝ Qin confidence",
    )
    for name, color, width in (
        ("current_v2", "#d95f02", 0.8),
        ("trailing_20ms", "#1b9e77", 0.9),
        ("robust_jump_filter", "#6a3d9a", 0.9),
    ):
        selected = series[name]
        keys = sorted(selected.prediction_by_key, key=lambda key: key_time_s[key])
        top.scatter(
            [key_time_s[key] for key in keys][::4],
            [selected.prediction_by_key[key] / 1_000.0 for key in keys][::4],
            s=width * 5,
            alpha=0.55,
            color=color,
            linewidths=0,
            label=name.replace("_", " "),
            rasterized=True,
        )
    top.set_ylabel("Receiver-relative CFO (kHz)")
    top.set_title("D3 Radio1/RX1: raw-disjoint 100 ms windows, no TLE conditioning")
    top.set_xlim(0, 60)
    last_source_time = float(np.max(time))
    top.axvspan(last_source_time, 60.0, color="#eeeeee", alpha=0.65, linewidth=0)
    top.text(
        (last_source_time + 60.0) / 2.0,
        top.get_ylim()[0] + 0.04 * np.ptp(top.get_ylim()),
        "no extracted exact-pilot\nframe rows",
        color="#555555",
        ha="center",
        va="bottom",
        fontsize=9,
    )
    top.legend(loc="lower left", ncol=4, frameon=False)
    bins = np.arange(0, 61)
    for name, color in (
        ("current_v2", "#d95f02"),
        ("trailing_20ms", "#1b9e77"),
        ("robust_jump_filter", "#6a3d9a"),
    ):
        selected = series[name]
        centers = []
        medians = []
        p90 = []
        for left, right in zip(bins[:-1], bins[1:], strict=True):
            values = [
                abs(value)
                for key, value in selected.residual_by_key.items()
                if left <= key_time_s[key] < right
            ]
            if values:
                centers.append(left + 0.5)
                medians.append(float(np.median(values)))
                p90.append(float(np.quantile(values, 0.90)))
        bottom.plot(centers, medians, color=color, label=name.replace("_", " "))
        bottom.plot(centers, p90, color=color, alpha=0.35, linestyle="--")
    bottom.set_yscale("log")
    bottom.set_ylim(5, 3_000)
    bottom.set_ylabel("|Post-seed causal frame-CFO innovation| (Hz)")
    bottom.set_xlabel("Capture time (s)")
    bottom.axvspan(last_source_time, 60.0, color="#eeeeee", alpha=0.65, linewidth=0)
    bottom.legend(
        loc="upper left",
        ncol=3,
        frameon=False,
        title="solid = median; dashed = P90, 1 s bins",
    )
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_metrics(output: Path, evidence: dict[str, Any]) -> None:
    models = evidence["models"]
    comparisons = evidence["paired_one_second_block_bootstrap"]
    names = ["trailing_20ms", "current_v2", "robust_jump_filter", "phase_gated_jump_filter"]
    labels = ["20 ms line", "current V2", "robust jump", "phase-gated jump"]
    colors = ["#1b9e77", "#d95f02", "#6a3d9a", "#7570b3"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4))
    paired_labels = ["V2", "jump\n(same V2 frames)", "20 ms", "jump\n(same 20 ms frames)"]
    paired_values = [
        comparisons["robust_jump_vs_current_v2"]["baseline_block_equal_rms_hz"],
        comparisons["robust_jump_vs_current_v2"]["candidate_block_equal_rms_hz"],
        comparisons["robust_jump_vs_trailing_20ms"]["baseline_block_equal_rms_hz"],
        comparisons["robust_jump_vs_trailing_20ms"]["candidate_block_equal_rms_hz"],
    ]
    px = np.arange(len(paired_labels))
    axes[0].bar(px, paired_values, color=["#d95f02", "#6a3d9a", "#1b9e77", "#6a3d9a"])
    axes[0].set_xticks(px, paired_labels, rotation=18, ha="right")
    axes[0].set_ylabel("Block-equal frame-CFO innovation RMS (Hz)")
    axes[0].set_title("Matched-frame prediction error")
    for index, value in enumerate(paired_values):
        axes[0].text(index, value, f"{value:.1f}", ha="center", va="bottom", fontsize=8)
    x = np.arange(len(names))
    axes[1].bar(
        x,
        [100.0 * models[name]["prediction_coverage_fraction"] for name in names],
        color=colors,
    )
    axes[1].set_xticks(x, labels, rotation=20, ha="right")
    axes[1].set_ylabel("Supported frames predicted (%)")
    axes[1].set_ylim(0, 105)
    axes[1].set_title("Utilization")
    jump = models["robust_jump_filter"]
    observed = [
        jump["one_sigma_coverage"],
        jump["two_sigma_coverage"],
        jump["three_sigma_coverage"],
    ]
    target = [0.6827, 0.9545, 0.9973]
    width = 0.36
    sx = np.arange(3)
    axes[2].bar(sx - width / 2, observed, width, label="observed", color="#6a3d9a")
    axes[2].bar(sx + width / 2, target, width, label="Gaussian target", color="#bdbdbd")
    axes[2].set_xticks(sx, ["1σ", "2σ", "3σ"])
    axes[2].set_ylim(0, 1.05)
    axes[2].set_ylabel("Coverage fraction")
    axes[2].set_title("One-step normalized innovation coverage")
    axes[2].legend(frameon=False)
    for container in axes[2].containers:
        axes[2].bar_label(container, fmt="%.2f", fontsize=8)
    fig.suptitle("D3 post-seed causal comparison on fixed raw-disjoint windows")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_phase_and_synthetic(
    output: Path, evidence: dict[str, Any], plotting: dict[str, Any]
) -> None:
    arcs = plotting["phase_arcs"]
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(13, 7))
    arc_centers = [
        (window.absolute_time_s[start] + window.absolute_time_s[end]) / 2.0
        for window, (start, end) in arcs
    ]
    arc_durations_ms = [(end - start + 1) / FRAME_RATE_HZ * 1_000.0 for _, (start, end) in arcs]
    top.scatter(
        arc_centers,
        arc_durations_ms,
        s=36,
        color="#1b9e77",
        label="V2-derived contiguous arc duration",
    )
    qualified = plotting["v2_qualified_times_s"]
    top.scatter(
        qualified,
        np.zeros(len(qualified)),
        marker="v",
        s=55,
        color="#d95f02",
        label="V2 aggregate-qualified window",
    )
    top.set_xlim(0, 60)
    top.set_ylim(-5, max(50.0, max(arc_durations_ms, default=0.0) * 1.15))
    top.set_ylabel("No-reacquisition arc duration (ms)\n(V2 event markers at 0 ms)")
    top.set_xlabel("Capture time (s)")
    phase = evidence["phase_lock"]
    top.set_title(
        "Local modulo-π phase evidence from "
        f"{evidence['corpus']['seed_window_count']} overlapping initialized windows; "
        f"n={phase['explicit_no_reacquisition_phase_arc_count']}, "
        f"median/max={phase['explicit_phase_arc_median_duration_ms']:.1f}/"
        f"{phase['explicit_phase_arc_maximum_duration_ms']:.1f} ms"
    )
    top.legend(loc="upper right", frameon=False, ncol=2)
    synthetic = evidence["synthetic_known_truth"]
    labels = ["20 ms line", "robust jump", "offline quadratic"]
    keys = ["trailing_20ms", "robust_jump_filter", "offline_quadratic"]
    x = np.arange(len(keys))
    width = 0.36
    bottom.bar(
        x - width / 2,
        [synthetic["smooth_ramp"]["rmse_hz"][key] for key in keys],
        width,
        label="smooth ramp",
        color="#377eb8",
    )
    bottom.bar(
        x + width / 2,
        [synthetic["jump_800hz"]["rmse_hz"][key] for key in keys],
        width,
        label="800 Hz step; score t≥110 ms",
        color="#e41a1c",
    )
    bottom.set_xticks(x, labels)
    bottom.set_ylabel("Common-index known-truth RMSE (Hz)")
    bottom.set_yscale("log")
    bottom.set_title("Synthetic stress: common method-available indices; 10 ms after step excluded")
    bottom.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _plot_representative_window(output: Path, plotting: dict[str, Any]) -> None:
    windows: tuple[WindowRows, ...] = plotting["selected_windows"]
    series: dict[str, PredictionSeries] = plotting["series"]
    representative = max(
        windows,
        key=lambda window: (
            max((end - start + 1 for start, end in phase_arcs(window)), default=0),
            -window.index,
        ),
    )
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    relative_ms = (representative.absolute_time_s - representative.absolute_time_s[0]) * 1_000.0
    all_exact = np.concatenate([window.exact_coherence for window in windows])
    all_control = np.concatenate([window.control_coherence for window in windows])
    _, exact_scale, margin_scale = _qin_confidence(all_exact, all_control)
    confidence, _, _ = _qin_confidence(
        representative.exact_coherence,
        representative.control_coherence,
        exact_scale=exact_scale,
        margin_scale=margin_scale,
    )
    colors = np.zeros((len(representative.absolute_time_s), 4))
    colors[:, :3] = (0.16, 0.46, 0.70)
    colors[:, 3] = 0.025 + 0.75 * confidence**1.25
    top.scatter(
        relative_ms,
        representative.cfo_hz,
        s=18,
        c=colors,
        linewidths=0,
        label="frame CFO; opacity ∝ Qin confidence",
    )
    representative_arc = max(phase_arcs(representative), key=lambda arc: arc[1] - arc[0])
    arc_left_ms = relative_ms[representative_arc[0]]
    arc_right_ms = relative_ms[representative_arc[1]]
    for axis in (top, bottom):
        axis.axvspan(
            arc_left_ms,
            arc_right_ms,
            color="#1b9e77",
            alpha=0.10,
            linewidth=0,
            label="selected contiguous phase arc" if axis is top else None,
        )
    for name, color in (
        ("current_v2", "#d95f02"),
        ("trailing_20ms", "#1b9e77"),
        ("robust_jump_filter", "#6a3d9a"),
    ):
        selected = series[name]
        x = []
        y = []
        for offset in range(len(representative.frame_index)):
            key = representative.key(offset)
            if key in selected.prediction_by_key:
                x.append(relative_ms[offset])
                y.append(selected.prediction_by_key[key])
        top.plot(x, y, color=color, linewidth=1.5, label=name.replace("_", " "))
        residual_x = []
        residual_y = []
        for offset in range(len(representative.frame_index)):
            key = representative.key(offset)
            if key in selected.residual_by_key:
                residual_x.append(relative_ms[offset])
                residual_y.append(selected.residual_by_key[key])
        bottom.plot(
            residual_x, residual_y, color=color, linewidth=1.0, label=name.replace("_", " ")
        )
    top.set_ylabel("Receiver-relative CFO (Hz)")
    top.set_title(
        f"Rule-selected example: raw-disjoint window {representative.index}, "
        "longest V2-derived no-reacquisition arc"
    )
    top.legend(frameon=False, ncol=4)
    bottom.axhline(0.0, color="#444444", linewidth=0.8)
    bottom.set_ylabel("Frame CFO − causal prediction (Hz)")
    bottom.set_xlabel("Time from first frame (ms)")
    bottom.legend(frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):.{digits}f}"


def _write_report(path: Path, evidence: dict[str, Any], figures: dict[str, str]) -> None:
    models = evidence["models"]
    phase = evidence["phase_lock"]
    synthetic = evidence["synthetic_known_truth"]
    rows = []
    for label, key, mode in (
        ("Trailing robust line", "trailing_20ms", "post-seed causal, 20 ms"),
        ("Current PNT V2", "current_v2", "post-seed causal"),
        ("Robust jump filter", "robust_jump_filter", "post-seed causal"),
        ("Phase-gated jump filter", "phase_gated_jump_filter", "post-seed causal"),
        ("Frozen robust line", "block_60_40_holdout", "60/40 forward"),
        ("Robust polynomial smoother", "offline_block_smoother", "offline/full"),
    ):
        item = models[key]
        rows.append(
            f"| {label} | {mode} | {_fmt(item['count'], 0)} | "
            f"{_fmt(item['prediction_coverage_fraction'] * 100)}% | "
            f"{_fmt(item['rms_hz'])} | {_fmt(item['mae_hz'])} | "
            f"{_fmt(item['p95_abs_hz'])} |"
        )
    jump_vs_v2 = evidence["paired_one_second_block_bootstrap"]["robust_jump_vs_current_v2"]
    jump_vs_line = evidence["paired_one_second_block_bootstrap"]["robust_jump_vs_trailing_20ms"]
    seed_count = evidence["corpus"]["seed_window_count"]
    jump = models["robust_jump_filter"]
    text = f"""# D3 pilot-filter prototypes: robust CFO and explicit locklets

## Result

The robust jump filter reduces the largest D3 V2 frame-CFO innovation error, but it does **not** yet beat the simple 20 ms trailing robust line. On common frames grouped into one-second blocks, it improves RMS over current V2 by {100 * jump_vs_v2["fractional_rms_improvement"]:.1f}% (descriptive three-second moving-block resampling interval {100 * jump_vs_v2["descriptive_resampling_95_low"]:.1f}% to {100 * jump_vs_v2["descriptive_resampling_95_high"]:.1f}%). Against the 20 ms line it is {abs(100 * jump_vs_line["fractional_rms_improvement"]):.1f}% worse (descriptive interval {abs(100 * jump_vs_line["descriptive_resampling_95_high"]):.1f}% to {abs(100 * jump_vs_line["descriptive_resampling_95_low"]):.1f}% worse). These are innovations against the noisy extracted frame-CFO estimator; true CFO is unknown.

This is a retrospective development benchmark on source-conditioned D3 windows, not an independent scientific validation and not a satellite identification.

## Matched causal comparison

| Common prediction set | Baseline block-equal RMS | Jump-filter block-equal RMS | Common frames | One-second blocks |
|---|---:|---:|---:|---:|
| Current V2 vs jump | {_fmt(jump_vs_v2["baseline_block_equal_rms_hz"])} Hz | {_fmt(jump_vs_v2["candidate_block_equal_rms_hz"])} Hz | {_fmt(jump_vs_v2["common_frame_count"], 0)} | {_fmt(jump_vs_v2["block_count"], 0)} |
| 20 ms line vs jump | {_fmt(jump_vs_line["baseline_block_equal_rms_hz"])} Hz | {_fmt(jump_vs_line["candidate_block_equal_rms_hz"])} Hz | {_fmt(jump_vs_line["common_frame_count"], 0)} | {_fmt(jump_vs_line["block_count"], 0)} |

These are the headline comparisons because each pair is scored on exactly the same frames and gives equal weight to each occupied one-second block.

## Own-available-prediction statistics

| Model | Score type | Predictions | Utilization | RMS (Hz) | MAE (Hz) | P95 absolute error (Hz) |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

These marginal rows use each model's own available predictions and therefore must not be rank-compared when utilization differs. Every filter is initialized independently in each 100 ms seed window; this is not a continuous 60 s replay. “Causal” here starts after the strongest whole-capture-frozen GLRT seed, epoch, and CFO have already been selected; it is not an end-to-end online detector score. The fixed raw-disjoint subset has {evidence["corpus"]["raw_disjoint_windows_with_frames"]}/{evidence["corpus"]["raw_disjoint_planned_window_count"]} planned windows with emitted frame rows and {evidence["corpus"]["raw_disjoint_supported_frame_count"]:,} supported frames. Windows without frame rows are outside the utilization denominator. The 60/40 row freezes a robust line after the first 60 ms and scores the final 40 ms. The offline smoother uses future data and is an in-sample error floor/reference, not a forecast.

The jump filter's normalized one-step innovations are still underdispersed: observed 1σ/2σ/3σ coverage is {_fmt(jump["one_sigma_coverage"] * 100)}/{_fmt(jump["two_sigma_coverage"] * 100)}/{_fmt(jump["three_sigma_coverage"] * 100)}%, versus nominal Gaussian 68.3/95.5/99.7%. Its covariance remains too tight.

## Phase-lock evidence

- Current V2 qualifies {phase["current_v2_qualified_windows"]}/{seed_count} independently initialized 100 ms windows in {phase["current_v2_qualified_window_interval_component_count"]} disjoint interval components. This is a window-overlap count, not a physical-emitter count.
- The full matched rolled-Qin replay has {phase["rolled_qin_supported_frames"]} supported frames and {phase["rolled_qin_qualified_windows"]} qualified windows.
- A separate V2-derived contiguous-arc criterion finds {phase["explicit_no_reacquisition_phase_arc_count"]} local arcs in {phase["explicit_phase_arc_window_count"]} overlapping windows and {phase["explicit_phase_arc_one_second_block_count"]} one-second blocks. Total/median/max duration is {_fmt(phase["explicit_phase_arc_total_duration_ms"])}/{_fmt(phase["explicit_phase_arc_median_duration_ms"])}/{_fmt(phase["explicit_phase_arc_maximum_duration_ms"])} ms. It is not a nested replacement for V2 qualification, and the arcs are not independent physical locklets.
- These are modulo-pi locklets only. They do not establish absolute carrier phase, code phase, pseudorange, or continuity across windows.

## Synthetic known-truth stress test

| Scenario | 20 ms line RMSE | Robust jump RMSE | Offline quadratic RMSE | Mean change points |
|---|---:|---:|---:|---:|
| Smooth ramp | {_fmt(synthetic["smooth_ramp"]["rmse_hz"]["trailing_20ms"])} Hz | {_fmt(synthetic["smooth_ramp"]["rmse_hz"]["robust_jump_filter"])} Hz | {_fmt(synthetic["smooth_ramp"]["rmse_hz"]["offline_quadratic"])} Hz | {_fmt(synthetic["smooth_ramp"]["mean_change_point_count"], 2)} |
| +800 Hz step, t>=110 ms | {_fmt(synthetic["jump_800hz"]["rmse_hz"]["trailing_20ms"])} Hz | {_fmt(synthetic["jump_800hz"]["rmse_hz"]["robust_jump_filter"])} Hz | {_fmt(synthetic["jump_800hz"]["rmse_hz"]["offline_quadratic"])} Hz | {_fmt(synthetic["jump_800hz"]["mean_change_point_count"], 2)} |

All three synthetic methods are scored on their common method-available indices; the stepped case deliberately excludes the first 10 ms after the change. The offline quadratic is a full-window fit, not causal prediction. The state machine keeps one locklet on the smooth ramp and detects one change point on the stepped signal. This is consistent with covariance/measurement mismatch being important on D3, but it does not rule out lifecycle or model errors on real data.

## Figures

![Causal timeline]({figures["timeline"]})

![Metrics and calibration]({figures["metrics"]})

![Phase arcs and synthetic stress]({figures["phase_synthetic"]})

![Representative before/after window]({figures["representative"]})

## What to change next

1. Keep the 20 ms trailing robust line as the reference causal benchmark for untouched-dwell validation; a new filter must beat it before promotion.
2. Feed the jump filter independent block observations with empirically calibrated covariance, not correlated per-frame measurements with nominally tiny errors.
3. Make the phase discriminator produce an explicit raw modulo-pi observation and covariance. The present lifecycle wrapper reuses V2 phase-update decisions, so it is not an independent phase filter.
4. Promote a lock only after a minimum contiguous no-reacquisition arc; terminate it at a confirmed change point or coast expiry.
5. Validate the frozen configuration on D4 and later dwells with whole-second/block resampling, full rolled-Qin controls, and even-Qin training/odd-Qin scoring.
6. Keep TLE matching downstream. Over a 20–100 ms locklet, orbit-time delay is almost perfectly absorbed by free CFO/rate nuisance.

## Provenance and limitations

- Source schema: `{evidence["schema"]}`.
- Seed selection: `{evidence["selection"]}`.
- Inference unit: one-second time block; 287/598 adjacent seed pairs overlap.
- Capture IQ continuity is device-counter anchored with zero recorded gaps, missing samples, or overflows.
- Hyperparameters were fixed for this prototype but not nested-cross-validated.
- Three-second circular moving-block intervals are descriptive, not calibrated confidence intervals.
- All {seed_count} rolled-Qin windows were replayed; zero support is evidence of pilot specificity on these selected RF windows, not a universal false-alarm rate.
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    summary = json.loads(arguments.source_summary.read_text(encoding="utf-8"))
    windows = _load_windows(arguments.source_npz)
    evidence, plotting = evaluate(windows, summary)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    _style()
    figure_paths = {
        "timeline": arguments.output_root / "01-d3-causal-filter-timeline.png",
        "metrics": arguments.output_root / "02-d3-filter-metrics-and-calibration.png",
        "phase_synthetic": arguments.output_root / "03-phase-locklets-and-synthetic.png",
        "representative": arguments.output_root / "04-representative-before-after.png",
    }
    _plot_causal_timeline(figure_paths["timeline"], plotting)
    _plot_metrics(figure_paths["metrics"], evidence)
    _plot_phase_and_synthetic(figure_paths["phase_synthetic"], evidence, plotting)
    _plot_representative_window(figure_paths["representative"], plotting)
    archived_seed = arguments.source_npz.parent / "radio1-rx1-phase-lock-100ms-scan.json"
    replay_script = arguments.source_npz.parent / "extract-d3-filter-benchmark.py"
    archived_seed_sha = _sha256(archived_seed)
    if archived_seed_sha != summary["source_sha256"]:
        raise ValueError("archived phase-lock seed evidence digest does not match replay summary")
    evidence["source"] = {
        "npz_path": str(arguments.source_npz),
        "npz_sha256": _sha256(arguments.source_npz),
        "summary_path": str(arguments.source_summary),
        "summary_sha256": _sha256(arguments.source_summary),
        "archived_seed_path": str(archived_seed),
        "archived_seed_sha256": archived_seed_sha,
        "replay_script_path": str(replay_script),
        "replay_script_sha256": _sha256(replay_script),
        "pnt_source_sha256": summary["pnt_source_sha256"],
        "recording_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "capture_release_sha": CAPTURE_RELEASE_SHA,
    }
    evidence["figures"] = {
        key: {"path": str(path), "sha256": _sha256(path)} for key, path in figure_paths.items()
    }
    evidence_path = arguments.output_root / "d3-pilot-filter-prototype-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    relative_figures = {
        key: str(path.relative_to(arguments.report.parent)) for key, path in figure_paths.items()
    }
    _write_report(arguments.report, evidence, relative_figures)
    print(
        json.dumps(
            {
                "evidence": str(evidence_path),
                "report": str(arguments.report),
                "models": evidence["models"],
                "phase_lock": evidence["phase_lock"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
