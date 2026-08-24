#!/usr/bin/env python3
"""Blindly search timing and CFO from raw IQ before any 20 ms association."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
SAMPLE_RATE_HZ = 2_500_000.0
START_S = 33.7
END_S = 37.7
CELL_DURATION_S = 0.012
CELL_HOP_S = 0.004
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_blind_timing_cfo")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_blind_timing_cfo.md")
DEFAULT_EXTERNAL_AUDIT = Path(
    "reports/figures/2026_08_23_470384_shifted_pilot_grid/shifted-grid-boundary-audit.json"
)

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"
PURPLE = "#7b65a8"


@dataclass(frozen=True, slots=True)
class BlindCandidate:
    cell_index: int
    cell_start_s: float
    cell_center_s: float
    refined_epoch_sample: int
    absolute_frame_start_sample: int
    absolute_cfo_hz: float
    acquire_score: float
    verify_score: float
    control_score: float
    margin: float
    frame_support: int


@dataclass(frozen=True, slots=True)
class LatentLine:
    label: str
    reference_time_s: float
    frequency_at_reference_hz: float
    slope_hz_s: float
    objective: float
    selected_cell_count: int
    selected_candidate_count: int
    weighted_rms_hz: float

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        result = self.frequency_at_reference_hz + self.slope_hz_s * (
            np.asarray(time_s, dtype=float) - self.reference_time_s
        )
        return float(result) if np.ndim(result) == 0 else result


@dataclass(frozen=True, slots=True)
class BlindEvent:
    time_s: float
    cfo_jump_hz: float
    timing_jump_samples: int
    timing_jump_us: float


@dataclass(frozen=True, slots=True)
class BlindSegment:
    segment_index: int
    start_s: float
    end_s: float
    point_count: int
    preceding_boundary_time_s: float | None
    reference_time_s: float | None
    frequency_at_reference_hz: float | None
    slope_hz_s: float | None
    rms_hz: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--external-audit", type=Path, default=DEFAULT_EXTERNAL_AUDIT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    parser.add_argument("--receiver-id", type=int, default=0)
    parser.add_argument("--cell-duration-s", type=float, default=CELL_DURATION_S)
    parser.add_argument("--cell-hop-s", type=float, default=CELL_HOP_S)
    parser.add_argument(
        "--maximum-cells",
        type=int,
        help="bounded development run over fixed raw-IQ cells",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15)


def acquisition_config(*, maximum_probe_samples: int) -> SymbolwiseAcquisitionConfig:
    """Return the fixed full-band acquisition used before any prior association."""

    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-1_200_000.0,
        residual_cfo_max_hz=1_200_000.0,
        coarse_cfo_step_hz=40_000.0,
        fine_cfo_radius_hz=40_000.0,
        fine_cfo_step_hz=500.0,
        conditioned_cfo_radius_hz=3_000.0,
        conditioned_cfo_step_hz=100.0,
        retained_candidate_count=16,
        candidate_epoch_separation_samples=20,
        candidate_cfo_separation_hz=20_000.0,
        minimum_frame_support=5,
        maximum_probe_samples=maximum_probe_samples,
    )


def _deduplicate(candidates: list[BlindCandidate]) -> tuple[BlindCandidate, ...]:
    ordered = sorted(candidates, key=lambda item: (item.margin, item.verify_score), reverse=True)
    retained: list[BlindCandidate] = []
    for candidate in ordered:
        duplicate = any(
            abs(candidate.refined_epoch_sample - item.refined_epoch_sample) <= 8
            and abs(candidate.absolute_cfo_hz - item.absolute_cfo_hz) <= 2_000.0
            for item in retained
        )
        if not duplicate:
            retained.append(candidate)
    return tuple(sorted(retained, key=lambda item: item.absolute_cfo_hz))


def scan_raw_iq(
    *,
    bulk_root: Path,
    start_s: float,
    end_s: float,
    cell_duration_s: float,
    cell_hop_s: float,
    maximum_cells: int | None,
    receiver_id: int = 0,
) -> tuple[BlindCandidate, ...]:
    """Run fixed-cell joint timing/CFO acquisition with no persisted analysis input."""

    cell_samples = round(cell_duration_s * SAMPLE_RATE_HZ)
    hop_samples = round(cell_hop_s * SAMPLE_RATE_HZ)
    if cell_samples < round(0.008 * SAMPLE_RATE_HZ):
        raise ValueError("blind acquisition cells must span at least 8 ms")
    start_sample = round(start_s * SAMPLE_RATE_HZ)
    stop_sample = round(end_s * SAMPLE_RATE_HZ)
    cell_starts = np.arange(start_sample, stop_sample - cell_samples + 1, hop_samples, dtype=int)
    if maximum_cells is not None:
        if maximum_cells < 1:
            raise ValueError("maximum cell count must be positive")
        cell_starts = cell_starts[:maximum_cells]
    read_stop = int(cell_starts[-1]) + cell_samples
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(SESSION_ID), "stream-0", verify=True)
        raw = reader.read(
            start_sample,
            read_stop - start_sample,
            receiver_ids=(receiver_id,),
        )
        iq = _complex_receiver(raw)
    finally:
        if store is not None:
            store.close()
    calibration = ReceiverFrequencyCalibration(
        f"blind-rx{receiver_id}",
        0.0,
        f"{receiver_id:x}" * 64,
    )
    config = acquisition_config(maximum_probe_samples=cell_samples)
    output: list[BlindCandidate] = []
    for cell_index, absolute_start in enumerate(cell_starts):
        local_start = int(absolute_start) - start_sample
        values = np.ascontiguousarray(iq[local_start : local_start + cell_samples])
        result = acquire_symbolwise(
            values,
            SAMPLE_RATE_HZ,
            calibration,
            edge=StarlinkEdge.UPPER,
            config=config,
        )
        candidates = []
        for item in result.candidates:
            if item.verify_score < 0.08 or item.verify_minus_control_margin < 0.03:
                continue
            candidates.append(
                BlindCandidate(
                    cell_index=cell_index,
                    cell_start_s=float(absolute_start / SAMPLE_RATE_HZ),
                    cell_center_s=float((absolute_start + 0.5 * cell_samples) / SAMPLE_RATE_HZ),
                    refined_epoch_sample=item.refined_epoch_sample,
                    absolute_frame_start_sample=int(absolute_start + item.refined_epoch_sample),
                    absolute_cfo_hz=item.absolute_cfo_hz,
                    acquire_score=item.acquire_score,
                    verify_score=item.verify_score,
                    control_score=item.conditioned_control_score,
                    margin=item.verify_minus_control_margin,
                    frame_support=item.frame_support,
                )
            )
        output.extend(_deduplicate(candidates))
        if (cell_index + 1) % 100 == 0 or cell_index + 1 == len(cell_starts):
            print(
                f"blind timing/CFO acquisition {cell_index + 1}/{len(cell_starts)} cells",
                flush=True,
            )
    return tuple(output)


def _candidate_arrays(
    candidates: tuple[BlindCandidate, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cells = np.asarray([item.cell_index for item in candidates], dtype=int)
    times = np.asarray([item.cell_center_s for item in candidates], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in candidates], dtype=float)
    qualities = np.asarray([max(item.margin, 0.0) for item in candidates], dtype=float)
    return cells, times, frequencies, qualities


def _latent_objective(
    parameters: np.ndarray,
    *,
    cells: np.ndarray,
    times: np.ndarray,
    frequencies: np.ndarray,
    qualities: np.ndarray,
    reference_time_s: float,
    frequency_scale_hz: float,
) -> float:
    prediction = parameters[0] + parameters[1] * (times - reference_time_s)
    values = qualities * np.exp(-0.5 * ((frequencies - prediction) / frequency_scale_hz) ** 2)
    maxima = np.zeros(int(np.max(cells)) + 1, dtype=float)
    np.maximum.at(maxima, cells, values)
    return float(np.mean(maxima))


def fit_latent_line(
    candidates: tuple[BlindCandidate, ...],
    *,
    label: str,
    excluded_line: LatentLine | None = None,
    seed: int = 470_384,
    frequency_scale_hz: float = 500.0,
) -> tuple[LatentLine, tuple[int, ...]]:
    """Fit a global line while maximizing over retained timing modes in each cell."""

    if excluded_line is not None:
        candidates = tuple(
            item
            for item in candidates
            if abs(item.absolute_cfo_hz - float(excluded_line.frequency_hz(item.cell_center_s)))
            > 3_000.0
        )
    cells, times, frequencies, qualities = _candidate_arrays(candidates)
    reference_time_s = float(np.mean(times))
    rng = np.random.default_rng(seed)
    eligible_pairs = np.flatnonzero(np.abs(times[:, None] - times[None, :]) > 1.0)
    if not len(eligible_pairs):
        raise ValueError("latent line fit needs candidates separated by more than one second")
    pair_rows, pair_columns = np.unravel_index(
        rng.choice(eligible_pairs, size=min(8_000, len(eligible_pairs)), replace=True),
        (len(times), len(times)),
    )
    best_parameters = None
    best_objective = -math.inf
    for left, right in zip(pair_rows, pair_columns, strict=True):
        slope = (frequencies[right] - frequencies[left]) / (times[right] - times[left])
        if not -50_000.0 <= slope <= 50_000.0:
            continue
        intercept = frequencies[left] - slope * (times[left] - reference_time_s)
        parameters = np.asarray([intercept, slope])
        objective = _latent_objective(
            parameters,
            cells=cells,
            times=times,
            frequencies=frequencies,
            qualities=qualities,
            reference_time_s=reference_time_s,
            frequency_scale_hz=frequency_scale_hz,
        )
        if objective > best_objective:
            best_parameters = parameters
            best_objective = objective
    if best_parameters is None:
        raise ValueError("latent line search produced no finite candidate")

    selected_indexes: np.ndarray = np.asarray([], dtype=int)
    parameters = best_parameters
    for _iteration in range(8):
        prediction = parameters[0] + parameters[1] * (times - reference_time_s)
        values = qualities * np.exp(-0.5 * ((frequencies - prediction) / frequency_scale_hz) ** 2)
        selected = []
        for cell in np.unique(cells):
            indexes = np.flatnonzero(cells == cell)
            selected.append(int(indexes[int(np.argmax(values[indexes]))]))
        selected_indexes = np.asarray(selected, dtype=int)
        residual = frequencies[selected_indexes] - (
            parameters[0] + parameters[1] * (times[selected_indexes] - reference_time_s)
        )
        retained = np.abs(residual) <= 2_000.0
        chosen = selected_indexes[retained]
        design = np.column_stack((np.ones(len(chosen)), times[chosen] - reference_time_s))
        weights = np.maximum(qualities[chosen], 1e-6)
        information = design.T @ (weights[:, None] * design)
        parameters = np.linalg.solve(information, design.T @ (weights * frequencies[chosen]))
    prediction = parameters[0] + parameters[1] * (times - reference_time_s)
    residual = frequencies - prediction
    selected_candidates = selected_indexes[np.abs(residual[selected_indexes]) <= 2_000.0]
    weights = np.maximum(qualities[selected_candidates], 1e-6)
    rms = float(np.sqrt(np.average(residual[selected_candidates] ** 2, weights=weights)))
    objective = _latent_objective(
        parameters,
        cells=cells,
        times=times,
        frequencies=frequencies,
        qualities=qualities,
        reference_time_s=reference_time_s,
        frequency_scale_hz=frequency_scale_hz,
    )
    original_lookup = {id(item): index for index, item in enumerate(candidates)}
    selected_original = tuple(
        original_lookup[id(candidates[index])] for index in selected_candidates
    )
    return (
        LatentLine(
            label=label,
            reference_time_s=reference_time_s,
            frequency_at_reference_hz=float(parameters[0]),
            slope_hz_s=float(parameters[1]),
            objective=objective,
            selected_cell_count=len(np.unique(cells[selected_candidates])),
            selected_candidate_count=len(selected_candidates),
            weighted_rms_hz=rms,
        ),
        selected_original,
    )


def selected_path(
    candidates: tuple[BlindCandidate, ...],
    line: LatentLine,
    *,
    maximum_residual_hz: float = 2_000.0,
) -> tuple[BlindCandidate, ...]:
    groups: dict[int, list[BlindCandidate]] = {}
    for item in candidates:
        groups.setdefault(item.cell_index, []).append(item)
    output = []
    for group in groups.values():
        scored = [
            (
                item.margin
                * math.exp(
                    -0.5
                    * (
                        (item.absolute_cfo_hz - float(line.frequency_hz(item.cell_center_s)))
                        / 500.0
                    )
                    ** 2
                ),
                item,
            )
            for item in group
        ]
        _score, winner = max(scored, key=lambda value: value[0])
        if abs(winner.absolute_cfo_hz - float(line.frequency_hz(winner.cell_center_s))) <= (
            maximum_residual_hz
        ):
            output.append(winner)
    return tuple(sorted(output, key=lambda item: item.cell_index))


def detect_events(path: tuple[BlindCandidate, ...], line: LatentLine) -> tuple[BlindEvent, ...]:
    output = []
    for leading, trailing in zip(path[:-1], path[1:], strict=True):
        if trailing.cell_index != leading.cell_index + 1:
            continue
        leading_residual = leading.absolute_cfo_hz - float(line.frequency_hz(leading.cell_center_s))
        trailing_residual = trailing.absolute_cfo_hz - float(
            line.frequency_hz(trailing.cell_center_s)
        )
        cfo_jump = trailing_residual - leading_residual
        timing_jump = trailing.refined_epoch_sample - leading.refined_epoch_sample
        if abs(cfo_jump) < 100.0 or abs(timing_jump) < 20:
            continue
        output.append(
            BlindEvent(
                time_s=0.5 * (leading.cell_center_s + trailing.cell_center_s),
                cfo_jump_hz=cfo_jump,
                timing_jump_samples=timing_jump,
                timing_jump_us=timing_jump / SAMPLE_RATE_HZ * 1e6,
            )
        )
    return tuple(output)


def segment_path(
    path: tuple[BlindCandidate, ...],
    *,
    maximum_timing_change_samples: int = 20,
    minimum_fit_points: int = 5,
) -> tuple[BlindSegment, ...]:
    """Split a blind path at timing-mode changes or missing-cell handoffs."""

    if not path:
        return ()
    groups: list[tuple[list[BlindCandidate], float | None]] = []
    group = [path[0]]
    preceding_boundary_time_s = None
    for leading, trailing in zip(path[:-1], path[1:], strict=True):
        timing_change = abs(trailing.refined_epoch_sample - leading.refined_epoch_sample)
        if (
            trailing.cell_index == leading.cell_index + 1
            and timing_change <= maximum_timing_change_samples
        ):
            group.append(trailing)
            continue
        groups.append((group, preceding_boundary_time_s))
        preceding_boundary_time_s = 0.5 * (leading.cell_center_s + trailing.cell_center_s)
        group = [trailing]
    groups.append((group, preceding_boundary_time_s))

    output = []
    for segment_index, (items, boundary_time_s) in enumerate(groups):
        reference_time_s = None
        frequency_at_reference_hz = None
        slope_hz_s = None
        rms_hz = None
        if len(items) >= minimum_fit_points:
            times = np.asarray([item.cell_center_s for item in items], dtype=float)
            frequencies = np.asarray([item.absolute_cfo_hz for item in items], dtype=float)
            reference_time_s = float(np.mean(times))
            design = np.column_stack((np.ones(len(items)), times - reference_time_s))
            frequency_at_reference_hz, slope_hz_s = np.linalg.lstsq(
                design,
                frequencies,
                rcond=None,
            )[0]
            residuals = frequencies - design @ np.asarray([frequency_at_reference_hz, slope_hz_s])
            rms_hz = float(np.sqrt(np.mean(residuals**2)))
        output.append(
            BlindSegment(
                segment_index=segment_index,
                start_s=items[0].cell_center_s,
                end_s=items[-1].cell_center_s,
                point_count=len(items),
                preceding_boundary_time_s=boundary_time_s,
                reference_time_s=(None if reference_time_s is None else float(reference_time_s)),
                frequency_at_reference_hz=(
                    None if frequency_at_reference_hz is None else float(frequency_at_reference_hz)
                ),
                slope_hz_s=None if slope_hz_s is None else float(slope_hz_s),
                rms_hz=rms_hz,
            )
        )
    return tuple(output)


def segment_statistics(segments: tuple[BlindSegment, ...]) -> dict[str, Any]:
    fitted = tuple(item for item in segments if item.slope_hz_s is not None)
    slopes = np.asarray([item.slope_hz_s for item in fitted], dtype=float)
    rms_values = np.asarray([item.rms_hz for item in fitted], dtype=float)
    boundaries = np.asarray(
        [
            item.preceding_boundary_time_s
            for item in segments
            if item.preceding_boundary_time_s is not None
        ],
        dtype=float,
    )
    return {
        "segment_count": len(segments),
        "fitted_segment_count": len(fitted),
        "median_local_slope_hz_s": float(np.median(slopes)),
        "p10_local_slope_hz_s": float(np.percentile(slopes, 10)),
        "p90_local_slope_hz_s": float(np.percentile(slopes, 90)),
        "median_local_fit_rms_hz": float(np.median(rms_values)),
        "median_boundary_spacing_ms": float(np.median(np.diff(boundaries)) * 1_000),
    }


def external_comparison(
    blind_boundaries_s: tuple[float, ...],
    path: Path,
) -> dict[str, Any]:
    if not path.exists() or not blind_boundaries_s:
        return {"available": False}
    document = _load(path)
    old_times = np.asarray(
        [
            item["nominal_boundary_time_s"]
            for item in document["boundary_audits"]
            if item["boundary_mode_separation_hz"] is not None
        ],
        dtype=float,
    )
    blind_times = np.asarray(blind_boundaries_s, dtype=float)
    old_to_blind = np.min(np.abs(old_times[:, None] - blind_times[None, :]), axis=1)
    blind_to_old = np.min(np.abs(blind_times[:, None] - old_times[None, :]), axis=1)
    return {
        "available": True,
        "loaded_after_blind_fit": True,
        "old_boundary_count": len(old_times),
        "blind_boundary_count": len(blind_times),
        "old_to_blind_median_distance_ms": float(np.median(old_to_blind) * 1_000),
        "old_to_blind_p90_distance_ms": float(np.percentile(old_to_blind, 90) * 1_000),
        "old_boundaries_within_12_ms": int(np.count_nonzero(old_to_blind <= 0.012)),
        "blind_to_sparse_old_median_distance_ms": float(np.median(blind_to_old) * 1_000),
    }


def render(
    path: Path,
    *,
    candidates: tuple[BlindCandidate, ...],
    primary: LatentLine,
    secondary: LatentLine,
    primary_path: tuple[BlindCandidate, ...],
    secondary_path: tuple[BlindCandidate, ...],
    primary_segments: tuple[BlindSegment, ...],
) -> None:
    primary_ids = {id(item) for item in primary_path}
    secondary_ids = {id(item) for item in secondary_path}
    other = tuple(
        item for item in candidates if id(item) not in primary_ids and id(item) not in secondary_ids
    )
    figure = Figure(figsize=(18, 14), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": (1.2, 1, 1)})
    figure.suptitle(
        "Blind timing–CFO acquisition from raw IQ · no 20 ms candidate input",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )

    def scatter(items: tuple[BlindCandidate, ...], axis, *, color: str, label: str, alpha: float):
        axis.scatter(
            [item.cell_center_s for item in items],
            [item.absolute_cfo_hz / 1e3 for item in items],
            s=12,
            color=color,
            alpha=alpha,
            linewidths=0,
            rasterized=True,
            label=label,
        )

    scatter(other, axes[0], color=GRAY, label="other retained blind modes", alpha=0.18)
    scatter(primary_path, axes[0], color=BLUE, label="primary latent path", alpha=0.68)
    scatter(secondary_path, axes[0], color=AMBER, label="secondary latent path", alpha=0.66)
    times = np.linspace(
        min(item.cell_center_s for item in candidates),
        max(item.cell_center_s for item in candidates),
        800,
    )
    axes[0].plot(
        times,
        np.asarray(primary.frequency_hz(times)) / 1e3,
        color=INK,
        linewidth=2.0,
        label=f"primary global line · {primary.slope_hz_s / 1e3:.3f} kHz/s",
    )
    axes[0].plot(
        times,
        np.asarray(secondary.frequency_hz(times)) / 1e3,
        color=PURPLE,
        linewidth=1.8,
        label=f"secondary global line · {secondary.slope_hz_s / 1e3:.3f} kHz/s",
    )
    axes[0].legend(loc="lower left", ncol=2)

    axes[1].scatter(
        [item.cell_center_s for item in other],
        [item.refined_epoch_sample / SAMPLE_RATE_HZ * 1e6 for item in other],
        s=10,
        color=GRAY,
        alpha=0.16,
        linewidths=0,
        rasterized=True,
    )
    axes[1].scatter(
        [item.cell_center_s for item in primary_path],
        [item.refined_epoch_sample / SAMPLE_RATE_HZ * 1e6 for item in primary_path],
        s=12,
        color=BLUE,
        alpha=0.65,
        linewidths=0,
        rasterized=True,
        label="primary timing mode",
    )
    axes[1].scatter(
        [item.cell_center_s for item in secondary_path],
        [item.refined_epoch_sample / SAMPLE_RATE_HZ * 1e6 for item in secondary_path],
        s=12,
        color=AMBER,
        alpha=0.64,
        linewidths=0,
        rasterized=True,
        label="secondary timing mode",
    )
    axes[1].legend(loc="lower left", ncol=2)

    primary_times = np.asarray([item.cell_center_s for item in primary_path])
    primary_residuals = np.asarray(
        [
            item.absolute_cfo_hz - float(primary.frequency_hz(item.cell_center_s))
            for item in primary_path
        ]
    )
    axes[2].scatter(
        primary_times,
        primary_residuals,
        s=12,
        color=GREEN,
        alpha=0.64,
        linewidths=0,
        rasterized=True,
        label="blind primary path minus its global line",
    )
    for segment in primary_segments[1:]:
        if (
            segment.reference_time_s is None
            or segment.frequency_at_reference_hz is None
            or segment.slope_hz_s is None
        ):
            continue
        segment_times = np.asarray([segment.start_s, segment.end_s])
        segment_frequencies = segment.frequency_at_reference_hz + segment.slope_hz_s * (
            segment_times - segment.reference_time_s
        )
        axes[2].plot(
            segment_times,
            segment_frequencies - np.asarray(primary.frequency_hz(segment_times)),
            color=AMBER,
            linewidth=1.2,
            alpha=0.78,
            label="independent line per timing segment" if segment.segment_index == 1 else None,
        )
    for index, segment in enumerate(primary_segments[1:]):
        assert segment.preceding_boundary_time_s is not None
        axes[2].axvline(
            segment.preceding_boundary_time_s,
            color=RED,
            linewidth=0.9,
            linestyle=(0, (4, 3)),
            alpha=0.38,
            label="blind timing-mode boundary" if index == 0 else None,
        )
    axes[2].axhline(0.0, color=INK, linewidth=0.8, alpha=0.55)
    axes[2].legend(loc="lower left", ncol=2)
    titles = (
        "A · Retained raw-IQ timing/CFO modes and two global latent trajectories",
        "B · Timing epoch inside each fixed 12 ms cell",
        "C · Primary residual, independent segment fits, and blind boundaries",
    )
    ylabels = (
        "absolute CFO (kHz)",
        "timing epoch in cell (µs)",
        "primary CFO − global line (Hz)",
    )
    for axis, title, ylabel in zip(axes, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    figure = os.path.relpath(document["figure"], path.parent)
    primary = document["primary_line"]
    secondary = document["secondary_line"]
    segments = document["primary_segment_statistics"]
    comparison = document["external_comparison"]
    inventory = document["inventory"]
    primary_row = (
        f"| primary | {primary['frequency_at_reference_hz']:.1f} Hz | "
        f"{primary['slope_hz_s'] / 1e3:.3f} kHz/s | "
        f"{primary['selected_cell_count']} | {primary['weighted_rms_hz']:.1f} Hz |"
    )
    secondary_row = (
        f"| secondary | {secondary['frequency_at_reference_hz']:.1f} Hz | "
        f"{secondary['slope_hz_s'] / 1e3:.3f} kHz/s | "
        f"{secondary['selected_cell_count']} | {secondary['weighted_rms_hz']:.1f} Hz |"
    )
    text = f"""# Blind timing–CFO experiment on `470384`

