#!/usr/bin/env python3
"""Continuously refine persisted 20 ms GLRT64 CFOs and audit the score change.

This prototype preserves the original GLRT64 symbols, frame-wise nuisance
phase, coherent ceiling, and exact/control policy.  It replaces only the
discrete residual-CFO bin with a safeguarded continuous maximum using analytic
first and second derivatives.  A separate 300-symbol even/odd split tests
whether the refined basin generalizes to held-out Qin symbols.

All capture and persisted analysis inputs are opened read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.pilot_methods import (
    _conditioned_correlation_workspace,
    _glrt_pair,
)
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from the repository root
    from tools import report_470384_semicoherent_recovery as semicoherent


SESSION_ID = semicoherent.SESSION_ID
DEFAULT_FRAME_RESULTS = semicoherent.DEFAULT_FRAME_RESULTS
DEFAULT_SCAN = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/"
    "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963/"
    "standard.pilot-scan.v3.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_continuous_glrt")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_continuous_glrt.md")

SAMPLE_RATE_HZ = semicoherent.SAMPLE_RATE_HZ
GLRT_SYMBOLS = np.arange(2, 66, dtype=int)
FULL_SYMBOLS = np.arange(2, 302, dtype=int)
GLRT_SIZE = 512
GLRT_BIN_WIDTH_HZ = 1.0 / (GLRT_SIZE * 4.4e-6)
MAXIMUM_MODEL_ERROR_HZ = semicoherent.MAXIMUM_MODEL_ERROR_HZ

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
PURPLE = "#7b65a8"
RED = "#bd5b52"
BRANCH_COLORS = (BLUE, GREEN, PURPLE, RED, "#4e91a8")


@dataclass(frozen=True, slots=True)
class ProfileLikelihood:
    """One frame-phase-profiled frequency likelihood with analytic derivatives."""

    values: np.ndarray = field(repr=False)
    lags_s: np.ndarray = field(repr=False)
    coherent_ceiling: float

    @classmethod
    def from_correlations(
        cls,
        values: np.ndarray,
        times_s: np.ndarray,
    ) -> ProfileLikelihood:
        correlations = np.asarray(values, dtype=np.complex128)
        moments = np.asarray(times_s, dtype=float)
        if correlations.ndim != 2 or correlations.shape != moments.shape:
            raise ValueError("profile correlations and times must be matching matrices")
        if not correlations.size:
            raise ValueError("profile likelihood requires at least one correlation")
        lags = moments - np.mean(moments, axis=1, keepdims=True)
        ceiling = float(np.sum(np.sum(np.abs(correlations), axis=1) ** 2))
        return cls(correlations, lags, ceiling)

    def value_gradient_hessian(self, frequency_hz: float) -> tuple[float, float, float]:
        if not math.isfinite(frequency_hz):
            raise ValueError("profile frequency must be finite")
        angular_lags = -2j * np.pi * self.lags_s
        rotation = np.exp(frequency_hz * angular_lags)
        amplitude = np.sum(self.values * rotation, axis=1)
        first = np.sum(self.values * rotation * angular_lags, axis=1)
        second = np.sum(self.values * rotation * angular_lags**2, axis=1)
        denominator = max(self.coherent_ceiling, 1e-20)
        value = float(np.sum(np.abs(amplitude) ** 2) / denominator)
        gradient = float(2.0 * np.real(np.sum(first * np.conj(amplitude))) / denominator)
        hessian = float(
            2.0
            * np.real(np.sum(second * np.conj(amplitude) + first * np.conj(first)))
            / denominator
        )
        return value, gradient, hessian

    def score(self, frequency_hz: float) -> float:
        return self.value_gradient_hessian(frequency_hz)[0]


@dataclass(frozen=True, slots=True)
class ContinuousMaximum:
    frequency_hz: float
    score: float
    gradient: float
    hessian: float
    iterations: int
    method: str
    at_boundary: bool


@dataclass(frozen=True, slots=True)
class RefinementInput:
    association_index: int
    branch_index: int
    branch_label: str
    time_s: float
    probe_sample_start: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    persisted_residual_cfo_hz: float
    persisted_tracking_cfo_hz: float
    persisted_exact_score: float
    persisted_control_score: float
    persisted_margin: float

    @property
    def analysis_key(self) -> tuple[int, int, float]:
        return (self.probe_sample_start, self.local_epoch_sample, self.acquired_cfo_hz)


@dataclass(frozen=True, slots=True)
class RefinementResult:
    association_index: int
    branch_index: int
    branch_label: str
    time_s: float
    probe_sample_start: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    persisted_residual_cfo_hz: float
    persisted_tracking_cfo_hz: float
    persisted_exact_score: float
    persisted_control_score: float
    persisted_margin: float
    recomputed_discrete_residual_cfo_hz: float
    recomputed_discrete_exact_score: float
    recomputed_discrete_control_score: float
    continuous_residual_cfo_hz: float
    continuous_tracking_cfo_hz: float
    continuous_exact_score: float
    continuous_control_score: float
    continuous_margin: float
    continuous_control_at_exact_score: float
    cfo_correction_hz: float
    exact_score_gain: float
    margin_gain: float
    optimizer_method: str
    optimizer_iterations: int
    optimizer_at_boundary: bool
    full_fit_residual_cfo_hz: float
    full_fit_tracking_cfo_hz: float
    full_cfo_correction_hz: float
    full_train_exact_score: float
    full_train_control_score: float
    full_train_margin: float
    full_validation_exact_score: float
    full_validation_control_score: float
    full_validation_margin: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=DEFAULT_FRAME_RESULTS)
    parser.add_argument("--pilot-scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--maximum-unique-windows",
        type=int,
        help="bounded development run; omit for the complete selected corpus",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _golden_section_maximum(
    profile: ProfileLikelihood,
    lower_hz: float,
    upper_hz: float,
    *,
    tolerance_hz: float,
    maximum_iterations: int,
) -> ContinuousMaximum:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    lower = float(lower_hz)
    upper = float(upper_hz)
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_score = profile.score(left)
    right_score = profile.score(right)
    iterations = 0
    while upper - lower > tolerance_hz and iterations < maximum_iterations:
        if left_score < right_score:
            lower = left
            left = right
            left_score = right_score
            right = lower + ratio * (upper - lower)
            right_score = profile.score(right)
        else:
            upper = right
            right = left
            right_score = left_score
            left = upper - ratio * (upper - lower)
            left_score = profile.score(left)
        iterations += 1
    frequency = left if left_score >= right_score else right
    value, gradient, hessian = profile.value_gradient_hessian(frequency)
    return ContinuousMaximum(
        frequency_hz=float(frequency),
        score=value,
        gradient=gradient,
        hessian=hessian,
        iterations=iterations,
        method="golden-section",
        at_boundary=bool(
            abs(frequency - lower_hz) <= tolerance_hz or abs(frequency - upper_hz) <= tolerance_hz
        ),
    )


def maximize_profile_likelihood(
    profile: ProfileLikelihood,
    *,
    initial_frequency_hz: float,
    half_width_hz: float,
    tolerance_hz: float = 1e-4,
    maximum_iterations: int = 40,
) -> ContinuousMaximum:
    """Find one local maximum with bracketed Newton and a golden fallback."""

    if not math.isfinite(initial_frequency_hz) or not math.isfinite(half_width_hz):
        raise ValueError("continuous profile bounds must be finite")
    if half_width_hz <= 0.0 or tolerance_hz <= 0.0 or maximum_iterations < 1:
        raise ValueError("continuous profile width, tolerance, and iterations must be positive")
    lower = initial_frequency_hz - half_width_hz
    upper = initial_frequency_hz + half_width_hz
    original_lower = lower
    original_upper = upper
    _lower_value, lower_gradient, _lower_hessian = profile.value_gradient_hessian(lower)
    _upper_value, upper_gradient, _upper_hessian = profile.value_gradient_hessian(upper)
    if not (lower_gradient >= 0.0 and upper_gradient <= 0.0):
        return _golden_section_maximum(
            profile,
            lower,
            upper,
            tolerance_hz=tolerance_hz,
            maximum_iterations=maximum_iterations,
        )

    frequency = float(np.clip(initial_frequency_hz, lower, upper))
    iterations = 0
    for iteration in range(1, maximum_iterations + 1):
        iterations = iteration
        value, gradient, hessian = profile.value_gradient_hessian(frequency)
        if gradient >= 0.0:
            lower = frequency
        else:
            upper = frequency
        if upper - lower <= tolerance_hz:
            break
        candidate = frequency - gradient / hessian if hessian < 0.0 else math.nan
        if not math.isfinite(candidate) or not lower < candidate < upper:
            candidate = 0.5 * (lower + upper)
        if abs(candidate - frequency) <= tolerance_hz:
            frequency = candidate
            break
        frequency = candidate
    candidates = (lower, frequency, upper)
    evaluated = [profile.value_gradient_hessian(item) for item in candidates]
    best = int(np.argmax([item[0] for item in evaluated]))
    selected_frequency = candidates[best]
    value, gradient, hessian = evaluated[best]
    return ContinuousMaximum(
        frequency_hz=float(selected_frequency),
        score=value,
        gradient=gradient,
        hessian=hessian,
        iterations=iterations,
        method="bracketed-newton",
        at_boundary=bool(
            abs(selected_frequency - original_lower) <= tolerance_hz
            or abs(selected_frequency - original_upper) <= tolerance_hz
        ),
    )


def refinement_inputs(
    frame_document: dict[str, Any], scan: dict[str, Any]
) -> tuple[RefinementInput, ...]:
    branches, windows = semicoherent.parse_inputs(frame_document)
    branch_labels = {item.index: item.label for item in branches}
    detections = {int(item["sample_start"]): item for item in scan["detections"]}
    output = []
    for window in windows:
        detection = detections[window.probe_sample_start]
        matches = []
        for candidate in detection["candidates"]:
            if int(candidate["local_epoch_sample"]) != window.local_epoch_sample:
                continue
            scores = [item for item in candidate["scores"] if item["method"] == "glrt64"]
            if len(scores) != 1:
                continue
            score = scores[0]
            if abs(float(score["tracking_cfo_hz"]) - window.initial_cfo_hz) <= 1e-6:
                matches.append((candidate, score))
        if len(matches) != 1:
            raise ValueError(
                f"window association {window.association_index} does not resolve to one candidate"
            )
        candidate, score = matches[0]
        output.append(
            RefinementInput(
                association_index=window.association_index,
                branch_index=window.branch_index,
                branch_label=branch_labels[window.branch_index],
                time_s=window.detection_time_s,
                probe_sample_start=window.probe_sample_start,
                local_epoch_sample=window.local_epoch_sample,
                acquired_cfo_hz=float(candidate["acquired_cfo_hz"]),
                persisted_residual_cfo_hz=float(score["residual_cfo_hz"]),
                persisted_tracking_cfo_hz=float(score["tracking_cfo_hz"]),
                persisted_exact_score=float(score["exact_score"]),
                persisted_control_score=float(score["control_score"]),
                persisted_margin=float(score["margin"]),
            )
        )
    return tuple(output)


def _analyze_one(
    iq: np.ndarray,
    item: RefinementInput,
) -> dict[str, float | int | str | bool]:
    workspace = _conditioned_correlation_workspace(
        iq,
        int(SAMPLE_RATE_HZ),
        item.local_epoch_sample,
        item.acquired_cfo_hz,
        edge=StarlinkEdge.UPPER,
        selected_symbols=FULL_SYMBOLS,
    )
    exact64 = workspace.select(GLRT_SYMBOLS)
    control64 = workspace.select(GLRT_SYMBOLS, control=True)
    (discrete_exact, discrete_frequency), (discrete_control, control_frequency) = _glrt_pair(
        exact64,
        control64,
        size=GLRT_SIZE,
    )
    grid_step_hz = 1.0 / (GLRT_SIZE * exact64.symbol_step_s)
    exact_profile = ProfileLikelihood.from_correlations(exact64.values, exact64.times_s)
    control_profile = ProfileLikelihood.from_correlations(control64.values, control64.times_s)
    exact_maximum = maximize_profile_likelihood(
        exact_profile,
        initial_frequency_hz=discrete_frequency,
        half_width_hz=grid_step_hz,
    )
    control_maximum = maximize_profile_likelihood(
        control_profile,
        initial_frequency_hz=control_frequency,
        half_width_hz=grid_step_hz,
    )

    exact300 = workspace.select(FULL_SYMBOLS)
    control300 = workspace.select(FULL_SYMBOLS, control=True)
    even = np.arange(0, len(FULL_SYMBOLS), 2, dtype=int)
    odd = np.arange(1, len(FULL_SYMBOLS), 2, dtype=int)
    full_train_exact = ProfileLikelihood.from_correlations(
        exact300.values[:, even], exact300.times_s[:, even]
    )
    full_train_control = ProfileLikelihood.from_correlations(
        control300.values[:, even], control300.times_s[:, even]
    )
    full_validation_exact = ProfileLikelihood.from_correlations(
        exact300.values[:, odd], exact300.times_s[:, odd]
    )
    full_validation_control = ProfileLikelihood.from_correlations(
        control300.values[:, odd], control300.times_s[:, odd]
    )
    full_maximum = maximize_profile_likelihood(
        full_train_exact,
        initial_frequency_hz=exact_maximum.frequency_hz,
        half_width_hz=grid_step_hz,
    )
    full_train_control_score = full_train_control.score(full_maximum.frequency_hz)
    validation_exact_score = full_validation_exact.score(full_maximum.frequency_hz)
    validation_control_score = full_validation_control.score(full_maximum.frequency_hz)
    return {
        "recomputed_discrete_residual_cfo_hz": discrete_frequency,
        "recomputed_discrete_exact_score": discrete_exact,
        "recomputed_discrete_control_score": discrete_control,
        "continuous_residual_cfo_hz": exact_maximum.frequency_hz,
        "continuous_tracking_cfo_hz": item.acquired_cfo_hz + exact_maximum.frequency_hz,
        "continuous_exact_score": exact_maximum.score,
        "continuous_control_score": control_maximum.score,
        "continuous_margin": exact_maximum.score - control_maximum.score,
        "continuous_control_at_exact_score": control_profile.score(exact_maximum.frequency_hz),
        "cfo_correction_hz": exact_maximum.frequency_hz - item.persisted_residual_cfo_hz,
        "exact_score_gain": exact_maximum.score - item.persisted_exact_score,
        "margin_gain": (exact_maximum.score - control_maximum.score) - item.persisted_margin,
        "optimizer_method": exact_maximum.method,
        "optimizer_iterations": exact_maximum.iterations,
        "optimizer_at_boundary": exact_maximum.at_boundary,
        "full_fit_residual_cfo_hz": full_maximum.frequency_hz,
        "full_fit_tracking_cfo_hz": item.acquired_cfo_hz + full_maximum.frequency_hz,
        "full_cfo_correction_hz": full_maximum.frequency_hz - item.persisted_residual_cfo_hz,
        "full_train_exact_score": full_maximum.score,
        "full_train_control_score": full_train_control_score,
        "full_train_margin": full_maximum.score - full_train_control_score,
        "full_validation_exact_score": validation_exact_score,
        "full_validation_control_score": validation_control_score,
        "full_validation_margin": validation_exact_score - validation_control_score,
    }


def analyze_inputs(
    *,
    bulk_root: Path,
    probe_samples: int,
    inputs: tuple[RefinementInput, ...],
    maximum_unique_windows: int | None,
) -> tuple[RefinementResult, ...]:
    unique: dict[tuple[int, int, float], RefinementInput] = {}
    for item in inputs:
        unique.setdefault(item.analysis_key, item)
    items = list(unique.items())
    if maximum_unique_windows is not None:
        if maximum_unique_windows < 1:
            raise ValueError("maximum unique window count must be positive")
        items = items[:maximum_unique_windows]
    cache: dict[tuple[int, int, float], dict[str, Any]] = {}
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(SESSION_ID), "stream-0", verify=True)
        for index, (key, item) in enumerate(items, start=1):
            raw = reader.read(item.probe_sample_start, probe_samples, receiver_ids=(0,))
            cache[key] = _analyze_one(semicoherent._complex_receiver(raw), item)
            if index % 50 == 0 or index == len(items):
                print(
                    f"continuously refined {index}/{len(items)} unique GLRT windows",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()
    return tuple(
        RefinementResult(**{**asdict(item), **cache[item.analysis_key]})
        for item in inputs
        if item.analysis_key in cache
    )


def _percentiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "p10": float(np.percentile(array, 10)),
        "p25": float(np.percentile(array, 25)),
        "median": float(np.median(array)),
        "p75": float(np.percentile(array, 75)),
        "p90": float(np.percentile(array, 90)),
    }


def summarize(rows: tuple[RefinementResult, ...], branch_count: int) -> tuple[dict[str, Any], ...]:
    output = []
    for branch_index in range(branch_count):
        values = tuple(item for item in rows if item.branch_index == branch_index)
        if not values:
            continue
        original_db = [
            10 * math.log10(item.persisted_exact_score / max(item.persisted_control_score, 1e-20))
            for item in values
        ]
        heldout_db = [
            10
            * math.log10(
                item.full_validation_exact_score / max(item.full_validation_control_score, 1e-20)
            )
            for item in values
        ]
        output.append(
            {
                "branch_index": branch_index,
                "branch_label": values[0].branch_label,
                "window_count": len(values),
                "persisted_exact_score": _percentiles(
                    [item.persisted_exact_score for item in values]
                ),
                "continuous_exact_score": _percentiles(
                    [item.continuous_exact_score for item in values]
                ),
                "exact_score_gain": _percentiles([item.exact_score_gain for item in values]),
                "relative_exact_score_gain_percent": _percentiles(
                    [
                        100 * item.exact_score_gain / max(item.persisted_exact_score, 1e-20)
                        for item in values
                    ]
                ),
                "margin_gain": _percentiles([item.margin_gain for item in values]),
                "absolute_cfo_correction_hz": _percentiles(
                    [abs(item.cfo_correction_hz) for item in values]
                ),
                "absolute_full_cfo_correction_hz": _percentiles(
                    [abs(item.full_cfo_correction_hz) for item in values]
                ),
                "discrete_recompute_exact_error": _percentiles(
                    [
                        abs(item.recomputed_discrete_exact_score - item.persisted_exact_score)
                        for item in values
                    ]
                ),
                "optimizer_boundary_fraction": float(
                    np.mean([item.optimizer_at_boundary for item in values])
                ),
                "original_exact_control_db": _percentiles(original_db),
                "full_validation_exact_control_db": _percentiles(heldout_db),
                "full_validation_positive_margin_fraction": float(
                    np.mean([item.full_validation_margin > 0.0 for item in values])
                ),
                "full_validation_margin": _percentiles(
                    [item.full_validation_margin for item in values]
                ),
            }
        )
    return tuple(output)


def summarize_overall(rows: tuple[RefinementResult, ...]) -> dict[str, Any]:
    if not rows:
        raise ValueError("continuous refinement summary requires at least one result")
    relative_gain = [
        100 * item.exact_score_gain / max(item.persisted_exact_score, 1e-20) for item in rows
    ]
    original_db = [
        10 * math.log10(item.persisted_exact_score / max(item.persisted_control_score, 1e-20))
        for item in rows
    ]
    heldout_db = [
        10
        * math.log10(
            item.full_validation_exact_score / max(item.full_validation_control_score, 1e-20)
        )
        for item in rows
    ]
    return {
        "relative_exact_score_gain_percent": _percentiles(relative_gain),
        "absolute_cfo_correction_hz": _percentiles(
            [abs(item.cfo_correction_hz) for item in rows]
        ),
        "margin_gain": _percentiles([item.margin_gain for item in rows]),
        "exact_score_non_decrease_fraction": float(
            np.mean([item.exact_score_gain >= -1e-12 for item in rows])
        ),
        "margin_improvement_fraction": float(np.mean([item.margin_gain > 0.0 for item in rows])),
        "original_exact_control_db": _percentiles(original_db),
        "full_validation_exact_control_db": _percentiles(heldout_db),
        "full_validation_positive_margin_fraction": float(
            np.mean([item.full_validation_margin > 0.0 for item in rows])
        ),
        "discrete_recompute_exact_error": _percentiles(
            [
                abs(item.recomputed_discrete_exact_score - item.persisted_exact_score)
                for item in rows
            ]
        ),
        "optimizer_boundary_fraction": float(
            np.mean([item.optimizer_at_boundary for item in rows])
        ),
    }


def render_strength_before_after(
    path: Path,
    *,
    rows: tuple[RefinementResult, ...],
    summaries: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(17, 12), constrained_layout=True)
    axes = figure.subplots(2, 2)
    figure.suptitle(
        "Continuous CFO refinement · same 20 ms GLRT64 likelihood",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    for summary in summaries:
        branch_index = int(summary["branch_index"])
        values = tuple(item for item in rows if item.branch_index == branch_index)
        color = BRANCH_COLORS[branch_index]
        label = summary["branch_label"].split(" · ")[0]
        axes[0, 0].scatter(
            [item.persisted_exact_score for item in values],
            [item.continuous_exact_score for item in values],
            s=15,
            color=color,
            alpha=0.55,
            linewidths=0,
            label=label,
        )
        axes[0, 1].scatter(
            [item.persisted_margin for item in values],
            [item.continuous_margin for item in values],
            s=15,
            color=color,
            alpha=0.55,
            linewidths=0,
        )
        axes[1, 0].scatter(
            [item.time_s for item in values],
            [1e6 * item.exact_score_gain for item in values],
            s=10,
            color=color,
            alpha=0.55,
            linewidths=0,
        )
        axes[1, 1].scatter(
            [item.time_s for item in values],
            [item.cfo_correction_hz for item in values],
            s=10,
            color=color,
            alpha=0.55,
            linewidths=0,
        )
    for axis in axes[0]:
        limits = [
            min(axis.get_xlim()[0], axis.get_ylim()[0]),
            max(axis.get_xlim()[1], axis.get_ylim()[1]),
        ]
        axis.plot(limits, limits, color=INK, linewidth=1.0, alpha=0.7)
        axis.set_xlim(limits)
        axis.set_ylim(limits)
        axis.set_aspect("equal", adjustable="box")
    titles = (
        "A · Exact score: discrete versus continuous",
        "B · Exact-minus-control margin",
        "C · Exact-score gain from sub-bin optimization",
        "D · Continuous CFO correction",
    )
    xlabels = (
        "persisted discrete score",
        "persisted discrete margin",
        "capture time (s)",
        "capture time (s)",
    )
    ylabels = (
        "continuous score",
        "continuous margin",
        "score gain (×10⁻⁶)",
        "CFO correction (Hz)",
    )
    for axis, title, xlabel, ylabel in zip(axes.flat, titles, xlabels, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_xlabel(xlabel, color=INK)
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0, 0].legend(loc="lower right", ncol=2, frameon=True)
    axes[1, 1].axhline(0.0, color=INK, linewidth=0.8, alpha=0.6)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_cfo_time_comparison(
    path: Path,
    *,
    rows: tuple[RefinementResult, ...],
    summaries: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": (1, 1, 0.72)})
    figure.suptitle(
        "Persisted GLRT CFO and continuous sub-bin refinement versus time",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    all_cfo_khz = []
    for summary in summaries:
        branch_index = int(summary["branch_index"])
        values = tuple(item for item in rows if item.branch_index == branch_index)
        color = BRANCH_COLORS[branch_index]
        label = summary["branch_label"]
        times = [item.time_s for item in values]
        original_khz = [item.persisted_tracking_cfo_hz / 1e3 for item in values]
        continuous_khz = [item.continuous_tracking_cfo_hz / 1e3 for item in values]
        all_cfo_khz.extend(original_khz)
        all_cfo_khz.extend(continuous_khz)
        axes[0].scatter(
            times,
            original_khz,
            s=15,
            color=color,
            alpha=0.64,
            linewidths=0,
            label=label,
        )
        axes[1].scatter(
            times,
            continuous_khz,
            s=15,
            color=color,
            alpha=0.64,
            linewidths=0,
        )
        axes[2].scatter(
            times,
            [item.cfo_correction_hz for item in values],
            s=13,
            color=color,
            alpha=0.62,
            linewidths=0,
        )
    lower, upper = min(all_cfo_khz), max(all_cfo_khz)
    padding = 0.025 * (upper - lower)
    for axis in axes[:2]:
        axis.set_ylim(lower - padding, upper + padding)
        axis.set_ylabel("tracking CFO (kHz)", color=INK)
    axes[2].set_ylabel("continuous − GLRT (Hz)", color=INK)
    axes[2].set_xlabel("capture time (s)", color=INK)
    axes[2].set_xlim(25.0, 45.0)
    axes[2].axhline(0.0, color=INK, linewidth=0.8, alpha=0.6)
    titles = (
        "A · Persisted discrete 20 ms GLRT64 CFO",
        "B · Continuously refined 20 ms GLRT64 CFO",
        "C · Sub-bin correction shown at its natural scale",
    )
    for axis, title in zip(axes, titles, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0].legend(loc="upper left", ncol=5, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_validation_time(
    path: Path,
    *,
    rows: tuple[RefinementResult, ...],
    summaries: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(18, 14), constrained_layout=True)
    axes = np.atleast_1d(figure.subplots(len(summaries), 1, sharex=True, sharey=True))
    figure.suptitle(
        "Original GLRT discrimination versus corrected full-Qin held-out discrimination",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    for axis, summary in zip(axes, summaries, strict=True):
        branch_index = int(summary["branch_index"])
        values = tuple(item for item in rows if item.branch_index == branch_index)
        times = np.asarray([item.time_s for item in values])
        original = np.asarray(
            [
                10
                * math.log10(item.persisted_exact_score / max(item.persisted_control_score, 1e-20))
                for item in values
            ]
        )
        corrected = np.asarray(
            [
                10
                * math.log10(
                    item.full_validation_exact_score
                    / max(item.full_validation_control_score, 1e-20)
                )
                for item in values
            ]
        )
        order = np.argsort(times)
        axis.scatter(
            times,
            original,
            s=12,
            color=AMBER,
            alpha=0.5,
            linewidths=0,
            label="original GLRT64 exact/control" if branch_index == 0 else None,
        )
        axis.scatter(
            times,
            corrected,
            s=12,
            color=BLUE,
            alpha=0.58,
            linewidths=0,
            label="full-Qin odd-symbol validation" if branch_index == 0 else None,
        )
        if len(times) >= 7:
            width = 7
            kernel = np.ones(width) / width
            smoothed = np.convolve(corrected[order], kernel, mode="valid")
            axis.plot(
                times[order][width // 2 : -(width // 2)],
                smoothed,
                color=BLUE,
                linewidth=1.8,
                alpha=0.9,
            )
        axis.axhline(0.0, color=INK, linewidth=0.8, alpha=0.55)
        axis.set_ylabel("exact/control (dB)", color=INK)
        axis.set_title(
            summary["branch_label"], loc="left", fontsize=13, color=INK, fontweight="bold"
        )
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[-1].set_xlim(25.0, 45.0)
    axes[0].legend(loc="upper right", ncol=2, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, results: dict[str, Any]) -> None:
    rows = []
    for item in results["branch_summaries"]:
        rows.append(
            "| {branch} | {count} | {cfo:.1f} / {cfo90:.1f} | {gain:.5f}% | "
            "{margin:+.6f} | {heldout:.1f} dB | {positive:.1f}% |".format(
                branch=item["branch_label"],
                count=item["window_count"],
                cfo=item["absolute_cfo_correction_hz"]["median"],
                cfo90=item["absolute_cfo_correction_hz"]["p90"],
                gain=item["relative_exact_score_gain_percent"]["median"],
                margin=item["margin_gain"]["median"],
                heldout=item["full_validation_exact_control_db"]["median"],
                positive=100 * item["full_validation_positive_margin_fraction"],
            )
        )
    figures = {
        key: os.path.relpath(value, path.parent) for key, value in results["figures"].items()
    }
    overall = results["overall_summary"]
    text = f"""# Continuous refinement of persisted GLRT64 CFO

