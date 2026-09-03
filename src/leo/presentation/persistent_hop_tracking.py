"""Static operator visualization for long-scan trajectories and TLE candidates."""

from __future__ import annotations

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryResult,
)
from leo.presentation.persistent_hop_analysis import _RENDER_LOCK, _save
from leo.scanner.persistent_hop_tracking import PersistentHopTleCandidateV1


def render_persistent_hop_tracking_png(
    trajectory: PersistentHopTrajectoryResult,
    candidates: tuple[PersistentHopCfoCandidate, ...],
    associations: tuple[PersistentHopTleCandidateV1, ...],
) -> bytes:
    """Plot the primary TLE-blind tracks and annotate candidate-only matches."""

    by_candidate = {item.candidate_id: item for item in candidates}
    association_by_tracklet = {
        tracklet_id: item
        for item in associations
        if item.hypothesis_rank == 1
        for tracklet_id in item.tracklet_ids
    }
    primary_ids = set(trajectory.hypotheses[0].tracklet_ids)
    start_ns = min(
        by_candidate[point.candidate_id].support_center_utc_ns
        for tracklet in trajectory.tracklets
        if tracklet.tracklet_id in primary_ids
        for point in tracklet.points
    )
    with _RENDER_LOCK:
        figure = Figure(figsize=(15.5, 8.2), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        colors = ("#1976d2", "#d32f2f", "#00897b", "#8e24aa", "#ef6c00", "#455a64")
        for index, tracklet in enumerate(
            item for item in trajectory.tracklets if item.tracklet_id in primary_ids
        ):
            rows = tuple(by_candidate[point.candidate_id] for point in tracklet.points)
            x = [(item.support_center_utc_ns - start_ns) / 1e9 for item in rows]
            y = [point.normalized_dealiased_cfo_hz for point in tracklet.points]
            channel, edge, receiver_id, _actual_rf_hz = tracklet.lane_key
            association = association_by_tracklet.get(tracklet.tracklet_id)
            match = ""
            if association is not None:
                catalog = (
                    "null"
                    if association.leading_catalog_number is None
                    else f"NORAD {association.leading_catalog_number}"
                )
                disposition = "abstain" if association.abstention_recommended else "heldout"
                match = f" · {catalog} ({disposition})"
            label = (
                f"CH{channel}{'L' if edge.value == 'lower' else 'U'} RX{receiver_id}"
                f" · {tracklet.normalized_rate_hz_per_s:+.0f} Hz/s{match}"
            )
            axis.plot(
                x,
                y,
                marker=".",
                markersize=3.0,
                linewidth=1.1,
                alpha=0.78,
                color=colors[index % len(colors)],
                label=label,
            )
        axis.set_xlabel("UTC-bound time since first retained support (s)")
        axis.set_ylabel(
            f"Dealiased CFO normalized to {trajectory.canonical_rf_hz / 1e9:.1f} GHz (Hz)"
        )
        axis.grid(alpha=0.2)
        axis.legend(loc="best", fontsize=7)
        axis.set_title(
            "TLE-blind cross-channel Doppler trajectories with causal catalogue diagnostics\n"
            "Labels are candidate-only; heldout and wrong-time controls never assert identity",
            loc="left",
            fontweight="bold",
        )
        return _save(figure)


__all__ = ["render_persistent_hop_tracking_png"]
