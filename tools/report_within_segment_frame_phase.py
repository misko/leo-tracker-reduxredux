#!/usr/bin/env python3
# ruff: noqa: E501
"""Analyze actual Starlink-frame phase correlations inside frozen CFO segments.

The 20 ms dense-GLRT probe is only an independently acquired container.  The
scientific observations in this report are the approximately 1/750-second
Starlink frames recovered inside each container.  Correlations never cross a
probe boundary because each probe has an independently selected CFO and epoch.
No quadratic or cubic CFO trajectory is fitted.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.frame_phase import (
    circular_concentration,
    estimate_frame_phase_states,
    fit_heldout_constant_phase_increment,
    wrapped_cycle_difference,
)
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260822T143020-c4482829e26c"
STREAM_ID = "stream-0"
RECEIVER_ID = 1
SCOPE_ID = "sha256:424ec0775d22b40bd7f84ab693a65c412f5675c2c1aba6a4e3e89bf9342ba9ba"
PROBE_SECONDS = 0.020
SYMBOLS = np.arange(2, 66)
RNG_SEED = 20260822
BLOCK_SECONDS = 0.30
MAX_LAG_FRAMES = 12
PERMUTATIONS = 300


@dataclass(frozen=True, slots=True)
class Segment:
    label: str
    start_s: float
    end_s: float
    reference_s: float
    rate_hz_s: float
    cfo_at_reference_hz: float

    def frequency_hz(self, time_s: float | np.ndarray) -> np.ndarray:
        times = np.asarray(time_s, dtype=float)
        return self.cfo_at_reference_hz + self.rate_hz_s * (times - self.reference_s)


SEGMENTS = (
    Segment("P1", 20.250, 26.925, 20.250, -6_188.325399204048, -157_618.43809679453),
    Segment("P2", 26.950, 33.300, 26.950, -6_113.603385019892, -201_944.48215763876),
    Segment("P4", 40.625, 47.050, 40.625, -6_055.816602137965, -194_835.66819964952),
    Segment("P5", 47.125, 49.425, 47.125, -6_291.359764216548, -236_282.73828298785),
)


@dataclass(frozen=True, slots=True)
class Candidate:
    sample_start: int
    time_s: float
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class FrameRecord:
    segment: str
    probe_sample_start: int
    probe_time_s: float
    frame_index: int
    frame_midpoint_sample: int
    frame_midpoint_time_s: float
    phase_cycles: float
    coherence: float
    median_absolute_residual_cycles: float
    control_phase_cycles: float
    control_coherence: float
    control_median_absolute_residual_cycles: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_within_segment_frame_phase/candidates"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_within_segment_frame_phase"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_22_within_segment_frame_phase.md"),
    )
    return parser.parse_args()


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _load_candidates(path: Path) -> tuple[Candidate, ...]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            rows.append(
                Candidate(
                    sample_start=int(item["sample_start"]),
                    time_s=float(item["time_s"]),
                    rank=int(item["rank"]),
                    local_epoch_sample=int(item["local_epoch_sample"]),
                    tracking_cfo_hz=float(item["tracking_cfo_hz"]),
                    exact_score=float(item["exact_score"]),
                    control_score=float(item["control_score"]),
                    margin=float(item["margin"]),
                )
            )
    return tuple(sorted(rows, key=lambda item: (item.sample_start, item.rank)))


def _select_candidates(
    segment: Segment,
    candidates: tuple[Candidate, ...],
    *,
    maximum_line_error_hz: float = 2_500.0,
    minimum_margin: float = 0.05,
) -> tuple[Candidate, ...]:
    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.sample_start, []).append(candidate)
    selected = []
    for rows in grouped.values():
        time_s = rows[0].time_s
        expected = float(segment.frequency_hz(time_s))
        candidate = min(
            rows,
            key=lambda item: (
                abs(item.tracking_cfo_hz - expected),
                -item.margin,
                item.rank,
            ),
        )
        if (
            abs(candidate.tracking_cfo_hz - expected) <= maximum_line_error_hz
            and candidate.margin >= minimum_margin
        ):
            selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: item.sample_start))


def _extract_frames(reader, segment: Segment, candidates: tuple[Candidate, ...]):
    probe_samples = round(PROBE_SECONDS * reader.sample_rate_hz)
    by_second: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_second.setdefault(int(candidate.time_s), []).append(candidate)
    records: list[FrameRecord] = []
    probe_rows = []
    frame_period_samples = reader.sample_rate_hz / FRAME_RATE_HZ
    for second in sorted(by_second):
        second_candidates = by_second[second]
        outer_start = min(item.sample_start for item in second_candidates)
        outer_stop = max(item.sample_start for item in second_candidates) + probe_samples
        outer = _complex_receiver(
            reader.read(
                outer_start,
                outer_stop - outer_start,
                receiver_ids=(RECEIVER_ID,),
            )
        )
        for candidate in second_candidates:
            local_start = candidate.sample_start - outer_start
            values = np.ascontiguousarray(outer[local_start : local_start + probe_samples])
            workspace = _conditioned_correlation_workspace(
                values,
                reader.sample_rate_hz,
                candidate.local_epoch_sample,
                candidate.tracking_cfo_hz,
                edge=StarlinkEdge.LOWER,
                selected_symbols=SYMBOLS,
            )
            exact = workspace.select(SYMBOLS)
            control = workspace.select(SYMBOLS, control=True)
            states = estimate_frame_phase_states(
                exact.values,
                control.values,
                exact.normalized_power,
                control.normalized_power,
                exact.times_s,
            )
            retained = 0
            for state in states:
                global_time_s = candidate.time_s + state.midpoint_s
                if not segment.start_s <= global_time_s <= segment.end_s:
                    continue
                midpoint_sample = candidate.sample_start + round(
                    state.midpoint_s * reader.sample_rate_hz
                )
                records.append(
                    FrameRecord(
                        segment=segment.label,
                        probe_sample_start=candidate.sample_start,
                        probe_time_s=candidate.time_s,
                        frame_index=state.frame_index,
                        frame_midpoint_sample=midpoint_sample,
                        frame_midpoint_time_s=global_time_s,
                        phase_cycles=state.phase_cycles,
                        coherence=state.coherence,
                        median_absolute_residual_cycles=state.median_absolute_residual_cycles,
                        control_phase_cycles=state.control_phase_cycles,
                        control_coherence=state.control_coherence,
                        control_median_absolute_residual_cycles=state.control_median_absolute_residual_cycles,
                    )
                )
                retained += 1
            probe_rows.append(
                {
                    "sample_start": candidate.sample_start,
                    "time_s": candidate.time_s,
                    "tracking_cfo_hz": candidate.tracking_cfo_hz,
                    "line_error_hz": candidate.tracking_cfo_hz
                    - float(segment.frequency_hz(candidate.time_s)),
                    "margin": candidate.margin,
                    "epoch_modulo_frame_samples": float(
                        (candidate.sample_start + candidate.local_epoch_sample)
                        % frame_period_samples
                    ),
                    "frame_count": retained,
                }
            )
    return tuple(records), probe_rows


def _group_records(records: tuple[FrameRecord, ...]) -> tuple[tuple[FrameRecord, ...], ...]:
    grouped: dict[int, list[FrameRecord]] = {}
    for record in records:
        grouped.setdefault(record.probe_sample_start, []).append(record)
    return tuple(
        tuple(sorted(rows, key=lambda item: item.frame_index))
        for _, rows in sorted(grouped.items())
    )


def _lag_curve(
    groups: tuple[tuple[FrameRecord, ...], ...],
    *,
    control: bool = False,
    max_lag: int = MAX_LAG_FRAMES,
) -> tuple[np.ndarray, np.ndarray]:
    concentrations = []
    counts = []
    attribute = "control_phase_cycles" if control else "phase_cycles"
    for lag in range(1, max_lag + 1):
        per_group = []
        pair_count = 0
        for group in groups:
            phases = np.asarray([getattr(item, attribute) for item in group])
            if len(phases) > lag:
                differences = wrapped_cycle_difference(phases[lag:], phases[:-lag])
                per_group.append(circular_concentration(differences))
                pair_count += len(differences)
        concentrations.append(float(np.mean(per_group)) if per_group else 0.0)
        counts.append(pair_count)
    return np.asarray(concentrations), np.asarray(counts)


def _lag_null(
    groups: tuple[tuple[FrameRecord, ...], ...],
    *,
    repetitions: int = PERMUTATIONS,
    seed: int = RNG_SEED,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    phase_groups = tuple(np.asarray([item.phase_cycles for item in group]) for group in groups)
    null = np.zeros((repetitions, MAX_LAG_FRAMES), dtype=float)
    for repetition in range(repetitions):
        shuffled = tuple(rng.permutation(values) for values in phase_groups)
        for lag in range(1, MAX_LAG_FRAMES + 1):
            per_group = [
                circular_concentration(wrapped_cycle_difference(values[lag:], values[:-lag]))
                for values in shuffled
                if len(values) > lag
            ]
            null[repetition, lag - 1] = float(np.mean(per_group)) if per_group else 0.0
    return null


def _heldout_rows(groups: tuple[tuple[FrameRecord, ...], ...]) -> list[dict[str, float]]:
    rows = []
    for group in groups:
        if len(group) < 4:
            continue
        indexes = np.asarray([item.frame_index for item in group])
        exact = fit_heldout_constant_phase_increment([item.phase_cycles for item in group], indexes)
        control = fit_heldout_constant_phase_increment(
            [item.control_phase_cycles for item in group], indexes
        )
        rows.append(
            {
                "time_s": group[0].probe_time_s,
                "exact_error_cycles": float(np.median(exact.heldout_errors_cycles)),
                "control_error_cycles": float(np.median(control.heldout_errors_cycles)),
                "increment_cycles_per_frame": exact.increment_cycles_per_frame,
                "training_concentration": exact.training_concentration,
            }
        )
    return rows


def _block_rows(
    segment: Segment,
    records: tuple[FrameRecord, ...],
    *,
    block_seconds: float = BLOCK_SECONDS,
) -> list[dict[str, float]]:
    result = []
    start = segment.start_s
    while start < segment.end_s:
        stop = min(start + block_seconds, segment.end_s)
        selected = tuple(item for item in records if start <= item.probe_time_s < stop)
        groups = _group_records(selected)
        if len(groups) >= 5:
            exact_lag, _ = _lag_curve(groups, max_lag=1)
            control_lag, _ = _lag_curve(groups, control=True, max_lag=1)
            heldout = _heldout_rows(groups)
            result.append(
                {
                    "start_s": start,
                    "stop_s": stop,
                    "midpoint_s": 0.5 * (start + stop),
                    "probe_count": len(groups),
                    "frame_count": len(selected),
                    "lag1_exact": float(exact_lag[0]),
                    "lag1_control": float(control_lag[0]),
                    "heldout_exact_error_cycles": float(
                        np.median([item["exact_error_cycles"] for item in heldout])
                    ),
                    "heldout_control_error_cycles": float(
                        np.median([item["control_error_cycles"] for item in heldout])
                    ),
                }
            )
        start = stop
    return result


def _block_max_null(
    segment: Segment,
    records: tuple[FrameRecord, ...],
    *,
    repetitions: int = PERMUTATIONS,
    seed: int = RNG_SEED,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    groups = _group_records(records)
    indexed_groups: dict[int, list[np.ndarray]] = {}
    for group in groups:
        block_index = int((group[0].probe_time_s - segment.start_s) // BLOCK_SECONDS)
        indexed_groups.setdefault(block_index, []).append(
            np.asarray([item.phase_cycles for item in group])
        )
    indexed_groups = {index: values for index, values in indexed_groups.items() if len(values) >= 5}
    null = np.zeros(repetitions, dtype=float)
    for repetition in range(repetitions):
        block_values = []
        for phase_groups in indexed_groups.values():
            per_group = []
            for phases in phase_groups:
                shuffled = rng.permutation(phases)
                if len(shuffled) > 1:
                    per_group.append(
                        circular_concentration(
                            wrapped_cycle_difference(shuffled[1:], shuffled[:-1])
                        )
                    )
            block_values.append(float(np.mean(per_group)) if per_group else 0.0)
        null[repetition] = max(block_values, default=0.0)
    return null


def _third_rows(segment: Segment, records: tuple[FrameRecord, ...]) -> list[dict[str, Any]]:
    edges = np.linspace(segment.start_s, segment.end_s, 4)
    result = []
    for index, label in enumerate(("early", "middle", "late")):
        selected = tuple(
            item for item in records if edges[index] <= item.probe_time_s < edges[index + 1]
        )
        groups = _group_records(selected)
        lag, _ = _lag_curve(groups, max_lag=1)
        control_lag, _ = _lag_curve(groups, control=True, max_lag=1)
        heldout = _heldout_rows(groups)
        result.append(
            {
                "part": label,
                "start_s": float(edges[index]),
                "stop_s": float(edges[index + 1]),
                "probe_count": len(groups),
                "frame_count": len(selected),
                "lag1_exact": float(lag[0]),
                "lag1_control": float(control_lag[0]),
                "heldout_exact_error_cycles": float(
                    np.median([item["exact_error_cycles"] for item in heldout])
                ),
                "heldout_control_error_cycles": float(
                    np.median([item["control_error_cycles"] for item in heldout])
                ),
            }
        )
    return result


def _segment_metrics(
    segment: Segment,
    records: tuple[FrameRecord, ...],
    probes: list[dict[str, Any]],
    candidate_probe_count: int,
) -> dict[str, Any]:
    groups = _group_records(records)
    exact_lag, lag_counts = _lag_curve(groups)
    control_lag, _ = _lag_curve(groups, control=True)
    lag_null = _lag_null(groups, seed=RNG_SEED + int(segment.label[1:]))
    heldout = _heldout_rows(groups)
    blocks = _block_rows(segment, records)
    block_null = _block_max_null(
        segment,
        records,
        seed=RNG_SEED + 100 + int(segment.label[1:]),
    )
    best_block = max(blocks, key=lambda item: item["lag1_exact"])
    return {
        "label": segment.label,
        "interval_s": [segment.start_s, segment.end_s],
        "duration_s": segment.end_s - segment.start_s,
        "rate_hz_s": segment.rate_hz_s,
        "candidate_probe_count": candidate_probe_count,
        "selected_probe_count": len(groups),
        "selected_probe_fraction": len(groups) / max(candidate_probe_count, 1),
        "actual_frame_count": len(records),
        "actual_frame_duration_ms": 1_000.0 / FRAME_RATE_HZ,
        "within_frame": {
            "exact_median_residual_cycles": float(
                np.median([item.median_absolute_residual_cycles for item in records])
            ),
            "control_median_residual_cycles": float(
                np.median([item.control_median_absolute_residual_cycles for item in records])
            ),
            "exact_median_coherence": float(np.median([item.coherence for item in records])),
            "control_median_coherence": float(
                np.median([item.control_coherence for item in records])
            ),
        },
        "lag": {
            "lag_frames": list(range(1, MAX_LAG_FRAMES + 1)),
            "pair_count": lag_counts.tolist(),
            "exact_concentration": exact_lag.tolist(),
            "control_concentration": control_lag.tolist(),
            "permutation_p95": np.percentile(lag_null, 95, axis=0).tolist(),
            "lag1_permutation_p": float(
                (1 + np.count_nonzero(lag_null[:, 0] >= exact_lag[0])) / (len(lag_null) + 1)
            ),
            "lag1_four_segment_bonferroni_p": float(
                min(
                    1.0,
                    len(SEGMENTS)
                    * (1 + np.count_nonzero(lag_null[:, 0] >= exact_lag[0]))
                    / (len(lag_null) + 1),
                )
            ),
        },
        "heldout": {
            "probe_count": len(heldout),
            "exact_median_error_cycles": float(
                np.median([item["exact_error_cycles"] for item in heldout])
            ),
            "control_median_error_cycles": float(
                np.median([item["control_error_cycles"] for item in heldout])
            ),
            "exact_probe_fraction_le_0_10": float(
                np.mean([item["exact_error_cycles"] <= 0.10 for item in heldout])
            ),
        },
        "thirds": _third_rows(segment, records),
        "blocks": blocks,
        "best_block": {
            **best_block,
            "max_lag1_look_elsewhere_p": float(
                (1 + np.count_nonzero(block_null >= best_block["lag1_exact"]))
                / (len(block_null) + 1)
            ),
            "max_lag1_four_segment_bonferroni_p": float(
                min(
                    1.0,
                    len(SEGMENTS)
                    * (1 + np.count_nonzero(block_null >= best_block["lag1_exact"]))
                    / (len(block_null) + 1),
                )
            ),
            "permutation_repetitions": len(block_null),
        },
        "probes": probes,
        "heldout_probes": heldout,
    }


def _synthetic_metrics() -> dict[str, Any]:
    rng = np.random.default_rng(RNG_SEED)
    indexes = np.arange(15)
    continuous = []
    resets = []
    continuous_errors = []
    reset_errors = []
    for _ in range(256):
        phase0 = rng.uniform(-0.5, 0.5)
        increment = rng.uniform(-0.45, 0.45)
        values = wrapped_cycle_difference(
            phase0 + increment * indexes + rng.normal(0.0, 0.02, len(indexes)),
            0.0,
        )
        random_values = rng.uniform(-0.5, 0.5, len(indexes))
        continuous.append(circular_concentration(wrapped_cycle_difference(values[1:], values[:-1])))
        resets.append(
            circular_concentration(wrapped_cycle_difference(random_values[1:], random_values[:-1]))
        )
        continuous_errors.extend(
            fit_heldout_constant_phase_increment(values, indexes).heldout_errors_cycles
        )
        reset_errors.extend(
            fit_heldout_constant_phase_increment(random_values, indexes).heldout_errors_cycles
        )
    return {
        "frame_count_per_probe": len(indexes),
        "probe_count": 256,
        "continuous_lag1_concentration": float(np.mean(continuous)),
        "random_reset_lag1_concentration": float(np.mean(resets)),
        "continuous_heldout_median_error_cycles": float(np.median(continuous_errors)),
        "random_reset_heldout_median_error_cycles": float(np.median(reset_errors)),
    }


def _plot_overview(metrics: list[dict[str, Any]], path: Path) -> None:
    labels = [item["label"] for item in metrics]
    x = np.arange(len(labels))
    figure, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    width = 0.34
    axes[0].bar(
        x - width / 2,
        [item["within_frame"]["exact_median_coherence"] for item in metrics],
        width,
        color="#4C78A8",
        label="exact pilot",
    )
    axes[0].bar(
        x + width / 2,
        [item["within_frame"]["control_median_coherence"] for item in metrics],
        width,
        color="#BAB0AC",
        label="rolled control",
    )
    axes[0].set_title("A · phase is measurable inside many frames", loc="left")
    axes[0].set_ylabel("median within-frame coherence")
    axes[0].legend(fontsize=8)
    axes[1].bar(
        x - width / 2,
        [item["lag"]["exact_concentration"][0] for item in metrics],
        width,
        color="#59A14F",
        label="exact lag-1",
    )
    axes[1].bar(
        x + width / 2,
        [item["lag"]["control_concentration"][0] for item in metrics],
        width,
        color="#BAB0AC",
        label="rolled control",
    )
    axes[1].scatter(
        x,
        [item["lag"]["permutation_p95"][0] for item in metrics],
        marker="_",
        s=160,
        linewidth=2,
        color="#E15759",
        label="permuted 95%",
    )
    axes[1].set_title("B · adjacent actual-frame phase correlation", loc="left")
    axes[1].set_ylabel("lag-1 phase-difference concentration R")
    axes[1].legend(fontsize=8)
    axes[2].bar(
        x - width / 2,
        [item["heldout"]["exact_median_error_cycles"] for item in metrics],
        width,
        color="#F28E2B",
        label="exact pilot",
    )
    axes[2].bar(
        x + width / 2,
        [item["heldout"]["control_median_error_cycles"] for item in metrics],
        width,
        color="#BAB0AC",
        label="rolled control",
    )
    axes[2].axhline(0.10, color="#111111", linestyle="--", linewidth=0.8, label="0.10 gate")
    axes[2].axhline(0.25, color="#888888", linestyle=":", linewidth=0.8, label="random median")
    axes[2].set_title("C · whole-segment held-out constant-increment prediction", loc="left")
    axes[2].set_ylabel("median error (cycles)")
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(axis="y", alpha=0.14)
    figure.suptitle(
        "Within-segment phase of actual 1/750-second Starlink frames",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.91))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_segment(
    segment: Segment,
    records: tuple[FrameRecord, ...],
    metric: dict[str, Any],
    path: Path,
) -> None:
    figure, axes = plt.subplots(4, 1, figsize=(14, 11.5), sharex=False)
    probes = metric["probes"]
    probe_times = np.asarray([item["time_s"] for item in probes])
    axes[0].scatter(
        probe_times,
        np.asarray([item["tracking_cfo_hz"] for item in probes]) / 1_000.0,
        s=8,
        facecolors="none",
        edgecolors="#F28E2B",
        linewidths=0.55,
        label="selected independent dense candidate",
    )
    dense_time = np.linspace(segment.start_s, segment.end_s, 300)
    axes[0].plot(
        dense_time,
        segment.frequency_hz(dense_time) / 1_000.0,
        color="#111111",
        linewidth=0.9,
        label=f"frozen straight {segment.label}: {segment.rate_hz_s / 1_000:.3f} kHz/s",
    )
    axes[0].set_ylabel("CFO (kHz)")
    axes[0].set_title(
        "A · independent 20 ms containers select the carrier; they are not the phase unit",
        loc="left",
    )
    axes[0].legend(fontsize=8)

    frame_times = np.asarray([item.frame_midpoint_time_s for item in records])
    coherence = np.asarray([item.coherence for item in records])
    axes[1].scatter(
        frame_times,
        [item.phase_cycles for item in records],
        s=5 + 12 * coherence,
        c=coherence,
        cmap="viridis",
        vmin=0,
        vmax=1,
        alpha=0.70,
        linewidths=0,
        rasterized=True,
    )
    axes[1].set_ylim(-0.52, 0.52)
    axes[1].set_ylabel("frame-local phase (cycles)")
    axes[1].set_title(
        "B · every marker is one actual ≈1.33 ms frame; phase reference restarts per 20 ms container",
        loc="left",
    )

    lags = np.asarray(metric["lag"]["lag_frames"])
    axes[2].plot(
        lags,
        metric["lag"]["exact_concentration"],
        marker="o",
        markersize=3,
        color="#4C78A8",
        label="exact pilot",
    )
    axes[2].plot(
        lags,
        metric["lag"]["control_concentration"],
        marker="o",
        markersize=3,
        color="#BAB0AC",
        label="rolled control",
    )
    axes[2].plot(
        lags,
        metric["lag"]["permutation_p95"],
        linestyle="--",
        color="#E15759",
        label="within-container permutation 95%",
    )
    axes[2].set_xlabel("lag (actual Starlink frames; 1 frame ≈1.33 ms)")
    axes[2].set_ylabel("phase-difference concentration R")
    axes[2].set_title("C · correlation as a function of actual-frame lag", loc="left")
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.14)

    blocks = metric["blocks"]
    block_time = np.asarray([item["midpoint_s"] for item in blocks])
    axes[3].plot(
        block_time,
        [item["lag1_exact"] for item in blocks],
        color="#59A14F",
        marker="o",
        markersize=3,
        label="lag-1 R exact",
    )
    axes[3].plot(
        block_time,
        [item["lag1_control"] for item in blocks],
        color="#BAB0AC",
        marker="o",
        markersize=3,
        label="lag-1 R control",
    )
    error_axis = axes[3].twinx()
    error_axis.plot(
        block_time,
        [item["heldout_exact_error_cycles"] for item in blocks],
        color="#F28E2B",
        linestyle="--",
        marker=".",
        label="held-out exact error",
    )
    error_axis.axhline(
        0.10,
        color="#111111",
        linestyle=":",
        linewidth=0.75,
        label="0.10 held-out gate",
    )
    axes[3].set_xlabel("stored capture time (s); fixed non-overlapping 0.30 s blocks")
    axes[3].set_ylabel("lag-1 concentration R")
    error_axis.set_ylabel("held-out error (cycles)")
    axes[3].set_title("D · where within the segment does correlation appear?", loc="left")
    handles, labels = axes[3].get_legend_handles_labels()
    error_handles, error_labels = error_axis.get_legend_handles_labels()
    axes[3].legend(handles + error_handles, labels + error_labels, fontsize=8, ncol=4)
    axes[3].grid(alpha=0.14)
    figure.suptitle(
        f"{segment.label} · actual-frame phase correlation · {SESSION_ID} · {STREAM_ID}/RX{RECEIVER_ID}",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _write_state_artifact(records: dict[str, tuple[FrameRecord, ...]], path: Path) -> None:
    with path.open("wb") as raw_target:
        compressed = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_target,
            mtime=0,
        )
        target = io.TextIOWrapper(compressed, encoding="utf-8")
        with target:
            target.write(
                json.dumps(
                    {
                        "kind": "metadata",
                        "schema": "org.leo.research.within-segment-actual-frame-phase/v1",
                        "session_id": SESSION_ID,
                        "stream_id": STREAM_ID,
                        "receiver_id": RECEIVER_ID,
                        "frame_rate_hz": FRAME_RATE_HZ,
                        "cross_probe_phase_comparisons": False,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            for label in sorted(records):
                for record in records[label]:
                    target.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def _report(metrics: dict[str, Any], path: Path) -> None:
    practical_reading = {
        "P1": "intermittent predictive blocks",
        "P2": "broadest correlation; late third predictive",
        "P4": "detectable but not predictive",
        "P5": "late segment predictive",
    }
    lines = [
        "# Is carrier phase correlated inside individual straight CFO segments?",
        "",
        "## Answer",
        "",
        "Yes. **P1, P2, and late P5 contain intervals in which the phase of adjacent actual "
        "Starlink frames is correlated and one constant phase increment predicts held-out frames.** "
        "P2 is the most broadly consistent segment; P1 is intermittent, and P5 becomes useful late "
        "in the segment. P4 does not show practically useful frame-to-frame phase correlation under "
        "this estimator.",
        "",
        "This report deliberately changes the unit of analysis from a boundary or a 20 ms "
        "acquisition probe to the actual approximately 1.33 ms Starlink frame. A 20 ms probe is "
        "only an independently acquired container holding about fifteen actual frames. All lag and "
        "prediction calculations below operate on those actual frames.",
        "",
        "> **Most important limitation:** phase is comparable between actual frames inside one 20 ms",
        "> container. Each next 20 ms container independently selects CFO and frame epoch, so this",
        "> report pools within-container correlations by segment but does not claim one continuous",
        "> absolute phase trace across an entire multi-second segment.",
        "",
        "![Within-segment actual-frame overview](figures/2026_08_22_within_segment_frame_phase/within-segment-overview.png)",
        "",
        "## Question and motivation",
        "",
        "The boundary report asked whether phase could bridge P1→P2 or P4→P5. That is a harder "
        "question and obscures a prerequisite: do ordinary consecutive Starlink frames have "
        "predictable phase anywhere inside a single segment? Here P1, P2, P4, and P5 are analyzed "
        "one at a time, with no boundary phase jump fitted.",
        "",
        "A segment may contain frame-local phase without containing inter-frame continuity. These "
        "are different statements. Local coherence asks whether the known symbols share one phase "
        "inside a frame. Lag correlation asks whether the phase difference between actual frames is "
        "repeatable. Held-out prediction asks whether that repeatability is strong enough to predict "
        "frames excluded from fitting.",
        "",
        "## Frozen input and coverage",
        "",
        f"- Recording: `{SESSION_ID}`, `{STREAM_ID}/RX{RECEIVER_ID}`, scope `{SCOPE_ID}`.",
        "- Four frozen degree-1 segments: P1, P2, P4, and P5.",
        "- Full segment intervals reacquired with back-to-back 20 ms dense Research windows.",
        "- Each window: 81 coarse CFO hypotheses, 32 independently scored basins, GLRT-4096.",
        "- Candidate association: nearest frozen straight line within 2.5 kHz and exact-minus-control margin≥0.05, after independent scoring.",
        "- Phase estimator: Qin lower-edge symbols 2–65, one independent circular state per approximately 1/750-second frame.",
        "- CFO model: one independently acquired constant CFO per 20 ms container. The frozen degree-1 line enters association/display only. No quadratic/cubic CFO fit.",
        "",
        "| Segment | Frozen interval | CFO rate | Candidate windows | Selected windows | Actual frames |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in metrics["segments"]:
        lines.append(
            f"| {item['label']} | {item['interval_s'][0]:.3f}–{item['interval_s'][1]:.3f} s | "
            f"{item['rate_hz_s']:.1f} Hz/s | {item['candidate_probe_count']} | "
            f"{item['selected_probe_count']} ({100 * item['selected_probe_fraction']:.1f}%) | "
            f"{item['actual_frame_count']} |"
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "For actual-frame phases `φ[g,f]` in 20 ms container `g`, the lag-`L` statistic is "
            "`R[g,L] = |mean_f(exp(i·2π·(φ[g,f+L]−φ[g,f])))|`; the reported segment value is "
            "the mean of `R[g,L]` over containers. R near 1 means the phase increment is repeatable "
            "inside a container even if independently acquired containers have different residual "
            "CFO. R near 0 means it is diffuse. The rolled-pilot control and a "
            "within-container phase-order permutation provide two null comparisons.",
            "",
            "A separate held-out test fits one constant phase increment using two of every three "
            "actual frames and predicts the interleaved third. A median error near 0.25 cycles is "
            "random circular prediction; ≤0.10 cycles is the exploratory useful-prediction gate. "
            "Fixed, non-overlapping 0.30 s blocks locate correlated parts without hand-drawing "
            "windows around favorable points. The duration is an exploratory report choice, not a "
            "production threshold. The reported best-block p-value compares the maximum block R "
            "with 300 matched phase-order permutations, correcting for searching all blocks inside "
            "that segment. A four-segment Bonferroni value is also reported; this is conservative "
            "and makes the family of P1/P2/P4/P5 searches explicit.",
            "",
            "Synthetic controls verify the interpretation. A noisy constant-increment sequence has "
            f"lag-1 R={metrics['synthetic']['continuous_lag1_concentration']:.3f} and "
            f"{metrics['synthetic']['continuous_heldout_median_error_cycles']:.3f}-cycle held-out "
            "error; random per-frame resets have "
            f"R={metrics['synthetic']['random_reset_lag1_concentration']:.3f} and "
            f"{metrics['synthetic']['random_reset_heldout_median_error_cycles']:.3f}-cycle error.",
            "",
            "## Segment-level results",
            "",
            "| Segment | Exact/control within-frame coherence | Lag-1 R exact/control | Lag-1 four-segment p | Held-out exact/control error | Exact probes ≤0.10 | Best 0.30 s block R / blocks+segments p | Practical reading |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in metrics["segments"]:
        best = item["best_block"]
        lines.append(
            f"| {item['label']} | {item['within_frame']['exact_median_coherence']:.3f}/"
            f"{item['within_frame']['control_median_coherence']:.3f} | "
            f"{item['lag']['exact_concentration'][0]:.3f}/{item['lag']['control_concentration'][0]:.3f} | "
            f"{item['lag']['lag1_four_segment_bonferroni_p']:.4f} | "
            f"{item['heldout']['exact_median_error_cycles']:.3f}/"
            f"{item['heldout']['control_median_error_cycles']:.3f} cycles | "
            f"{100 * item['heldout']['exact_probe_fraction_le_0_10']:.1f}% | "
            f"{best['lag1_exact']:.3f} / {best['max_lag1_four_segment_bonferroni_p']:.4f} | "
            f"{practical_reading[item['label']]} |"
        )
    lines.extend([""])
    for item in metrics["segments"]:
        label = item["label"]
        best = item["best_block"]
        lines.extend(
            [
                f"## {label}",
                "",
                f"![{label} actual-frame phase](figures/2026_08_22_within_segment_frame_phase/{label.lower()}-actual-frame-phase.png)",
                "",
                f"{label} contributes {item['actual_frame_count']} actual-frame estimates from "
                f"{item['selected_probe_count']} independently acquired containers. Its overall "
                f"lag-1 concentration is {item['lag']['exact_concentration'][0]:.3f} versus "
                f"{item['lag']['control_concentration'][0]:.3f} for control; the matched permutation "
                f"p-value is {item['lag']['lag1_permutation_p']:.4f} within the segment and "
                f"{item['lag']['lag1_four_segment_bonferroni_p']:.4f} after the four-segment "
                "correction. The overall held-out error is "
                f"{item['heldout']['exact_median_error_cycles']:.3f} cycles versus "
                f"{item['heldout']['control_median_error_cycles']:.3f} for control.",
                "",
                f"The strongest fixed 0.30 s block is {best['start_s']:.3f}–{best['stop_s']:.3f} s "
                f"with lag-1 R={best['lag1_exact']:.3f}, held-out error "
                f"{best['heldout_exact_error_cycles']:.3f} cycles, and max-over-block permutation "
                f"p={best['max_lag1_look_elsewhere_p']:.4f} within the segment and "
                f"{best['max_lag1_four_segment_bonferroni_p']:.4f} after the four-segment correction.",
                "",
                "| Part | Interval | Probes | Actual frames | Lag-1 R exact/control | Held-out exact/control error |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for part in item["thirds"]:
            lines.append(
                f"| {part['part']} | {part['start_s']:.3f}–{part['stop_s']:.3f} s | "
                f"{part['probe_count']} | {part['frame_count']} | "
                f"{part['lag1_exact']:.3f}/{part['lag1_control']:.3f} | "
                f"{part['heldout_exact_error_cycles']:.3f}/"
                f"{part['heldout_control_error_cycles']:.3f} cycles |"
            )
        lines.extend([""])
    lines.extend(
        [
            "## Interpretation",
            "",
            "P1, P2, and P5 each have a fixed 0.30 s block whose maximum lag-1 R survives the "
            "max-over-block permutation correction and whose independently reported held-out error "
            "is below 0.10 cycles. P2 is the broadest result: its late third also passes the 0.10-"
            "cycle held-out target. P5's useful behavior is concentrated late, and P1 alternates "
            "between strongly and weakly predictive blocks. These intervals support a constant "
            "residual-CFO phase model over consecutive actual frames inside a 20 ms container.",
            "",
            "P4 illustrates why statistical and practical significance must be separated. Its "
            "overall lag-1 R is slightly above the permutation/control level and becomes detectable "
            "with thousands of frames, but held-out prediction is random-like and its best block "
            "does not survive the max-over-block control. P4 therefore does not supply a useful "
            "phase state.",
            "",
            "That still does not provide a seconds-long continuous phase trajectory. Independent "
            "container acquisition changes the phase reference every 20 ms, and the recording lacks "
            "device sample counters across possible capture stalls. The next research implementation "
            "should start from the correlated P1/P2/P5 blocks and maintain one continuous timing/CFO/phase "
            "state across container boundaries, validating it on held-out actual frames before "
            "attempting P1→P2 continuity.",
            "",
            "## Reproducibility",
            "",
            "- Generator: `tools/report_within_segment_frame_phase.py`.",
            "- Metrics: `figures/2026_08_22_within_segment_frame_phase/within-segment-frame-phase-metrics.json`.",
            "- Compact actual-frame states: `segment-frame-phase-states.jsonl.gz`.",
            "- Dense candidates and run configurations: `candidates/{p1,p2,p4,p5}/`.",
            "- All random controls use the persisted seed in the metrics artifact.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        reader = store.reader(bundle, STREAM_ID, verify=True)
        all_records: dict[str, tuple[FrameRecord, ...]] = {}
        segment_metrics = []
        for segment in SEGMENTS:
            candidate_path = (
                args.candidate_root
                / segment.label.lower()
                / "dense-independent-glrt-candidates.jsonl.gz"
            )
            candidates = _load_candidates(candidate_path)
            candidate_probe_count = len({item.sample_start for item in candidates})
            selected = _select_candidates(segment, candidates)
            records, probes = _extract_frames(reader, segment, selected)
            all_records[segment.label] = records
            metric = _segment_metrics(
                segment,
                records,
                probes,
                candidate_probe_count,
            )
            segment_metrics.append(metric)
            _plot_segment(
                segment,
                records,
                metric,
                args.output_root / f"{segment.label.lower()}-actual-frame-phase.png",
            )
        metrics = {
            "schema": "org.leo.research.within-segment-frame-phase/v1",
            "recording": {
                "session_id": SESSION_ID,
                "stream_id": STREAM_ID,
                "receiver_id": RECEIVER_ID,
                "scope_id": SCOPE_ID,
            },
            "method": {
                "actual_frame_rate_hz": FRAME_RATE_HZ,
                "actual_frame_duration_ms": 1_000.0 / FRAME_RATE_HZ,
                "probe_duration_ms": 1_000.0 * PROBE_SECONDS,
                "probe_is_phase_unit": False,
                "cross_probe_phase_comparisons": False,
                "maximum_lag_frames": MAX_LAG_FRAMES,
                "block_seconds": BLOCK_SECONDS,
                "permutations": PERMUTATIONS,
                "rng_seed": RNG_SEED,
                "cfo_model": "one independently acquired constant CFO per 20 ms container; frozen degree-1 line for post-detection association/display only",
            },
            "synthetic": _synthetic_metrics(),
            "segments": segment_metrics,
        }
        (args.output_root / "within-segment-frame-phase-metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_state_artifact(
            all_records,
            args.output_root / "segment-frame-phase-states.jsonl.gz",
        )
        _plot_overview(segment_metrics, args.output_root / "within-segment-overview.png")
        _report(metrics, args.report)
    finally:
        store.close()


if __name__ == "__main__":
    main()
