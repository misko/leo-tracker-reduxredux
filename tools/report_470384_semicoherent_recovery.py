#!/usr/bin/env python3
"""Recover weak Qin Doppler lines by pooling frame likelihoods semi-coherently.

The persisted detector makes one GLRT64 decision from each 20 ms probe, while
the earlier frame experiment maximized a separate 300-symbol CFO in every
1.333 ms frame.  This diagnostic keeps the original complex time-domain Qin
matched correlations, gives every frame an independent nuisance phase, and
fits one frequency line across 20, 50, or 100 ms groups.

Even and odd pilot symbols form disjoint fit and validation views spanning the
same frame.  The rolled Qin sequence receives the identical held-out
evaluation.  No inter-frame carrier-phase continuity is assumed and all radio
and persisted analysis inputs are opened read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
DEFAULT_FRAME_RESULTS = Path(
    "reports/figures/2026_08_23_470384_qin_frames_25_45/qin-frame-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_semicoherent_recovery")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_semicoherent_recovery.md")

SAMPLE_RATE_HZ = 2_500_000.0
SYMBOLS = np.arange(2, 302, dtype=int)
RESIDUAL_GRID_HZ = np.arange(-6_000.0, 6_000.0 + 12.5, 25.0)
LINE_OFFSET_GRID_HZ = np.arange(-2_500.0, 2_500.0 + 12.5, 25.0)
COARSE_SLOPE_GRID_HZ_S = np.arange(-12_000.0, 2_000.0 + 250.0, 500.0)
REFINE_SLOPE_STEP_HZ_S = 100.0
MAXIMUM_MODEL_ERROR_HZ = 2_500.0
MAXIMUM_GROUP_GAP_S = 0.055
GROUP_SCALES_MS = (20, 50, 100)
FREQUENCY_SPLIT_GATE_HZ = 250.0
SLOPE_SPLIT_GATE_HZ_S = 1_000.0

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
PURPLE = "#7b65a8"
RED = "#bd5b52"
BRANCH_COLORS = (BLUE, GREEN, PURPLE, RED, "#4e91a8")
SCALE_COLORS = {20: PURPLE, 50: GREEN, 100: BLUE}


@dataclass(frozen=True, slots=True)
class Branch:
    index: int
    label: str
    start_s: float
    end_s: float
    reference_time_s: float
    coefficients_hz: tuple[float, ...]

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        result = np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )
        return float(result) if np.ndim(result) == 0 else result


@dataclass(frozen=True, slots=True)
class Window:
    association_index: int
    branch_index: int
    detection_time_s: float
    probe_sample_start: int
    aligned_sample_start: int
    local_epoch_sample: int
    initial_cfo_hz: float
    glrt_exact_score: float
    glrt_control_score: float
    glrt_margin: float
    selection_model_error_hz: float

    @property
    def analysis_key(self) -> tuple[int, int, float]:
        return (self.probe_sample_start, self.local_epoch_sample, self.initial_cfo_hz)


@dataclass(frozen=True, slots=True)
class FrameLikelihood:
    time_s: float
    nco_cfo_hz: float
    even_exact_power: np.ndarray = field(repr=False)
    even_exact_ceiling: float
    even_control_power: np.ndarray = field(repr=False)
    even_control_ceiling: float
    odd_exact_power: np.ndarray = field(repr=False)
    odd_exact_ceiling: float
    odd_control_power: np.ndarray = field(repr=False)
    odd_control_ceiling: float


@dataclass(frozen=True, slots=True)
class LineEstimate:
    frequency_at_reference_hz: float
    slope_hz_s: float
    reference_time_s: float
    score: float
    frequency_at_boundary: bool
    slope_at_boundary: bool


@dataclass(frozen=True, slots=True)
class GroupFit:
    branch_index: int
    scale_ms: int
    group_index: int
    association_indices: tuple[int, ...]
    window_count: int
    frame_count: int
    start_time_s: float
    end_time_s: float
    reference_time_s: float
    model_frequency_hz: float
    train_frequency_hz: float
    train_slope_hz_s: float
    validation_frequency_hz: float
    validation_slope_hz_s: float
    train_exact_score: float
    train_control_score: float
    train_margin: float
    validation_exact_score: float
    validation_control_score: float
    validation_margin: float
    frequency_split_hz: float
    slope_split_hz_s: float
    frequency_at_boundary: bool
    slope_at_boundary: bool
    reference_segment_index: int | None = None
    reference_frequency_error_hz: float | None = None
    reference_slope_error_hz_s: float | None = None

    @property
    def span_s(self) -> float:
        return self.end_time_s - self.start_time_s

    @property
    def sequence_supported(self) -> bool:
        return self.train_margin > 0.0 and self.validation_margin > 0.0

    @property
    def frequency_repeatable(self) -> bool:
        return self.frequency_split_hz <= FREQUENCY_SPLIT_GATE_HZ

    @property
    def rate_repeatable(self) -> bool:
        return self.slope_split_hz_s <= SLOPE_SPLIT_GATE_HZ_S

    @property
    def qualified(self) -> bool:
        return bool(
            self.sequence_supported
            and self.frequency_repeatable
            and self.rate_repeatable
            and not self.frequency_at_boundary
            and not self.slope_at_boundary
        )

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        result = self.train_frequency_hz + self.train_slope_hz_s * (
            np.asarray(time_s, dtype=float) - self.reference_time_s
        )
        return float(result) if np.ndim(result) == 0 else result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=DEFAULT_FRAME_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--maximum-unique-windows",
        type=int,
        help="bounded development run; omit for the complete selected corpus",
    )
    parser.add_argument(
        "--reuse-results",
        type=Path,
        help="reuse group fits from an earlier result and rerender summaries/figures",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def parse_inputs(document: dict[str, Any]) -> tuple[tuple[Branch, ...], tuple[Window, ...]]:
    """Load the frozen branch/window selection from the prior all-frame pass."""

    metadata = document["input"]
    expected = {
        "session_id": SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "edge": "upper",
    }
    for key, value in expected.items():
        if metadata[key] != value:
            raise ValueError(f"frame evidence has unexpected {key}")
    branches = tuple(
        Branch(
            index=int(item["branch"]["index"]),
            label=str(item["branch"]["label"]),
            start_s=float(item["branch"]["start_s"]),
            end_s=float(item["branch"]["end_s"]),
            reference_time_s=float(item["branch"]["reference_time_s"]),
            coefficients_hz=tuple(float(value) for value in item["branch"]["coefficients_hz"]),
        )
        for item in document["branches"]
    )
    windows = tuple(
        Window(
            association_index=int(item["association_index"]),
            branch_index=int(item["branch_index"]),
            detection_time_s=float(item["detection_time_s"]),
            probe_sample_start=int(item["probe_sample_start"]),
            aligned_sample_start=int(item["aligned_sample_start"]),
            local_epoch_sample=int(item["local_epoch_sample"]),
            initial_cfo_hz=float(item["initial_cfo_hz"]),
            glrt_exact_score=float(item["glrt_exact_score"]),
            glrt_control_score=float(item["glrt_control_score"]),
            glrt_margin=float(item["glrt_margin"]),
            selection_model_error_hz=float(item["selection_model_error_hz"]),
        )
        for item in document["candidate_windows"]
        if float(item["selection_model_error_hz"]) <= MAXIMUM_MODEL_ERROR_HZ
    )
    return branches, windows


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15)


def normalized_frequency_curves(
    values: np.ndarray,
    times_s: np.ndarray,
    symbol_indexes: np.ndarray,
    frequency_grid_hz: np.ndarray = RESIDUAL_GRID_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-frame coherent power curves and their coherent ceilings."""

    correlations = np.asarray(values, dtype=np.complex128)
    moments = np.asarray(times_s, dtype=float)
    indexes = np.asarray(symbol_indexes, dtype=int)
    grid = np.asarray(frequency_grid_hz, dtype=float)
    if correlations.ndim != 2 or moments.shape != correlations.shape:
        raise ValueError("correlation values and times must be matching matrices")
    if indexes.ndim != 1 or not indexes.size or np.any(indexes < 0):
        raise ValueError("symbol indexes must be a nonempty nonnegative vector")
    if indexes[-1] >= correlations.shape[1] or np.any(np.diff(indexes) <= 0):
        raise ValueError("symbol indexes must be ordered and lie inside the correlations")
    if grid.ndim != 1 or len(grid) < 3 or np.any(np.diff(grid) <= 0):
        raise ValueError("frequency grid must be ordered and contain at least three points")
    selected_times = moments[:, indexes]
    lags = selected_times - np.mean(selected_times, axis=1, keepdims=True)
    if not np.allclose(lags, lags[:1], rtol=0.0, atol=2e-12):
        raise ValueError("all frames must share one within-frame symbol geometry")
    selected = correlations[:, indexes]
    phase_bank = np.exp(-2j * np.pi * lags[0, None, :] * grid[:, None])
    amplitudes = selected @ phase_bank.T
    powers = np.abs(amplitudes) ** 2
    ceilings = np.sum(np.abs(selected), axis=1) ** 2
    return np.asarray(powers, dtype=np.float32), np.asarray(ceilings, dtype=float)