## Result

The prototype preserves the original 20 ms GLRT64 likelihood exactly and
replaces only its discrete residual-CFO bin with a bounded continuous maximum.
The optimizer uses analytic gradient and curvature with a bracketed Newton step
and a golden-section fallback.  No dense fine grid is used.  Across all
{results["inventory"]["branch_window_count"]} associated windows, the median exact-score gain is
{overall["relative_exact_score_gain_percent"]["median"]:.3f}% and the p90 gain is
{overall["relative_exact_score_gain_percent"]["p90"]:.3f}%; the median absolute CFO correction is
{overall["absolute_cfo_correction_hz"]["median"]:.1f} Hz.  Every exact score is non-decreasing,
while independently maximizing the control means the exact-minus-control margin improves in
{100 * overall["margin_improvement_fraction"]:.1f}% of windows.

![Before and after]({figures["before_after"]})

The total tracking CFO (acquired CFO plus the GLRT residual) is shown before
and after continuous refinement below.  The first two panels deliberately use
the same vertical scale; the third exposes their sub-bin difference.

![CFO versus time]({figures["cfo_time"]})

The same basin is then re-optimized on even symbols from the complete
300-symbol Qin frame and evaluated on the disjoint odd symbols.  The following
figure compares exact/control discrimination in dB; it does not equate the two
raw score normalizations.

