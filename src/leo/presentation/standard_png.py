"""Publication-quality PNG rendering for verified Standard presentation views."""

from __future__ import annotations

import io
import math
from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import Any

import matplotlib

matplotlib.use("Agg")
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.presentation.standard_pipeline import StandardPlotViewV2, StandardViewKindV2

_RENDER_LOCK = RLock()
_LANE_COLORS = ("#00a6d6", "#f28e2b", "#8e5bb7", "#59a14f")
_DEGREE_STYLES = {1: "--", 2: "-.", 3: "-"}


@dataclass(frozen=True, slots=True)
class StandardPngPathSource:
    """Verified full-resolution path inputs used only by the PNG renderer."""

    path_id: str
    label: str
    time_offset_s: float
    tuned_center_frequency_hz: int
    sample_rate_hz: int
    receiver_id: int
    waterfall: dict[str, Any]
    pilot_scan: dict[str, Any]
    trajectory_feedback: dict[str, Any]
    trajectory_table: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StandardPngSource:
    """Run-bound full-resolution plot source; never serialized by the API."""

    session_id: str
    subject_id: str
    elapsed_start_s: float
    elapsed_end_s: float
    paths: tuple[StandardPngPathSource, ...]


def render_standard_plot_png(
    view: StandardPlotViewV2,
    *,
    cfo_companion: StandardPlotViewV2 | None = None,
) -> bytes:
    """Render one verified bounded presentation view as a labeled scientific figure.

    GLRT64 figures may include the separately verified CFO view.  This recreates
    the reviewed trajectory-feedback layout without merging their public JSON
    contracts or reading raw IQ.
    """

    if cfo_companion is not None:
        if view.view_kind is not StandardViewKindV2.GLRT64:
            raise ValueError("a CFO companion is accepted only for the GLRT64 figure")
        if cfo_companion.view_kind is not StandardViewKindV2.CFO_TRAJECTORY:
            raise ValueError("GLRT64 companion must be the CFO trajectory view")
        if (
            cfo_companion.session_id != view.session_id
            or cfo_companion.subject_id != view.subject_id
            or cfo_companion.receiver_path_ids != view.receiver_path_ids
            or cfo_companion.time_domain != view.time_domain
        ):
            raise ValueError("GLRT64 and CFO presentation views are not co-bound")

    with _RENDER_LOCK:
        figure = _figure(view)
        if view.view_kind is StandardViewKindV2.WATERFALL:
            _render_waterfall(figure, view)
        elif view.view_kind is StandardViewKindV2.GLRT64:
            _render_glrt64(figure, view, cfo_companion)
        elif view.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            _render_cfo(figure, view)
        else:
            _render_metric(figure, view)
        return _save(figure)


def render_full_standard_plot_png(
    source: StandardPngSource, view_kind: StandardViewKindV2
) -> bytes:
    """Render verified full source arrays without weakening bounded JSON contracts."""

    if view_kind not in {
        StandardViewKindV2.WATERFALL,
        StandardViewKindV2.GLRT64,
        StandardViewKindV2.CFO_TRAJECTORY,
        StandardViewKindV2.QAM,
    }:
        raise ValueError("full-source rendering is unsupported for this view")
    with _RENDER_LOCK:
        if view_kind is StandardViewKindV2.WATERFALL:
            return _render_full_waterfall(source)
        if view_kind is StandardViewKindV2.GLRT64:
            return _render_full_pilot_methods(source)
        if view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            return _render_full_cfo_trajectories(source)
        return _render_full_qam(source)


