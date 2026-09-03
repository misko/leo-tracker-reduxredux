#!/usr/bin/env python3
"""Run matched native-25 fractional GLRT for capture 0181f7f0ffa1.

The 25 MS/s GLRT acquisitions are independent within complete 20 ms native-IQ
windows.  Window centers are the modes of the long, high-quality native PSS
track so the expensive comparison evaluates common signal support without
posting clipped or gap-crossing blocks.  PSS does not seed GLRT epoch or CFO.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.standard.configuration import production_receiver_standard_config  # noqa: E402
from leo.analysis.standard.full_capture_glrt20ms import (  # noqa: E402
    WindowResult,
    _acquisition_config,
    _analyze_window,
    _run_parallel,
)
from leo.analysis.starlink.pilot_search_geometry import (  # noqa: E402
    compile_pilot_search_geometry,
)
from leo.contracts.states import StarlinkEdge  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

CAPTURE_ID = "cap-20260902T224009-0181f7f0ffa1"
SAMPLE_RATE_HZ = 25_000_000
TUNED_CENTER_HZ = 1_932_500_000
RF_BANDWIDTH_HZ = 25_000_000
STARLINK_CHANNEL = 4
RF_REFERENCE_HZ = 11_690_312_500.0
FRAME_RATE_HZ = 750.0
WINDOW_MS = 20

Json = dict[str, Any]
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Native25Row:
    mode_id: str
    center_time_s: float
    window_start_sample: int
    integer_global_epoch_sample: int
    fractional_global_epoch_sample: float
    integer_frame_phase_s: float
    fractional_frame_phase_s: float
    fractional_epoch_status: str
    fractional_epoch_offset_samples: float
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    robust_cfo_slope_hz_s: float | None
    robust_cfo_rms_hz: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--pss-product", type=Path, required=True)
    parser.add_argument("--low-epoch-product", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def _load(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return value


def _select_pss_track(pss: Json) -> tuple[Json, list[Json], FloatArray]:
    source = pss["source"]
    if (
        source["session_id"] != CAPTURE_ID
        or int(source["sample_rate_hz"]) != SAMPLE_RATE_HZ
        or int(source["receiver_id"]) != 0
        or pss["starlink_edge"] != "upper"
    ):
        raise ValueError("PSS product is not the native-25 upper-edge RX0 source")
    eligible = [
        track
        for track in pss["tracks"]
        if track["origin"] == "independent_blind"
        and len(track["mode_ids"]) >= 20
        and float(track["rms_residual_us"]) <= 0.1
    ]
    if not eligible:
        raise ValueError("PSS product has no long, precise independent track")
    track = max(eligible, key=lambda item: len(item["mode_ids"]))
    by_id = {item["mode_id"]: item for item in pss["modes"]}
    modes = [by_id[item] for item in track["mode_ids"]]
    times = np.asarray([float(item["center_time_s"]) for item in modes], dtype=float)
    local = times - float(track["time_origin_s"])
    predicted = np.polyval(np.asarray(track["coefficients_descending_s"], dtype=float), local)
    phases = predicted + np.asarray(track["residuals_us"], dtype=float) * 1e-6
    return track, modes, phases


def _select_low_locklet(epoch: Json, start_s: float, stop_s: float) -> tuple[Json, FloatArray]:
    source = epoch["source"]
    if (
        source["session_id"] != CAPTURE_ID
        or int(source["sample_rate_hz"]) != 2_500_000
        or int(source["receiver_id"]) != 0
        or epoch["starlink_edge"] != "upper"
    ):
        raise ValueError("low-rate epoch product is not the paired 2.5 MS/s RX0 source")
    high_first = 1_788_388_813_368_136_209
    low_first = int(source["timing"]["first_estimate_utc_ns"])
    common_shift_s = (low_first - high_first) * 1e-9

    def overlap(locklet: Json) -> float:
        left = float(locklet["global_start_time_s"]) + common_shift_s
        right = float(locklet["global_end_time_s"]) + common_shift_s
        return max(0.0, min(stop_s, right) - max(start_s, left))

    candidates = [item for item in epoch["locklets"] if item["status"] == "complete"]
    if not candidates:
        raise ValueError("low-rate epoch product has no complete locklet")
    locklet = max(candidates, key=overlap)
    if overlap(locklet) <= 0:
        raise ValueError("low-rate epoch product has no PSS-overlapping locklet")
    return locklet, np.asarray(
        [float(item["global_center_time_s"]) + common_shift_s for item in locklet["observations"]],
        dtype=float,
    )


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("expected one selected CI16 receiver")
    return np.ascontiguousarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0
    )


def _run_native25(
    recordings_root: Path,
    modes: list[Json],
    *,
    workers: int,
) -> tuple[list[Native25Row], Json]:
    if not 1 <= workers <= 12:
        raise ValueError("workers must lie in 1..12")
    config = production_receiver_standard_config(sample_rate_hz=SAMPLE_RATE_HZ)
    window_samples = SAMPLE_RATE_HZ * WINDOW_MS // 1_000
    acquisition = _acquisition_config(window_samples, config.feedback)
    geometry = compile_pilot_search_geometry(
        receiver_id=0,
        starlink_channel=STARLINK_CHANNEL,
        edge=StarlinkEdge.UPPER,
        tuned_center_frequency_hz=TUNED_CENTER_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rf_bandwidth_hz=RF_BANDWIDTH_HZ,
        residual_cfo_min_hz=config.feedback.cfo_search_min_hz,
        residual_cfo_max_hz=config.feedback.cfo_search_max_hz,
    )
    capability = PinnedLocalRoot(recordings_root)
    store: RecordingStore | None = None
    verified_reads = 0
    read_seconds = 0.0
    started = time.perf_counter()
    try:
        store = RecordingStore.open_pinned(capability)
        reader = store.reader(store.inspect(CAPTURE_ID), "stream-0", verify=True)

        def windows():
            nonlocal verified_reads, read_seconds
            for index, mode in enumerate(modes):
                center = float(mode["center_time_s"])
                start = round((center - WINDOW_MS / 2_000) * SAMPLE_RATE_HZ)
                read_started = time.perf_counter()
                span = reader.read_device_span(
                    start,
                    window_samples,
                    receiver_ids=(0,),
                )
                read_seconds += time.perf_counter() - read_started
                if not bool(np.all(span.valid_samples)):
                    raise ValueError(
                        f"PSS-supported GLRT window {index} is clipped or crosses a gap"
                    )
                if len(np.unique(span.continuity_segment_ids)) != 1:
                    raise ValueError(f"PSS-supported GLRT window {index} crosses continuity")
                verified_reads += 1
                yield index, start, _complex_receiver(span.samples)

        def analyze(index: int, start: int, samples: np.ndarray) -> WindowResult:
            return _analyze_window(
                index,
                start,
                samples,
                sample_rate_hz=SAMPLE_RATE_HZ,
                edge=StarlinkEdge.UPPER,
                acquisition_config=acquisition,
                glrt_size=config.feedback.glrt_size,
                margin_gate=config.full_capture_glrt20ms.margin_gate,
                frequency_reference=geometry.frequency_reference,
                refine_fractional_epoch=True,
            )

        results = _run_parallel(windows(), analyze, workers=workers)
    finally:
        if store is not None:
            store.close()
        capability.close()
    elapsed = time.perf_counter() - started

    rows: list[Native25Row] = []
    rejected = {"margin": 0, "fractional": 0, "missing": 0}
    period_s = 1.0 / FRAME_RATE_HZ
    for mode, result in zip(modes, results, strict=True):
        required = (
            result.epoch_sample,
            result.acquired_cfo_hz,
            result.tracking_cfo_hz,
            result.glrt_exact_score,
            result.glrt_control_score,
            result.glrt_margin,
        )
        if any(item is None for item in required):
            rejected["missing"] += 1
            continue
        if not result.passed_margin_gate:
            rejected["margin"] += 1
            continue
        if (
            result.fractional_epoch_status != "complete"
            or result.fractional_epoch_offset_samples is None
        ):
            rejected["fractional"] += 1
            continue
        integer_global = result.sample_start + int(result.epoch_sample)
        fractional_global = integer_global + float(result.fractional_epoch_offset_samples)
        rows.append(
            Native25Row(
                mode_id=str(mode["mode_id"]),
                center_time_s=float(mode["center_time_s"]),
                window_start_sample=result.sample_start,
                integer_global_epoch_sample=integer_global,
                fractional_global_epoch_sample=fractional_global,
                integer_frame_phase_s=(integer_global / SAMPLE_RATE_HZ) % period_s,
                fractional_frame_phase_s=(fractional_global / SAMPLE_RATE_HZ) % period_s,
                fractional_epoch_status=result.fractional_epoch_status,
                fractional_epoch_offset_samples=float(result.fractional_epoch_offset_samples),
                acquired_cfo_hz=float(result.acquired_cfo_hz),
                tracking_cfo_hz=float(result.tracking_cfo_hz),
                exact_score=float(result.glrt_exact_score),
                control_score=float(result.glrt_control_score),
                margin=float(result.glrt_margin),
                robust_cfo_slope_hz_s=result.robust_slope_hz_s,
                robust_cfo_rms_hz=result.robust_residual_rms_hz,
            )
        )
    return rows, {
        "requested_window_count": len(modes),
        "verified_complete_window_count": verified_reads,
        "retained_fractional_margin_pass_count": len(rows),
        "rejected_counts": rejected,
        "workers": workers,
        "summed_verified_read_seconds": read_seconds,
        "wall_seconds": elapsed,
        "window_ms": WINDOW_MS,
        "window_stride": "PSS-track-mode centers (62.5 ms nominal)",
        "native_iq": True,
        "decimated": False,
        "frequency_reference_center_hz": geometry.frequency_reference.center_hz,
    }


def _unwrap_phase(phases_s: FloatArray) -> FloatArray:
    radians = np.asarray(phases_s, dtype=float) * (2.0 * np.pi * FRAME_RATE_HZ)
    return np.unwrap(radians) / (2.0 * np.pi * FRAME_RATE_HZ)


def _align_cycles(values_s: FloatArray, reference_s: FloatArray) -> FloatArray:
    period = 1.0 / FRAME_RATE_HZ
    shift = round(float(np.median(reference_s - values_s)) / period) * period
    return values_s + shift


def _quadratic_fit(times_s: FloatArray, phases_s: FloatArray) -> tuple[Json, FloatArray]:
    times = np.asarray(times_s, dtype=float)
    phases = np.asarray(phases_s, dtype=float)
    reference = float(np.mean(times))
    local = times - reference
    design = np.column_stack((np.ones(len(times)), local, 0.5 * local**2))
    coefficients = np.linalg.lstsq(design, phases, rcond=None)[0]
    predicted = design @ coefficients
    residual = phases - predicted
    dof = max(1, len(times) - 3)
    variance = float(np.dot(residual, residual) / dof)
    covariance = np.linalg.pinv(design.T @ design) * variance
    curvature_sigma = math.sqrt(max(float(covariance[2, 2]), 0.0))
    return {
        "point_count": len(times),
        "reference_time_s": reference,
        "phase_at_reference_s": float(coefficients[0]),
        "timing_drift_s_s": float(coefficients[1]),
        "timing_curvature_s_s2": float(coefficients[2]),
        "equivalent_doppler_rate_hz_s": float(-RF_REFERENCE_HZ * coefficients[2]),
        "formal_equivalent_doppler_rate_sigma_hz_s": float(RF_REFERENCE_HZ * curvature_sigma),
        "residual_rms_us": float(np.sqrt(np.mean(residual**2)) * 1e6),
        "residual_mad_us": float(1.4826 * np.median(np.abs(residual - np.median(residual))) * 1e6),
        "maximum_absolute_residual_us": float(np.max(np.abs(residual)) * 1e6),
    }, residual * 1e6


def _robust_native_mask(
    times: FloatArray,
    cfo: FloatArray,
    phase: FloatArray,
) -> npt.NDArray[np.bool_]:
    mask = np.ones(len(times), dtype=bool)
    for _ in range(5):
        local = times[mask] - float(np.mean(times[mask]))
        cfo_fit = np.polyfit(local, cfo[mask], 2)
        cfo_residual = cfo - np.polyval(cfo_fit, times - float(np.mean(times[mask])))
        cfo_scale = 1.4826 * np.median(np.abs(cfo_residual[mask] - np.median(cfo_residual[mask])))
        _, timing_residual = _quadratic_fit(times[mask], phase[mask])
        timing_center = float(np.median(timing_residual))
        timing_scale = 1.4826 * np.median(np.abs(timing_residual - timing_center))
        timing_all_fit, _ = _quadratic_fit(times[mask], phase[mask])
        ref = float(timing_all_fit["reference_time_s"])
        model = (
            float(timing_all_fit["phase_at_reference_s"])
            + float(timing_all_fit["timing_drift_s_s"]) * (times - ref)
            + 0.5 * float(timing_all_fit["timing_curvature_s_s2"]) * (times - ref) ** 2
        )
        timing_all = (phase - model) * 1e6
        updated = (np.abs(cfo_residual) <= max(500.0, 6.0 * cfo_scale)) & (
            np.abs(timing_all - timing_center) <= max(0.25, 6.0 * timing_scale)
        )
        if np.array_equal(updated, mask):
            break
        mask = updated
    return mask


def _affine_difference_rms(a: FloatArray, b: FloatArray, times: FloatArray) -> float:
    difference = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    local = np.asarray(times, dtype=float) - float(np.mean(times))
    design = np.column_stack((np.ones(len(local)), local))
    residual = difference - design @ np.linalg.lstsq(design, difference, rcond=None)[0]
    return float(np.sqrt(np.mean(residual**2)) * 1e6)


def _cfo_fit(times: FloatArray, values: FloatArray, reference: float) -> tuple[Json, FloatArray]:
    local = times - reference
    coefficients = np.polyfit(local, values, 2)
    predicted = np.polyval(coefficients, local)
    residual = values - predicted
    return {
        "reference_time_s": reference,
        "cfo_at_reference_hz": float(coefficients[2]),
        "cfo_slope_at_reference_hz_s": float(coefficients[1]),
        "cfo_curvature_hz_s2": float(2 * coefficients[0]),
        "residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
    }, predicted


def _plot_comparison(
    path: Path,
    arrays: dict[str, FloatArray],
    facts: Json,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(17, 11), constrained_layout=True)
    methods = (
        ("pss", "#f97316", "native-25 PSS"),
        ("native25", "#111827", "native-25 fractional GLRT"),
        ("low", "#2563eb", "2.5 MS/s fractional GLRT RX0"),
    )
    for key, color, label in methods:
        axes[0, 0].scatter(
            arrays[f"{key}_times"],
            arrays[f"{key}_linear_residual_us"],
            s=16,
            color=color,
            alpha=0.78,
            label=label,
        )
        axes[0, 1].scatter(
            arrays[f"{key}_times"],
            arrays[f"{key}_quadratic_residual_us"],
            s=16,
            color=color,
            alpha=0.78,
            label=label,
        )
    for axis in axes[0]:
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_ylabel("Timing residual (µs)")
        axis.grid(alpha=0.22)
    axes[0, 0].set_title("A · Linear residuals expose the shared Doppler curvature")
    axes[0, 1].set_title("B · Independent quadratic residuals on the same units")
    axes[0, 0].legend(fontsize=9)

    reference = float(facts["comparison"]["reference_time_s"])
    for key, color, label in (
        ("native25", "#111827", "native-25 acquired CFO"),
        ("low", "#2563eb", "2.5 MS/s canonical CFO"),
    ):
        times = arrays[f"{key}_cfo_times"]
        fit = arrays[f"{key}_cfo_fit"]
        axes[1, 0].plot(
            times,
            (fit - np.interp(reference, times, fit)) / 1e3,
            color=color,
            linewidth=2.2,
            label=label,
        )
        axes[1, 0].scatter(
            times,
            (arrays[f"{key}_cfo"] - np.interp(reference, times, fit)) / 1e3,
            s=11,
            color=color,
            alpha=0.45,
        )
    axes[1, 0].axhline(0.0, color="black", linewidth=0.8)
    axes[1, 0].set_xlabel("Seconds from native-25 stream start")
    axes[1, 0].set_ylabel("CFO change from common reference (kHz)")
    axes[1, 0].set_title("C · Both GLRT receivers measure the same IQ-sign frequency fall")
    axes[1, 0].legend(fontsize=9)
    axes[1, 0].grid(alpha=0.22)

    labels = ["25M integer\nGLRT", "25M fractional\nGLRT", "2.5M fractional\nGLRT", "25M PSS"]
    rms = [
        facts["fits"]["native25_integer"]["residual_rms_us"],
        facts["fits"]["native25_fractional"]["residual_rms_us"],
        facts["fits"]["low_fractional"]["residual_rms_us"],
        facts["fits"]["pss"]["residual_rms_us"],
    ]
    bars = axes[1, 1].bar(labels, rms, color=["#94a3b8", "#111827", "#2563eb", "#f97316"])
    for bar, value in zip(bars, rms, strict=True):
        axes[1, 1].text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    axes[1, 1].set_ylabel("Quadratic timing-fit RMS (µs)")
    axes[1, 1].set_title("D · Fractional timing precision (lower is better)")
    axes[1, 1].grid(axis="y", alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · native 25 MS/s fractional GLRT versus 2.5 MS/s GLRT and PSS\n"
        "Independent native-IQ GLRT acquisition; complete PSS-supported 20 ms windows only",
        fontsize=14,
    )
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_detail(path: Path, arrays: dict[str, FloatArray], facts: Json) -> None:
    times = arrays["native25_times"]
    figure, axes = plt.subplots(3, 1, figsize=(16, 12), constrained_layout=True)
    axes[0].scatter(
        times,
        arrays["native25_integer_residual_us"],
        s=18,
        color="#94a3b8",
        alpha=0.7,
        label="integer 25M epoch",
    )
    axes[0].scatter(
        times,
        arrays["native25_quadratic_residual_us"],
        s=18,
        color="#111827",
        alpha=0.82,
        label="fractional 25M epoch",
    )
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_ylabel("Quadratic residual (µs)")
    axes[0].set_title("A · Direct fractional evaluation versus the 40 ns integer grid")
    axes[0].legend()
    axes[0].grid(alpha=0.22)

    axes[1].scatter(times, arrays["native25_offsets"], s=18, color="#7c3aed", alpha=0.8)
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Fractional correction (25M samples)")
    axes[1].set_title("B · Fractional offset from independently acquired integer epoch")
    axes[1].grid(alpha=0.22)

    axes[2].scatter(
        times, arrays["native25_exact"], s=17, color="#059669", alpha=0.75, label="exact score"
    )
    axes[2].scatter(
        times, arrays["native25_control"], s=17, color="#dc2626", alpha=0.7, label="rolled control"
    )
    axes[2].scatter(
        times, arrays["native25_margin"], s=17, color="#2563eb", alpha=0.7, label="exact − control"
    )
    axes[2].axhline(0.025, color="black", linestyle="--", linewidth=1, label="production gate")
    axes[2].set_xlabel("Seconds from native-25 stream start")
    axes[2].set_ylabel("Normalized GLRT score")
    axes[2].set_title("C · Every posted point passes the exact-minus-control gate")
    axes[2].legend(ncol=4, fontsize=9)
    axes[2].grid(alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · native 25 MS/s fractional GLRT diagnostics\n"
        f"{facts['runtime']['retained_fractional_margin_pass_count']} retained of "
        f"{facts['runtime']['requested_window_count']} complete matched windows",
        fontsize=14,
    )
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    pss = _load(args.pss_product)
    low_epoch = _load(args.low_epoch_product)
    pss_track, modes, pss_phase = _select_pss_track(pss)
    low_locklet, low_times = _select_low_locklet(
        low_epoch,
        float(min(item["center_time_s"] for item in modes)),
        float(max(item["center_time_s"] for item in modes)),
    )
    rows, runtime = _run_native25(args.recordings_root, modes, workers=args.workers)
    if len(rows) < 20:
        raise ValueError("native-25 fractional GLRT retained too few matched windows")

    mode_index = {item["mode_id"]: index for index, item in enumerate(modes)}
    pss_selected = np.asarray([pss_phase[mode_index[row.mode_id]] for row in rows], dtype=float)
    native_times = np.asarray([row.center_time_s for row in rows], dtype=float)
    native_integer = _unwrap_phase(
        np.asarray([row.integer_frame_phase_s for row in rows], dtype=float)
    )
    native_fractional = _unwrap_phase(
        np.asarray([row.fractional_frame_phase_s for row in rows], dtype=float)
    )
    native_integer = _align_cycles(native_integer, pss_selected)
    native_fractional = _align_cycles(native_fractional, pss_selected)
    native_cfo = np.asarray([row.acquired_cfo_hz for row in rows], dtype=float)
    native_mask = _robust_native_mask(native_times, native_cfo, native_fractional)
    rows = [row for row, keep in zip(rows, native_mask, strict=True) if keep]
    native_times = native_times[native_mask]
    pss_selected = pss_selected[native_mask]
    native_integer = native_integer[native_mask]
    native_fractional = native_fractional[native_mask]
    native_cfo = native_cfo[native_mask]

    low_observations = [
        item
        for item in low_locklet["observations"]
        if item["epoch_fit_inlier"] and item["cfo_branch_inlier"]
    ]
    low_times_all = np.asarray(
        [
            time
            for item, time in zip(low_locklet["observations"], low_times, strict=True)
            if item["epoch_fit_inlier"] and item["cfo_branch_inlier"]
        ],
        dtype=float,
    )
    common = (low_times_all >= native_times.min()) & (low_times_all <= native_times.max())
    low_times_selected = low_times_all[common]
    low_phase = np.asarray(
        [float(item["unwrapped_frame_phase_s"]) for item in low_observations], dtype=float
    )[common]
    low_cfo = np.asarray(
        [float(item["canonical_cfo_hz"]) for item in low_observations], dtype=float
    )[common]
    low_phase = _align_cycles(low_phase, np.full_like(low_phase, np.median(pss_selected)))

    fits: Json = {}
    residuals: dict[str, FloatArray] = {}
    fits["pss"], residuals["pss"] = _quadratic_fit(native_times, pss_selected)
    fits["native25_integer"], residuals["native25_integer"] = _quadratic_fit(
        native_times, native_integer
    )
    fits["native25_fractional"], residuals["native25"] = _quadratic_fit(
        native_times, native_fractional
    )
    fits["low_fractional"], residuals["low"] = _quadratic_fit(low_times_selected, low_phase)
    linear_residuals: dict[str, FloatArray] = {}
    for key, times, phase in (
        ("pss", native_times, pss_selected),
        ("native25", native_times, native_fractional),
        ("low", low_times_selected, low_phase),
    ):
        local = times - float(np.mean(times))
        linear_residuals[key] = (phase - np.polyval(np.polyfit(local, phase, 1), local)) * 1e6

    reference = float(np.mean(native_times))
    native_cfo_fit, native_cfo_predicted = _cfo_fit(native_times, native_cfo, reference)
    low_cfo_fit, low_cfo_predicted = _cfo_fit(low_times_selected, low_cfo, reference)
    comparison = {
        "reference_time_s": reference,
        "native25_pss_affine_removed_difference_rms_us": _affine_difference_rms(
            native_fractional, pss_selected, native_times
        ),
        "native25_retained_fraction": len(rows) / runtime["requested_window_count"],
        "native25_integer_to_fractional_rms_ratio": (
            fits["native25_integer"]["residual_rms_us"]
            / fits["native25_fractional"]["residual_rms_us"]
        ),
        "native25_minus_low_doppler_rate_hz_s": (
            fits["native25_fractional"]["equivalent_doppler_rate_hz_s"]
            - fits["low_fractional"]["equivalent_doppler_rate_hz_s"]
        ),
        "native25_minus_pss_doppler_rate_hz_s": (
            fits["native25_fractional"]["equivalent_doppler_rate_hz_s"]
            - fits["pss"]["equivalent_doppler_rate_hz_s"]
        ),
        "native25_cfo_fit": native_cfo_fit,
        "low_cfo_fit": low_cfo_fit,
    }
    facts = {
        "schema_version": 1,
        "analysis_kind": "0181-native25-fractional-glrt-comparison",
        "capture_id": CAPTURE_ID,
        "source": {
            "pss_result_digest": pss["result_digest"],
            "pss_track_id": pss_track["track_id"],
            "low_epoch_result_digest": low_epoch["result_digest"],
            "low_locklet_digest": low_locklet["locklet_digest"],
        },
        "method": {
            "native_sample_rate_hz": SAMPLE_RATE_HZ,
            "native_window_ms": WINDOW_MS,
            "native_window_selection": "centers of the long precise independent PSS track",
            "native_glrt_acquisition": "independent standard wide CFO/epoch search in each window",
            "native_fractional_method": (
                "five-cell circular log-parabola followed by direct normalized Lanczos-16 "
                "fractional-IQ GLRT evaluation"
            ),
            "decimation_or_projection": False,
            "postselection": (
                "margin-pass and bracketed fractional peak, then iterative native-GLRT-only "
                "quadratic CFO/timing trajectory gate"
            ),
        },
        "runtime": {**runtime, "trajectory_retained_count": len(rows)},
        "fits": fits,
        "comparison": comparison,
        "rows": [asdict(item) for item in rows],
        "limitations": [
            "The expensive native-25 search is evaluated only at complete windows centered on the "
            "independently selected PSS track; PSS does not seed GLRT epoch or CFO.",
            "The 25 MS/s capture has counter-proven gaps, so the comparison measures retained "
            "common support rather than continuous 60-second coverage.",
            "Quadratic-fit formal uncertainties do not account for overlap autocorrelation.",
            "Receiver CFO intercepts are not compared because the two radios have independent "
            "oscillators and baseband centers; slopes and timing curvature are comparable.",
            "Candidate evidence does not establish Starlink or satellite identity.",
        ],
    }
    arrays = {
        "pss_times": native_times,
        "pss_linear_residual_us": linear_residuals["pss"],
        "pss_quadratic_residual_us": residuals["pss"],
        "native25_times": native_times,
        "native25_linear_residual_us": linear_residuals["native25"],
        "native25_quadratic_residual_us": residuals["native25"],
        "native25_integer_residual_us": residuals["native25_integer"],
        "native25_offsets": np.asarray(
            [row.fractional_epoch_offset_samples for row in rows], dtype=float
        ),
        "native25_exact": np.asarray([row.exact_score for row in rows], dtype=float),
        "native25_control": np.asarray([row.control_score for row in rows], dtype=float),
        "native25_margin": np.asarray([row.margin for row in rows], dtype=float),
        "low_times": low_times_selected,
        "low_linear_residual_us": linear_residuals["low"],
        "low_quadratic_residual_us": residuals["low"],
        "native25_cfo_times": native_times,
        "native25_cfo": native_cfo,
        "native25_cfo_fit": native_cfo_predicted,
        "low_cfo_times": low_times_selected,
        "low_cfo": low_cfo,
        "low_cfo_fit": low_cfo_predicted,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _plot_comparison(args.output_dir / "native25-fractional-glrt-comparison.png", arrays, facts)
    _plot_detail(args.output_dir / "native25-fractional-glrt-detail.png", arrays, facts)
    (args.output_dir / "analysis-summary.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"runtime": facts["runtime"], "fits": fits, "comparison": comparison},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