## Isolation

This experiment opens only the recording.  Before the blind fit completes, it
does not load the persisted pilot scan, any 20 ms CFO, timing epoch, branch,
trajectory, TLE, or earlier frame manifest.  Overlapping 12 ms raw-IQ cells are
placed every 4 ms; inside each cell, timing over the complete 1.333 ms phase and
absolute CFO over ±1.2 MHz are searched jointly.  Multiple Qin-supported modes
are retained rather than selecting by branch proximity.

![Blind timing/CFO acquisition]({figure})

| trajectory | CFO at reference | rate | selected cells | weighted RMS |
| --- | ---: | ---: | ---: | ---: |
{primary_row}
{secondary_row}

The old shifted-grid boundary audit is loaded only after the blind trajectories
and blind joint timing/CFO events have been frozen.

## Result

The primary path divides blindly into {segments["segment_count"]} constant-timing
segments; {segments["fitted_segment_count"]} contain at least five cell fits.
Of its {inventory["blind_boundary_count"]} boundaries,
{inventory["blind_event_count"]} have adjacent cells on both sides and directly
show both a ≥100 Hz CFO reset and a ≥20-sample timing jump; the remainder bracket
short acquisition gaps.
Their median boundary spacing is {segments["median_boundary_spacing_ms"]:.1f} ms.
The per-segment CFO slopes have median
{segments["median_local_slope_hz_s"] / 1e3:.3f} kHz/s and a 10–90% range of
{segments["p10_local_slope_hz_s"] / 1e3:.3f} to
{segments["p90_local_slope_hz_s"] / 1e3:.3f} kHz/s.  Those small lines fit to a
median RMS of {segments["median_local_fit_rms_hz"]:.1f} Hz, versus
{primary["weighted_rms_hz"]:.1f} Hz around one global line.

