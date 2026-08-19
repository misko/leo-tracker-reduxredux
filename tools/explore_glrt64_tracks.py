#!/usr/bin/env python3
"""Explore conservative CFO track linkers on the GLRT-64 probe output.

This is an offline diagnostic, not a Standard-pipeline tracker.  It consumes
the comparison CSV, filters on a configurable exact-minus-control GLRT-64
margin, and compares three deterministic linking strategies:

* local continuity graph components;
* predictive nearest-track assignment with bounded gaps; and
* iterative robust quadratic extraction with contiguous inlier support; and
* endpoint-predicted stitching of conservative tracklets across longer gaps.

The current input retains one acquisition winner per timestamp.  It can test
branch linking and outlier rejection, but not simultaneous multi-target data
association.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DEFAULT_INPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv"
)
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-glrt64-tracks.png"
)


@dataclass(frozen=True, slots=True)
class Candidate:
    index: int
    time_s: float
    acquired_cfo_hz: float
    residual_cfo_hz: float
    refined_cfo_hz: float
    glrt64_score: float
    glrt64_control_score: float
    glrt64_margin: float
    qam_accuracy: float | None


@dataclass(frozen=True, slots=True)
class Track:
    track_id: int
    candidate_indexes: tuple[int, ...]
    start_s: float
    end_s: float
    duration_s: float
    point_count: int
    median_margin: float
    rms_residual_hz: float
    model_kind: str
    model_t0_s: float
    model_coefficients_hz: tuple[float, ...]

    def predict(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(self.model_coefficients_hz, np.asarray(time_s) - self.model_t0_s)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-margin", type=float, default=0.20)
    return parser.parse_args()


def _load(path: Path) -> tuple[Candidate, ...]:
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    candidates = []
    for row in rows:
        required = (
            row["acquired_cfo_hz"],
            row["glrt64_residual_cfo_hz"],
            row["glrt64_score"],
            row["glrt64_control_score"],
            row["glrt64_margin"],
        )
        if not all(required):
            continue
        acquired = float(row["acquired_cfo_hz"])
        residual = float(row["glrt64_residual_cfo_hz"])
        candidates.append(
            Candidate(
                index=int(row["index"]),
                time_s=float(row["time_s"]),
                acquired_cfo_hz=acquired,
                residual_cfo_hz=residual,
                refined_cfo_hz=acquired + residual,
                glrt64_score=float(row["glrt64_score"]),
                glrt64_control_score=float(row["glrt64_control_score"]),
                glrt64_margin=float(row["glrt64_margin"]),
                qam_accuracy=float(row["qam_accuracy"]) if row["qam_accuracy"] else None,
            )
        )
    if not candidates:
        raise ValueError("input contains no complete GLRT-64 candidates")
    if any(
        left.time_s >= right.time_s for left, right in zip(candidates, candidates[1:], strict=False)
    ):
        raise ValueError("GLRT-64 candidates must have strictly increasing timestamps")
    return tuple(candidates)


def _fit_track(
    track_id: int,
    indexes: np.ndarray,
    candidates: tuple[Candidate, ...],
    *,
    model_kind: str,
    degree: int,
) -> Track:
    selected = [candidates[int(index)] for index in indexes]
    times = np.asarray([item.time_s for item in selected])
    frequency = np.asarray([item.refined_cfo_hz for item in selected])
    t0 = float(np.mean(times))
    actual_degree = min(degree, len(selected) - 1)
    coefficients = np.polyfit(times - t0, frequency, actual_degree)
    residual = frequency - np.polyval(coefficients, times - t0)
    return Track(
        track_id=track_id,
        candidate_indexes=tuple(int(index) for index in indexes),
        start_s=float(times.min()),
        end_s=float(times.max()),
        duration_s=float(times.max() - times.min()),
        point_count=len(selected),
        median_margin=float(np.median([item.glrt64_margin for item in selected])),
        rms_residual_hz=float(np.sqrt(np.mean(residual**2))),
        model_kind=model_kind,
        model_t0_s=t0,
        model_coefficients_hz=tuple(float(value) for value in coefficients),
    )


def _renumber(
    groups: list[np.ndarray],
    candidates: tuple[Candidate, ...],
    *,
    model_kind: str,
    degree: int,
    minimum_points: int,
) -> tuple[Track, ...]:
    retained = [group for group in groups if len(group) >= minimum_points]
    retained.sort(
        key=lambda group: (
            candidates[int(group[0])].time_s,
            candidates[int(group[0])].refined_cfo_hz,
        )
    )
    return tuple(
        _fit_track(index + 1, group, candidates, model_kind=model_kind, degree=degree)
        for index, group in enumerate(retained)
    )


def continuity_tracks(
    candidates: tuple[Candidate, ...],
    selected: np.ndarray,
    *,
    maximum_gap_s: float = 0.15,
    base_frequency_gate_hz: float = 2_000.0,
    maximum_slope_hz_per_s: float = 25_000.0,
    minimum_points: int = 5,
) -> tuple[Track, ...]:
    """Connected components under explicit local time/frequency gates."""

    chosen = np.flatnonzero(selected)
    if not chosen.size:
        return ()
    parent = {int(index): int(index) for index in chosen}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for position, right in enumerate(chosen):
        right_candidate = candidates[int(right)]
        for left in chosen[:position][::-1]:
            left_candidate = candidates[int(left)]
            gap = right_candidate.time_s - left_candidate.time_s
            if gap > maximum_gap_s:
                break
            gate = base_frequency_gate_hz + maximum_slope_hz_per_s * gap
            if abs(right_candidate.refined_cfo_hz - left_candidate.refined_cfo_hz) <= gate:
                union(int(left), int(right))
    components: dict[int, list[int]] = {}
    for index in chosen:
        components.setdefault(find(int(index)), []).append(int(index))
    return _renumber(
        [np.asarray(group, dtype=int) for group in components.values()],
        candidates,
        model_kind="continuity-linear-summary",
        degree=1,
        minimum_points=minimum_points,
    )


@dataclass(slots=True)
class _ActiveTrack:
    indexes: list[int]

    def prediction(self, candidates: tuple[Candidate, ...], time_s: float) -> float:
        recent = self.indexes[-min(8, len(self.indexes)) :]
        if len(recent) < 2:
            return candidates[recent[-1]].refined_cfo_hz
        times = np.asarray([candidates[index].time_s for index in recent])
        frequency = np.asarray([candidates[index].refined_cfo_hz for index in recent])
        slope, intercept = np.polyfit(times, frequency, 1)
        return float(slope * time_s + intercept)


def predictive_tracks(
    candidates: tuple[Candidate, ...],
    selected: np.ndarray,
    *,
    maximum_gap_s: float = 0.30,
    base_prediction_gate_hz: float = 4_000.0,
    gate_growth_hz_per_s: float = 20_000.0,
    minimum_points: int = 5,
) -> tuple[Track, ...]:
    """Greedy constant-velocity association with births and bounded misses."""

    active: list[_ActiveTrack] = []
    completed: list[np.ndarray] = []
    for index in np.flatnonzero(selected):
        candidate = candidates[int(index)]
        still_active = []
        for track in active:
            gap = candidate.time_s - candidates[track.indexes[-1]].time_s
            if gap <= maximum_gap_s:
                still_active.append(track)
            else:
                completed.append(np.asarray(track.indexes, dtype=int))
        active = still_active
        options: list[tuple[float, _ActiveTrack]] = []
        for track in active:
            gap = candidate.time_s - candidates[track.indexes[-1]].time_s
            residual = abs(
                candidate.refined_cfo_hz - track.prediction(candidates, candidate.time_s)
            )
            gate = base_prediction_gate_hz + gate_growth_hz_per_s * gap
            if residual <= gate:
                options.append((residual / gate, track))
        if options:
            min(options, key=lambda item: item[0])[1].indexes.append(int(index))
        else:
            active.append(_ActiveTrack([int(index)]))
    completed.extend(np.asarray(track.indexes, dtype=int) for track in active)
    return _renumber(
        completed,
        candidates,
        model_kind="predictive-quadratic-summary",
        degree=2,
        minimum_points=minimum_points,
    )


def _endpoint_line(
    indexes: tuple[int, ...] | list[int],
    candidates: tuple[Candidate, ...],
    *,
    from_end: bool,
    point_count: int = 8,
) -> tuple[float, float]:
    selected = indexes[-point_count:] if from_end else indexes[:point_count]
    times = np.asarray([candidates[index].time_s for index in selected])
    frequency = np.asarray([candidates[index].refined_cfo_hz for index in selected])
    if len(selected) < 2:
        return 0.0, float(frequency[0])
    slope, intercept = np.polyfit(times, frequency, 1)
    return float(slope), float(intercept)


def stitched_predictive_tracks(
    candidates: tuple[Candidate, ...],
    selected: np.ndarray,
    *,
    maximum_stitch_gap_s: float = 3.0,
    base_frequency_gate_hz: float = 3_000.0,
    gate_growth_hz_per_s: float = 2_000.0,
    maximum_slope_difference_hz_per_s: float = 10_000.0,
    minimum_points: int = 5,
) -> tuple[Track, ...]:
    """Stitch local predictive tracklets when endpoint forecasts agree."""

    groups = [list(track.candidate_indexes) for track in predictive_tracks(candidates, selected)]
    while True:
        best: tuple[float, int, int] | None = None
        for left_index, left in enumerate(groups):
            left_end = candidates[left[-1]].time_s
            left_slope, left_intercept = _endpoint_line(left, candidates, from_end=True)
            for right_index, right in enumerate(groups):
                if right_index == left_index:
                    continue
                right_start = candidates[right[0]].time_s
                gap = right_start - left_end
                if gap <= 0 or gap > maximum_stitch_gap_s:
                    continue
                right_slope, _ = _endpoint_line(right, candidates, from_end=False)
                if abs(left_slope - right_slope) > maximum_slope_difference_hz_per_s:
                    continue
                prediction = left_slope * right_start + left_intercept
                residual = abs(candidates[right[0]].refined_cfo_hz - prediction)
                gate = base_frequency_gate_hz + gate_growth_hz_per_s * gap
                if residual > gate:
                    continue
                cost = residual / gate + abs(left_slope - right_slope) / (
                    maximum_slope_difference_hz_per_s * 2
                )
                if best is None or cost < best[0]:
                    best = (cost, left_index, right_index)
        if best is None:
            break
        _, left_index, right_index = best
        groups[left_index].extend(groups[right_index])
        del groups[right_index]
    return _renumber(
        [np.asarray(group, dtype=int) for group in groups],
        candidates,
        model_kind="stitched-predictive-quadratic-summary",
        degree=2,
        minimum_points=minimum_points,
    )


def _contiguous_subsets(
    indexes: np.ndarray,
    candidates: tuple[Candidate, ...],
    maximum_gap_s: float,
) -> tuple[np.ndarray, ...]:
    if not indexes.size:
        return ()
    ordered = indexes[np.argsort([candidates[int(index)].time_s for index in indexes])]
    splits = [0]
    for position in range(1, len(ordered)):
        if (
            candidates[int(ordered[position])].time_s
            - candidates[int(ordered[position - 1])].time_s
            > maximum_gap_s
        ):
            splits.append(position)
    splits.append(len(ordered))
    return tuple(ordered[left:right] for left, right in zip(splits, splits[1:], strict=False))


def robust_quadratic_tracks(
    candidates: tuple[Candidate, ...],
    selected: np.ndarray,
    *,
    residual_gate_hz: float = 2_500.0,
    maximum_gap_s: float = 0.20,
    minimum_points: int = 8,
    iterations: int = 2_000,
    maximum_tracks: int = 12,
    seed: int = 20_260_819,
) -> tuple[Track, ...]:
    """Iteratively extract robust curves, retaining only contiguous support."""

    rng = np.random.default_rng(seed)
    remaining = np.flatnonzero(selected)
    groups: list[np.ndarray] = []
    while len(remaining) >= minimum_points and len(groups) < maximum_tracks:
        best: np.ndarray | None = None
        best_score = (-1, -math.inf)
        for _ in range(iterations):
            sample = rng.choice(remaining, size=3, replace=False)
            sample_times = np.asarray([candidates[int(index)].time_s for index in sample])
            if float(np.ptp(sample_times)) < 0.5:
                continue
            t0 = float(np.mean(sample_times))
            sample_frequency = np.asarray(
                [candidates[int(index)].refined_cfo_hz for index in sample]
            )
            coefficients = np.polyfit(sample_times - t0, sample_frequency, 2)
            # Reject implausibly agile curves before they can collect noise.
            acceleration_hz_per_s2 = abs(2 * coefficients[0])
            if acceleration_hz_per_s2 > 50_000:
                continue
            times = np.asarray([candidates[int(index)].time_s for index in remaining])
            frequency = np.asarray([candidates[int(index)].refined_cfo_hz for index in remaining])
            slope = 2 * coefficients[0] * (times - t0) + coefficients[1]
            residual = abs(frequency - np.polyval(coefficients, times - t0))
            inliers = remaining[(residual <= residual_gate_hz) & (abs(slope) <= 100_000)]
            for subset in _contiguous_subsets(inliers, candidates, maximum_gap_s):
                if len(subset) < minimum_points:
                    continue
                score = (
                    len(subset),
                    sum(candidates[int(index)].glrt64_margin for index in subset),
                )
                if score > best_score:
                    best_score = score
                    best = subset
        if best is None:
            break
        groups.append(best)
        remove = set(int(index) for index in best)
        remaining = np.asarray([index for index in remaining if int(index) not in remove])
    return _renumber(
        groups,
        candidates,
        model_kind="robust-contiguous-quadratic",
        degree=2,
        minimum_points=minimum_points,
    )


def _assignment(tracks: tuple[Track, ...]) -> dict[int, int]:
    return {
        candidate_index: track.track_id
        for track in tracks
        for candidate_index in track.candidate_indexes
    }


def _render_panel(axis, candidates, selected, tracks, title):
    time = np.asarray([item.time_s for item in candidates])
    frequency = np.asarray([item.refined_cfo_hz for item in candidates]) / 1_000
    margin = np.asarray([item.glrt64_margin for item in candidates])
    axis.scatter(time[~selected], frequency[~selected], s=5, color="#aaaaaa", alpha=0.12)
    axis.scatter(
        time[selected],
        frequency[selected],
        c=margin[selected],
        s=9,
        cmap="viridis",
        vmin=0.2,
        vmax=max(0.8, float(np.max(margin[selected]))),
        alpha=0.65,
    )
    colors = ("#d1495b", "#0077b6", "#f77f00", "#6a4c93", "#2a9d8f", "#bc6c25")
    for track in tracks:
        grid = np.linspace(track.start_s, track.end_s, 250)
        axis.plot(
            grid,
            track.predict(grid) / 1_000,
            color=colors[(track.track_id - 1) % len(colors)],
            linewidth=1.7,
        )
        axis.text(
            track.start_s,
            float(track.predict(track.start_s)) / 1_000,
            f" T{track.track_id}",
            color=colors[(track.track_id - 1) % len(colors)],
            fontsize=8,
            va="bottom",
        )
    axis.set_title(title, loc="left", fontweight="bold")
    axis.set_ylabel("GLRT-64 refined CFO (kHz)")
    axis.grid(alpha=0.2)


def _render(
    output: Path,
    candidates: tuple[Candidate, ...],
    selected: np.ndarray,
    approaches: tuple[tuple[str, tuple[Track, ...]], ...],
    minimum_margin: float,
) -> tuple[Path, ...]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "run with: uv run --with 'matplotlib>=3.10,<4' python tools/explore_glrt64_tracks.py"
        ) from error

    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(
        len(approaches),
        1,
        figsize=(16, 4 * len(approaches)),
        sharex=True,
        constrained_layout=True,
    )
    individual_paths = []
    for axis, (name, tracks) in zip(axes, approaches, strict=True):
        title = {
            "continuity": "A. Local continuity graph",
            "predictive": "B. Predictive nearest-track association",
            "robust_quadratic": "C. Iterative robust contiguous quadratics",
            "stitched_predictive": "D. Predictive tracklets with endpoint stitching",
        }[name]
        _render_panel(axis, candidates, selected, tracks, title)
        individual = output.with_name(f"{output.stem}-{name}.png")
        single, single_axis = plt.subplots(figsize=(16, 4.5), constrained_layout=True)
        _render_panel(single_axis, candidates, selected, tracks, title)
        single_axis.set_xlabel("Elapsed recording time (s)")
        single.savefig(individual, dpi=160, metadata={"Software": "leo-tracker"})
        plt.close(single)
        individual_paths.append(individual)
    axes[-1].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        f"GLRT-64 candidate-track experiments · margin ≥ {minimum_margin:.2f} · candidate-only",
        fontweight="bold",
    )
    figure.savefig(output, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)
    return tuple(individual_paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    if not math.isfinite(args.minimum_margin):
        raise ValueError("minimum margin must be finite")
    candidates = _load(args.input)
    selected = np.asarray(
        [item.glrt64_margin >= args.minimum_margin for item in candidates], dtype=bool
    )
    approaches = (
        ("continuity", continuity_tracks(candidates, selected)),
        ("predictive", predictive_tracks(candidates, selected)),
        ("robust_quadratic", robust_quadratic_tracks(candidates, selected)),
        ("stitched_predictive", stitched_predictive_tracks(candidates, selected)),
    )
    plots = _render(
        args.output,
        candidates,
        selected,
        approaches,
        args.minimum_margin,
    )
    document = {
        "input": str(args.input.resolve()),
        "input_sha256": _sha256(args.input),
        "candidate_count": len(candidates),
        "selected_count": int(np.count_nonzero(selected)),
        "minimum_glrt64_margin": args.minimum_margin,
        "one_candidate_per_timestamp_limitation": True,
        "production_calibrated": False,
        "approaches": {name: [asdict(track) for track in tracks] for name, tracks in approaches},
        "plots": [
            {"path": str(path.resolve()), "sha256": _sha256(path)} for path in (args.output, *plots)
        ],
    }
    metadata = args.output.with_suffix(".json")
    metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, tracks in approaches:
        print(
            f"{name}: {len(tracks)} retained tracks; "
            + ", ".join(
                f"T{track.track_id}={track.start_s:.2f}-{track.end_s:.2f}s/"
                f"{track.point_count} points/{track.rms_residual_hz:.0f}Hz rms"
                for track in tracks
            )
        )
    print(json.dumps({"png": str(args.output.resolve()), "metadata": str(metadata.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