def _render_full_cfo_trajectories(source: StandardPngSource) -> bytes:
    figure = Figure(
        figsize=(15.0, 4.0 * len(source.paths)),
        dpi=160,
        constrained_layout=True,
    )
    FigureCanvasAgg(figure)
    axes = figure.subplots(len(source.paths), 1, sharex=True, squeeze=False)[:, 0]
    for path_index, (axis, path) in enumerate(zip(axes, source.paths, strict=True)):
        observation_times: list[float] = []
        observation_cfo: list[float] = []
        for detection in path.pilot_scan["detections"]:
            for candidate in detection["candidates"]:
                score = next(
                    (item for item in candidate["scores"] if item["method"] == "glrt64"),
                    None,
                )
                if score is not None:
                    observation_times.append(path.time_offset_s + float(detection["time_s"]))
                    observation_cfo.append(float(score["tracking_cfo_hz"]) / 1_000.0)
        axis.scatter(
            observation_times,
            observation_cfo,
            s=4,
            color="#8b949e",
            alpha=0.22,
            rasterized=True,
            label="GLRT64 candidate CFO",
        )
        for row in path.trajectory_table["trajectories"]:
            if not bool(row["fit_matches_well"]):
                continue
            start = path.time_offset_s + float(row["start_s"])
            end = path.time_offset_s + float(row["end_s"])
            times = np.linspace(start, end, max(40, round((end - start) * 20)))
            relative = times - path.time_offset_s - float(row["reference_time_s"])
            cfo = np.polyval(np.asarray(row["coefficients_hz"], dtype=float), relative) / 1_000.0
            degree = int(row["polynomial_degree"])
            selected = bool(row["selected_for_correction"])
            axis.plot(
                times,
                cfo,
                color=_LANE_COLORS[path_index % len(_LANE_COLORS)],
                linestyle=_DEGREE_STYLES[degree],
                linewidth=2.7 if selected else 1.0,
                alpha=0.98 if selected else 0.42,
                label=f"degree {degree}{' · selected' if selected else ''}",
            )
        axis.set_title(path.label, loc="left", fontsize=10, fontweight="bold")
        axis.set_ylabel("Baseband CFO (kHz)")
        axis.set_xlim(source.elapsed_start_s, source.elapsed_end_s)
        axis.grid(alpha=0.2)
        handles, labels = axis.get_legend_handles_labels()
        if handles:
            unique = dict(zip(labels, handles, strict=True))
            axis.legend(unique.values(), unique.keys(), loc="best", fontsize=8, ncols=4)
    axes[-1].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        "GLRT64 candidate CFO and iterative polynomial trajectories\n"
        "linear, quadratic, cubic · candidate-only · no attribution\n"
        f"{source.session_id}",
        fontsize=12,
        fontweight="bold",
    )
    return _save(figure, dpi=160)


def _figure(view: StandardPlotViewV2) -> Figure:
    lane_count = max(1, len(view.receiver_path_ids))
    height = 4.0 if lane_count == 1 else 2.85 * lane_count + 1.25
    figure = Figure(figsize=(15.5, height), dpi=120, constrained_layout=True)
    FigureCanvasAgg(figure)
    figure.set_facecolor("white")
    figure.suptitle(
        _title(view),
        fontsize=14,
        fontweight="bold",
    )
    return figure


def _title(view: StandardPlotViewV2) -> str:
    names = {
        StandardViewKindV2.WATERFALL: "Frequency × time waterfall",
        StandardViewKindV2.GLRT64: "GLRT64 trajectory feedback",
        StandardViewKindV2.QAM: "Known-pilot QAM timeline",
        StandardViewKindV2.CFO_TRAJECTORY: "Candidate CFO trajectories",
        StandardViewKindV2.POWER: "Receiver power timeline",
        StandardViewKindV2.QUALITY: "Recording quality coverage",
    }
    return (
        f"{names[view.view_kind]} · {view.session_id}\n"
        "candidate-only evidence · no attribution or payload decoding"
    )


def _axes(figure: Figure, view: StandardPlotViewV2) -> tuple[Any, ...]:
    axes = figure.subplots(len(view.receiver_path_ids), 1, sharex=True, squeeze=False)
    return tuple(axes[:, 0])


