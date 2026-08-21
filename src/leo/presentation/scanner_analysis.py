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


def render_scanner_waterfall_png(metrics: ScannerAnalysisMetricsV1) -> bytes:
    """Render target- and receiver-faceted waterfalls without crossing retunes."""

    with _RENDER_LOCK:
        configuration = metrics.configuration
        receivers = configuration.receiver_ids
        rows = max(item.channel for item in configuration.targets)
        columns = 2 * len(receivers)
        figure = Figure(
            figsize=(5.0 * columns, 3.25 * rows + 1.0),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(rows, columns, squeeze=False)
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
        for frame in metrics.frames:
            edge_column = 0 if frame.target.edge.value == "lower" else len(receivers)
            for receiver_column, receiver_id in enumerate(receivers):
                axis = axes[frame.target.channel - 1, edge_column + receiver_column]
                if frame.status == "failed":
                    axis.text(0.5, 0.5, frame.reason, ha="center", va="center")
                    axis.set_axis_off()
                    continue
                waterfall = frame.waterfalls[receiver_column]
                matrix = _waterfall_matrix(waterfall)
                actual_rf_hz = (
                    int(frame.actual_if_center_hz or frame.target.if_center_hz)
                    + configuration.lnb_lo_hz
                )
                frequencies_mhz = (
                    actual_rf_hz + np.asarray(waterfall.frequency_bin_centers_hz, dtype=np.float64)
                ) / 1_000_000.0
                half_bin = (
                    (frequencies_mhz[1] - frequencies_mhz[0]) / 2.0
                    if len(frequencies_mhz) > 1
                    else configuration.sample_rate_hz / 2_000_000.0
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
                        1_000 * frame.sample_count / configuration.sample_rate_hz,
                        0.0,
                    ),
                    vmin=lower,
                    vmax=upper,
                    rasterized=True,
                )
                axis.set_title(
                    f"CH{frame.target.channel} {frame.target.edge.value} · RX{receiver_id}",
                    loc="left",
                    fontsize=9,
                    fontweight="bold",
                )
                axis.set_xlabel("RF frequency (MHz)")
                axis.set_ylabel("Dwell time (ms)")
        if image is not None:
            figure.colorbar(
                image,
                ax=[axis for axis in axes.flat if axis.get_visible()],
                label="Power spectral density (dBFS)",
                pad=0.01,
            )
        figure.suptitle(
            f"Segmented scanner waterfall · no FFT crosses a retune boundary\n{metrics.scan_id}",
            fontsize=14,
            fontweight="bold",
        )
        return _save(figure)


def render_scanner_glrt64_response_png(metrics: ScannerAnalysisMetricsV1) -> bytes:
    """Render complete per-probe GLRT64 margins for every channel edge."""

    with _RENDER_LOCK:
        rows = max(item.channel for item in metrics.configuration.targets)
        figure = Figure(
            figsize=(16.0, 3.4 * rows + 1.0),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(rows, 2, sharex=True, sharey=True, squeeze=False)
        gate = metrics.configuration.glrt64_margin_gate
        for frame in metrics.frames:
            column = 0 if frame.target.edge.value == "lower" else 1
            axis = axes[frame.target.channel - 1, column]
            if frame.status == "failed":
                axis.text(0.5, 0.5, frame.reason, ha="center", va="center")
                axis.set_axis_off()
                continue
            for receiver_index, receiver_id in enumerate(metrics.configuration.receiver_ids):
                probes = tuple(item for item in frame.probes if item.receiver_id == receiver_id)
                times = np.asarray([item.probe_start_ms for item in probes], dtype=float)
                margins = np.asarray(
                    [
                        max((candidate.margin for candidate in item.candidates), default=np.nan)
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
            axis.axhline(
                gate,
                color="#d1495b",
                linestyle="--",
                linewidth=1.1,
                label=f"margin gate {gate:.3f}",
            )
            if frame.first_detection is not None:
                hit = frame.first_detection
                axis.scatter(
                    [hit.probe_start_ms],
                    [hit.margin],
                    marker="*",
                    s=100,
                    color="#00a878",
                    edgecolor="black",
                    linewidth=0.5,
                    zorder=5,
                    label="first member of confirmed pair",
                )
            axis.set_title(
                f"CH{frame.target.channel} {frame.target.edge.value} · {frame.decision.value}",
                loc="left",
                fontsize=10,
                fontweight="bold",
            )
            axis.set_ylabel("GLRT64 exact − control margin")
            axis.grid(alpha=0.2)
            handles, labels = axis.get_legend_handles_labels()
            unique = dict(zip(labels, handles, strict=True))
            axis.legend(unique.values(), unique.keys(), loc="best", fontsize=7)
        for axis in axes[-1]:
            axis.set_xlabel("Probe start within dwell (ms)")
        figure.suptitle(
            "Complete scanner GLRT64 response · 20 ms probes / 10 ms stride\n"
            "star = first member of the same-receiver CFO-consistent confirming pair\n"
            f"{metrics.scan_id}",
            fontsize=13,
            fontweight="bold",
        )
        return _save(figure)


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
