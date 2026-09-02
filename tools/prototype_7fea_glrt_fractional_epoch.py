#!/usr/bin/env python3
"""Replay 7fea RX0 GLRT peaks and prototype fractional-sample epochs.

This is a capture-local research diagnostic, not a Standard product.  It keeps
the persisted candidate CFO and known-pilot hypothesis fixed, evaluates the
exact GLRT-64 score at five integer epochs around every accepted H4/L3 epoch,
and interpolates the local maximum with both ordinary and log-score parabolas.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores  # noqa: E402
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

CAPTURE_ID = "cap-20260902T152702-7fea7427619d"
HOUGH_LABEL = "H4"
LOCKLET_INDEX = 3
GRID_OFFSETS = np.arange(-2, 3, dtype=np.int64)

Json = dict[str, Any]
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ReplayRow:
    opportunity_index: int
    center_time_s: float
    window_start_sample: int
    persisted_local_epoch_sample: int
    persisted_global_epoch_sample: int
    persisted_exact_score: float
    persisted_control_score: float
    persisted_margin: float
    acquired_cfo_hz: float
    exact_scores: tuple[float, ...]
    control_scores: tuple[float, ...]
    raw_peak_correction_samples: float
    log_peak_correction_samples: float
    margin_peak_correction_samples: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--epoch-product", type=Path, required=True)
    parser.add_argument("--full-product", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    return parser.parse_args()


def _load(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return value


def parabolic_peak(
    scores: FloatArray,
    offsets: FloatArray,
    *,
    logarithmic: bool = False,
) -> float:
    """Return a bracketed three-point peak, bounded to half a grid cell."""

    values = np.asarray(scores, dtype=float)
    grid = np.asarray(offsets, dtype=float)
    if values.ndim != 1 or grid.ndim != 1 or values.size != grid.size or values.size < 3:
        raise ValueError("scores and offsets must be equal vectors with at least three cells")
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(grid)):
        raise ValueError("peak inputs must be finite")
    steps = np.diff(grid)
    if np.any(steps <= 0) or not np.allclose(steps, steps[0], rtol=0.0, atol=1e-12):
        raise ValueError("peak offsets must be a uniformly increasing grid")
    index = int(np.argmax(values))
    if index == 0 or index == len(values) - 1:
        return float(grid[index])
    selected = values[index - 1 : index + 2]
    if logarithmic:
        selected = np.log(np.maximum(selected, np.finfo(float).tiny))
    denominator = float(selected[0] - 2.0 * selected[1] + selected[2])
    if not math.isfinite(denominator) or denominator >= -np.finfo(float).eps:
        return float(grid[index])
    fraction = float(
        np.clip(0.5 * (selected[0] - selected[2]) / denominator, -0.5, 0.5)
    )
    return float(grid[index] + fraction * steps[0])


def quadratic_timing_fit(
    times_s: FloatArray,
    phases_s: FloatArray,
    *,
    rf_reference_hz: float,
) -> Json:
    """Fit the same p0 + drift*dt + 0.5*curvature*dt^2 coordinate."""

    times = np.asarray(times_s, dtype=float)
    phases = np.asarray(phases_s, dtype=float)
    if times.ndim != 1 or phases.shape != times.shape or len(times) < 3:
        raise ValueError("timing fit requires at least three paired vectors")
    reference = float(np.mean(times))
    local = times - reference
    design = np.column_stack((np.ones(len(times)), local, 0.5 * local**2))
    coefficients = np.linalg.lstsq(design, phases, rcond=None)[0]
    predicted = design @ coefficients
    residuals = phases - predicted
    degrees_of_freedom = max(1, len(times) - 3)
    variance = float(np.dot(residuals, residuals) / degrees_of_freedom)
    covariance = np.linalg.pinv(design.T @ design) * variance
    curvature_sigma = math.sqrt(max(float(covariance[2, 2]), 0.0))
    return {
        "point_count": len(times),
        "reference_time_s": reference,
        "phase_at_reference_s": float(coefficients[0]),
        "timing_drift_s_s": float(coefficients[1]),
        "timing_curvature_s_s2": float(coefficients[2]),
        "equivalent_doppler_rate_hz_s": float(-rf_reference_hz * coefficients[2]),
        "formal_equivalent_doppler_rate_sigma_hz_s": float(
            rf_reference_hz * curvature_sigma
        ),
        "residual_rms_us": float(np.sqrt(np.mean(residuals**2)) * 1e6),
        "residual_mad_us": float(
            1.4826 * np.median(np.abs(residuals - np.median(residuals))) * 1e6
        ),
        "maximum_absolute_residual_us": float(np.max(np.abs(residuals)) * 1e6),
        "predicted_s": predicted,
        "residuals_us": residuals * 1e6,
    }


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("expected one selected CI16 receiver")
    return np.asarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64))
        / 2**15,
        dtype=np.complex128,
    )


def _selected_rows(epoch: Json) -> tuple[Json, list[Json]]:
    matches = [
        item
        for item in epoch["locklets"]
        if item["source_hough_track_label"] == HOUGH_LABEL
        and int(item["locklet_index"]) == LOCKLET_INDEX
    ]
    if len(matches) != 1 or matches[0]["status"] != "complete":
        raise ValueError("expected one complete RX0 H4/L3 locklet")
    rows = [item for item in matches[0]["observations"] if item["epoch_fit_inlier"]]
    if len(rows) < 3:
        raise ValueError("selected locklet has insufficient epoch inliers")
    return matches[0], rows


def _full_windows(full: Json) -> dict[int, Json]:
    rows = [item for segment in full["segments"] for item in segment["windows"]]
    return {int(item["opportunity_index"]): item for item in rows}


def _replay(
    recordings_root: Path,
    epoch: Json,
    full: Json,
    rows: list[Json],
    *,
    workers: int,
) -> tuple[list[ReplayRow], Json]:
    if not 1 <= workers <= 24:
        raise ValueError("workers must lie in 1..24")
    source = epoch["source"]
    if source["session_id"] != CAPTURE_ID or int(source["receiver_id"]) != 0:
        raise ValueError("prototype is bound to 7fea RX0")
    sample_rate_hz = int(source["sample_rate_hz"])
    if sample_rate_hz != 2_500_000 or full["starlink_edge"] != "lower":
        raise ValueError("prototype expects the 2.5 MS/s lower-edge product")
    windows = _full_windows(full)
    selected = [(item, windows[int(item["opportunity_index"])]) for item in rows]
    first = min(int(window["global_device_sample_start"]) for _, window in selected)
    stop = max(int(window["global_device_sample_stop"]) for _, window in selected)

    capability = PinnedLocalRoot(recordings_root)
    store: RecordingStore | None = None
    started = time.perf_counter()
    try:
        store = RecordingStore.open_pinned(capability)
        reader = store.reader(
            store.inspect(source["session_id"]), source["stream_id"], verify=True
        )
        span = reader.read_device_span(
            first,
            stop - first,
            receiver_ids=(int(source["receiver_id"]),),
        )
        if not np.all(span.valid_samples):
            raise ValueError("replayed locklet span contains invalid device-axis samples")
        if len(np.unique(span.continuity_segment_ids)) != 1:
            raise ValueError("replayed locklet span crosses a continuity boundary")
        raw = span.samples
    finally:
        if store is not None:
            store.close()
        capability.close()
    read_seconds = time.perf_counter() - started

    def evaluate(pair: tuple[Json, Json]) -> ReplayRow:
        observation, window = pair
        window_start = int(window["global_device_sample_start"])
        window_stop = int(window["global_device_sample_stop"])
        local_start = window_start - first
        values = _complex_receiver(raw[local_start : local_start + window_stop - window_start])
        local_epoch = int(window["global_epoch_device_sample"]) - window_start
        frequencies = np.full(len(GRID_OFFSETS), float(window["acquired_cfo_hz"]))
        scores = conditioned_glrt64_scores(
            values,
            sample_rate_hz,
            epoch_samples=local_epoch + GRID_OFFSETS,
            acquired_cfo_hz=frequencies,
            edge=StarlinkEdge.LOWER,
        )
        exact = np.asarray([item.exact_score for item in scores], dtype=float)
        control = np.asarray([item.control_score for item in scores], dtype=float)
        margin = exact - control
        return ReplayRow(
            opportunity_index=int(observation["opportunity_index"]),
            center_time_s=float(observation["global_center_time_s"]),
            window_start_sample=window_start,
            persisted_local_epoch_sample=local_epoch,
            persisted_global_epoch_sample=int(window["global_epoch_device_sample"]),
            persisted_exact_score=float(window["glrt_exact_score"]),
            persisted_control_score=float(window["glrt_control_score"]),
            persisted_margin=float(window["glrt_margin"]),
            acquired_cfo_hz=float(window["acquired_cfo_hz"]),
            exact_scores=tuple(float(item) for item in exact),
            control_scores=tuple(float(item) for item in control),
            raw_peak_correction_samples=parabolic_peak(
                exact, GRID_OFFSETS.astype(float)
            ),
            log_peak_correction_samples=parabolic_peak(
                exact, GRID_OFFSETS.astype(float), logarithmic=True
            ),
            margin_peak_correction_samples=parabolic_peak(
                margin, GRID_OFFSETS.astype(float)
            ),
        )

    score_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        replayed = list(executor.map(evaluate, selected))
    score_seconds = time.perf_counter() - score_started
    reproduction = np.asarray(
        [item.exact_scores[2] - item.persisted_exact_score for item in replayed], dtype=float
    )
    control_reproduction = np.asarray(
        [item.control_scores[2] - item.persisted_control_score for item in replayed], dtype=float
    )
    return replayed, {
        "device_span_start_sample": first,
        "device_span_stop_sample": stop,
        "device_span_samples": stop - first,
        "verified_read_seconds": read_seconds,
        "score_replay_seconds": score_seconds,
        "workers": workers,
        "maximum_exact_score_reproduction_error": float(np.max(np.abs(reproduction))),
        "maximum_control_score_reproduction_error": float(
            np.max(np.abs(control_reproduction))
        ),
    }


def _fit_inventory(
    replayed: list[ReplayRow], rows: list[Json], *, sample_rate_hz: int, rf_reference_hz: float
) -> tuple[Json, dict[str, FloatArray]]:
    times = np.asarray([item.center_time_s for item in replayed], dtype=float)
    original = np.asarray([item["unwrapped_frame_phase_s"] for item in rows], dtype=float)
    raw_correction = np.asarray(
        [item.raw_peak_correction_samples for item in replayed], dtype=float
    )
    log_correction = np.asarray(
        [item.log_peak_correction_samples for item in replayed], dtype=float
    )
    margin_correction = np.asarray(
        [item.margin_peak_correction_samples for item in replayed], dtype=float
    )
    integer_peak_offsets = np.asarray(
        [GRID_OFFSETS[int(np.argmax(item.exact_scores))] for item in replayed], dtype=int
    )
    phases = {
        "integer": original,
        "raw_score_parabola": original + raw_correction / sample_rate_hz,
        "log_score_parabola": original + log_correction / sample_rate_hz,
        "margin_parabola": original + margin_correction / sample_rate_hz,
    }
    fits = {
        name: quadratic_timing_fit(times, values, rf_reference_hz=rf_reference_hz)
        for name, values in phases.items()
    }
    corrections = {
        "raw_score_parabola": raw_correction,
        "log_score_parabola": log_correction,
        "margin_parabola": margin_correction,
    }
    inventory: Json = {}
    u_start, u_stop = 40.4, 42.7
    u = (times >= u_start) & (times <= u_stop)
    for name, fit in fits.items():
        residuals = np.asarray(fit.pop("residuals_us"), dtype=float)
        fit.pop("predicted_s")
        row: Json = dict(fit)
        row["u_interval_rms_us"] = float(np.sqrt(np.mean(residuals[u] ** 2)))
        row["u_interval_peak_to_peak_us"] = float(np.ptp(residuals[u]))
        if name != "integer":
            correction = corrections[name]
            row.update(
                {
                    "median_correction_samples": float(np.median(correction)),
                    "p95_absolute_correction_samples": float(
                        np.quantile(np.abs(correction), 0.95)
                    ),
                    "maximum_absolute_correction_samples": float(np.max(np.abs(correction))),
                    "fraction_with_integer_peak_move": float(
                        np.mean(integer_peak_offsets != 0)
                    ),
                }
            )
        inventory[name] = row
    inventory["nonoverlap_stride_parity"] = {}
    opportunity_indexes = np.asarray(
        [item.opportunity_index for item in replayed], dtype=int
    )
    for parity in (0, 1):
        selected = opportunity_indexes % 2 == parity
        inventory["nonoverlap_stride_parity"][str(parity)] = {}
        for name in ("integer", "log_score_parabola"):
            fit = quadratic_timing_fit(
                times[selected], phases[name][selected], rf_reference_hz=rf_reference_hz
            )
            fit.pop("predicted_s")
            fit.pop("residuals_us")
            inventory["nonoverlap_stride_parity"][str(parity)][name] = fit
    inventory["interpolator_sensitivity_samples"] = {
        "raw_minus_log_median_absolute": float(
            np.median(np.abs(raw_correction - log_correction))
        ),
        "raw_minus_log_p95_absolute": float(
            np.quantile(np.abs(raw_correction - log_correction), 0.95)
        ),
        "margin_minus_log_median_absolute": float(
            np.median(np.abs(margin_correction - log_correction))
        ),
        "margin_minus_log_p95_absolute": float(
            np.quantile(np.abs(margin_correction - log_correction), 0.95)
        ),
    }
    arrays = {
        "times": times,
        "original": original,
        "raw_correction": raw_correction,
        "log_correction": log_correction,
        "margin_correction": margin_correction,
    }
    for name, values in phases.items():
        fit = quadratic_timing_fit(times, values, rf_reference_hz=rf_reference_hz)
        arrays[f"{name}_residuals"] = np.asarray(fit["residuals_us"], dtype=float)
    return inventory, arrays


def _plot(
    path: Path,
    replayed: list[ReplayRow],
    arrays: dict[str, FloatArray],
    fits: Json,
) -> None:
    times = arrays["times"]
    integer = arrays["integer_residuals"]
    fractional = arrays["log_score_parabola_residuals"]
    parity = np.asarray([item.opportunity_index % 2 for item in replayed], dtype=int)
    figure, axes = plt.subplots(3, 1, figsize=(16, 12), constrained_layout=True)

    axes[0].scatter(times, integer, s=15, color="#94a3b8", alpha=0.65, label="integer epoch")
    axes[0].scatter(
        times,
        fractional,
        s=14,
        color="#2563eb",
        alpha=0.8,
        label="log-parabolic fractional epoch",
    )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_ylabel("Quadratic residual (µs)")
    axes[0].set_title(
        "A · Full H4/L3 locklet: fractional interpolation removes most integer-sample banding"
    )
    axes[0].legend()
    axes[0].grid(alpha=0.22)

    zoom = (times >= 40.4) & (times <= 42.7)
    for value, color, label in ((0, "#2563eb", "even stride"), (1, "#7c3aed", "odd stride")):
        selected = zoom & (parity == value)
        axes[1].scatter(
            times[selected],
            integer[selected],
            s=25,
            facecolors="none",
            edgecolors=color,
            alpha=0.65,
            label=f"integer · {label}",
        )
        axes[1].scatter(
            times[selected],
            fractional[selected],
            s=16,
            color=color,
            alpha=0.9,
            label=f"fractional · {label}",
        )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xlim(40.35, 42.75)
    axes[1].set_ylabel("Quadratic residual (µs)")
    axes[1].set_title(
        "B · U-shaped plateau zoom: the score peak moves continuously within a sample"
    )
    axes[1].legend(ncol=2, fontsize=9)
    axes[1].grid(alpha=0.22)

    axes[2].scatter(
        times,
        arrays["raw_correction"],
        s=13,
        color="#0f766e",
        alpha=0.65,
        label="ordinary-score parabola",
    )
    axes[2].scatter(
        times,
        arrays["log_correction"],
        s=13,
        color="#ea580c",
        alpha=0.7,
        label="log-score parabola (primary prototype)",
    )
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_xlabel("Capture time on low-rate device clock (s)")
    axes[2].set_ylabel("Correction from persisted epoch (samples)")
    axes[2].set_title(
        "C · Estimated sub-sample correction; values beyond ±0.5 include a local integer move"
    )
    axes[2].legend()
    axes[2].grid(alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · RX0 H4/L3 GLRT-64 fractional epoch prototype\n"
        f"integer RMS {fits['integer']['residual_rms_us']:.4f} µs → "
        f"log-parabolic {fits['log_score_parabola']['residual_rms_us']:.4f} µs; "
        "fixed persisted CFO and hypothesis",
        fontsize=14,
    )
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_profiles(path: Path, replayed: list[ReplayRow]) -> None:
    targets = (40.57, 41.45, 41.46, 42.61)
    chosen = [
        min(replayed, key=lambda item: abs(item.center_time_s - target)) for target in targets
    ]
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    dense = np.linspace(-0.6, 0.6, 121)
    for axis, row in zip(axes.flat, chosen, strict=True):
        scores = np.asarray(row.exact_scores, dtype=float)
        peak = int(np.argmax(scores))
        if peak == 0 or peak == len(scores) - 1:
            raise ValueError("representative score profile has an unbracketed peak")
        local_x = GRID_OFFSETS[peak - 1 : peak + 2].astype(float)
        local_y = np.log(scores[peak - 1 : peak + 2])
        coefficients = np.polyfit(local_x, local_y, 2)
        center = row.log_peak_correction_samples
        display_x = center + dense
        axis.plot(GRID_OFFSETS, scores, "o-", color="#64748b", label="exact GLRT score")
        axis.plot(
            display_x,
            np.exp(np.polyval(coefficients, display_x)),
            color="#ea580c",
            linewidth=2,
            label="local log-parabola",
        )
        axis.axvline(0, color="black", linestyle=":", label="persisted epoch")
        axis.axvline(center, color="#2563eb", linestyle="--", label="fractional peak")
        axis.set_title(
            f"t={row.center_time_s:.2f} s · parity {row.opportunity_index % 2} · "
            f"correction {center:+.3f} sample"
        )
        axis.set_xlabel("Integer samples from persisted epoch")
        axis.set_ylabel("Exact GLRT-64 score")
        axis.grid(alpha=0.22)
    axes[0, 0].legend(fontsize=8)
    figure.suptitle(
        "Discrete known-pilot correlation peaks and local fractional interpolation\n"
        "five scores are direct IQ replay; smooth curves are three-cell diagnostic fits",
        fontsize=14,
    )
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_before_after(
    path: Path,
    replayed: list[ReplayRow],
    arrays: dict[str, FloatArray],
    fits: Json,
) -> None:
    """Render integer and fractional timing residuals on identical axes."""

    times = arrays["times"]
    before = arrays["integer_residuals"]
    after = arrays["log_score_parabola_residuals"]
    parity = np.asarray([item.opportunity_index % 2 for item in replayed], dtype=int)
    figure, axes = plt.subplots(
        2,
        2,
        figsize=(16, 9.5),
        sharey=True,
        constrained_layout=True,
    )
    panels = (
        (axes[0, 0], before, "A · Before: persisted integer epochs", None),
        (axes[0, 1], after, "B · After: fractional GLRT peaks", None),
        (axes[1, 0], before, "C · Before: U-region zoom", (40.35, 42.75)),
        (axes[1, 1], after, "D · After: same U-region and y scale", (40.35, 42.75)),
    )
    for axis, residuals, title, x_limits in panels:
        for value, color, label in (
            (0, "#2563eb", "even opportunities"),
            (1, "#7c3aed", "odd opportunities"),
        ):
            selected = parity == value
            axis.scatter(
                times[selected],
                residuals[selected],
                s=18,
                color=color,
                alpha=0.75,
                edgecolors="none",
                label=label,
            )
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_ylim(-0.30, 0.30)
        if x_limits is not None:
            axis.set_xlim(*x_limits)
        axis.set_title(title)
        axis.set_xlabel("Capture time on low-rate device clock (s)")
        axis.grid(alpha=0.22)
    axes[0, 0].set_ylabel("Quadratic timing residual (µs)")
    axes[1, 0].set_ylabel("Quadratic timing residual (µs)")
    axes[0, 0].legend(fontsize=9)
    axes[0, 0].text(
        0.02,
        0.05,
        f"RMS {fits['integer']['residual_rms_us']:.4f} µs\n"
        f"rate {fits['integer']['equivalent_doppler_rate_hz_s'] / 1e3:.5f} kHz/s",
        transform=axes[0, 0].transAxes,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cbd5e1"},
    )
    axes[0, 1].text(
        0.02,
        0.05,
        f"RMS {fits['log_score_parabola']['residual_rms_us']:.4f} µs\n"
        f"rate {fits['log_score_parabola']['equivalent_doppler_rate_hz_s'] / 1e3:.5f} kHz/s",
        transform=axes[0, 1].transAxes,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cbd5e1"},
    )
    figure.suptitle(
        f"{CAPTURE_ID} · RX0 H4/L3 GLRT timing before and after fractional interpolation\n"
        "Identical y axes; separate quadratic fit for each timing estimate",
        fontsize=14,
    )
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    epoch = _load(args.epoch_product)
    full = _load(args.full_product)
    locklet, rows = _selected_rows(epoch)
    replayed, runtime = _replay(
        args.recordings_root, epoch, full, rows, workers=args.workers
    )
    sample_rate_hz = int(epoch["source"]["sample_rate_hz"])
    fits, arrays = _fit_inventory(
        replayed,
        rows,
        sample_rate_hz=sample_rate_hz,
        rf_reference_hz=float(epoch["rf_reference_hz"]),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _plot(args.output_dir / "fractional-glrt-epoch-comparison.png", replayed, arrays, fits)
    _plot_profiles(args.output_dir / "fractional-glrt-peak-profiles.png", replayed)
    _plot_before_after(
        args.output_dir / "fractional-glrt-before-after.png", replayed, arrays, fits
    )
    facts = {
        "schema_version": 1,
        "analysis_kind": "7fea-rx0-glrt-fractional-epoch-prototype",
        "capture_id": CAPTURE_ID,
        "source_epoch_result_digest": epoch["result_digest"],
        "source_full_glrt_result_digest": full["result_digest"],
        "scope": {
            "radio_id": epoch["source"]["radio_id"],
            "stream_id": epoch["source"]["stream_id"],
            "receiver_id": epoch["source"]["receiver_id"],
            "sample_rate_hz": sample_rate_hz,
            "starlink_edge": epoch["starlink_edge"],
            "hough_track_label": locklet["source_hough_track_label"],
            "locklet_index": locklet["locklet_index"],
            "point_count": len(rows),
        },
        "method": {
            "score": "conditioned exact GLRT-64 at fixed persisted acquired CFO",
            "integer_offset_grid_samples": GRID_OFFSETS.tolist(),
            "primary_interpolator": "three-cell parabola in log exact-score",
            "sensitivity_interpolators": [
                "three-cell parabola in ordinary exact-score",
                "three-cell parabola in ordinary exact-minus-control margin",
            ],
            "maximum_fraction_within_peak_cell_samples": 0.5,
            "production_behavior_changed": False,
        },
        "runtime": runtime,
        "fits": fits,
        "rows": [asdict(item) for item in replayed],
        "limitations": [
            "This is an in-sample replay of one already selected locklet, not a detection study.",
            "The candidate CFO and lower-edge hypothesis remain fixed at their persisted values.",
            "The parabolic curve is inferred from three integer score cells; it is not a direct "
            "fractionally shifted template evaluation.",
            "Overlapping 20 ms windows remain statistically dependent at the 10 ms stride.",
        ],
    }
    (args.output_dir / "fractional-glrt-epoch-prototype.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"runtime": runtime, "fits": fits}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
