#!/usr/bin/env python3
"""Compare pure GLRT, pure Symbolwise, and fused CFO segmentation.

This is an offline candidate-generation diagnostic.  GLRT-64 uses its own
exact-minus-control margin and residual-refined CFO.  Current Symbolwise uses
only its own verification margin and acquired CFO, with high-confidence seeds
grown through positive-margin points inside a robust CFO corridor.  The third
panel intentionally shows GLRT-seeded Symbolwise geometry as method fusion.
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
    "glrt-symbolwise-segmentation.png"
)


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    key: str
    label: str
    frequency_label: str
    candidates: tuple
    scores: np.ndarray
    selected: np.ndarray
    tracks: tuple


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


def _negative_side_sigma(scores: np.ndarray) -> float:
    negative = np.abs(scores[scores < 0])
    if not negative.size:
        raise ValueError("a negative Symbolwise margin tail is required")
    return float(np.median(negative) / 0.6744897501960817)


def _contiguous(indexes: np.ndarray, candidates: tuple, maximum_gap_s: float):
    if not len(indexes):
        return ()
    ordered = indexes[np.argsort([candidates[int(index)].time_s for index in indexes])]
    groups: list[list[int]] = [[int(ordered[0])]]
    for index in ordered[1:]:
        if (
            candidates[int(index)].time_s - candidates[groups[-1][-1]].time_s
            > maximum_gap_s
        ):
            groups.append([])
        groups[-1].append(int(index))
    return tuple(np.asarray(group, dtype=int) for group in groups)


def _symbolwise_seed_and_grow(tracker, candidates: tuple, scores: np.ndarray):
    """Grow robust five-sigma Symbolwise seeds through positive-margin IQ."""

    high_gate = 5.0 * _negative_side_sigma(scores)
    seeds = tracker.robust_quadratic_tracks(
        candidates,
        scores >= high_gate,
        residual_gate_hz=8_000.0,
        maximum_gap_s=1.0,
        minimum_points=8,
        iterations=5_000,
        maximum_tracks=16,
    )
    groups: list[np.ndarray] = []
    claimed: set[int] = set()
    for seed in seeds:
        seed_indexes = set(seed.candidate_indexes)
        prediction = seed.predict(
            np.asarray([candidate.time_s for candidate in candidates], dtype=float)
        )
        times = np.asarray([candidate.time_s for candidate in candidates], dtype=float)
        frequency = np.asarray(
            [candidate.refined_cfo_hz for candidate in candidates], dtype=float
        )
        eligible = np.flatnonzero(
            (scores >= 0.0)
            & (times >= seed.start_s - 1.0)
            & (times <= seed.end_s + 1.0)
            & (np.abs(frequency - prediction) <= 8_000.0)
        )
        components = _contiguous(eligible, candidates, maximum_gap_s=0.35)
        matching = [
            component
            for component in components
            if seed_indexes.intersection(int(index) for index in component)
        ]
        if not matching:
            continue
        group = max(matching, key=len)
        unclaimed = np.asarray(
            [int(index) for index in group if int(index) not in claimed], dtype=int
        )
        if len(unclaimed) < 8:
            continue
        groups.append(unclaimed)
        claimed.update(int(index) for index in unclaimed)
    groups.sort(key=lambda group: candidates[int(group[0])].time_s)
    tracks = tuple(
        tracker._fit_track(  # noqa: SLF001 - shared exploratory tracker primitive
            track_id,
            group,
            candidates,
            model_kind="symbolwise-five-sigma-seed-positive-corridor",
            degree=2,
        )
        for track_id, group in enumerate(groups, start=1)
    )
    selected = np.zeros(len(candidates), dtype=bool)
    for track in tracks:
        selected[np.asarray(track.candidate_indexes, dtype=int)] = True
    return high_gate, selected, tracks


def _results(tracker, family, rows: tuple[dict[str, str], ...]):
    glrt_spec = next(spec for spec in family.METHODS if spec.key == "glrt64")
    symbolwise_spec = next(spec for spec in family.METHODS if spec.key == "symbolwise")
    glrt = family._candidates(tracker, rows, glrt_spec)
    symbolwise = family._candidates(tracker, rows, symbolwise_spec)
    glrt_scores = np.asarray([candidate.glrt64_margin for candidate in glrt])
    symbolwise_scores = np.asarray([candidate.glrt64_margin for candidate in symbolwise])
    glrt_selection = glrt_scores >= 0.18
    glrt_tracks = tracker.robust_quadratic_tracks(
        glrt,
        glrt_selection,
        residual_gate_hz=2_500.0,
        maximum_gap_s=0.60,
        minimum_points=8,
        iterations=5_000,
        maximum_tracks=16,
    )
    symbolwise_gate, symbolwise_selection, symbolwise_tracks = _symbolwise_seed_and_grow(
        tracker, symbolwise, symbolwise_scores
    )
    fused_tracks = tracker.robust_quadratic_tracks(
        symbolwise,
        glrt_selection,
        residual_gate_hz=8_000.0,
        maximum_gap_s=0.60,
        minimum_points=8,
        iterations=5_000,
        maximum_tracks=16,
    )
    fused_selection = np.zeros(len(symbolwise), dtype=bool)
    for track in fused_tracks:
        fused_selection[np.asarray(track.candidate_indexes, dtype=int)] = True
    return (
        SegmentationResult(
            "glrt64",
            "Pure GLRT-64 · margin ≥ 0.18 · refined CFO · robust ±2.5 kHz",
            "GLRT-64 refined CFO (kHz)",
            glrt,
            glrt_scores,
            glrt_selection,
            glrt_tracks,
        ),
        SegmentationResult(
            "symbolwise",
            f"Pure Symbolwise · 5σ seeds ≥ {symbolwise_gate:.4f} · positive-margin grow",
            "Symbolwise acquired CFO (kHz)",
            symbolwise,
            symbolwise_scores,
            symbolwise_selection,
            symbolwise_tracks,
        ),
        SegmentationResult(
            "fused",
            "Fusion reference · GLRT-64 seeds · Symbolwise CFO · robust ±8 kHz",
            "Symbolwise acquired CFO (kHz)",
            symbolwise,
            glrt_scores,
            fused_selection,
            fused_tracks,
        ),
    )


def _render(output: Path, results: tuple[SegmentationResult, ...]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "run with: uv run --with 'matplotlib>=3.10,<4' python "
            "tools/compare_glrt_symbolwise_segmentation.py"
        ) from error
    figure, axes = plt.subplots(3, 1, figsize=(16, 13), sharex=True, constrained_layout=True)
    colors = ("#d1495b", "#0077b6", "#f77f00", "#6a4c93", "#2a9d8f", "#bc6c25")
    for axis, result in zip(axes, results, strict=True):
        times = np.asarray([candidate.time_s for candidate in result.candidates])
        frequency = np.asarray(
            [candidate.refined_cfo_hz for candidate in result.candidates]
        ) / 1_000
        axis.scatter(times, frequency, s=5, color="#aaaaaa", alpha=0.12)
        axis.scatter(
            times[result.selected],
            frequency[result.selected],
            c=result.scores[result.selected],
            s=12,
            cmap="viridis",
            alpha=0.75,
        )
        for track in result.tracks:
            grid = np.linspace(track.start_s, track.end_s, 200)
            color = colors[(track.track_id - 1) % len(colors)]
            axis.plot(grid, track.predict(grid) / 1_000, color=color, linewidth=2)
            axis.text(
                track.start_s,
                float(track.predict(track.start_s)) / 1_000,
                f" T{track.track_id}",
                color=color,
                fontsize=8,
                va="bottom",
            )
        axis.set_title(result.label, loc="left", fontweight="bold")
        axis.set_ylabel(result.frequency_label)
        axis.grid(alpha=0.2)
    axes[-1].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        "GLRT-64 versus current Symbolwise segmentation · candidate-only",
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
    tracker = _module("glrt_symbolwise_tracker", "explore_glrt64_tracks.py")
    family = _module("glrt_symbolwise_family", "explore_all_pilot_method_tracks.py")
    with args.input.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    results = _results(tracker, family, rows)
    _render(args.output, results)
    document = {
        "input": str(args.input.resolve()),
        "input_sha256": _sha256(args.input),
        "png": str(args.output.resolve()),
        "png_sha256": _sha256(args.output),
        "production_calibrated": False,
        "one_candidate_per_timestamp_limitation": True,
        "results": [
            {
                "key": result.key,
                "label": result.label,
                "selected_count": int(np.count_nonzero(result.selected)),
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
                "tracks": {result.key: len(result.tracks) for result in results},
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