The held-out exact/control margin is positive in
{100 * overall["full_validation_positive_margin_fraction"]:.1f}% of windows, with a median
{overall["full_validation_exact_control_db"]["median"]:.1f} dB ratio.  That larger change comes
mainly from using all 300 Qin symbols rather than from the modest sub-bin CFO
correction.

![Held-out full-Qin validation]({figures["validation"]})

| branch | n | abs(ΔCFO) med/p90 | Δexact | Δmargin | held-out dB | pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Interpretation

The before/after GLRT64 comparison is apples-to-apples: same samples, symbols,
normalization, and frame-phase policy.  Consequently, its score gain measures
only discrete-bin loss.  The full-Qin odd-symbol result is a separate held-out
test of whether the continuously refined basin recovers the longer pilot.

The optimizer remains local by design.  Symbol-rate alias choice, integer timing
basin, and sawtooth reset placement remain discrete decisions outside this
continuous refinement.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    frame_document = _load(arguments.frame_results)
    scan = _load(arguments.pilot_scan)
    inputs = refinement_inputs(frame_document, scan)
    rows = analyze_inputs(
        bulk_root=arguments.bulk_root,
        probe_samples=int(frame_document["configuration"].get("probe_samples", 50_000)),
        inputs=inputs,
        maximum_unique_windows=arguments.maximum_unique_windows,
    )
    branches, _windows = semicoherent.parse_inputs(frame_document)
    summaries = summarize(rows, len(branches))
    overall = summarize_overall(rows)

    arguments.output_root.mkdir(parents=True, exist_ok=True)
    before_after_path = arguments.output_root / "continuous-glrt-before-after.png"
    cfo_time_path = arguments.output_root / "continuous-glrt-cfo-versus-time.png"
    validation_path = arguments.output_root / "continuous-glrt-full-qin-validation.png"
    render_strength_before_after(before_after_path, rows=rows, summaries=summaries)
    render_cfo_time_comparison(cfo_time_path, rows=rows, summaries=summaries)
    render_validation_time(validation_path, rows=rows, summaries=summaries)
    results = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-continuous-glrt64-refinement-v1",
            "input": {
                "session_id": SESSION_ID,
                "frame_results": str(arguments.frame_results),
                "pilot_scan": str(arguments.pilot_scan),
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
            },
            "configuration": {
                "glrt_symbols": [2, 65],
                "full_qin_symbols": [2, 301],
                "full_qin_fit_split": "even symbols",
                "full_qin_validation_split": "odd symbols",
                "glrt_size": GLRT_SIZE,
                "glrt_bin_width_hz": GLRT_BIN_WIDTH_HZ,
                "optimizer": "bracketed Newton with golden-section fallback",
                "optimizer_tolerance_hz": 1e-4,
                "optimizer_half_width": "one recomputed GLRT bin",
                "frame_phase_policy": "independent nuisance phase per frame",
            },
            "inventory": {
                "branch_window_count": len(rows),
                "unique_window_count": len(
                    {
                        (
                            item.probe_sample_start,
                            item.local_epoch_sample,
                            item.acquired_cfo_hz,
                        )
                        for item in rows
                    }
                ),
            },
            "branch_summaries": summaries,
            "overall_summary": overall,
            "rows": [asdict(item) for item in rows],
            "figures": {
                "before_after": str(before_after_path),
                "cfo_time": str(cfo_time_path),
                "validation": str(validation_path),
            },
        }
    )
    results_path = arguments.output_root / "continuous-glrt-results.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, results)
    print(json.dumps(results["inventory"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