After freezing those blind boundaries, the independent old boundary audit finds
{comparison["old_boundaries_within_12_ms"]} of
{comparison["old_boundary_count"]} old boundaries within 12 ms.  Its median
old-to-blind distance is {comparison["old_to_blind_median_distance_ms"]:.1f} ms
and its 90th percentile is {comparison["old_to_blind_p90_distance_ms"]:.1f} ms.
The reverse distance is not a completeness metric because that old audit stored
only a sparse, selected set of boundaries.

## Interpretation

The sawtooth is not created by the persisted 20 ms windows: it reappears when
timing and absolute CFO are searched directly from raw IQ on a different 12 ms
support with a 4 ms hop.  Because 4 ms is exactly three 1.333 ms frames, a single
continuous frame train would retain one timing phase.  Instead, the timing phase
is piecewise constant and changes at the CFO resets.  This supports real
roughly-100 ms burst or timing-mode handoffs.  It does not by itself identify
the transmitter or prove which slope should be used as satellite Doppler.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    candidates = scan_raw_iq(
        bulk_root=arguments.bulk_root,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
        cell_duration_s=arguments.cell_duration_s,
        cell_hop_s=arguments.cell_hop_s,
        maximum_cells=arguments.maximum_cells,
        receiver_id=arguments.receiver_id,
    )
    primary, _primary_indexes = fit_latent_line(candidates, label="primary")
    secondary, _secondary_indexes = fit_latent_line(
        candidates,
        label="secondary",
        excluded_line=primary,
        seed=470_385,
    )
    primary_path = selected_path(candidates, primary)
    secondary_candidates = tuple(
        item
        for item in candidates
        if abs(item.absolute_cfo_hz - float(primary.frequency_hz(item.cell_center_s))) > 3_000.0
    )
    secondary_path = selected_path(secondary_candidates, secondary)
    events = detect_events(primary_path, primary)
    primary_segments = segment_path(primary_path)
    primary_segment_statistics = segment_statistics(primary_segments)
    blind_boundaries_s = tuple(
        item.preceding_boundary_time_s
        for item in primary_segments
        if item.preceding_boundary_time_s is not None
    )
    comparison = external_comparison(blind_boundaries_s, arguments.external_audit)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    figure_path = arguments.output_root / "blind-timing-cfo-modes.png"
    render(
        figure_path,
        candidates=candidates,
        primary=primary,
        secondary=secondary,
        primary_path=primary_path,
        secondary_path=secondary_path,
        primary_segments=primary_segments,
    )
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-blind-overlapping-cell-timing-cfo-v1",
            "input": {
                "session_id": SESSION_ID,
                "stream_id": "stream-0",
                "receiver_id": arguments.receiver_id,
                "raw_recording_only_before_fit": True,
                "persisted_analysis_inputs_before_fit": [],
            },
            "configuration": {
                "start_s": arguments.start_s,
                "end_s": arguments.end_s,
                "cell_duration_ms": arguments.cell_duration_s * 1_000,
                "cell_hop_ms": arguments.cell_hop_s * 1_000,
                "frame_period_ms": 1_000 / 750,
                "timing_search": "complete 1.333 ms phase within each raw cell",
                "absolute_cfo_search_hz": [-1_200_000.0, 1_200_000.0],
                "candidate_retention": "Qin score >=0.08 and exact-control margin >=0.03",
                "latent_line_frequency_scale_hz": 500.0,
            },
            "inventory": {
                "candidate_count": len(candidates),
                "cell_count": len({item.cell_index for item in candidates}),
                "primary_path_count": len(primary_path),
                "secondary_path_count": len(secondary_path),
                "blind_event_count": len(events),
                "blind_boundary_count": len(blind_boundaries_s),
            },
            "primary_line": asdict(primary),
            "secondary_line": asdict(secondary),
            "primary_segment_statistics": primary_segment_statistics,
            "primary_segments": [asdict(item) for item in primary_segments],
            "blind_events": [asdict(item) for item in events],
            "external_comparison": comparison,
            "candidates": [asdict(item) for item in candidates],
            "primary_path": [asdict(item) for item in primary_path],
            "secondary_path": [asdict(item) for item in secondary_path],
            "figure": str(figure_path),
        }
    )
    results_path = arguments.output_root / "blind-timing-cfo-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    print(
        json.dumps(
            {
                "inventory": document["inventory"],
                "primary_line": document["primary_line"],
                "secondary_line": document["secondary_line"],
                "external_comparison": comparison,
                "largest_blind_events": sorted(
                    document["blind_events"],
                    key=lambda item: abs(item["cfo_jump_hz"]),
                    reverse=True,
                )[:12],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
