#!/usr/bin/env python3
"""Optimize every 1.333 ms Qin frame directly from raw IQ at absolute CFO."""

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
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_global_frame_line as frame_line
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_global_frame_line as frame_line
    from tools import report_470384_semicoherent_recovery as semicoherent


START_S = 33.7
END_S = 37.7
BRANCH_INDEX = 3
DEFAULT_JOINT_RESULTS = Path(
    "reports/figures/2026_08_23_470384_joint_frame_surface/joint-all-frame-cfo-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_direct_frame_cfo")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_direct_frame_cfo.md")
COARSE_OFFSETS_HZ = np.arange(-6_000.0, 6_000.1, 100.0)
FINE_OFFSETS_HZ = np.arange(-100.0, 100.1, 2.0)

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"


@dataclass(frozen=True, slots=True)
class SymbolSamples:
    positions: np.ndarray
    exact_reference: np.ndarray
    control_reference: np.ndarray


@dataclass(frozen=True, slots=True)
class DirectFrameFit:
    association_index: int
    frame_index: int
    time_s: float
    center_cfo_hz: float
    direct_cfo_hz: float
    old_local_curve_cfo_hz: float
    train_exact_score: float
    validation_exact_score: float
    validation_control_score: float
    validation_exact_control_db: float
    old_cfo_validation_exact_score: float
    old_cfo_validation_control_score: float
    at_search_boundary: bool


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=semicoherent.DEFAULT_FRAME_RESULTS)
    parser.add_argument("--joint-results", type=Path, default=DEFAULT_JOINT_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    parser.add_argument(
        "--maximum-windows",
        type=int,
        help="bounded development run over ordered probe windows",
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
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (
        2**15
    )


def build_symbol_samples(*, even: bool) -> SymbolSamples:
    exact = np.asarray(
        qin_edge_pilot_frame(int(semicoherent.SAMPLE_RATE_HZ), StarlinkEdge.UPPER),
        dtype=np.complex128,
    )
    control = np.asarray(
        qin_edge_pilot_frame(
            int(semicoherent.SAMPLE_RATE_HZ),
            StarlinkEdge.UPPER,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        ),
        dtype=np.complex128,
    )
    symbols = semicoherent.SYMBOLS[0::2] if even else semicoherent.SYMBOLS[1::2]
    symbol_period = semicoherent.SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S
    positions: list[int] = []
    for symbol in symbols:
        start = round(int(symbol) * symbol_period)
        stop = min(round((int(symbol) + 1) * symbol_period), len(exact))
        positions.extend(range(start, stop))
    indexes = np.asarray(positions, dtype=int)
    return SymbolSamples(indexes, exact[indexes], control[indexes])


def _normalized_score(
    products: np.ndarray,
    denominator: float,
    positions: np.ndarray,
    frequency_hz: float,
) -> float:
    phase = np.exp(
        -2j * np.pi * float(frequency_hz) * np.asarray(positions, dtype=float)
        / semicoherent.SAMPLE_RATE_HZ
    )
    return float(abs(np.dot(products, phase)) ** 2 / max(denominator, 1e-20))


def optimize_absolute_cfo(
    products: np.ndarray,
    denominator: float,
    positions: np.ndarray,
    *,
    center_cfo_hz: float,
    coarse_offsets_hz: np.ndarray = COARSE_OFFSETS_HZ,
    fine_offsets_hz: np.ndarray = FINE_OFFSETS_HZ,
    coarse_phase_bank: np.ndarray | None = None,
    fine_phase_bank: np.ndarray | None = None,
) -> tuple[float, float, bool]:
    """Maximize one raw-frame matched filter without a probe-level CFO correction."""

    samples = np.asarray(products, dtype=np.complex128)
    moments = np.asarray(positions, dtype=float)
    coarse = np.asarray(coarse_offsets_hz, dtype=float)
    fine = np.asarray(fine_offsets_hz, dtype=float)
    if samples.ndim != 1 or moments.shape != samples.shape or not samples.size:
        raise ValueError("raw frame products and positions must be matching vectors")
    center_phase = np.exp(
        -2j * np.pi * center_cfo_hz * moments / semicoherent.SAMPLE_RATE_HZ
    )
    coarse_bank = (
        np.exp(
            -2j
            * np.pi
            * coarse[:, None]
            * moments[None, :]
            / semicoherent.SAMPLE_RATE_HZ
        )
        if coarse_phase_bank is None
        else np.asarray(coarse_phase_bank, dtype=np.complex128)
    )
    if coarse_bank.shape != (len(coarse), len(moments)):
        raise ValueError("coarse phase bank does not match the search grid and frame")
    coarse_power = np.abs(coarse_bank @ (samples * center_phase)) ** 2
    coarse_position = int(np.argmax(coarse_power))
    coarse_frequency = center_cfo_hz + float(coarse[coarse_position])
    refine_phase = np.exp(
        -2j * np.pi * coarse_frequency * moments / semicoherent.SAMPLE_RATE_HZ
    )
    fine_bank = (
        np.exp(
            -2j
            * np.pi
            * fine[:, None]
            * moments[None, :]
            / semicoherent.SAMPLE_RATE_HZ
        )
        if fine_phase_bank is None
        else np.asarray(fine_phase_bank, dtype=np.complex128)
    )
    if fine_bank.shape != (len(fine), len(moments)):
        raise ValueError("fine phase bank does not match the search grid and frame")
    fine_power = np.abs(fine_bank @ (samples * refine_phase)) ** 2
    fine_position = int(np.argmax(fine_power))
    frequency = coarse_frequency + float(fine[fine_position])
    score = float(fine_power[fine_position] / max(denominator, 1e-20))
    boundary = coarse_position in (0, len(coarse) - 1)
    return frequency, score, boundary


def analyze_frames(
    *,
    bulk_root: Path,
    probe_samples: int,
    windows: tuple[semicoherent.Window, ...],
    likelihoods: dict[tuple[int, int, float], tuple[semicoherent.FrameLikelihood, ...]],
    joint_fit: frame_line.LinearFit,
) -> tuple[DirectFrameFit, ...]:
    even = build_symbol_samples(even=True)
    odd = build_symbol_samples(even=False)
    coarse_phase_bank = np.exp(
        -2j
        * np.pi
        * COARSE_OFFSETS_HZ[:, None]
        * even.positions[None, :]
        / semicoherent.SAMPLE_RATE_HZ
    )
    fine_phase_bank = np.exp(
        -2j
        * np.pi
        * FINE_OFFSETS_HZ[:, None]
        * even.positions[None, :]
        / semicoherent.SAMPLE_RATE_HZ
    )
    frame_period = semicoherent.SAMPLE_RATE_HZ / FRAME_RATE_HZ
    output: list[DirectFrameFit] = []
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(semicoherent.SESSION_ID), "stream-0", verify=True)
        for window_index, window in enumerate(windows, start=1):
            raw = reader.read(window.aligned_sample_start, probe_samples, receiver_ids=(0,))
            iq = _complex_receiver(raw)
            old_frames = likelihoods[window.analysis_key]
            old_cfos, _old_margins = frame_line.independent_frame_cfos(old_frames)
            for frame_index, (old_frame, old_cfo) in enumerate(
                zip(old_frames, old_cfos, strict=True)
            ):
                frame_start = round(frame_index * frame_period)
                even_received = iq[frame_start + even.positions]
                odd_received = iq[frame_start + odd.positions]
                even_products = np.conj(even.exact_reference) * even_received
                odd_exact_products = np.conj(odd.exact_reference) * odd_received
                odd_control_products = np.conj(odd.control_reference) * odd_received
                even_denominator = float(
                    np.vdot(even.exact_reference, even.exact_reference).real
                    * np.vdot(even_received, even_received).real
                )
                odd_exact_denominator = float(
                    np.vdot(odd.exact_reference, odd.exact_reference).real
                    * np.vdot(odd_received, odd_received).real
                )
                odd_control_denominator = float(
                    np.vdot(odd.control_reference, odd.control_reference).real
                    * np.vdot(odd_received, odd_received).real
                )
                center = float(joint_fit.frequency_hz(old_frame.time_s))
                direct_cfo, train_score, boundary = optimize_absolute_cfo(
                    even_products,
                    even_denominator,
                    even.positions,
                    center_cfo_hz=center,
                    coarse_phase_bank=coarse_phase_bank,
                    fine_phase_bank=fine_phase_bank,
                )
                validation_exact = _normalized_score(
                    odd_exact_products,
                    odd_exact_denominator,
                    odd.positions,
                    direct_cfo,
                )
                validation_control = _normalized_score(
                    odd_control_products,
                    odd_control_denominator,
                    odd.positions,
                    direct_cfo,
                )
                old_validation_exact = _normalized_score(
                    odd_exact_products,
                    odd_exact_denominator,
                    odd.positions,
                    float(old_cfo),
                )
                old_validation_control = _normalized_score(
                    odd_control_products,
                    odd_control_denominator,
                    odd.positions,
                    float(old_cfo),
                )
                output.append(
                    DirectFrameFit(
                        association_index=window.association_index,
                        frame_index=frame_index,
                        time_s=old_frame.time_s,
                        center_cfo_hz=center,
                        direct_cfo_hz=direct_cfo,
                        old_local_curve_cfo_hz=float(old_cfo),
                        train_exact_score=train_score,
                        validation_exact_score=validation_exact,
                        validation_control_score=validation_control,
                        validation_exact_control_db=10.0
                        * math.log10(validation_exact / max(validation_control, 1e-20)),
                        old_cfo_validation_exact_score=old_validation_exact,
                        old_cfo_validation_control_score=old_validation_control,
                        at_search_boundary=boundary,
                    )
                )
            if window_index % 25 == 0 or window_index == len(windows):
                print(
                    f"optimized raw frames for {window_index}/{len(windows)} timing locks",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()
    return tuple(output)


def _grouped(values: tuple[DirectFrameFit, ...]) -> tuple[tuple[DirectFrameFit, ...], ...]:
    groups: dict[int, list[DirectFrameFit]] = {}
    for item in values:
        groups.setdefault(item.association_index, []).append(item)
    return tuple(tuple(group) for group in groups.values())


def sawtooth_metrics(
    values: tuple[DirectFrameFit, ...],
    *,
    field: str,
    joint_fit: frame_line.LinearFit,
) -> dict[str, float]:
    groups = _grouped(values)
    swings = []
    slopes = []
    boundary_resets = []
    for group in groups:
        times = np.asarray([item.time_s for item in group])
        cfos = np.asarray([getattr(item, field) for item in group])
        residuals = cfos - np.asarray(joint_fit.frequency_hz(times))
        swings.append(float(residuals[-1] - residuals[0]))
        slopes.append(float(np.polyfit(times - np.mean(times), residuals, 1)[0]))
    for leading, trailing in zip(groups[:-1], groups[1:], strict=True):
        leading_time = leading[-1].time_s
        trailing_time = trailing[0].time_s
        leading_residual = getattr(leading[-1], field) - float(joint_fit.frequency_hz(leading_time))
        trailing_residual = getattr(trailing[0], field) - float(
            joint_fit.frequency_hz(trailing_time)
        )
        boundary_resets.append(float(trailing_residual - leading_residual))
    return {
        "median_within_probe_swing_hz": float(np.median(swings)),
        "median_absolute_within_probe_swing_hz": float(np.median(np.abs(swings))),
        "median_within_probe_residual_slope_hz_s": float(np.median(slopes)),
        "median_boundary_reset_hz": float(np.median(boundary_resets)),
        "median_absolute_boundary_reset_hz": float(np.median(np.abs(boundary_resets))),
    }


def aggregate_metrics(values: tuple[DirectFrameFit, ...]) -> dict[str, Any]:
    direct_exact = np.asarray([item.validation_exact_score for item in values])
    direct_control = np.asarray([item.validation_control_score for item in values])
    old_exact = np.asarray([item.old_cfo_validation_exact_score for item in values])
    old_control = np.asarray([item.old_cfo_validation_control_score for item in values])
    return {
        "direct_validation_exact_mean": float(np.mean(direct_exact)),
        "direct_validation_control_mean": float(np.mean(direct_control)),
        "direct_validation_exact_control_db": 10.0
        * math.log10(float(np.sum(direct_exact)) / max(float(np.sum(direct_control)), 1e-20)),
        "direct_qin_over_control_frame_fraction": float(np.mean(direct_exact > direct_control)),
        "old_cfo_direct_validation_exact_mean": float(np.mean(old_exact)),
        "old_cfo_direct_validation_control_mean": float(np.mean(old_control)),
        "old_cfo_direct_validation_exact_control_db": 10.0
        * math.log10(float(np.sum(old_exact)) / max(float(np.sum(old_control)), 1e-20)),
        "direct_exact_score_gain_db_vs_old_cfo": 10.0
        * math.log10(float(np.sum(direct_exact)) / max(float(np.sum(old_exact)), 1e-20)),
        "search_boundary_frame_count": sum(item.at_search_boundary for item in values),
    }


def render(
    path: Path,
    *,
    values: tuple[DirectFrameFit, ...],
    groups: tuple[tuple[DirectFrameFit, ...], ...],
    joint_fit: frame_line.LinearFit,
    branch: semicoherent.Branch,
    start_s: float,
    end_s: float,
    zoom: bool,
) -> None:
    times = np.asarray([item.time_s for item in values])
    model = np.asarray(branch.frequency_hz(times))
    joint = np.asarray(joint_fit.frequency_hz(times))
    old = np.asarray([item.old_local_curve_cfo_hz for item in values])
    direct = np.asarray([item.direct_cfo_hz for item in values])
    validation_db = np.asarray([item.validation_exact_control_db for item in values])
    positive = validation_db > 0.0
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True)
    figure.suptitle(
        "Per-frame absolute CFO optimization directly from raw IQ",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    for group in groups:
        start = group[0].time_s - 0.5 * (4.0 / 3.0) / 1e3
        for axis in axes:
            axis.axvline(
                start,
                color=RED,
                linewidth=0.55,
                linestyle=(0, (3, 3)),
                alpha=0.16,
                zorder=0,
            )
    axes[0].scatter(times, old - model, s=9, color=BLUE, alpha=0.58, linewidths=0)
    axes[0].plot(times, joint - model, color=AMBER, linewidth=2.0, label="joint CFO line")
    axes[0].legend(loc="lower left")
    axes[1].scatter(
        times[~positive],
        direct[~positive] - model[~positive],
        s=8,
        color=GRAY,
        alpha=0.24,
        linewidths=0,
        label=f"direct raw fit, held-out Qin≤control ({np.count_nonzero(~positive)})",
    )
    axes[1].scatter(
        times[positive],
        direct[positive] - model[positive],
        s=10,
        color=GREEN,
        alpha=0.62,
        linewidths=0,
        label=f"direct raw fit, held-out Qin>control ({np.count_nonzero(positive)})",
    )
    axes[1].plot(times, joint - model, color=AMBER, linewidth=2.0, label="joint CFO line")
    axes[1].legend(loc="lower left", ncol=2)
    axes[2].scatter(
        times,
        direct - old,
        s=9,
        color=GREEN,
        alpha=0.50,
        linewidths=0,
        label="direct raw CFO − old locally centered CFO",
    )
    axes[2].axhline(0.0, color=INK, linewidth=0.8, alpha=0.55)
    axes[2].legend(loc="lower left")
    titles = (
        "A · Previous frame CFOs from probe-centered likelihood curves",
        "B · New independent frame CFOs from direct absolute-frequency correction",
        "C · Change caused by removing the 20 ms CFO correction",
    )
    ylabels = (
        "old frame CFO − B4 (Hz)",
        "direct frame CFO − B4 (Hz)",
        "direct CFO − old CFO (Hz)",
    )
    if zoom:
        combined = np.concatenate((old - model, direct - model))
        limit = max(500.0, float(np.percentile(np.abs(combined), 92)))
        axes[0].set_ylim(-limit, limit)
        axes[1].set_ylim(-limit, limit)
        difference_limit = max(500.0, float(np.percentile(np.abs(direct - old), 92)))
        axes[2].set_ylim(-difference_limit, difference_limit)
    else:
        shared_limit = max(
            float(np.max(np.abs(old - model))),
            float(np.max(np.abs(direct - model))),
        )
        axes[0].set_ylim(-1.03 * shared_limit, 1.03 * shared_limit)
        axes[1].set_ylim(-1.03 * shared_limit, 1.03 * shared_limit)
    for axis, title, ylabel in zip(axes, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[-1].set_xlim(start_s, end_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    full_figure = os.path.relpath(document["figures"]["full"], path.parent)
    zoom_figure = os.path.relpath(document["figures"]["zoom"], path.parent)
    aggregate = document["aggregate"]
    old = document["sawtooth"]["old_local_curve_cfo"]
    direct = document["sawtooth"]["direct_raw_frame_cfo"]
    swing_row = (
        "| median within-probe residual swing | "
        f"{old['median_within_probe_swing_hz']:+.1f} Hz | "
        f"{direct['median_within_probe_swing_hz']:+.1f} Hz |"
    )
    reset_row = (
        "| median absolute boundary reset | "
        f"{old['median_absolute_boundary_reset_hz']:.1f} Hz | "
        f"{direct['median_absolute_boundary_reset_hz']:.1f} Hz |"
    )
    slope_row = (
        "| median residual slope | "
        f"{old['median_within_probe_residual_slope_hz_s'] / 1e3:+.3f} kHz/s | "
        f"{direct['median_within_probe_residual_slope_hz_s'] / 1e3:+.3f} kHz/s |"
    )
    text = f"""# Direct raw-IQ CFO optimization for every 1.333 ms frame

## Method

Each frame is returned to raw IQ.  Candidate absolute CFO is applied directly
to every pilot sample in that frame, and the even-symbol Qin matched-filter
power is maximized independently.  No 20 ms probe CFO is applied.  Odd Qin
symbols and the rolled control sequence provide disjoint validation.  The
20 ms acquisition is retained only to locate frame timing.

![Full direct-frame comparison]({full_figure})

![Zoomed direct-frame comparison]({zoom_figure})

| statistic | old probe-centered frame CFO | direct raw-frame CFO |
| --- | ---: | ---: |
{swing_row}
{reset_row}
{slope_row}

The direct fits achieve {aggregate['direct_validation_exact_control_db']:.2f} dB aggregate
held-out exact/control discrimination, and
{aggregate['direct_qin_over_control_frame_fraction'] * 100:.1f}% of individual frames favor Qin over
control.  {aggregate['search_boundary_frame_count']} frames land at the ±6 kHz search boundary.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    frame_document = _load(arguments.frame_results)
    joint_document = _load(arguments.joint_results)
    joint_fit = frame_line.LinearFit(**joint_document["joint_fit"])
    branches, windows = semicoherent.parse_inputs(frame_document)
    branch = next(item for item in branches if item.index == BRANCH_INDEX)
    selected_windows = tuple(
        item
        for item in windows
        if item.branch_index == BRANCH_INDEX
        and arguments.start_s <= item.detection_time_s < arguments.end_s
    )
    if arguments.maximum_windows is not None:
        if arguments.maximum_windows < 1:
            raise ValueError("maximum window count must be positive")
        selected_windows = selected_windows[: arguments.maximum_windows]
    probe_samples = int(frame_document["configuration"].get("probe_samples", 50_000))
    likelihoods = semicoherent.analyze_unique_windows(
        bulk_root=arguments.bulk_root,
        probe_samples=probe_samples,
        windows=selected_windows,
        maximum_unique_windows=None,
    )
    values = analyze_frames(
        bulk_root=arguments.bulk_root,
        probe_samples=probe_samples,
        windows=selected_windows,
        likelihoods=likelihoods,
        joint_fit=joint_fit,
    )
    groups = _grouped(values)
    old_sawtooth = sawtooth_metrics(
        values,
        field="old_local_curve_cfo_hz",
        joint_fit=joint_fit,
    )
    direct_sawtooth = sawtooth_metrics(
        values,
        field="direct_cfo_hz",
        joint_fit=joint_fit,
    )
    aggregate = aggregate_metrics(values)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    full_path = arguments.output_root / "direct-frame-cfo-full.png"
    zoom_path = arguments.output_root / "direct-frame-cfo-zoom.png"
    for path, zoom in ((full_path, False), (zoom_path, True)):
        render(
            path,
            values=values,
            groups=groups,
            joint_fit=joint_fit,
            branch=branch,
            start_s=arguments.start_s,
            end_s=arguments.end_s,
            zoom=zoom,
        )
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-direct-raw-independent-frame-cfo-v1",
            "input": {
                "session_id": semicoherent.SESSION_ID,
                "frame_results": str(arguments.frame_results),
                "joint_results": str(arguments.joint_results),
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
                "branch_label": branch.label,
            },
            "configuration": {
                "start_s": arguments.start_s,
                "end_s": arguments.end_s,
                "frame_duration_ms": 4.0 / 3.0,
                "train_symbols": "even Qin symbols",
                "validation_symbols": "odd Qin symbols",
                "control": "odd symbols from rolled Qin control",
                "frequency_correction": "absolute CFO applied directly to raw frame samples",
                "probe_cfo_usage": "none",
                "timing_source": "20 ms acquisition timing lock",
                "coarse_offsets_hz": [
                    float(COARSE_OFFSETS_HZ[0]),
                    float(COARSE_OFFSETS_HZ[-1]),
                    float(COARSE_OFFSETS_HZ[1] - COARSE_OFFSETS_HZ[0]),
                ],
                "fine_offsets_hz": [
                    float(FINE_OFFSETS_HZ[0]),
                    float(FINE_OFFSETS_HZ[-1]),
                    float(FINE_OFFSETS_HZ[1] - FINE_OFFSETS_HZ[0]),
                ],
            },
            "inventory": {
                "probe_count": len(groups),
                "frame_count": len(values),
            },
            "aggregate": aggregate,
            "sawtooth": {
                "old_local_curve_cfo": old_sawtooth,
                "direct_raw_frame_cfo": direct_sawtooth,
            },
            "frame_fits": [asdict(item) for item in values],
            "figures": {"full": str(full_path), "zoom": str(zoom_path)},
        }
    )
    results_path = arguments.output_root / "direct-frame-cfo-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    print(
        json.dumps(
            {
                "inventory": document["inventory"],
                "aggregate": aggregate,
                "sawtooth": document["sawtooth"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