def _render_waterfall(figure: Figure, view: StandardPlotViewV2) -> None:
    axes = _axes(figure, view)
    image = None
    for axis, lane in zip(axes, view.receiver_path_ids, strict=True):
        cells = [item for item in view.waterfall_cells if item.receiver_path_id == lane]
        times = sorted({item.time_s for item in cells})
        frequencies = sorted({item.frequency_hz for item in cells})
        time_indexes = {value: index for index, value in enumerate(times)}
        frequency_indexes = {value: index for index, value in enumerate(frequencies)}
        powers = np.full((len(times), len(frequencies)), np.nan)
        for cell in cells:
            powers[time_indexes[cell.time_s], frequency_indexes[cell.frequency_hz]] = cell.power_db
        image = axis.pcolormesh(
            np.asarray(frequencies) / 1_000.0,
            np.asarray(times),
            powers,
            cmap="viridis",
            shading="nearest",
            vmin=None if view.color_axis is None else view.color_axis.full_source_min,
            vmax=None if view.color_axis is None else view.color_axis.full_source_max,
            rasterized=True,
        )
        axis.set_title(_lane_label(lane), loc="left", fontsize=10, fontweight="bold")
        axis.set_ylabel("Elapsed time (s)")
        axis.set_xlim(
            view.horizontal_axis.full_source_min / 1_000.0,
            view.horizontal_axis.full_source_max / 1_000.0,
        )
        axis.set_ylim(view.time_domain.elapsed_end_s, view.time_domain.elapsed_start_s)
        axis.grid(False)
    axes[-1].set_xlabel("Baseband frequency (kHz)")
    if image is not None:
        figure.colorbar(image, ax=list(axes), label="Power spectral density (dBFS)", pad=0.012)


def _render_full_waterfall(source: StandardPngSource) -> bytes:
    matrices: list[np.ndarray] = []
    for path in source.paths:
        receiver_ids = tuple(path.waterfall["receiver_ids"])
        try:
            receiver_index = receiver_ids.index(path.receiver_id)
        except ValueError as error:
            raise ValueError("waterfall receiver inventory disagrees with PNG source") from error
        matrices.append(
            np.asarray(
                [tile["receiver_power_dbfs"][receiver_index] for tile in path.waterfall["tiles"]],
                dtype=np.float64,
            )
        )
    finite = np.concatenate(tuple(matrix[np.isfinite(matrix)] for matrix in matrices))
    if not finite.size:
        raise ValueError("waterfall contains no finite power values")
    lower, upper = (float(value) for value in np.percentile(finite, (3.0, 99.7)))
    if upper <= lower:
        upper = lower + 1.0

    columns = 2 if len(source.paths) > 1 else 1
    rows = math.ceil(len(source.paths) / columns)
    figure = Figure(
        figsize=(8.2 * columns, 4.2 * rows + 1.0),
        dpi=160,
        constrained_layout=True,
    )
    FigureCanvasAgg(figure)
    axes = figure.subplots(rows, columns, squeeze=False)
    last_image = None
    for axis, path, matrix in zip(axes.flat, source.paths, matrices, strict=False):
        frequencies_mhz = (
            path.tuned_center_frequency_hz
            + np.asarray(path.waterfall["frequency_bin_centers_hz"], dtype=np.float64)
        ) / 1_000_000.0
        half_bin_mhz = (
            (frequencies_mhz[1] - frequencies_mhz[0]) / 2.0
            if len(frequencies_mhz) > 1
            else path.sample_rate_hz / 2_000_000.0
        )
        last_image = axis.imshow(
            matrix,
            cmap="magma",
            interpolation="nearest",
            aspect="auto",
            origin="upper",
            extent=(
                frequencies_mhz[0] - half_bin_mhz,
                frequencies_mhz[-1] + half_bin_mhz,
                path.time_offset_s
                + path.waterfall["coverage"]["expected_samples"] / path.sample_rate_hz,
                path.time_offset_s,
            ),
            vmin=lower,
            vmax=upper,
            rasterized=True,
        )
        axis.set_title(path.label, loc="left", fontsize=10, fontweight="bold")
        axis.set_xlabel("Tuned-domain frequency (MHz)")
        axis.set_ylabel("Elapsed time (s; increases downward)")
        axis.grid(False)
    for axis in tuple(axes.flat)[len(source.paths) :]:
        axis.set_visible(False)
    if last_image is not None:
        figure.colorbar(
            last_image,
            ax=[axis for axis in axes.flat if axis.get_visible()],
            label="Power spectral density (dBFS)",
            pad=0.02,
        )
    first = source.paths[0]
    figure.suptitle(
        f"Verified full-dwell waterfall · {source.session_id}\n"
        f"{len(first.waterfall['tiles'])} time bins × "
        f"{len(first.waterfall['frequency_bin_centers_hz'])} frequency bins · "
        f"{first.waterfall['fft_samples']}-sample Hann FFT",
        fontsize=14,
        fontweight="bold",
    )
    return _save(figure, dpi=160)