def analyze_unique_windows(
    *,
    bulk_root: Path,
    probe_samples: int,
    windows: tuple[Window, ...],
    maximum_unique_windows: int | None,
) -> dict[tuple[int, int, float], tuple[FrameLikelihood, ...]]:
    """Read every unique selected timing lock and retain compact likelihood curves."""

    unique: dict[tuple[int, int, float], Window] = {}
    for window in windows:
        unique.setdefault(window.analysis_key, window)
    items = list(unique.items())
    if maximum_unique_windows is not None:
        if maximum_unique_windows < 1:
            raise ValueError("maximum unique window count must be positive")
        items = items[:maximum_unique_windows]
    even = np.arange(0, len(SYMBOLS), 2, dtype=int)
    odd = np.arange(1, len(SYMBOLS), 2, dtype=int)
    output: dict[tuple[int, int, float], tuple[FrameLikelihood, ...]] = {}
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(SESSION_ID), "stream-0", verify=True)
        for index, (key, window) in enumerate(items, start=1):
            raw = reader.read(window.aligned_sample_start, probe_samples, receiver_ids=(0,))
            iq = _complex_receiver(raw)
            workspace = _conditioned_correlation_workspace(
                iq,
                int(SAMPLE_RATE_HZ),
                0,
                window.initial_cfo_hz,
                edge=StarlinkEdge.UPPER,
                selected_symbols=SYMBOLS,
            )
            exact = workspace.select(SYMBOLS)
            control = workspace.select(SYMBOLS, control=True)
            if not exact.values.size or exact.values.shape != control.values.shape:
                raise ValueError(f"timing lock at {window.detection_time_s:.3f} s has no frames")
            even_exact, even_exact_ceiling = normalized_frequency_curves(
                exact.values, exact.times_s, even
            )
            even_control, even_control_ceiling = normalized_frequency_curves(
                control.values, control.times_s, even
            )
            odd_exact, odd_exact_ceiling = normalized_frequency_curves(
                exact.values, exact.times_s, odd
            )
            odd_control, odd_control_ceiling = normalized_frequency_curves(
                control.values, control.times_s, odd
            )
            absolute_offset_s = window.aligned_sample_start / SAMPLE_RATE_HZ
            output[key] = tuple(
                FrameLikelihood(
                    time_s=float(absolute_offset_s + np.mean(exact.times_s[frame_index])),
                    nco_cfo_hz=window.initial_cfo_hz,
                    even_exact_power=even_exact[frame_index],
                    even_exact_ceiling=float(even_exact_ceiling[frame_index]),
                    even_control_power=even_control[frame_index],
                    even_control_ceiling=float(even_control_ceiling[frame_index]),
                    odd_exact_power=odd_exact[frame_index],
                    odd_exact_ceiling=float(odd_exact_ceiling[frame_index]),
                    odd_control_power=odd_control[frame_index],
                    odd_control_ceiling=float(odd_control_ceiling[frame_index]),
                )
                for frame_index in range(exact.values.shape[0])
            )
            if index % 50 == 0 or index == len(items):
                print(
                    f"computed likelihood curves for {index}/{len(items)} unique locks",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()
    return output


def _curve_fields(
    split: Literal["even", "odd"], sequence: Literal["exact", "control"]
) -> tuple[str, str]:
    return f"{split}_{sequence}_power", f"{split}_{sequence}_ceiling"


def _sample_uniform_curves(
    curves: np.ndarray,
    frequencies_hz: np.ndarray,
    frequency_grid_hz: np.ndarray = RESIDUAL_GRID_HZ,
) -> np.ndarray:
    """Linearly sample one uniform curve per row at a matching target matrix."""

    values = np.asarray(curves, dtype=float)
    targets = np.asarray(frequencies_hz, dtype=float)
    grid = np.asarray(frequency_grid_hz, dtype=float)
    if values.ndim != 2 or targets.ndim != 2 or values.shape[0] != targets.shape[0]:
        raise ValueError("curves and targets must be row-aligned matrices")
    step = float(grid[1] - grid[0])
    if not np.allclose(np.diff(grid), step, rtol=0.0, atol=1e-12):
        raise ValueError("frequency curve grid must be uniform")
    positions = (targets - grid[0]) / step
    valid = (positions >= 0.0) & (positions <= len(grid) - 1)
    lower = np.clip(np.floor(positions).astype(int), 0, len(grid) - 2)
    fraction = np.clip(positions - lower, 0.0, 1.0)
    rows = np.arange(values.shape[0])[:, None]
    sampled = values[rows, lower] * (1.0 - fraction) + values[rows, lower + 1] * fraction
    return np.where(valid, sampled, 0.0)


def line_score(
    frames: tuple[FrameLikelihood, ...],
    *,
    split: Literal["even", "odd"],
    sequence: Literal["exact", "control"],
    reference_time_s: float,
    frequencies_at_reference_hz: np.ndarray,
    slope_hz_s: float,
) -> np.ndarray:
    """Evaluate one slope for a vector of intercepts with frame phases removed."""

    if not frames:
        raise ValueError("line score requires at least one frame")
    power_field, ceiling_field = _curve_fields(split, sequence)
    curves = np.stack([getattr(frame, power_field) for frame in frames])
    ceilings = np.asarray([getattr(frame, ceiling_field) for frame in frames], dtype=float)
    times = np.asarray([frame.time_s for frame in frames], dtype=float)
    ncos = np.asarray([frame.nco_cfo_hz for frame in frames], dtype=float)
    intercepts = np.asarray(frequencies_at_reference_hz, dtype=float)
    targets = intercepts[None, :] + slope_hz_s * (times[:, None] - reference_time_s) - ncos[:, None]
    sampled = _sample_uniform_curves(curves, targets)
    denominator = float(np.sum(ceilings))
    return np.sum(sampled, axis=0) / max(denominator, 1e-20)


def fit_likelihood_line(
    frames: tuple[FrameLikelihood, ...],
    *,
    branch: Branch,
    split: Literal["even", "odd"],
) -> LineEstimate:
    """Fit one absolute-frequency line to a disjoint symbol split."""

    if len(frames) < 3:
        raise ValueError("likelihood line fit requires at least three frames")
    reference_time_s = float(np.mean([frame.time_s for frame in frames]))
    model_frequency_hz = float(branch.frequency_hz(reference_time_s))
    intercepts = model_frequency_hz + LINE_OFFSET_GRID_HZ

    def search(slopes: np.ndarray) -> tuple[float, float, float]:
        best_score = -math.inf
        best_frequency = math.nan
        best_slope = math.nan
        for slope in slopes:
            scores = line_score(
                frames,
                split=split,
                sequence="exact",
                reference_time_s=reference_time_s,
                frequencies_at_reference_hz=intercepts,
                slope_hz_s=float(slope),
            )
            position = int(np.argmax(scores))
            if float(scores[position]) > best_score:
                best_score = float(scores[position])
                best_frequency = float(intercepts[position])
                best_slope = float(slope)
        return best_frequency, best_slope, best_score

    coarse_frequency, coarse_slope, _coarse_score = search(COARSE_SLOPE_GRID_HZ_S)
    refined_slopes = np.arange(
        max(float(COARSE_SLOPE_GRID_HZ_S[0]), coarse_slope - 500.0),
        min(float(COARSE_SLOPE_GRID_HZ_S[-1]), coarse_slope + 500.0) + 0.5 * REFINE_SLOPE_STEP_HZ_S,
        REFINE_SLOPE_STEP_HZ_S,
    )
    frequency, slope, score = search(refined_slopes)
    return LineEstimate(
        frequency_at_reference_hz=frequency,
        slope_hz_s=slope,
        reference_time_s=reference_time_s,
        score=score,
        frequency_at_boundary=bool(
            abs(frequency - model_frequency_hz) >= float(np.max(np.abs(LINE_OFFSET_GRID_HZ))) - 1e-9
        ),
        slope_at_boundary=bool(
            slope <= float(COARSE_SLOPE_GRID_HZ_S[0]) + 1e-9
            or slope >= float(COARSE_SLOPE_GRID_HZ_S[-1]) - 1e-9
        ),
    )


def _evaluate_line(
    frames: tuple[FrameLikelihood, ...],
    fit: LineEstimate,
    *,
    split: Literal["even", "odd"],
    sequence: Literal["exact", "control"],
) -> float:
    return float(
        line_score(
            frames,
            split=split,
            sequence=sequence,
            reference_time_s=fit.reference_time_s,
            frequencies_at_reference_hz=np.asarray([fit.frequency_at_reference_hz]),
            slope_hz_s=fit.slope_hz_s,
        )[0]
    )


def build_window_groups(
    windows: tuple[Window, ...],
    likelihoods: dict[tuple[int, int, float], tuple[FrameLikelihood, ...]],
    *,
    scale_ms: int,
) -> tuple[tuple[Window, ...], ...]:
    """Return sliding consecutive groups whose actual frame span fits the scale."""

    if scale_ms not in GROUP_SCALES_MS:
        raise ValueError(f"unsupported semi-coherent scale: {scale_ms}")
    available = tuple(window for window in windows if window.analysis_key in likelihoods)
    ordered = tuple(sorted(available, key=lambda item: item.detection_time_s))
    if scale_ms == 20:
        return tuple((window,) for window in ordered)
    maximum_span_s = scale_ms / 1_000.0
    groups: list[tuple[Window, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for start in range(len(ordered)):
        members = [ordered[start]]
        first_frames = likelihoods[ordered[start].analysis_key]
        group_start = first_frames[0].time_s
        previous_time = ordered[start].detection_time_s
        for candidate in ordered[start + 1 :]:
            gap = candidate.detection_time_s - previous_time
            if gap > MAXIMUM_GROUP_GAP_S:
                break
            candidate_frames = likelihoods[candidate.analysis_key]
            if candidate_frames[-1].time_s - group_start > maximum_span_s + 1e-9:
                break
            members.append(candidate)
            previous_time = candidate.detection_time_s
        if len(members) < 2:
            continue
        key = tuple(item.association_index for item in members)
        if key not in seen:
            seen.add(key)
            groups.append(tuple(members))
    return tuple(groups)


def fit_groups(
    *,
    branches: tuple[Branch, ...],
    windows: tuple[Window, ...],
    likelihoods: dict[tuple[int, int, float], tuple[FrameLikelihood, ...]],
) -> tuple[GroupFit, ...]:
    """Fit and disjointly validate every requested branch/scale group."""

    output: list[GroupFit] = []
    for branch in branches:
        branch_windows = tuple(item for item in windows if item.branch_index == branch.index)
        for scale_ms in GROUP_SCALES_MS:
            groups = build_window_groups(branch_windows, likelihoods, scale_ms=scale_ms)
            for members in groups:
                frames = tuple(
                    frame for window in members for frame in likelihoods[window.analysis_key]
                )
                train = fit_likelihood_line(frames, branch=branch, split="even")
                validation = fit_likelihood_line(frames, branch=branch, split="odd")
                train_control = _evaluate_line(frames, train, split="even", sequence="control")
                validation_exact = _evaluate_line(frames, train, split="odd", sequence="exact")
                validation_control = _evaluate_line(frames, train, split="odd", sequence="control")
                output.append(
                    GroupFit(
                        branch_index=branch.index,
                        scale_ms=scale_ms,
                        group_index=len(output),
                        association_indices=tuple(item.association_index for item in members),
                        window_count=len(members),
                        frame_count=len(frames),
                        start_time_s=frames[0].time_s,
                        end_time_s=frames[-1].time_s,
                        reference_time_s=train.reference_time_s,
                        model_frequency_hz=float(branch.frequency_hz(train.reference_time_s)),
                        train_frequency_hz=train.frequency_at_reference_hz,
                        train_slope_hz_s=train.slope_hz_s,
                        validation_frequency_hz=validation.frequency_at_reference_hz,
                        validation_slope_hz_s=validation.slope_hz_s,
                        train_exact_score=train.score,
                        train_control_score=train_control,
                        train_margin=train.score - train_control,
                        validation_exact_score=validation_exact,
                        validation_control_score=validation_control,
                        validation_margin=validation_exact - validation_control,
                        frequency_split_hz=abs(
                            train.frequency_at_reference_hz - validation.frequency_at_reference_hz
                        ),
                        slope_split_hz_s=abs(train.slope_hz_s - validation.slope_hz_s),
                        frequency_at_boundary=(
                            train.frequency_at_boundary or validation.frequency_at_boundary
                        ),
                        slope_at_boundary=train.slope_at_boundary or validation.slope_at_boundary,
                    )
                )
            print(f"fit {len(groups)} {scale_ms} ms groups for {branch.label}", flush=True)
    return tuple(output)


def _coherent_reference_segments(
    frame_document: dict[str, Any], branch_index: int
) -> tuple[dict[str, Any], ...]:
    summary = next(
        item for item in frame_document["branches"] if int(item["branch"]["index"]) == branch_index
    )
    fit = summary["fit"]
    if fit.get("status") != "complete":
        return ()
    return tuple(
        segment
        for segment in fit["segments"]
        if float(segment["end_time_s"]) - float(segment["start_time_s"]) >= 0.020
        and float(segment["raw_rms_hz"]) <= 40.0
    )


def attach_reference_errors(
    groups: tuple[GroupFit, ...], frame_document: dict[str, Any]
) -> tuple[GroupFit, ...]:
    """Compare only groups fully contained by a later strong-frame segment."""

    output = []
    references = {
        branch_index: _coherent_reference_segments(frame_document, branch_index)
        for branch_index in range(len(frame_document["branches"]))
    }
    for group in groups:
        matches = [
            (index, segment)
            for index, segment in enumerate(references[group.branch_index])
            if group.start_time_s >= float(segment["start_time_s"]) - 0.002
            and group.end_time_s <= float(segment["end_time_s"]) + 0.002
        ]
        if not matches:
            output.append(group)
            continue
        index, segment = min(
            matches,
            key=lambda item: float(item[1]["end_time_s"]) - float(item[1]["start_time_s"]),
        )
        reference_frequency = float(segment["intercept_hz"]) + float(segment["slope_hz_s"]) * (
            group.reference_time_s - float(segment["center_time_s"])
        )
        output.append(
            GroupFit(
                **{
                    **asdict(group),
                    "reference_segment_index": index,
                    "reference_frequency_error_hz": group.train_frequency_hz - reference_frequency,
                    "reference_slope_error_hz_s": group.train_slope_hz_s
                    - float(segment["slope_hz_s"]),
                }
            )
        )
    return tuple(output)


def _percentiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=float)
    return {
        "p10": float(np.percentile(array, 10)),
        "p25": float(np.percentile(array, 25)),
        "median": float(np.median(array)),
        "p75": float(np.percentile(array, 75)),
        "p90": float(np.percentile(array, 90)),
    }


def summarize_groups(
    branches: tuple[Branch, ...], groups: tuple[GroupFit, ...]
) -> tuple[dict[str, Any], ...]:
    summaries = []
    for branch in branches:
        by_scale = []
        for scale_ms in GROUP_SCALES_MS:
            values = tuple(
                item
                for item in groups
                if item.branch_index == branch.index and item.scale_ms == scale_ms
            )
            referenced = tuple(
                item for item in values if item.reference_frequency_error_hz is not None
            )
            by_scale.append(
                {
                    "scale_ms": scale_ms,
                    "group_count": len(values),
                    "actual_span_s": _percentiles([item.span_s for item in values]),
                    "window_count": _percentiles([float(item.window_count) for item in values]),
                    "frame_count": _percentiles([float(item.frame_count) for item in values]),
                    "train_exact": _percentiles([item.train_exact_score for item in values]),
                    "train_control": _percentiles([item.train_control_score for item in values]),
                    "train_margin": _percentiles([item.train_margin for item in values]),
                    "validation_exact": _percentiles(
                        [item.validation_exact_score for item in values]
                    ),
                    "validation_control": _percentiles(
                        [item.validation_control_score for item in values]
                    ),
                    "validation_margin": _percentiles([item.validation_margin for item in values]),
                    "sequence_supported_fraction": float(
                        np.mean([item.sequence_supported for item in values])
                    )
                    if values
                    else 0.0,
                    "frequency_repeatable_fraction": float(
                        np.mean([item.frequency_repeatable for item in values])
                    )
                    if values
                    else 0.0,
                    "rate_repeatable_fraction": float(
                        np.mean([item.rate_repeatable for item in values])
                    )
                    if values
                    else 0.0,
                    "qualified_fraction": float(np.mean([item.qualified for item in values]))
                    if values
                    else 0.0,
                    "frequency_split_hz": _percentiles(
                        [item.frequency_split_hz for item in values]
                    ),
                    "slope_split_hz_s": _percentiles([item.slope_split_hz_s for item in values]),
                    "frequency_boundary_fraction": float(
                        np.mean([item.frequency_at_boundary for item in values])
                    )
                    if values
                    else 0.0,
                    "slope_boundary_fraction": float(
                        np.mean([item.slope_at_boundary for item in values])
                    )
                    if values
                    else 0.0,
                    "reference_comparison": {
                        "group_count": len(referenced),
                        "absolute_frequency_error_hz": _percentiles(
                            [abs(float(item.reference_frequency_error_hz)) for item in referenced]
                        ),
                        "absolute_slope_error_hz_s": _percentiles(
                            [abs(float(item.reference_slope_error_hz_s)) for item in referenced]
                        ),
                    },
                }
            )
        summaries.append(
            {
                "branch_index": branch.index,
                "branch_label": branch.label,
                "scales": by_scale,
            }
        )
    return tuple(summaries)


def summarize_baselines(
    branches: tuple[Branch, ...],
    windows: tuple[Window, ...],
    frame_document: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Summarize the persisted GLRT and independent-frame decision stages."""

    rows_by_association: dict[int, list[dict[str, Any]]] = {}
    for row in frame_document["frames"]:
        rows_by_association.setdefault(int(row["association_index"]), []).append(row)
    output = []
    for branch in branches:
        branch_windows = tuple(item for item in windows if item.branch_index == branch.index)
        rows = tuple(
            row
            for window in branch_windows
            for row in rows_by_association[window.association_index]
        )
        frame_margin = np.asarray(
            [float(item["exact_coherence"]) - float(item["control_coherence"]) for item in rows]
        )
        frame_exact = np.asarray([float(item["exact_coherence"]) for item in rows])
        output.append(
            {
                "branch_index": branch.index,
                "branch_label": branch.label,
                "window_count": len(branch_windows),
                "frame_count": len(rows),
                "glrt_margin": _percentiles([item.glrt_margin for item in branch_windows]),
                "glrt_positive_margin_fraction": float(
                    np.mean([item.glrt_margin > 0.0 for item in branch_windows])
                ),
                "frame_positive_margin_fraction": float(np.mean(frame_margin > 0.0)),
                "frame_strong_gate_fraction": float(
                    np.mean((frame_margin > 0.0) & (frame_exact >= 0.02))
                ),
            }
        )
    return tuple(output)


def _rows_by_branch(
    frame_document: dict[str, Any], branch_index: int
) -> tuple[dict[str, Any], ...]:
    return tuple(
        item for item in frame_document["frames"] if int(item["branch_index"]) == branch_index
    )


def _greedy_nonoverlapping(groups: tuple[GroupFit, ...]) -> tuple[GroupFit, ...]:
    selected = []
    stop = -math.inf
    for group in sorted(groups, key=lambda item: (item.start_time_s, -item.train_margin)):
        if group.start_time_s >= stop + 0.002:
            selected.append(group)
            stop = group.end_time_s
    return tuple(selected)


def render_time_comparison(
    path: Path,
    *,
    branches: tuple[Branch, ...],
    windows: tuple[Window, ...],
    groups: tuple[GroupFit, ...],
    frame_document: dict[str, Any],
) -> None:
    figure = Figure(figsize=(18, 15), constrained_layout=True)
    axes = figure.subplots(len(branches), 1, sharex=True, sharey=True)
    figure.suptitle(
        "Semi-coherent Qin line recovery · independent frames versus pooled likelihoods",
        fontsize=22,
        color=INK,
        fontweight="bold",
    )
    for axis, branch in zip(axes, branches, strict=True):
        rows = _rows_by_branch(frame_document, branch.index)
        axis.scatter(
            [float(item["reference_time_s"]) for item in rows],
            [float(item["residual_cfo_hz"]) for item in rows],
            s=5,
            color=GRAY,
            alpha=0.16,
            linewidths=0,
            rasterized=True,
        )
        branch_windows = tuple(item for item in windows if item.branch_index == branch.index)
        axis.scatter(
            [item.detection_time_s for item in branch_windows],
            [
                item.initial_cfo_hz - float(branch.frequency_hz(item.detection_time_s))
                for item in branch_windows
            ],
            s=15,
            color=AMBER,
            alpha=0.55,
            linewidths=0,
            zorder=2,
        )
        for scale_ms in (50, 100):
            candidates = tuple(
                item
                for item in groups
                if item.branch_index == branch.index
                and item.scale_ms == scale_ms
                and item.sequence_supported
                and item.frequency_repeatable
            )
            for group in _greedy_nonoverlapping(candidates):
                times = np.asarray([group.start_time_s, group.end_time_s])
                residual = np.asarray(group.frequency_hz(times)) - np.asarray(
                    branch.frequency_hz(times)
                )
                axis.plot(
                    times,
                    residual,
                    color=SCALE_COLORS[scale_ms],
                    linewidth=2.3 if group.rate_repeatable else 1.0,
                    alpha=0.9 if group.rate_repeatable else 0.3,
                    solid_capstyle="round",
                    zorder=4,
                )
        axis.axhline(0.0, color=INK, linewidth=0.8, alpha=0.65)
        axis.set_ylim(-2_500, 2_500)
        axis.set_ylabel("CFO − branch\nmodel (Hz)", color=INK)
        axis.set_title(branch.label, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[-1].set_xlim(25.0, 45.0)
    axes[0].legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                color=GRAY,
                alpha=0.5,
                label="independent 1.333 ms CFO",
            ),
            Line2D([], [], marker="o", linestyle="", color=AMBER, label="persisted 20 ms GLRT CFO"),
            Line2D([], [], color=GREEN, linewidth=2, label="≤50 ms semi-coherent line"),
            Line2D([], [], color=BLUE, linewidth=2, label="≤100 ms semi-coherent line"),
        ],
        loc="upper right",
        ncol=2,
        frameon=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170)


def render_statistical_comparison(
    path: Path,
    *,
    summaries: tuple[dict[str, Any], ...],
    baselines: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(17, 11), constrained_layout=True)
    axes = figure.subplots(2, 2)
    figure.suptitle(
        "What pooling changes · disjoint-symbol validation and parameter repeatability",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    x = np.arange(len(summaries), dtype=float)
    width = 0.22
    baseline_series = (
        (
            "1.333 ms Qin > control",
            [100 * item["frame_positive_margin_fraction"] for item in baselines],
            GRAY,
        ),
        (
            "1.333 ms strong gate",
            [100 * item["frame_strong_gate_fraction"] for item in baselines],
            AMBER,
        ),
        (
            "≤50 ms held-out support",
            [
                100
                * next(item for item in branch["scales"] if item["scale_ms"] == 50)[
                    "sequence_supported_fraction"
                ]
                for branch in summaries
            ],
            GREEN,
        ),
        (
            "≤100 ms held-out support",
            [
                100
                * next(item for item in branch["scales"] if item["scale_ms"] == 100)[
                    "sequence_supported_fraction"
                ]
                for branch in summaries
            ],
            BLUE,
        ),
    )
    comparison_width = 0.18
    for position, (label, values, color) in enumerate(baseline_series):
        axes[0, 0].bar(
            x + (position - 1.5) * comparison_width,
            values,
            width=comparison_width,
            color=color,
            alpha=0.86,
            label=label,
        )
    for position, scale_ms in enumerate(GROUP_SCALES_MS):
        offset = (position - 1) * width
        entries = [
            next(item for item in branch["scales"] if item["scale_ms"] == scale_ms)
            for branch in summaries
        ]
        axes[0, 1].bar(
            x + offset,
            [100 * item["qualified_fraction"] for item in entries],
            width=width,
            color=SCALE_COLORS[scale_ms],
            alpha=0.86,
        )
        freq_medians = [
            math.nan if item["frequency_split_hz"] is None else item["frequency_split_hz"]["median"]
            for item in entries
        ]
        freq_p90 = [
            math.nan if item["frequency_split_hz"] is None else item["frequency_split_hz"]["p90"]
            for item in entries
        ]
        axes[1, 0].errorbar(
            x + offset,
            freq_medians,
            yerr=[
                np.zeros(len(entries)),
                np.maximum(0.0, np.asarray(freq_p90) - np.asarray(freq_medians)),
            ],
            fmt="o",
            color=SCALE_COLORS[scale_ms],
            capsize=3,
        )
        slope_medians = [
            math.nan if item["slope_split_hz_s"] is None else item["slope_split_hz_s"]["median"]
            for item in entries
        ]
        slope_p90 = [
            math.nan if item["slope_split_hz_s"] is None else item["slope_split_hz_s"]["p90"]
            for item in entries
        ]
        axes[1, 1].errorbar(
            x + offset,
            slope_medians,
            yerr=[
                np.zeros(len(entries)),
                np.maximum(0.0, np.asarray(slope_p90) - np.asarray(slope_medians)),
            ],
            fmt="o",
            color=SCALE_COLORS[scale_ms],
            capsize=3,
        )
    labels = [item["branch_label"].split(" · ")[0] for item in summaries]
    titles = (
        "A · Detection survives; the independent strong-frame gate does not",
        "B · Semi-coherent sequence + CFO + Doppler-rate repeatability",
        "C · Even/odd center-CFO disagreement",
        "D · Even/odd Doppler-rate disagreement",
    )
    ylabels = ("supported groups (%)", "qualified groups (%)", "|Δ CFO| (Hz)", "|Δ rate| (Hz/s)")
    for axis, title, ylabel in zip(axes.flat, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.set_xticks(x, labels)
        axis.grid(True, axis="y", alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0, 0].set_ylim(0, 105)
    axes[0, 1].set_ylim(0, 105)
    axes[1, 0].axhline(FREQUENCY_SPLIT_GATE_HZ, color=INK, linewidth=1, linestyle="--", alpha=0.6)
    axes[1, 1].axhline(SLOPE_SPLIT_GATE_HZ_S, color=INK, linewidth=1, linestyle="--", alpha=0.6)
    axes[1, 0].set_yscale("symlog", linthresh=25)
    axes[1, 1].set_yscale("symlog", linthresh=100)
    axes[0, 0].legend(loc="lower right", ncol=2, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_early_late_zoom(
    path: Path,
    *,
    branches: tuple[Branch, ...],
    windows: tuple[Window, ...],
    groups: tuple[GroupFit, ...],
    frame_document: dict[str, Any],
) -> None:
    selections = ((2, 29.75, 30.35, "early B3"), (3, 35.75, 36.35, "later B4"))
    figure = Figure(figsize=(18, 9), constrained_layout=True)
    axes = figure.subplots(2, 1, sharey=True)
    figure.suptitle(
        "Same estimator before and after the strong full-frame transition",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    for axis, (branch_index, start_s, end_s, title) in zip(axes, selections, strict=True):
        branch = branches[branch_index]
        rows = tuple(
            item
            for item in _rows_by_branch(frame_document, branch_index)
            if start_s <= float(item["reference_time_s"]) <= end_s
        )
        axis.scatter(
            [float(item["reference_time_s"]) for item in rows],
            [float(item["residual_cfo_hz"]) for item in rows],
            s=12,
            color=GRAY,
            alpha=0.25,
            linewidths=0,
            rasterized=True,
        )
        selected_windows = tuple(
            item
            for item in windows
            if item.branch_index == branch_index and start_s <= item.detection_time_s <= end_s
        )
        axis.scatter(
            [item.detection_time_s for item in selected_windows],
            [
                item.initial_cfo_hz - float(branch.frequency_hz(item.detection_time_s))
                for item in selected_windows
            ],
            marker="x",
            s=30,
            color=AMBER,
            alpha=0.75,
            linewidths=1.2,
            zorder=3,
        )
        for scale_ms in (50, 100):
            candidates = tuple(
                item
                for item in groups
                if item.branch_index == branch_index
                and item.scale_ms == scale_ms
                and item.end_time_s >= start_s
                and item.start_time_s <= end_s
                and item.sequence_supported
                and item.frequency_repeatable
            )
            for group in _greedy_nonoverlapping(candidates):
                times = np.asarray([max(start_s, group.start_time_s), min(end_s, group.end_time_s)])
                residual = np.asarray(group.frequency_hz(times)) - np.asarray(
                    branch.frequency_hz(times)
                )
                axis.plot(
                    times,
                    residual,
                    color=SCALE_COLORS[scale_ms],
                    linewidth=3 if group.rate_repeatable else 1.2,
                    alpha=0.95 if group.rate_repeatable else 0.35,
                    zorder=4,
                )
        for segment in _coherent_reference_segments(frame_document, branch_index):
            if float(segment["end_time_s"]) < start_s or float(segment["start_time_s"]) > end_s:
                continue
            times = np.asarray([float(segment["start_time_s"]), float(segment["end_time_s"])])
            absolute = float(segment["intercept_hz"]) + float(segment["slope_hz_s"]) * (
                times - float(segment["center_time_s"])
            )
            axis.plot(
                times,
                absolute - np.asarray(branch.frequency_hz(times)),
                color=INK,
                linewidth=1.4,
                alpha=0.8,
                zorder=5,
            )
        axis.axhline(0.0, color=INK, linewidth=0.8, alpha=0.5)
        axis.set_xlim(start_s, end_s)
        axis.set_ylim(-1_800, 1_800)
        axis.set_ylabel("CFO − branch model (Hz)", color=INK)
        axis.set_title(
            f"{title} · {branch.label}",
            loc="left",
            fontsize=13,
            color=INK,
            fontweight="bold",
        )
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[0].legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color=GRAY, label="1.333 ms frame CFO"),
            Line2D([], [], marker="x", linestyle="", color=AMBER, label="20 ms GLRT CFO"),
            Line2D([], [], color=GREEN, linewidth=2.5, label="≤50 ms semi-coherent"),
            Line2D([], [], color=BLUE, linewidth=2.5, label="≤100 ms semi-coherent"),
            Line2D([], [], color=INK, linewidth=1.5, label="strong-frame batch reference"),
        ],
        loc="upper right",
        ncol=3,
        frameon=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, results: dict[str, Any]) -> None:
    summaries = results["branch_summaries"]
    baselines = results["baseline_summaries"]
    rows = []
    for branch in summaries:
        for scale in branch["scales"]:
            margin = scale["validation_margin"]
            frequency = scale["frequency_split_hz"]
            slope = scale["slope_split_hz_s"]
            rows.append(
                "| {branch} | {scale} | {count} | {support:.1f}% | {qualified:.1f}% | "
                "{margin} | {frequency} | {slope} |".format(
                    branch=branch["branch_label"],
                    scale=scale["scale_ms"],
                    count=scale["group_count"],
                    support=100 * scale["sequence_supported_fraction"],
                    qualified=100 * scale["qualified_fraction"],
                    margin="—" if margin is None else f"{margin['median']:.4f}",
                    frequency="—" if frequency is None else f"{frequency['median']:.0f}",
                    slope="—" if slope is None else f"{slope['median']:.0f}",
                )
            )
    reference_rows = []
    for branch in summaries:
        for scale in branch["scales"]:
            reference = scale["reference_comparison"]
            if not reference["group_count"]:
                continue
            frequency = reference["absolute_frequency_error_hz"]
            slope = reference["absolute_slope_error_hz_s"]
            reference_rows.append(
                "| {branch} | {scale} | {count} | {frequency:.0f} | {slope:.0f} |".format(
                    branch=branch["branch_label"],
                    scale=scale["scale_ms"],
                    count=reference["group_count"],
                    frequency=frequency["median"],
                    slope=slope["median"],
                )
            )
    figures = {
        key: os.path.relpath(value, path.parent) for key, value in results["figures"].items()
    }
    baseline_rows = []
    for baseline, branch in zip(baselines, summaries, strict=True):
        scale50 = next(item for item in branch["scales"] if item["scale_ms"] == 50)
        scale100 = next(item for item in branch["scales"] if item["scale_ms"] == 100)
        glrt_margin = baseline["glrt_margin"]
        baseline_rows.append(
            "| {branch} | {glrt:.3f} | {positive:.1f}% | {strong:.1f}% | "
            "{support50:.1f}% / {qualified50:.1f}% | "
            "{support100:.1f}% / {qualified100:.1f}% |".format(
                branch=branch["branch_label"],
                glrt=math.nan if glrt_margin is None else glrt_margin["median"],
                positive=100 * baseline["frame_positive_margin_fraction"],
                strong=100 * baseline["frame_strong_gate_fraction"],
                support50=100 * scale50["sequence_supported_fraction"],
                qualified50=100 * scale50["qualified_fraction"],
                support100=100 * scale100["sequence_supported_fraction"],
                qualified100=100 * scale100["qualified_fraction"],
            )
        )
    text = f"""# Semi-coherent recovery of weak Qin Doppler lines

## Result

This experiment returns to the original complex Qin matched correlations.  It
fits one absolute-frequency line across 20, 50, and 100 ms groups while
maximizing over an independent complex phase in every 1.333 ms frame.  Even
pilot symbols fit the line; odd symbols validate it.  The 17-symbol-rolled Qin
control is evaluated at exactly the fitted line, and no inter-frame phase
continuity is used.

![Time comparison]({figures["time_comparison"]})

![Statistical comparison]({figures["statistics"]})

![Early and late zoom]({figures["zoom"]})

## What changed from the earlier estimator

The sequence-specific evidence was never absent: exact Qin already beat the
rolled control in most independent early frames.  What failed was the separate
`exact >= 0.02` strength cut and, after that, frame-by-frame Doppler-rate
repeatability.  Pooling the original complex correlations restores the held-out
sequence test first and improves rate repeatability as the time support grows.

The semi-coherent columns are `held-out supported / repeatability-qualified`.

| branch | median GLRT margin | frame Qin>ctrl | frame strong gate | <=50 ms | <=100 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(baseline_rows)}

## Disjoint-symbol statistics

`supported` means exact Qin beats the rolled control in both the fit and held-out
symbols.  `qualified` additionally requires even/odd center CFO agreement within
{FREQUENCY_SPLIT_GATE_HZ:.0f} Hz, Doppler-rate agreement within
{SLOPE_SPLIT_GATE_HZ_S:.0f} Hz/s, and neither solution at a search boundary.
The groups overlap, so these are descriptive fractions rather than independent
trial p-values.

| branch | scale | groups | supported | qualified | held-out margin | ΔCFO | Δrate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Concordance with the later strong-frame ramps

For B4 and B5 only, a comparison is made when an entire semi-coherent group is
contained within one previously recovered 40 Hz-RMS frame segment.  These
segments are a useful internal reference, not independent truth.

| branch | scale (ms) | referenced groups | median |CFO error| (Hz) | median |rate error| (Hz/s) |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(reference_rows)}

Fixed 100 ms groups can cross a sawtooth reset.  In that case the even and odd
symbols may agree on a reproducible **window-average** rate that is not the
within-tooth Doppler rate.  The reference table avoids that ambiguity by using
only groups fully contained in one independently recovered tooth.  Adaptive
reset segmentation remains the next step for turning every supported group
into a physical sawtooth segment.

## Interpretation boundary

The semi-coherent statistic answers whether a common frequency line is present
without demanding carrier-phase continuity between frames.  A positive
exact-versus-control margin recovers sequence-specific evidence.  Agreement of
the even/odd fits is the separate test that the data identify the line's CFO and
rate.  Neither test assigns a satellite or resolves the receiver's absolute LNB
offset.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    document = _load(arguments.frame_results)
    branches, windows = parse_inputs(document)
    if arguments.reuse_results is None:
        likelihoods = analyze_unique_windows(
            bulk_root=arguments.bulk_root,
            probe_samples=int(document["configuration"].get("probe_samples", 50_000)),
            windows=windows,
            maximum_unique_windows=arguments.maximum_unique_windows,
        )
        available_windows = tuple(item for item in windows if item.analysis_key in likelihoods)
        groups = fit_groups(branches=branches, windows=available_windows, likelihoods=likelihoods)
        groups = attach_reference_errors(groups, document)
        unique_computed_window_count = len(likelihoods)
        computed_frame_count = sum(len(item) for item in likelihoods.values())
    else:
        reused = _load(arguments.reuse_results)
        if reused["input"]["session_id"] != SESSION_ID:
            raise ValueError("reused semi-coherent results belong to another capture")
        group_fields = {item.name for item in fields(GroupFit)}
        groups = tuple(
            GroupFit(**{key: value for key, value in item.items() if key in group_fields})
            for item in reused["groups"]
        )
        available_windows = windows
        unique_computed_window_count = int(reused["inventory"]["unique_computed_window_count"])
        computed_frame_count = int(reused["inventory"]["computed_frame_count"])
    summaries = summarize_groups(branches, groups)
    baselines = summarize_baselines(branches, available_windows, document)

    arguments.output_root.mkdir(parents=True, exist_ok=True)
    time_path = arguments.output_root / "semicoherent-recovery-time.png"
    statistics_path = arguments.output_root / "semicoherent-recovery-statistics.png"
    zoom_path = arguments.output_root / "semicoherent-recovery-early-late-zoom.png"
    render_time_comparison(
        time_path,
        branches=branches,
        windows=available_windows,
        groups=groups,
        frame_document=document,
    )
    render_statistical_comparison(statistics_path, summaries=summaries, baselines=baselines)
    render_early_late_zoom(
        zoom_path,
        branches=branches,
        windows=available_windows,
        groups=groups,
        frame_document=document,
    )
    results = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-semi-coherent-qin-line-v1",
            "input": {
                "session_id": SESSION_ID,
                "frame_results": str(arguments.frame_results),
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
            },
            "configuration": {
                "fit_symbols": "even symbols 2..301",
                "validation_symbols": "odd symbols 2..301",
                "frame_phase_policy": "independent nuisance phase per frame",
                "group_scales_ms": GROUP_SCALES_MS,
                "residual_frequency_grid_hz": [
                    float(RESIDUAL_GRID_HZ[0]),
                    float(RESIDUAL_GRID_HZ[-1]),
                    float(RESIDUAL_GRID_HZ[1] - RESIDUAL_GRID_HZ[0]),
                ],
                "line_offset_grid_hz": [
                    float(LINE_OFFSET_GRID_HZ[0]),
                    float(LINE_OFFSET_GRID_HZ[-1]),
                    float(LINE_OFFSET_GRID_HZ[1] - LINE_OFFSET_GRID_HZ[0]),
                ],
                "slope_grid_hz_s": [
                    float(COARSE_SLOPE_GRID_HZ_S[0]),
                    float(COARSE_SLOPE_GRID_HZ_S[-1]),
                    float(COARSE_SLOPE_GRID_HZ_S[1] - COARSE_SLOPE_GRID_HZ_S[0]),
                    REFINE_SLOPE_STEP_HZ_S,
                ],
                "maximum_model_error_hz": MAXIMUM_MODEL_ERROR_HZ,
                "maximum_group_gap_s": MAXIMUM_GROUP_GAP_S,
                "frequency_split_gate_hz": FREQUENCY_SPLIT_GATE_HZ,
                "slope_split_gate_hz_s": SLOPE_SPLIT_GATE_HZ_S,
            },
            "inventory": {
                "model_proximate_branch_window_count": len(windows),
                "computed_branch_window_count": len(available_windows),
                "unique_computed_window_count": unique_computed_window_count,
                "computed_frame_count": computed_frame_count,
                "group_count": len(groups),
            },
            "baseline_summaries": baselines,
            "branch_summaries": summaries,
            "groups": [
                {
                    **asdict(group),
                    "span_s": group.span_s,
                    "sequence_supported": group.sequence_supported,
                    "frequency_repeatable": group.frequency_repeatable,
                    "rate_repeatable": group.rate_repeatable,
                    "qualified": group.qualified,
                }
                for group in groups
            ],
            "figures": {
                "time_comparison": str(time_path),
                "statistics": str(statistics_path),
                "zoom": str(zoom_path),
            },
        }
    )
    results_path = arguments.output_root / "semicoherent-recovery-results.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, results)
    print(json.dumps(results["inventory"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
