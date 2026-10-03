"""Channel-local view of measured CFO candidates and their reconstructed tracks."""

from collections import defaultdict

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryResult,
)
from leo.analysis.starlink import CFO_ALIAS_SPACING_HZ
from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
from leo.presentation.persistent_hop_analysis import _RENDER_LOCK, _save

_COLORS = ("#d62728", "#6a3d9a", "#00876c", "#e37600", "#0057b8", "#b51b79")
_LANE_COLORS = (("#287da1", "#b56c13"), ("#8b5fbf", "#16866b"))


def pilot_residual(raw_cfo_hz, channel, edge, actual_rf_hz):
    """Undo tuning before wrapping; tracks must first undo RF normalization."""
    nominal = starlink_edge_rf_center_frequency_hz(channel, edge) - actual_rf_hz
    spacing = CFO_ALIAS_SPACING_HZ
    return (np.asarray(raw_cfo_hz) - nominal + spacing / 2) % spacing - spacing / 2


def alias_segments(times, canonical):
    """Split at alias wraps so a fit never draws a false diagonal connection."""
    boundaries = np.flatnonzero(np.abs(np.diff(canonical)) > CFO_ALIAS_SPACING_HZ / 2) + 1
    return zip(np.split(times, boundaries), np.split(canonical, boundaries), strict=True)


def render_scanner_track_overlay_png(
    trajectory: PersistentHopTrajectoryResult,
    candidates: tuple[PersistentHopCfoCandidate, ...],
    *,
    capture_start_utc_ns: int | None = None,
    capture_end_utc_ns: int | None = None,
) -> bytes:
    """Overlay actual lane fits and assigned support; never infer membership by proximity."""
    by_id = {row.candidate_id: row for row in candidates}
    origin = capture_start_utc_ns
    if origin is None:
        origin = min((row.support_center_utc_ns for row in candidates), default=0)
    lanes = defaultdict(list)
    for row in candidates:
        lanes[(row.channel, row.edge, row.receiver_id, row.actual_rf_hz)].append(row)
    spacing = CFO_ALIAS_SPACING_HZ
    shifts = (-spacing, 0, spacing)
    with _RENDER_LOCK:
        figure = Figure(figsize=(15.5, 11.5), dpi=160, constrained_layout=True)
        axes = figure.subplots(4, 1, sharex=True)
        for channel, axis in enumerate(axes, start=1):
            for low, high in ((-spacing, -spacing / 2), (spacing / 2, spacing)):
                axis.axhspan(low, high, color="#e9eef5", zorder=0)
            for boundary in (-spacing / 2, spacing / 2):
                axis.axhline(boundary, color="#8393a8", linestyle=":", linewidth=0.8)
            for (ch, edge, rx, rf), rows in sorted(lanes.items()):
                if ch != channel:
                    continue
                times = np.array([(row.support_center_utc_ns - origin) / 1e9 for row in rows])
                values = pilot_residual([row.measured_cfo_hz for row in rows], ch, edge, rf)
                color = _LANE_COLORS[edge.value == "upper"][rx % 2]
                for shift in shifts:
                    axis.scatter(
                        times,
                        values + shift,
                        s=11,
                        alpha=0.35,
                        color=color,
                        marker="o" if rx % 2 == 0 else "x",
                        linewidths=0.6,
                        label=f"{edge.value[0].upper()} RX{rx}" if shift == 0 else None,
                    )
            for index, track in enumerate(trajectory.tracklets):
                ch, edge, rx, rf = track.lane_key
                if ch != channel:
                    continue
                rows = [by_id[point.candidate_id] for point in track.points]
                if any(
                    (row.channel, row.edge, row.receiver_id, row.actual_rf_hz) != track.lane_key
                    for row in rows
                ):
                    raise ValueError("track support belongs to another lane")
                color = _COLORS[index % len(_COLORS)]
                start = (track.start_utc_ns - origin) / 1e9
                end = (track.end_utc_ns - origin) / 1e9
                times = np.linspace(start, end, 401)
                dt = times - (track.reference_utc_ns - origin) / 1e9
                raw = track.normalized_intercept_hz + track.normalized_rate_hz_per_s * dt
                raw = raw * rf / trajectory.canonical_rf_hz
                values = pilot_residual(raw, ch, edge, rf)
                for tx, fy in alias_segments(times, values):
                    for shift in shifts:
                        axis.plot(tx, fy + shift, color=color, linewidth=1.7, zorder=4)
                support_t = [(row.support_center_utc_ns - origin) / 1e9 for row in rows]
                support_y = pilot_residual([row.measured_cfo_hz for row in rows], ch, edge, rf)
                for shift in shifts:
                    axis.scatter(
                        support_t,
                        support_y + shift,
                        s=25,
                        facecolors="none",
                        edgecolors=color,
                        linewidths=0.8,
                        zorder=5,
                    )
                axis.annotate(
                    f"T{index + 1} {edge.value[0].upper()} RX{rx}",
                    (times[-1], values[-1]),
                    xytext=(3, 4),
                    textcoords="offset points",
                    fontsize=7,
                    color=color,
                    clip_on=True,
                )
            axis.set_ylim(-spacing, spacing)
            axis.set_ylabel(f"CH{channel}\nPilot-relative CFO (Hz)")
            axis.grid(alpha=0.18)
            if not any(key[0] == channel for key in lanes):
                axis.text(
                    0.5,
                    0.5,
                    "No passing tracking-input candidates",
                    transform=axis.transAxes,
                    ha="center",
                )
            if axis.get_legend_handles_labels()[0]:
                handles, labels = axis.get_legend_handles_labels()
                unique = dict(zip(labels, handles, strict=True))
                legend = axis.legend(
                    unique.values(), unique.keys(), loc="upper right", ncol=4, fontsize=8
                )
                if channel == 1:
                    axis.add_artist(legend)
        if capture_start_utc_ns is not None and capture_end_utc_ns is not None:
            axes[-1].set_xlim(0, (capture_end_utc_ns - capture_start_utc_ns) / 1e9)
        axes[-1].set_xlabel("Device time since capture start (s); GLRT support centers")
        figure.suptitle(
            "Passed GLRT64 candidates with reconstructed tracks by channel\n"
            "Solid: fitted tracks · rings: assigned GLRT candidates · faint: all tracking inputs\n"
            "Shaded bands show shifted alias copies, not new detections; "
            "no satellite identity implied",
            fontsize=13,
        )
        # Explicit legend distinguishes assignment evidence from geometric coincidence.
        axes[0].add_artist(
            axes[0].legend(
                handles=[
                    Line2D([], [], color="#333333", linewidth=1.7, label="Fitted track"),
                    Line2D(
                        [],
                        [],
                        color="#333333",
                        marker="o",
                        markerfacecolor="none",
                        linestyle="none",
                        label="Assigned candidate",
                    ),
                ],
                loc="lower left",
                fontsize=8,
            )
        )
        return _save(figure)