def _render_full_qam(source: StandardPngSource) -> bytes:
    figure = Figure(
        figsize=(15.0, 7.7 * len(source.paths)),
        dpi=160,
        constrained_layout=True,
    )
    FigureCanvasAgg(figure)
    grid = figure.add_gridspec(
        2 * len(source.paths),
        1,
        height_ratios=tuple(value for _ in source.paths for value in (2, 1)),
    )
    shared_x = None
    shared_accuracy_y = None
    shared_margin_y = None
    for path_index, path in enumerate(source.paths):
        qam_axis = figure.add_subplot(
            grid[2 * path_index],
            sharex=shared_x,
            sharey=shared_accuracy_y,
        )
        pilot_axis = figure.add_subplot(
            grid[2 * path_index + 1],
            sharex=shared_x,
            sharey=shared_margin_y,
        )
        if shared_x is None:
            shared_x = qam_axis
            shared_accuracy_y = qam_axis
            shared_margin_y = pilot_axis
        detections = path.pilot_scan["detections"]
        times = np.asarray([path.time_offset_s + float(item["time_s"]) for item in detections])
        accuracy = np.asarray(
            [
                math.nan if item["qam_accuracy"] is None else float(item["qam_accuracy"])
                for item in detections
            ]
        )
        margin = np.asarray([_symbolwise_margin(item["scores"]) for item in detections])
        positive = (accuracy >= 0.60) & (margin >= 0.05)
        qam_axis.plot(times, accuracy, color="#8c8c8c", linewidth=0.65, alpha=0.75)
        qam_axis.scatter(
            times[~positive],
            accuracy[~positive],
            s=8,
            color="#8c8c8c",
            alpha=0.55,
            label="searched probe",
        )
        qam_axis.scatter(
            times[positive],
            accuracy[positive],
            s=14,
            color="#00a878",
            alpha=0.9,
            label="accuracy ≥ 0.60 and pilot margin ≥ 0.05",
        )
        qam_axis.axhline(0.60, color="#d1495b", linestyle="--", linewidth=1.2)
        qam_axis.set_ylim(0, 1.02)
        qam_axis.set_ylabel("Known-pilot hard-symbol accuracy")
        qam_axis.set_title(path.label, loc="left", fontweight="bold")
        qam_axis.grid(alpha=0.2)
        qam_axis.legend(loc="upper right")

        pilot_axis.plot(times, margin, color="#355070", linewidth=0.8)
        pilot_axis.scatter(times[positive], margin[positive], s=11, color="#00a878", alpha=0.9)
        pilot_axis.axhline(0.05, color="#d1495b", linestyle="--", linewidth=1.2)
        pilot_axis.axhline(0.0, color="black", linewidth=0.6, alpha=0.5)
        pilot_axis.set_ylabel("Pilot verify − control margin")
        pilot_axis.grid(alpha=0.2)
        pilot_axis.set_xlim(source.elapsed_start_s, source.elapsed_end_s)
        if path_index == len(source.paths) - 1:
            pilot_axis.set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        f"{_probe_geometry_label(source)} · candidate-only known symbols · "
        f"no payload\n{source.session_id}",
        fontsize=11,
    )
    return _save(figure, dpi=160)


