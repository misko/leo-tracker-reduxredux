"""Deterministic scientific PNGs for segmented scanner analysis."""

from __future__ import annotations

import io
from threading import RLock

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2
from leo.scanner.analysis_models import ScannerAnalysisMetricsV1

_RENDER_LOCK = RLock()
_RECEIVER_COLORS = ("#00a6d6", "#f28e2b")
_BOUNDARY_COLOR = "#d62728"


def render_scanner_waterfall_png(metrics: ScannerAnalysisMetricsV1) -> bytes:
    """Render one scan-wide waterfall lane per receiver, split at retunes."""

    with _RENDER_LOCK:
        receivers = metrics.configuration.receiver_ids
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(
            figsize=(16.0, 2.8 * len(receivers) + 2.0),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(len(receivers), 1, sharex=True, squeeze=False)[:, 0]
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
                    axis.axvspan(start_ms, end_ms, color="#d9d9d9", alpha=0.8)
                    axis.text(
                        (start_ms + end_ms) / 2.0,
                        0.5,
                        "failed",
                        ha="center",
                        va="center",
                        transform=axis.get_xaxis_transform(),
                        fontsize=8,
                    )
                    continue
                waterfall = frame.waterfalls[receiver_index]
                matrix = _waterfall_matrix(waterfall)
                frequencies_mhz = np.asarray(
                    waterfall.frequency_bin_centers_hz, dtype=np.float64
                ) / 1_000_000.0
                half_bin = (
                    (frequencies_mhz[1] - frequencies_mhz[0]) / 2.0
                    if len(frequencies_mhz) > 1
                    else metrics.configuration.sample_rate_hz / 2_000_000.0
                )
                image = axis.imshow(
                    matrix.T,
                    cmap="magma",
                    interpolation="nearest",
                    aspect="auto",
                    origin="lower",
                    extent=(
                        start_ms,
                        end_ms,
                        frequencies_mhz[0] - half_bin,
                        frequencies_mhz[-1] + half_bin,
                    ),
                    vmin=lower,
                    vmax=upper,
                    rasterized=True,
                )
            for boundary_ms in boundaries[1:-1]:
                axis.axvline(boundary_ms, color=_BOUNDARY_COLOR, linewidth=1.0, zorder=4)
            axis.set_ylabel(f"RX{receiver_id}\nbaseband offset (MHz)")

        top_axis = axes[0]
        for frame_index, frame in enumerate(metrics.frames):
            start_ms, end_ms = boundaries[frame_index : frame_index + 2]
            actual_if_hz = frame.actual_if_center_hz or frame.requested_if_center_hz
            actual_rf_mhz = (
                actual_if_hz + metrics.configuration.lnb_lo_hz
            ) / 1_000_000.0
            top_axis.text(
                (start_ms + end_ms) / 2.0,
                1.02,
                f"CH{frame.target.channel} {frame.target.edge.value[0].upper()}\n"
                f"{actual_rf_mhz:.3f} MHz",
                ha="center",
                va="bottom",
                transform=top_axis.get_xaxis_transform(),
                fontsize=7,
            )
        axes[-1].set_xlabel("Stitched scan storage time (ms)")
        axes[-1].set_xlim(boundaries[0], boundaries[-1])
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


def render_scanner_glrt64_response_png(metrics: ScannerAnalysisMetricsV1) -> bytes:
    """Render every dwell's GLRT64 probes on one stitched scan-time axis."""

    with _RENDER_LOCK:
        boundaries = _frame_boundaries_ms(metrics)
        figure = Figure(figsize=(16.0, 6.5), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        gate = metrics.configuration.glrt64_margin_gate
        for frame_index, frame in enumerate(metrics.frames):
            start_ms, end_ms = boundaries[frame_index : frame_index + 2]
            if frame.status == "failed":
                axis.axvspan(start_ms, end_ms, color="#d9d9d9", alpha=0.8)
            else:
                for receiver_index, receiver_id in enumerate(
                    metrics.configuration.receiver_ids
                ):
                    probes = tuple(
                        item for item in frame.probes if item.receiver_id == receiver_id
                    )
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
                        color=_RECEIVER_COLORS[
                            receiver_index % len(_RECEIVER_COLORS)
                        ],
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
