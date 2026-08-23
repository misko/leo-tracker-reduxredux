"""Deterministic scientific PNGs for segmented scanner analysis."""

from __future__ import annotations

import io
import math
from threading import RLock

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2
from leo.scanner.analysis_models import (
    ScannerAnalysisMetricsV1,
    ScannerPilotDopplerSegmentsV1,
)

_RENDER_LOCK = RLock()
_RECEIVER_COLORS = ("#00a6d6", "#f28e2b")
_BOUNDARY_COLOR = "#d62728"


def render_scanner_waterfall_png(metrics: ScannerAnalysisMetricsV1) -> bytes:
    """Render one scan-wide waterfall lane per receiver, split at retunes."""

    with _RENDER_LOCK:
        receivers = metrics.configuration.receiver_ids
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(
            figsize=(8.2 * len(receivers), 8.0),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(1, len(receivers), sharex=True, sharey=True, squeeze=False)[0]
        matrices = [
            _waterfall_matrix(waterfall)
            for frame in metrics.frames
            for waterfall in frame.waterfalls
        ]
        finite_parts = tuple(matrix[np.isfinite(matrix)] for matrix in matrices if matrix.size)
        finite = np.concatenate(finite_parts) if finite_parts else np.asarray([], dtype=float)
        if finite.size:
            lower, upper = (float(item) for item in np.percentile(finite, (3.0, 99.7)))
            if upper <= lower:
                upper = lower + 1.0
        else:
            lower, upper = -160.0, -159.0

        image = None
        for receiver_index, (axis, receiver_id) in enumerate(zip(axes, receivers, strict=True)):
            for frame_index, frame in enumerate(metrics.frames):
                start_ms, end_ms = boundaries[frame_index : frame_index + 2]
                if frame.status == "failed":
                    axis.axhspan(start_ms, end_ms, color="#d9d9d9", alpha=0.8)
                    axis.text(
                        0.5,
                        (start_ms + end_ms) / 2.0,
                        "failed",
                        ha="center",
                        va="center",
                        transform=axis.get_yaxis_transform(),
                        fontsize=8,
                    )
                    continue
                waterfall = frame.waterfalls[receiver_index]
                matrix = _waterfall_matrix(waterfall)
                frequencies_mhz = (
                    np.asarray(waterfall.frequency_bin_centers_hz, dtype=np.float64) / 1_000_000.0
                )
                half_bin = (
                    (frequencies_mhz[1] - frequencies_mhz[0]) / 2.0
                    if len(frequencies_mhz) > 1
                    else metrics.configuration.sample_rate_hz / 2_000_000.0
                )
                image = axis.imshow(
                    matrix,
                    cmap="magma",
                    interpolation="nearest",
                    aspect="auto",
                    origin="upper",
                    extent=(
                        frequencies_mhz[0] - half_bin,
                        frequencies_mhz[-1] + half_bin,
                        end_ms,
                        start_ms,
                    ),
                    vmin=lower,
                    vmax=upper,
                    rasterized=True,
                )
            for boundary_ms in boundaries[1:-1]:
                axis.axhline(boundary_ms, color=_BOUNDARY_COLOR, linewidth=1.0, zorder=4)
            axis.set_title(f"RX{receiver_id}", loc="left", fontsize=10, fontweight="bold")
            axis.set_xlabel("Baseband frequency offset (MHz)")
            axis.set_ylabel("Stitched scan time (ms; increases downward)")
            axis.set_ylim(boundaries[-1], boundaries[0])
            axis.grid(False)

        label_axis = axes[0]
        for frame_index, frame in enumerate(metrics.frames):
            start_ms, end_ms = boundaries[frame_index : frame_index + 2]
            actual_if_hz = frame.actual_if_center_hz or frame.requested_if_center_hz
            actual_rf_mhz = (actual_if_hz + metrics.configuration.lnb_lo_hz) / 1_000_000.0
            label_axis.text(
                0.01,
                (start_ms + end_ms) / 2.0,
                f"CH{frame.target.channel} {frame.target.edge.value[0].upper()}\n"
                f"{actual_rf_mhz:.3f} MHz",
                ha="left",
                va="center",
                transform=label_axis.get_yaxis_transform(),
                fontsize=7,
                color="white",
                bbox={"facecolor": "black", "alpha": 0.45, "edgecolor": "none"},
            )
        if image is not None:
            figure.colorbar(
                image,
                ax=list(axes),
                label="Power spectral density (dBFS)",
                pad=0.01,
            )
        figure.suptitle(
            "Stitched scanner waterfall · red lines are retune boundaries · "
            "no FFT crosses a boundary\n"
            f"{metrics.scan_id}",
            fontsize=13,
            fontweight="bold",
        )
        return _save(figure)


def render_scanner_glrt64_response_png(
    metrics: ScannerAnalysisMetricsV1,
    pilot_doppler: ScannerPilotDopplerSegmentsV1 | None = None,
) -> bytes:
    """Render every dwell's GLRT64 probes on one stitched scan-time axis."""

    with _RENDER_LOCK:
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(figsize=(16.0, 6.5), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        gate = metrics.configuration.glrt64_margin_gate
        if pilot_doppler is not None:
            for segment_index, segment in enumerate(pilot_doppler.segments):
                frame_start_ms = boundaries[segment.target_index]
                axis.axvspan(
                    frame_start_ms + 1_000 * segment.window_start_s,
                    frame_start_ms + 1_000 * segment.window_end_s,
                    color="#f4c95d",
                    alpha=0.12,
                    zorder=0,
                    label="pilot tracking window" if segment_index == 0 else None,
                )
        for frame_index, frame in enumerate(metrics.frames):
            start_ms, end_ms = boundaries[frame_index : frame_index + 2]
            if frame.status == "failed":
                axis.axvspan(start_ms, end_ms, color="#d9d9d9", alpha=0.8)
            else:
                for receiver_index, receiver_id in enumerate(metrics.configuration.receiver_ids):
                    probes = tuple(item for item in frame.probes if item.receiver_id == receiver_id)
                    times = np.asarray(
                        [start_ms + item.probe_start_ms for item in probes], dtype=float
                    )
                    margins = np.asarray(
                        [
                            max(
                                (candidate.margin for candidate in item.candidates),
                                default=np.nan,
                            )
                            for item in probes
                        ],
                        dtype=float,
                    )
                    axis.plot(
                        times,
                        margins,
                        marker="o",
                        markersize=3.5,
                        linewidth=1.25,
                        color=_RECEIVER_COLORS[receiver_index % len(_RECEIVER_COLORS)],
                        label=f"RX{receiver_id} best candidate",
                    )
                if frame.first_detection is not None:
                    hit = frame.first_detection
                    axis.scatter(
                        [start_ms + hit.probe_start_ms],
                        [hit.margin],
                        marker="*",
                        s=100,
                        color="#00a878",
                        edgecolor="black",
                        linewidth=0.5,
                        zorder=5,
                        label="first member of confirmed pair",
                    )
            axis.text(
                (start_ms + end_ms) / 2.0,
                1.02,
                f"CH{frame.target.channel} {frame.target.edge.value[0].upper()}\n"
                f"{frame.decision.value}",
                ha="center",
                va="bottom",
                transform=axis.get_xaxis_transform(),
                fontsize=7,
            )

        axis.axhline(
            gate,
            color="#333333",
            linestyle="--",
            linewidth=1.1,
            label=f"margin gate {gate:.3f}",
        )
        for boundary_index, boundary_ms in enumerate(boundaries[1:-1]):
            axis.axvline(
                boundary_ms,
                color=_BOUNDARY_COLOR,
                linewidth=1.0,
                zorder=4,
                label="retune boundary" if boundary_index == 0 else None,
            )
        axis.set_xlim(boundaries[0], boundaries[-1])
        axis.set_xlabel("Stitched scan storage time (ms)")
        axis.set_ylabel("GLRT64 exact − control margin")
        axis.grid(alpha=0.2)
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        axis.legend(unique.values(), unique.keys(), loc="best", fontsize=8)
        figure.suptitle(
            "Full-scan GLRT64 response · red lines are retune boundaries\n"
            "20 ms probes / 10 ms stride · star = first member of confirming pair\n"
            f"{metrics.scan_id}",
            fontsize=13,
            fontweight="bold",
        )
        return _save(figure)


def render_scanner_pilot_doppler_png(
    metrics: ScannerAnalysisMetricsV1,
    product: ScannerPilotDopplerSegmentsV1,
) -> bytes:
    """Render acquisition context and local phase/rate evidence from the product."""

    with _RENDER_LOCK:
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(figsize=(15.5, 10.5), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axes = figure.subplots(2, 2)
        colors = ("#277da1", "#f8961e", "#43aa8b", "#9d4edd", "#d1495b")

        for segment in product.segments:
            color = colors[segment.segment_index % len(colors)]
            label = (
                f"CH{segment.target.channel} {segment.target.edge.value[0].upper()} "
                f"RX{segment.receiver_id}"
            )
            offset_ms = boundaries[segment.target_index]
            supported = tuple(item for item in segment.frames if item.measurement_supported)
            times_ms = np.asarray(
                [offset_ms + 1_000 * item.time_since_retune_s for item in supported],
                dtype=float,
            )
            measured = np.asarray(
                [item.absolute_cfo_measurement_hz for item in supported], dtype=float
            )
            tracked = np.asarray([item.tracked_absolute_cfo_hz for item in supported], dtype=float)
            if times_ms.size:
                axes[0, 0].scatter(times_ms, measured / 1_000, s=13, color=color, alpha=0.55)
                axes[0, 0].plot(
                    times_ms,
                    tracked / 1_000,
                    color=color,
                    linewidth=1.1,
                    alpha=0.8,
                    label=f"{label} Kalman",
                )
            if (
                segment.local_cfo_at_reference_hz is not None
                and segment.local_doppler_rate_hz_s is not None
            ):
                line_times_s = np.asarray(
                    [segment.window_start_s, segment.window_end_s], dtype=float
                )
                predicted = segment.local_cfo_at_reference_hz + segment.local_doppler_rate_hz_s * (
                    line_times_s - segment.reference_time_since_retune_s
                )
                axes[0, 0].plot(
                    offset_ms + 1_000 * line_times_s,
                    predicted / 1_000,
                    color=color,
                    linewidth=2.0,
                    linestyle="--",
                    label=f"{label} robust line",
                )
            axes[0, 0].axvspan(
                offset_ms + 1_000 * segment.window_start_s,
                offset_ms + 1_000 * segment.window_end_s,
                color=color,
                alpha=0.035,
            )

            rate_x = segment.target_index + 0.10 * segment.receiver_id
            rate_color = "#d48806" if segment.qualified else "#aeb8c2"
            if segment.local_doppler_rate_hz_s is not None:
                axes[0, 1].scatter(
                    rate_x,
                    segment.local_doppler_rate_hz_s / 1_000,
                    s=52,
                    color=rate_color,
                    marker="o",
                    label="direct local line",
                )
            if segment.kalman_doppler_rate_hz_s is not None:
                axes[0, 1].scatter(
                    rate_x,
                    segment.kalman_doppler_rate_hz_s / 1_000,
                    s=45,
                    color="#277da1",
                    marker="x",
                    label="modulo-π Kalman",
                )

            phase_times_ms = np.asarray(
                [1_000 * (item.time_since_retune_s - segment.window_start_s) for item in supported]
            )
            innovations = np.asarray(
                [item.phase_innovation_modulo_pi_rad for item in supported], dtype=float
            )
            if phase_times_ms.size:
                axes[1, 0].plot(
                    phase_times_ms,
                    innovations,
                    marker=".",
                    markersize=4,
                    linewidth=0.8,
                    color=color,
                    alpha=0.75,
                    label=label,
                )

            held_out = (
                np.nan
                if segment.held_out_frequency_rms_hz is None
                else segment.held_out_frequency_rms_hz
            )
            axes[1, 1].scatter(
                segment.supported_frame_fraction,
                held_out,
                s=48,
                color=rate_color,
            )
            axes[1, 1].annotate(
                label,
                (segment.supported_frame_fraction, held_out),
                xytext=(4, 3),
                textcoords="offset points",
                fontsize=7,
            )

        for boundary in boundaries[1:-1]:
            axes[0, 0].axvline(boundary, color=_BOUNDARY_COLOR, linewidth=0.7, alpha=0.4)
        axes[0, 0].set_title(
            "A · Per-frame CFO, Kalman state, and direct local fits",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].set_xlabel("stitched display time (ms; red = retune)")
        axes[0, 0].set_ylabel("receiver-relative CFO (kHz)")

        axes[0, 1].axhline(0, color="#17394d", linewidth=0.8)
        axes[0, 1].set_title(
            "B · Local Doppler-rate estimates; amber passed all gates",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].set_xlabel("target index (+ receiver offset)")
        axes[0, 1].set_ylabel("receiver-relative rate (kHz/s)")

        gate = product.config.phase_innovation_gate_rad
        axes[1, 0].axhline(gate, color="#d62728", linestyle=":", linewidth=0.9)
        axes[1, 0].axhline(-gate, color="#d62728", linestyle=":", linewidth=0.9)
        axes[1, 0].axhline(0, color="#17394d", linewidth=0.8)
        axes[1, 0].set_title(
            "C · Modulo-π phase innovations inside each independent window",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].set_xlabel("time since local window start (ms)")
        axes[1, 0].set_ylabel("wrapped phase innovation (rad)")

        axes[1, 1].axvline(
            product.config.minimum_supported_frame_fraction,
            color="#d62728",
            linestyle="--",
        )
        axes[1, 1].axhline(
            product.config.maximum_held_out_frequency_rms_hz,
            color="#d62728",
            linestyle="--",
        )
        axes[1, 1].set_title(
            "D · Coverage and held-out CFO prediction",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].set_xlabel("supported complete-frame fraction")
        axes[1, 1].set_ylabel("interleaved held-out RMS (Hz)")

        if not product.segments:
            axes[0, 0].text(
                0.5,
                0.5,
                product.reason,
                transform=axes[0, 0].transAxes,
                ha="center",
                va="center",
            )
        for axis in axes.flat:
            axis.grid(alpha=0.2)
            handles, labels = axis.get_legend_handles_labels()
            unique = dict(zip(labels, handles, strict=True))
            if unique:
                axis.legend(unique.values(), unique.keys(), fontsize=7, loc="best")
        figure.suptitle(
            "Scanner-native pilot phase and Doppler-rate analysis\n"
            f"{metrics.scan_id} · {product.qualified_segment_count}/"
            f"{product.analyzed_segment_count} qualified · 50–75 ms windows · "
            "no continuity across retunes or orbit/range claim",
            fontsize=15,
            fontweight="bold",
        )
        return _save(figure)


def render_scanner_pilot_carrier_tracking_png(
    metrics: ScannerAnalysisMetricsV1,
    product: ScannerPilotDopplerSegmentsV1,
) -> bytes:
    """Render scanner equivalents of frame-CFO panel A and rate-state panel C."""

    with _RENDER_LOCK:
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(figsize=(15.5, 6.8), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        cfo_axis, rate_axis = figure.subplots(1, 2)
        colors = ("#277da1", "#43aa8b", "#9d4edd", "#d1495b", "#f8961e")
        supported_count = 0
        coasted_count = 0
        supported_measurement_residuals: list[float] = []
        tracked_residuals: list[float] = []
        tracked_rates: list[float] = []
        rate_references: list[float] = []
        for segment in product.segments:
            color = colors[segment.segment_index % len(colors)]
            offset_ms = boundaries[segment.target_index]
            times_s = np.asarray([item.time_since_retune_s for item in segment.frames], dtype=float)
            times_ms = offset_ms + 1_000 * times_s
            supported = np.asarray(
                [item.measurement_supported for item in segment.frames], dtype=bool
            )
            measured = np.asarray(
                [item.absolute_cfo_measurement_hz for item in segment.frames], dtype=float
            )
            tracked = np.asarray(
                [item.tracked_absolute_cfo_hz for item in segment.frames], dtype=float
            )
            rates = np.asarray(
                [item.tracked_doppler_rate_hz_s for item in segment.frames], dtype=float
            )
            supported_count += int(np.count_nonzero(supported))
            coasted_count += int(np.count_nonzero(~supported))
            baseline = np.full_like(times_s, np.nan)
            if (
                segment.local_cfo_at_reference_hz is not None
                and segment.local_doppler_rate_hz_s is not None
            ):
                baseline = segment.local_cfo_at_reference_hz + segment.local_doppler_rate_hz_s * (
                    times_s - segment.reference_time_since_retune_s
                )
            measurement_residual = measured - baseline
            tracked_residual = tracked - baseline
            supported_measurement_residuals.extend(measurement_residual[supported])
            tracked_residuals.extend(tracked_residual)
            tracked_rates.extend(rates)
            rate_references.extend(
                value
                for value in (
                    segment.local_doppler_rate_hz_s,
                    segment.kalman_doppler_rate_hz_s if segment.qualified else None,
                )
                if value is not None
            )
            if np.any(~supported):
                cfo_axis.scatter(
                    times_ms[~supported],
                    measurement_residual[~supported],
                    s=12,
                    color="#aeb8c2",
                    alpha=0.35,
                    marker="x",
                    label="unsupported/coasted frame",
                )
                rate_axis.scatter(
                    times_ms[~supported],
                    rates[~supported] / 1_000,
                    s=12,
                    color="#aeb8c2",
                    alpha=0.35,
                    marker="x",
                    label="coasted rate state",
                )
            if np.any(supported):
                cfo_axis.scatter(
                    times_ms[supported],
                    measurement_residual[supported],
                    s=14,
                    color=color,
                    alpha=0.55,
                    label="supported frame CFO residual",
                )
                cfo_axis.scatter(
                    times_ms[supported],
                    tracked_residual[supported],
                    color="#d48806",
                    s=13,
                    alpha=0.65,
                    label="tracked CFO residual",
                )
                rate_axis.scatter(
                    times_ms[supported],
                    rates[supported] / 1_000,
                    s=13,
                    color="#d48806",
                    alpha=0.62,
                    label="tracked rate on supported frames",
                )
            if segment.local_doppler_rate_hz_s is not None:
                rate_axis.hlines(
                    segment.local_doppler_rate_hz_s / 1_000,
                    offset_ms + 1_000 * segment.window_start_s,
                    offset_ms + 1_000 * segment.window_end_s,
                    color=color,
                    linestyle="--",
                    linewidth=1.5,
                    label="direct local segment rate",
                )
        for boundary in boundaries[1:-1]:
            for axis in (cfo_axis, rate_axis):
                axis.axvline(boundary, color=_BOUNDARY_COLOR, linewidth=0.8, alpha=0.45)
        cfo_limits = _robust_display_limits(
            supported_measurement_residuals,
            minimum_span=1_000.0,
        )
        cfo_axis.set_ylim(*cfo_limits)
        rate_limits = _robust_display_limits(
            rate_references or tracked_rates,
            minimum_span=20_000.0,
        )
        rate_axis.set_ylim(rate_limits[0] / 1_000, rate_limits[1] / 1_000)
        clipped_cfo = sum(
            value < cfo_limits[0] or value > cfo_limits[1] for value in tracked_residuals
        )
        clipped_rate = sum(
            value < rate_limits[0] or value > rate_limits[1] for value in tracked_rates
        )
        if clipped_cfo:
            cfo_axis.text(
                0.99,
                0.02,
                f"{clipped_cfo} tracked-state outliers outside robust display range",
                transform=cfo_axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
                color="#6b7280",
            )
        if clipped_rate:
            rate_axis.text(
                0.99,
                0.02,
                f"{clipped_rate} tracked-rate outliers outside local-reference display range",
                transform=rate_axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
                color="#6b7280",
            )
        cfo_axis.axhline(0, color="#17394d", linewidth=0.8)
        cfo_axis.set_title(
            f"A · Frame CFO residuals vs local segment model ({supported_count} supported; "
            f"{coasted_count} coasted)",
            loc="left",
            fontweight="bold",
        )
        cfo_axis.set_ylabel("CFO residual vs local robust line (Hz)")
        rate_axis.set_title(
            "C · Carrier-rate state inside independent retune-bounded windows",
            loc="left",
            fontweight="bold",
        )
        rate_axis.set_ylabel("receiver-relative Doppler/CFO rate (kHz/s)")
        for axis in (cfo_axis, rate_axis):
            axis.set_xlabel("stitched display time (ms; red = retune)")
            axis.grid(alpha=0.2)
            handles, labels = axis.get_legend_handles_labels()
            unique = dict(zip(labels, handles, strict=True))
            if unique:
                axis.legend(unique.values(), unique.keys(), fontsize=8, loc="best")
        figure.suptitle(
            "Scanner frame-level pilot carrier tracking\n"
            f"{metrics.scan_id} · local baselines reset at every window and retune · "
            "no frozen cross-retune model",
            fontsize=15,
            fontweight="bold",
        )
        return _save(figure)


def render_scanner_pilot_segment_rates_png(
    metrics: ScannerAnalysisMetricsV1,
    product: ScannerPilotDopplerSegmentsV1,
) -> bytes:
    """Render Doppler-rate estimates across every 50--75 ms scanner segment."""

    with _RENDER_LOCK:
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(figsize=(15.5, 6.2), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        for segment in product.segments:
            color = "#d48806" if segment.qualified else "#aeb8c2"
            start = boundaries[segment.target_index] + 1_000 * segment.window_start_s
            end = boundaries[segment.target_index] + 1_000 * segment.window_end_s
            reference = boundaries[segment.target_index] + 1_000 * (
                segment.reference_time_since_retune_s
            )
            if segment.local_doppler_rate_hz_s is not None:
                local = segment.local_doppler_rate_hz_s / 1_000
                axis.hlines(
                    local,
                    start,
                    end,
                    color=color,
                    linewidth=3.0 if segment.qualified else 1.5,
                    label=(
                        "qualified direct local rate"
                        if segment.qualified
                        else "failed-gate direct rate"
                    ),
                )
                if segment.local_doppler_rate_sigma_hz_s is not None:
                    sigma = segment.local_doppler_rate_sigma_hz_s / 1_000
                    axis.fill_between(
                        (start, end),
                        local - sigma,
                        local + sigma,
                        color=color,
                        alpha=0.1,
                    )
            if segment.kalman_doppler_rate_hz_s is not None:
                axis.scatter(
                    reference,
                    segment.kalman_doppler_rate_hz_s / 1_000,
                    color="#277da1",
                    marker="x",
                    s=46,
                    label="segment-final modulo-π Kalman rate",
                )
            axis.annotate(
                f"CH{segment.target.channel}{segment.target.edge.value[0].upper()} "
                f"RX{segment.receiver_id}",
                (reference, segment.local_doppler_rate_hz_s / 1_000)
                if segment.local_doppler_rate_hz_s is not None
                else (reference, 0),
                xytext=(3, 4),
                textcoords="offset points",
                fontsize=7,
            )
        for boundary in boundaries[1:-1]:
            axis.axvline(boundary, color=_BOUNDARY_COLOR, linewidth=0.8, alpha=0.45)
        if not product.segments:
            axis.text(0.5, 0.5, product.reason, transform=axis.transAxes, ha="center", va="center")
        axis.axhline(0, color="#17394d", linewidth=0.7, alpha=0.6)
        axis.set_title(
            "Doppler-rate estimates over each independent 50–75 ms scanner segment",
            loc="left",
            fontweight="bold",
        )
        axis.set_xlabel("stitched display time (ms; red = retune)")
        axis.set_ylabel("receiver-relative Doppler/CFO rate (kHz/s)")
        axis.grid(alpha=0.2)
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        if unique:
            axis.legend(unique.values(), unique.keys(), fontsize=8, loc="best")
        figure.suptitle(
            "Scanner local pilot-segment Doppler rates\n"
            f"{metrics.scan_id} · {product.qualified_segment_count}/"
            f"{product.analyzed_segment_count} segments qualified · no cross-retune continuity",
            fontsize=15,
            fontweight="bold",
        )
        return _save(figure)


def _frame_boundaries_ms(metrics: ScannerAnalysisMetricsV1) -> tuple[float, ...]:
    """Return stitched display offsets without implying RF continuity."""

    boundaries = [0.0]
    for frame in metrics.frames:
        duration_ms = (
            1_000.0 * frame.sample_count / metrics.configuration.sample_rate_hz
            if frame.status == "complete"
            else float(metrics.configuration.dwell_ms)
        )
        boundaries.append(boundaries[-1] + duration_ms)
    return tuple(boundaries)


def _waterfall_matrix(waterfall: StandardNumericalWaterfallV2) -> np.ndarray:
    return np.asarray(
        [tile.receiver_power_dbfs[0] for tile in waterfall.tiles],
        dtype=np.float64,
    )


def _save(figure: Figure) -> bytes:
    output = io.BytesIO()
    figure.savefig(
        output,
        format="png",
        dpi=160,
        metadata={"Software": "leo-tracker standard scan analysis"},
    )
    return output.getvalue()


def _robust_display_limits(
    values: list[float],
    *,
    minimum_span: float,
) -> tuple[float, float]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if not finite.size:
        return (-minimum_span / 2, minimum_span / 2)
    lower, upper = (float(value) for value in np.quantile(finite, (0.005, 0.995)))
    center = (lower + upper) / 2
    span = max(minimum_span, (upper - lower) * 1.15)
    return center - span / 2, center + span / 2
