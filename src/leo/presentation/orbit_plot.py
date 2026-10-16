"""Storage-independent orbit/GLRT diagnostic figures.

These are in-memory presentation inputs, not persisted scientific contracts.
The caller owns selection, association, calibration, visibility and propagation:
points and curves must already share a frequency reference and time origin.
No observations are merged, discarded, refitted or reassigned by this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

import numpy as np
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D


@dataclass(frozen=True, slots=True)
class OrbitPeak:
    """One retained observation; ``None`` means unassociated, not undetected."""

    peak_id: str
    time_s: float
    frequency_hz: float
    satellite_id: str | None = None


@dataclass(frozen=True, slots=True)
class OrbitCurve:
    """A prediction in the same frequency frame as the observations.

    NaN frequency values break visibility or other unsupported intervals.
    Times must be finite and strictly increasing. Curves should be sampled
    densely enough that true adjacent changes are below half an alias period.
    """

    satellite_id: str
    time_s: tuple[float, ...]
    frequency_hz: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class OrbitLane:
    """One receiver/channel; use separate lanes for differing frequency frames."""

    receiver: str
    channel: str
    peaks: tuple[OrbitPeak, ...]
    curves: tuple[OrbitCurve, ...] = ()


def _frequency(values: np.ndarray, alias_period_hz: float | None) -> np.ndarray:
    if alias_period_hz is None:
        return values
    return (values + alias_period_hz / 2) % alias_period_hz - alias_period_hz / 2


def _curve_samples(
    curve: OrbitCurve, alias_period_hz: float | None
) -> tuple[np.ndarray, np.ndarray]:
    """Insert gaps at wrapping boundaries without losing either end sample."""
    times = np.asarray(curve.time_s, dtype=float)
    frequency = _frequency(np.asarray(curve.frequency_hz, dtype=float), alias_period_hz)
    if alias_period_hz is not None:
        breaks = np.flatnonzero(np.abs(np.diff(frequency)) > alias_period_hz / 2) + 1
        times = np.insert(times, breaks, np.nan)
        frequency = np.insert(frequency, breaks, np.nan)
    return times, frequency / 1000


def _validate(lanes: Sequence[OrbitLane]) -> None:
    if not lanes:
        raise ValueError("at least one receiver/channel lane is required")
    keys = [(lane.receiver, lane.channel) for lane in lanes]
    if len(set(keys)) != len(keys):
        raise ValueError("receiver/channel lanes must be unique")
    for lane in lanes:
        peak_ids = [peak.peak_id for peak in lane.peaks]
        if len(set(peak_ids)) != len(peak_ids):
            raise ValueError("peak IDs must be unique within each receiver/channel")
        for peak in lane.peaks:
            if not peak.peak_id or not isfinite(peak.time_s) or not isfinite(peak.frequency_hz):
                raise ValueError("peaks require IDs and finite times/frequencies")
            if peak.satellite_id == "":
                raise ValueError("use None, not an empty satellite ID, for unassociated peaks")
        curve_ids = {curve.satellite_id for curve in lane.curves}
        assigned_ids = {peak.satellite_id for peak in lane.peaks if peak.satellite_id is not None}
        if not assigned_ids <= curve_ids:
            raise ValueError("every associated satellite requires a curve in its lane")
        for curve in lane.curves:
            times = np.asarray(curve.time_s, dtype=float)
            frequency = np.asarray(curve.frequency_hz, dtype=float)
            if not curve.satellite_id or times.ndim != 1 or frequency.ndim != 1:
                raise ValueError("curves require a satellite ID and one-dimensional arrays")
            if len(times) != len(frequency) or len(times) < 2:
                raise ValueError("curves require at least two paired times/frequencies")
            if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
                raise ValueError("curve times must be finite and strictly increasing")
            if np.any(np.isinf(frequency)):
                raise ValueError("curve frequencies may contain NaN gaps but not infinity")


def make_orbit_plot(
    lanes: Sequence[OrbitLane],
    *,
    title: str,
    alias_period_hz: float | None = None,
    time_limits_s: tuple[float, float] | None = None,
    observation_label: str = "top-response windows",
    subtitle: str = "",
    lane_height_inches: float = 2.3,
    panel: str = "paired",
) -> Figure:
    """Plot all supplied observations/orbits beside unassociated observations.

    Counts use exactly the supplied records, not raw acquisition hypotheses,
    alias copies, or all windows in a recording. ``observation_label`` names
    that denominator. ``alias_period_hz`` wraps both points and curves into
    [-period/2, period/2); curves are broken at alias discontinuities. No
    global matplotlib backend or pyplot state is changed. The caller saves
    or embeds the returned Agg-backed Figure and is responsible for lifecycle.
    """
    _validate(lanes)
    if panel not in {"paired", "all", "unassociated"}:
        raise ValueError("unknown orbit plot panel")
    if not isfinite(lane_height_inches) or lane_height_inches <= 0:
        raise ValueError("lane height must be positive and finite")
    if alias_period_hz is not None and (not isfinite(alias_period_hz) or alias_period_hz <= 0):
        raise ValueError("alias period must be positive and finite")
    if time_limits_s is not None and (
        len(time_limits_s) != 2
        or not all(isfinite(value) for value in time_limits_s)
        or time_limits_s[0] >= time_limits_s[1]
    ):
        raise ValueError("time limits must be finite and increasing")

    satellite_ids = sorted({curve.satellite_id for lane in lanes for curve in lane.curves})
    # Use one mapping for the entire scan; never recycle a fixed ten-color cycle.
    palette = colormaps["turbo"]
    colors = {
        satellite: palette((index + 0.5) / max(len(satellite_ids), 1))
        for index, satellite in enumerate(satellite_ids)
    }
    total = sum(len(lane.peaks) for lane in lanes)
    unassigned = sum(peak.satellite_id is None for lane in lanes for peak in lane.peaks)
    legend_rows = max(1, (len(satellite_ids) + 1 + 5) // 6)
    figure = Figure(
        figsize=(16, lane_height_inches * len(lanes) + 1.5 + 0.25 * legend_rows), dpi=150
    )
    FigureCanvasAgg(figure)
    axes = figure.subplots(len(lanes), 2, sharex=True, sharey=True, squeeze=False)
    top_text = (
        f"{title}\n{total - unassigned:,}/{total:,} associated {observation_label}"
        f" · {unassigned:,} unassociated"
    )
    if subtitle:
        top_text += f"\n{subtitle}"
    figure.suptitle(top_text, fontsize=15, y=0.99)
    gray = "#757575"
    for lane, (left, right) in zip(lanes, axes, strict=True):
        loose = [peak for peak in lane.peaks if peak.satellite_id is None]
        for axis in (left, right):
            axis.scatter(
                [peak.time_s for peak in loose],
                _frequency(np.array([peak.frequency_hz for peak in loose]), alias_period_hz) / 1000,
                color=gray,
                s=11,
                alpha=0.7,
                linewidths=0,
                rasterized=True,
                label="Unassociated",
            )
            axis.grid(alpha=0.18)
            axis.set_axisbelow(True)
            axis.set_ylabel("Wrapped CFO (kHz)" if alias_period_hz else "Frequency (kHz)")
        for curve in lane.curves:
            times, frequency = _curve_samples(curve, alias_period_hz)
            left.plot(times, frequency, color=colors[curve.satellite_id], lw=1, alpha=0.75)
            if panel == "unassociated":
                right.plot(times, frequency, color=colors[curve.satellite_id], lw=1, alpha=0.75)
        for satellite in sorted({p.satellite_id for p in lane.peaks if p.satellite_id is not None}):
            peaks = [peak for peak in lane.peaks if peak.satellite_id == satellite]
            left.scatter(
                [peak.time_s for peak in peaks],
                _frequency(np.array([peak.frequency_hz for peak in peaks]), alias_period_hz) / 1000,
                color=colors[satellite],
                s=12,
                linewidths=0,
                rasterized=True,
                zorder=3,
            )
        count = len(lane.peaks)
        lane_name = f"{lane.receiver} · {lane.channel}"
        left.set_title(
            f"{lane_name} · all {count:,} · {count - len(loose):,} associated"
            f" + {len(loose):,} unassociated",
            fontsize=10,
        )
        right.set_title(f"{lane_name} · unassociated only: {len(loose):,}/{count:,}", fontsize=10)
    for axis in axes[-1]:
        axis.set_xlabel("Receive time since capture start (s)")
    if time_limits_s is not None:
        axes[0, 0].set_xlim(*time_limits_s)
    if alias_period_hz is not None:
        axes[0, 0].set_ylim(-alias_period_hz / 2000, alias_period_hz / 2000)
    handles = [Line2D([], [], color=gray, marker="o", linestyle="", label="Unassociated")]
    handles.extend(
        Line2D([], [], color=colors[satellite], marker="o", lw=1, label=satellite)
        for satellite in satellite_ids
    )
    figure.legend(
        handles=handles, loc="lower center", ncols=6, fontsize=8, bbox_to_anchor=(0.5, 0.025)
    )
    figure.text(
        0.5,
        0.008,
        "Left: supplied observations + orbit predictions. "
        "Right: the same unassociated records only. "
        "No alias copies, merging or reassignment. Colors denote satellite IDs.",
        ha="center",
        fontsize=8,
    )
    height = figure.get_size_inches()[1]
    figure.tight_layout(rect=(0, (0.5 + 0.25 * legend_rows) / height, 1, 1 - 1.0 / height))
    if panel != "paired":
        # Reuse identical drawing, colors and limits for the separate standard PNGs.
        selected = 0 if panel == "all" else 1
        for row in axes:
            figure.delaxes(row[1 - selected])
            box = row[selected].get_position()
            row[selected].set_position((0.07, box.y0, 0.90, box.height))
            row[selected].tick_params(axis="y", labelleft=True)
        figure.texts[-1].set_text(
            "Selected satellite orbit predictions + "
            + ("all supplied GLRT observations." if panel == "all" else "unassociated GLRT only.")
            + " Colors denote satellite IDs; no alias copies or refitting."
        )
    return figure