def _probe_geometry_label(source: StandardPngSource) -> str:
    geometries = {
        (
            int(path.pilot_scan["coarse_window_samples"]),
            int(path.pilot_scan["subwindow_samples"]),
            int(path.pilot_scan["probe_samples"]),
        )
        for path in source.paths
    }
    if len(geometries) != 1:
        return "Mixed Qin edge-pilot probe geometries"
    coarse, subwindow, probe = geometries.pop()
    probe_ms = 1_000 * probe / coarse
    subwindow_ms = 1_000 * subwindow / coarse
    return f"{probe_ms:g} ms Qin edge-pilot probes every {subwindow_ms:g} ms"


def _symbolwise_margin(scores: list[dict[str, Any]]) -> float:
    value = next(
        (score["margin"] for score in scores if score["method"] == "symbolwise"),
        None,
    )
    return math.nan if value is None else float(value)


def _render_full_pilot_methods(source: StandardPngSource) -> bytes:
    methods = (
        ("glrt64", "GLRT-64 searched residual-CFO margin", "#1d4e89"),
        ("symbolwise", "Current full-frame symbolwise margin", "#f4a261"),
        ("anchor8", "Anchor-8 conditioned phase margin", "#6d597a"),
    )
    figure = Figure(
        figsize=(15.0, 3.35 * len(methods) * len(source.paths)),
        dpi=160,
        constrained_layout=True,
    )
    FigureCanvasAgg(figure)
    grid = figure.add_gridspec(len(methods) * len(source.paths), 1)
    shared_x = None
    for path_index, path in enumerate(source.paths):
        detections = path.pilot_scan["detections"]
        times = np.asarray([path.time_offset_s + float(item["time_s"]) for item in detections])
        accuracy = np.asarray(
            [
                math.nan if item["qam_accuracy"] is None else float(item["qam_accuracy"])
                for item in detections
            ]
        )
        symbolwise = np.asarray([_symbolwise_margin(item["scores"]) for item in detections])
        positive = (accuracy >= 0.60) & (symbolwise >= 0.05)
        for method_index, (method, title, color) in enumerate(methods):
            axis = figure.add_subplot(
                grid[path_index * len(methods) + method_index],
                sharex=shared_x,
            )
            if shared_x is None:
                shared_x = axis
            margins = np.asarray([_method_margin(item["scores"], method) for item in detections])
            axis.plot(times, margins, color=color, linewidth=0.75, alpha=0.72)
            axis.scatter(times, margins, color=color, s=7, alpha=0.32, rasterized=True)
            axis.scatter(
                times[positive],
                margins[positive],
                color="#00a878",
                s=13,
                alpha=0.9,
                label="symbolwise/QAM-positive probe",
                rasterized=True,
            )
            if method == "glrt64":
                corrected = tuple(
                    item
                    for item in path.trajectory_feedback["results"]
                    if item["detector_method"] == "glrt64"
                )
                axis.scatter(
                    [path.time_offset_s + float(item["time_s"]) for item in corrected],
                    [float(item["corrected_margin"]) for item in corrected],
                    color="#d1495b",
                    marker="x",
                    s=18,
                    linewidths=0.8,
                    alpha=0.72,
                    label="after selected GLRT64 trajectory correction",
                    rasterized=True,
                )
            axis.axhline(0.0, color="black", linewidth=0.65, alpha=0.55)
            axis.set_ylabel("Exact − rolled-control score")
            axis.set_title(f"{path.label} · {title}", loc="left", fontsize=10, fontweight="bold")
            axis.grid(alpha=0.2)
            axis.set_xlim(source.elapsed_start_s, source.elapsed_end_s)
            # Deliberately do not share Y axes: these detector scores have
            # different natural ranges and are comparison evidence, not a
            # common calibrated probability.
            if method_index == 0:
                axis.legend(loc="upper right")
            if path_index == len(source.paths) - 1 and method_index == len(methods) - 1:
                axis.set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        "Qin edge-pilot detector comparison · independent Y scales\n"
        "Only GLRT64 proposes trajectory tracks · candidate-only · no payload\n"
        f"{source.session_id}",
        fontsize=12,
        fontweight="bold",
    )
    return _save(figure, dpi=160)


