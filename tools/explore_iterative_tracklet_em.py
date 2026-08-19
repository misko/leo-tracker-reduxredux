#!/usr/bin/env python3
"""Fit 1-second CFO tracklets, merge them, then refine with hard EM.

This offline diagnostic compares pure GLRT-64 and pure current Symbolwise.  It
uses nearest-neighbour endpoint state only to propose merges; every accepted
merge must survive a robust combined quadratic fit.  A final classification-EM
loop assigns observations either to one fitted curve or to clutter and refits
until stable.  It is candidate generation, not a production tracker.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DEFAULT_INPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv"
)
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-"
    "iterative-tracklet-em.png"
)


@dataclass(frozen=True, slots=True)
class MethodConfig:
    key: str
    label: str
    high_gate: float
    low_gate: float
    local_residual_gate_hz: float
    minimum_local_points: int
    minimum_high_points: int
    maximum_merge_gap_s: float
    endpoint_gate_hz: float
    endpoint_growth_hz_per_s: float
    maximum_slope_difference_hz_per_s: float
    final_residual_gate_hz: float


@dataclass(frozen=True, slots=True)
class MergeEvent:
    iteration: int
    left_start_s: float
    left_end_s: float
    right_start_s: float
    right_end_s: float
    gap_s: float
    endpoint_residual_hz: float
    combined_rms_hz: float


@dataclass(frozen=True, slots=True)
class MethodResult:
    config: MethodConfig
    candidates: tuple
    scores: np.ndarray
    seeds: tuple
    tracks: tuple
    merge_events: tuple[MergeEvent, ...]
    em_iterations: int


def _module(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _fit(indexes: np.ndarray, candidates: tuple, degree: int):
    times = np.asarray([candidates[int(index)].time_s for index in indexes])
    frequency = np.asarray([candidates[int(index)].refined_cfo_hz for index in indexes])
    t0 = float(np.mean(times))
    coefficients = np.polyfit(times - t0, frequency, min(degree, len(indexes) - 1))
    residual = frequency - np.polyval(coefficients, times - t0)
    return t0, coefficients, float(np.sqrt(np.mean(residual**2)))


def _predict(model, time_s: np.ndarray | float):
    t0, coefficients, _ = model
    return np.polyval(coefficients, np.asarray(time_s) - t0)


def _local_seed(
    indexes: np.ndarray,
    candidates: tuple,
    high: np.ndarray,
    config: MethodConfig,
):
    if len(indexes) < config.minimum_local_points:
        return None
    times = np.asarray([candidate.time_s for candidate in candidates])
    frequency = np.asarray([candidate.refined_cfo_hz for candidate in candidates])
    best: tuple[tuple[int, int, float], np.ndarray] | None = None
    for left_position in range(len(indexes)):
        for right_position in range(left_position + 1, len(indexes)):
            left, right = int(indexes[left_position]), int(indexes[right_position])
            if times[right] - times[left] < 0.15:
                continue
            slope = (frequency[right] - frequency[left]) / (times[right] - times[left])
            prediction = frequency[left] + slope * (times[indexes] - times[left])
            inliers = indexes[
                np.abs(frequency[indexes] - prediction) <= config.local_residual_gate_hz
            ]
            high_count = int(np.count_nonzero(high[inliers]))
            if (
                len(inliers) < config.minimum_local_points
                or high_count < config.minimum_high_points
            ):
                continue
            rms = _fit(inliers, candidates, 1)[2]
            key = (len(inliers), high_count, -rms)
            if best is None or key > best[0]:
                best = key, inliers
    if best is None:
        return None
    inliers = best[1]
    for _ in range(3):
        model = _fit(inliers, candidates, 1)
        prediction = _predict(model, times[indexes])
        refined = indexes[
            np.abs(frequency[indexes] - prediction) <= config.local_residual_gate_hz
        ]
        if (
            len(refined) < config.minimum_local_points
            or np.count_nonzero(high[refined]) < config.minimum_high_points
        ):
            break
        inliers = refined
    return np.asarray(sorted(int(index) for index in inliers), dtype=int)


def _initial_seeds(candidates: tuple, scores: np.ndarray, config: MethodConfig):
    times = np.asarray([candidate.time_s for candidate in candidates])
    low = scores >= config.low_gate
    high = scores >= config.high_gate
    duration = int(np.ceil(float(times.max())))
    seeds = []
    for window_start in range(duration):
        indexes = np.flatnonzero(
            (times >= window_start) & (times < window_start + 1.0) & low
        )
        seed = _local_seed(indexes, candidates, high, config)
        if seed is not None:
            seeds.append(seed)
    return tuple(seeds)


def _slope(model) -> float:
    coefficients = model[1]
    return float(coefficients[0]) if len(coefficients) == 2 else 0.0


def _merge_groups(candidates: tuple, groups: list[np.ndarray], config: MethodConfig):
    times = np.asarray([candidate.time_s for candidate in candidates])
    events: list[MergeEvent] = []
    while True:
        best = None
        for left_index, left in enumerate(groups):
            left_model = _fit(left, candidates, 1)
            for right_index, right in enumerate(groups):
                if times[right].min() <= times[left].max():
                    continue
                gap = float(times[right].min() - times[left].max())
                if gap > config.maximum_merge_gap_s:
                    continue
                right_model = _fit(right, candidates, 1)
                slope_difference = abs(_slope(left_model) - _slope(right_model))
                if slope_difference > config.maximum_slope_difference_hz_per_s:
                    continue
                right_start = float(times[right].min())
                endpoint_residual = abs(
                    float(_predict(left_model, right_start) - _predict(right_model, right_start))
                )
                endpoint_gate = (
                    config.endpoint_gate_hz + config.endpoint_growth_hz_per_s * gap
                )
                if endpoint_residual > endpoint_gate:
                    continue
                combined = np.unique(np.concatenate((left, right)))
                combined_rms = _fit(combined, candidates, 2)[2]
                if combined_rms > config.final_residual_gate_hz:
                    continue
                cost = (
                    endpoint_residual / endpoint_gate
                    + combined_rms / config.final_residual_gate_hz
                    + gap / config.maximum_merge_gap_s
                )
                if best is None or cost < best[0]:
                    best = (
                        cost,
                        left_index,
                        right_index,
                        combined,
                        gap,
                        endpoint_residual,
                        combined_rms,
                    )
        if best is None:
            break
        _, left_index, right_index, combined, gap, endpoint_residual, combined_rms = best
        left, right = groups[left_index], groups[right_index]
        events.append(
            MergeEvent(
                iteration=len(events) + 1,
                left_start_s=float(times[left].min()),
                left_end_s=float(times[left].max()),
                right_start_s=float(times[right].min()),
                right_end_s=float(times[right].max()),
                gap_s=gap,
                endpoint_residual_hz=endpoint_residual,
                combined_rms_hz=combined_rms,
            )
        )
        groups[left_index] = combined
        del groups[right_index]
    return groups, tuple(events)


def _hard_em(
    candidates: tuple,
    scores: np.ndarray,
    groups: list[np.ndarray],
    config: MethodConfig,
    *,
    maximum_iterations: int = 12,
):
    """Classification EM: assign to one curve or clutter, then refit."""

    times = np.asarray([candidate.time_s for candidate in candidates])
    frequency = np.asarray([candidate.refined_cfo_hz for candidate in candidates])
    eligible = scores >= config.low_gate
    previous = None
    for iteration in range(1, maximum_iterations + 1):
        models = [_fit(group, candidates, 2) for group in groups]
        assignments: list[list[int]] = [[] for _ in groups]
        for index in np.flatnonzero(eligible):
            options = []
            for track_index, (group, model) in enumerate(zip(groups, models, strict=True)):
                start, end = float(times[group].min()), float(times[group].max())
                if times[index] < start - 0.35 or times[index] > end + 0.35:
                    continue
                residual = abs(float(frequency[index] - _predict(model, times[index])))
                if residual <= config.final_residual_gate_hz:
                    options.append((residual, track_index))
            if options:
                assignments[min(options)[1]].append(int(index))
        updated = [
            np.asarray(indexes, dtype=int)
            for indexes in assignments
            if len(indexes) >= config.minimum_local_points
        ]
        state = tuple(tuple(int(index) for index in group) for group in updated)
        groups = updated
        if state == previous:
            return groups, iteration
        previous = state
    return groups, maximum_iterations


def _method_result(tracker, family, rows, config: MethodConfig):
    spec = next(spec for spec in family.METHODS if spec.key == config.key)
    candidates = family._candidates(tracker, rows, spec)
    scores = np.asarray([candidate.glrt64_margin for candidate in candidates])
    seeds = _initial_seeds(candidates, scores, config)
    merged, events = _merge_groups(candidates, list(seeds), config)
    # Isolated one-second seeds remain visible but are not promoted to final curves.
    merged = [
        group
        for group in merged
        if candidates[int(group[-1])].time_s - candidates[int(group[0])].time_s >= 1.5
    ]
    refined, em_iterations = _hard_em(candidates, scores, merged, config)
    tracks = tuple(
        tracker._fit_track(  # noqa: SLF001 - shared exploratory tracker primitive
            track_id,
            group,
            candidates,
            model_kind="one-second-tracklet-agglomeration-hard-em",
            degree=2,
        )
        for track_id, group in enumerate(
            sorted(refined, key=lambda group: candidates[int(group[0])].time_s), start=1
        )
    )
    seed_tracks = tuple(
        tracker._fit_track(  # noqa: SLF001 - shared exploratory tracker primitive
            track_id,
            seed,
            candidates,
            model_kind="one-second-local-linear-seed",
            degree=1,
        )
        for track_id, seed in enumerate(seeds, start=1)
    )
    return MethodResult(config, candidates, scores, seed_tracks, tracks, events, em_iterations)


def _configs(symbolwise_scores: np.ndarray):
    negative = np.abs(symbolwise_scores[symbolwise_scores < 0])
    symbolwise_high = float(np.median(negative) / 0.6744897501960817 * 5.0)
    return (
        MethodConfig(
            "glrt64",
            "Pure GLRT-64 residual-refined CFO",
            0.18,
            0.18,
            2_500.0,
            5,
            5,
            1.10,
            4_000.0,
            3_000.0,
            20_000.0,
            2_500.0,
        ),
        MethodConfig(
            "symbolwise",
            "Pure current Symbolwise acquired CFO",
            symbolwise_high,
            0.0,
            8_000.0,
            6,
            2,
            1.00,
            12_000.0,
            5_000.0,
            30_000.0,
            8_000.0,
        ),
    )


def _render(output: Path, results: tuple[MethodResult, ...]):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "run with: uv run --with 'matplotlib>=3.10,<4' python "
            "tools/explore_iterative_tracklet_em.py"
        ) from error
    figure, axes = plt.subplots(2, 1, figsize=(16, 11), sharex=True, constrained_layout=True)
    colors = ("#d1495b", "#0077b6", "#f77f00", "#6a4c93", "#2a9d8f")
    for axis, result in zip(axes, results, strict=True):
        times = np.asarray([candidate.time_s for candidate in result.candidates])
        frequency = np.asarray(
            [candidate.refined_cfo_hz for candidate in result.candidates]
        ) / 1_000
        axis.scatter(times, frequency, s=5, color="#b8b8b8", alpha=0.11)
        for seed in result.seeds:
            grid = np.linspace(seed.start_s, seed.end_s, 20)
            axis.plot(grid, seed.predict(grid) / 1_000, color="#4c78a8", alpha=0.32, lw=1)
        for track in result.tracks:
            indexes = np.asarray(track.candidate_indexes, dtype=int)
            color = colors[(track.track_id - 1) % len(colors)]
            axis.scatter(
                times[indexes],
                frequency[indexes],
                c=result.scores[indexes],
                cmap="viridis",
                s=13,
                alpha=0.78,
            )
            grid = np.linspace(track.start_s, track.end_s, 300)
            axis.plot(grid, track.predict(grid) / 1_000, color=color, lw=2.5)
            axis.text(
                track.start_s,
                float(track.predict(track.start_s)) / 1_000,
                f" T{track.track_id}",
                color=color,
                fontsize=9,
                va="bottom",
            )
        axis.set_title(
            f"{result.config.label} · {len(result.seeds)} local seeds · "
            f"{len(result.merge_events)} merges · {result.em_iterations} EM iterations",
            loc="left",
            fontweight="bold",
        )
        axis.set_ylabel("Tracking CFO (kHz)")
        axis.grid(alpha=0.2)
    axes[-1].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        "Iterative 1-second tracklet merge + hard-EM refinement · candidate-only",
        fontweight="bold",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    tracker = _module("iterative_tracklet_tracker", "explore_glrt64_tracks.py")
    family = _module("iterative_tracklet_family", "explore_all_pilot_method_tracks.py")
    with args.input.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    symbolwise_spec = next(spec for spec in family.METHODS if spec.key == "symbolwise")
    symbolwise = family._candidates(tracker, rows, symbolwise_spec)
    configs = _configs(np.asarray([candidate.glrt64_margin for candidate in symbolwise]))
    results = tuple(_method_result(tracker, family, rows, config) for config in configs)
    _render(args.output, results)
    document = {
        "input": str(args.input.resolve()),
        "input_sha256": _sha256(args.input),
        "png": str(args.output.resolve()),
        "png_sha256": _sha256(args.output),
        "production_calibrated": False,
        "one_candidate_per_timestamp_limitation": True,
        "algorithm": "one-second-local-ransac-nearest-endpoint-merge-hard-em-v1",
        "results": [
            {
                "method": result.config.key,
                "config": asdict(result.config),
                "local_seeds": [asdict(seed) for seed in result.seeds],
                "merge_events": [asdict(event) for event in result.merge_events],
                "em_iterations": result.em_iterations,
                "tracks": [asdict(track) for track in result.tracks],
            }
            for result in results
        ],
    }
    metadata = args.output.with_suffix(".json")
    metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "png": str(args.output.resolve()),
                "metadata": str(metadata.resolve()),
                "tracks": {result.config.key: len(result.tracks) for result in results},
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