def _method_margin(scores: list[dict[str, Any]], method: str) -> float:
    value = next((score["margin"] for score in scores if score["method"] == method), None)
    return math.nan if value is None else float(value)


def _render_glrt64(
    figure: Figure,
    view: StandardPlotViewV2,
    companion: StandardPlotViewV2 | None,
) -> None:
    axes = _axes(figure, view)
    cfo_by_lane = _cfo_inventory(companion)
    for row, (axis, lane) in enumerate(zip(axes, view.receiver_path_ids, strict=True)):
        lane_series = [item for item in view.series if item.receiver_path_id == lane]
        for series in lane_series:
            initial = ":initial:" in f":{series.series_id}:"
            axis.plot(
                [item.time_s for item in series.points],
                [item.value for item in series.points],
                linestyle="none" if initial else "-",
                marker="." if initial else None,
                markersize=2.5,
                linewidth=0.9,
                alpha=0.34 if initial else 0.82,
                color="#8b949e" if initial else _LANE_COLORS[row % len(_LANE_COLORS)],
                label="initial GLRT64 response" if initial else "trajectory-corrected GLRT64",
                rasterized=initial,
            )
        axis.axhline(0.0, color="#d62728", linewidth=0.75, linestyle=":", alpha=0.55)
        axis.set_ylabel("GLRT64\nresponse")
        axis.set_ylim(view.vertical_axis.full_source_min, view.vertical_axis.full_source_max)
        axis.set_title(_lane_label(lane), loc="left", fontsize=10, fontweight="bold")
        axis.grid(True, axis="x", color="#d0d7de", linewidth=0.55, alpha=0.65)
        observations, curves = cfo_by_lane.get(lane, ((), ()))
        if observations or curves:
            cfo_axis = axis.twinx()
            cfo_axis.scatter(
                [item.time_s for item in observations],
                [item.baseband_cfo_hz / 1_000.0 for item in observations],
                s=3,
                color="#111827",
                alpha=0.12,
                rasterized=True,
                label="observed CFO",
            )
            for curve in curves:
                cfo_axis.plot(
                    [item.time_s for item in curve.points],
                    [item.value / 1_000.0 for item in curve.points],
                    color=_LANE_COLORS[row % len(_LANE_COLORS)],
                    linestyle=_DEGREE_STYLES[curve.degree],
                    linewidth=2.6 if curve.selected_for_correction else 1.0,
                    alpha=0.96 if curve.selected_for_correction else 0.42,
                    label=f"degree {curve.degree} CFO fit",
                )
            if companion is not None:
                cfo_axis.set_ylim(
                    companion.vertical_axis.full_source_min / 1_000.0,
                    companion.vertical_axis.full_source_max / 1_000.0,
                )
            cfo_axis.set_ylabel("CFO (kHz)", color="#374151")
            cfo_axis.tick_params(axis="y", labelcolor="#374151")
        if row == 0:
            handles, labels = axis.get_legend_handles_labels()
            if handles:
                axis.legend(handles, labels, loc="upper left", fontsize=8, frameon=False)
    _finish_time_axes(axes, view)


def _cfo_inventory(
    companion: StandardPlotViewV2 | None,
) -> dict[str, tuple[tuple[Any, ...], tuple[Any, ...]]]:
    if companion is None:
        return {}
    observations: dict[str, list[Any]] = defaultdict(list)
    curves: dict[str, list[Any]] = defaultdict(list)
    for observation in companion.cfo_observations:
        observations[observation.receiver_path_id].append(observation)
    for curve in companion.trajectory_curves:
        curves[curve.receiver_path_id].append(curve)
    return {
        lane: (tuple(observations[lane]), tuple(curves[lane]))
        for lane in companion.receiver_path_ids
    }


def _render_cfo(figure: Figure, view: StandardPlotViewV2) -> None:
    axes = _axes(figure, view)
    inventory = _cfo_inventory(view)
    for row, (axis, lane) in enumerate(zip(axes, view.receiver_path_ids, strict=True)):
        observations, curves = inventory[lane]
        axis.scatter(
            [item.time_s for item in observations],
            [item.baseband_cfo_hz / 1_000.0 for item in observations],
            s=5,
            color="#8b949e",
            alpha=0.38,
            rasterized=True,
            label="GLRT64 CFO observations",
        )
        for curve in curves:
            axis.plot(
                [item.time_s for item in curve.points],
                [item.value / 1_000.0 for item in curve.points],
                color=_LANE_COLORS[row % len(_LANE_COLORS)],
                linestyle=_DEGREE_STYLES[curve.degree],
                linewidth=2.8 if curve.selected_for_correction else 1.1,
                alpha=0.98 if curve.selected_for_correction else 0.42,
                label=(
                    f"degree {curve.degree}{' · selected' if curve.selected_for_correction else ''}"
                ),
            )
        axis.set_ylim(
            view.vertical_axis.full_source_min / 1_000.0,
            view.vertical_axis.full_source_max / 1_000.0,
        )
        axis.set_ylabel("CFO (kHz)")
        axis.set_title(_lane_label(lane), loc="left", fontsize=10, fontweight="bold")
        axis.grid(True, color="#d0d7de", linewidth=0.55, alpha=0.65)
        if row == 0:
            axis.legend(loc="best", ncols=4, fontsize=8, frameon=False)
    _finish_time_axes(axes, view)


def _render_metric(figure: Figure, view: StandardPlotViewV2) -> None:
    axes = _axes(figure, view)
    for row, (axis, lane) in enumerate(zip(axes, view.receiver_path_ids, strict=True)):
        lane_series = [item for item in view.series if item.receiver_path_id == lane]
        for index, series in enumerate(lane_series):
            axis.plot(
                [item.time_s for item in series.points],
                [item.value for item in series.points],
                linewidth=0.9,
                alpha=0.88,
                color=_LANE_COLORS[index % len(_LANE_COLORS)],
                label=series.label,
            )
        axis.set_ylim(view.vertical_axis.full_source_min, view.vertical_axis.full_source_max)
        axis.set_ylabel(_metric_ylabel(view.view_kind))
        axis.set_title(_lane_label(lane), loc="left", fontsize=10, fontweight="bold")
        axis.grid(True, color="#d0d7de", linewidth=0.55, alpha=0.65)
        if row == 0 and lane_series:
            axis.legend(loc="best", fontsize=8, frameon=False)
    _finish_time_axes(axes, view)


def _metric_ylabel(kind: StandardViewKindV2) -> str:
    return {
        StandardViewKindV2.QAM: "QAM metric",
        StandardViewKindV2.POWER: "Power (dBFS)",
        StandardViewKindV2.QUALITY: "Valid fraction",
    }.get(kind, "Response")


def _finish_time_axes(axes: tuple[Any, ...], view: StandardPlotViewV2) -> None:
    for axis in axes:
        axis.set_xlim(view.time_domain.elapsed_start_s, view.time_domain.elapsed_end_s)
    axes[-1].set_xlabel("Seconds since earliest first-sample estimate")


def _lane_label(path_id: str) -> str:
    radio, _, receiver = path_id.partition(":")
    if receiver:
        return f"{radio} · {receiver.upper()}"
    return path_id


def _save(figure: Figure, *, dpi: int = 120) -> bytes:
    target = io.BytesIO()
    figure.savefig(
        target,
        format="png",
        dpi=dpi,
        facecolor="white",
        metadata={"Software": "leo-tracker Standard renderer"},
    )
    return target.getvalue()
