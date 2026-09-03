"""Deterministic PNGs for fractional-epoch persistent-hop V2 analysis."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.starlink import PilotMethod, TrajectoryObservation, fit_trajectory_bank
from leo.presentation.persistent_hop_analysis import (
    _RECEIVER_MARKERS,
    _RENDER_LOCK,
    _render_coverage,
    _robust_limits,
    _save,
    _session_elapsed_seconds,
    _trajectory_configuration,
)
from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV2,
    PersistentHopCandidateV2,
    PersistentHopProbeMetricV2,
)


def render_persistent_hop_analysis_pngs_v2(
    receipt: PersistentHopSessionReceiptV1,
    chunks: tuple[PersistentHopAnalysisChunkV2, ...],
) -> dict[str, bytes]:
    """Render V2 artifacts using only fractionally rescored decision values."""

    probes = tuple(probe for chunk in chunks for probe in chunk.probes)
    configuration = chunks[0].configuration if chunks else None
    with _RENDER_LOCK:
        return {
            "coverage": _render_coverage(receipt),
            "glrt64-response": _render_fractional_glrt(
                receipt,
                probes,
                gate=configuration.glrt64_margin_gate if configuration else 0.025,
                probe_ms=configuration.probe_ms if configuration else 20,
                probe_stride_ms=configuration.probe_stride_ms if configuration else 10,
            ),
            "cfo-trajectories": _render_fractional_cfo(receipt, probes),
        }


def _render_fractional_glrt(
    receipt: PersistentHopSessionReceiptV1,
    probes: tuple[PersistentHopProbeMetricV2, ...],
    *,
    gate: float,
    probe_ms: int,
    probe_stride_ms: int,
) -> bytes:
    figure = Figure(figsize=(15.5, 7.2), dpi=160, constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.subplots(1, 1)
    for receiver_index, receiver_id in enumerate(receipt.plan.receiver_ids):
        selected = [
            item.best
            for item in probes
            if item.receiver_id == receiver_id and item.best is not None
        ]
        axis.scatter(
            [item.fractional_time_s for item in selected],
            [item.fractional_margin for item in selected],
            s=6,
            alpha=0.38,
            marker=_RECEIVER_MARKERS[receiver_index % len(_RECEIVER_MARKERS)],
            color=("#00a6d6", "#f28e2b")[receiver_index % 2],
            linewidths=0.5,
            rasterized=True,
            label=f"RX{receiver_id} fractional winner",
        )
    axis.axhline(
        gate,
        color="#263238",
        linestyle="--",
        linewidth=1.1,
        label=f"fractional margin gate {gate:.3f}",
    )
    axis.set_xlim(0, _session_elapsed_seconds(receipt))
    axis.set_xlabel("Fractional device time since session start (s)")
    axis.set_ylabel("Fractional GLRT64 exact − control margin")
    axis.grid(alpha=0.2)
    axis.legend(loc="best", fontsize=8)
    axis.set_title(
        "Fractionally rescored GLRT64 response across the full persistent-hop session\n"
        f"{probe_ms} ms probes / {probe_stride_ms} ms stride · "
        "strongest complete fractional candidate per receiver/probe",
        loc="left",
        fontweight="bold",
    )
    return _save(figure)


def _render_fractional_cfo(
    receipt: PersistentHopSessionReceiptV1,
    probes: tuple[PersistentHopProbeMetricV2, ...],
) -> bytes:
    figure = Figure(figsize=(15.5, 11.0), dpi=160, constrained_layout=True)
    FigureCanvasAgg(figure)
    axes = figure.subplots(4, 1, sharex=True, squeeze=False)[:, 0]
    grouped: dict[tuple[int, str, int], list[tuple[float, float]]] = defaultdict(list)
    strongest_by_visit: dict[
        tuple[int, str, int, int], tuple[PersistentHopProbeMetricV2, PersistentHopCandidateV2]
    ] = {}
    all_cfo: list[float] = []
    for item in probes:
        key = (item.target.channel, item.target.edge.value, item.receiver_id)
        for candidate in item.fractional_candidates:
            if not candidate.passed_fractional_margin_gate:
                continue
            grouped[key].append((candidate.fractional_time_s, candidate.fractional_tracking_cfo_hz))
            all_cfo.append(candidate.fractional_tracking_cfo_hz)
            visit_key = (*key, item.visit_index)
            previous = strongest_by_visit.get(visit_key)
            if previous is None or candidate.fractional_margin > previous[1].fractional_margin:
                strongest_by_visit[visit_key] = (item, candidate)
    limits = _robust_limits(all_cfo, minimum_span=20_000.0)
    edge_colors = {"lower": "#277da1", "upper": "#d1495b"}
    for channel, axis in enumerate(axes, start=1):
        for edge in ("lower", "upper"):
            for receiver_index, receiver_id in enumerate(receipt.plan.receiver_ids):
                points = sorted(grouped[(channel, edge, receiver_id)])
                if not points:
                    continue
                times, cfo = zip(*points, strict=True)
                axis.scatter(
                    times,
                    cfo,
                    s=8,
                    alpha=0.45,
                    marker=_RECEIVER_MARKERS[receiver_index % len(_RECEIVER_MARKERS)],
                    color=edge_colors[edge],
                    linewidths=0.5,
                    rasterized=True,
                    label=f"{edge[0].upper()} RX{receiver_id}",
                )
                visit_points = tuple(
                    pair
                    for (row_channel, row_edge, row_receiver, _visit), pair in sorted(
                        strongest_by_visit.items()
                    )
                    if (row_channel, row_edge, row_receiver) == (channel, edge, receiver_id)
                )
                observations = tuple(
                    TrajectoryObservation(
                        observation_id=(
                            f"{receipt.session_id}:visit:{row.visit_index}:{edge}:rx:{receiver_id}:"
                            f"candidate:{candidate.candidate_rank}"
                        ),
                        method=PilotMethod.GLRT64,
                        sample_start=candidate.integer_session_sample,
                        time_s=candidate.fractional_time_s,
                        tracking_cfo_hz=candidate.fractional_tracking_cfo_hz,
                        score=candidate.fractional_exact_score,
                        control_score=candidate.fractional_control_score,
                        margin=candidate.fractional_margin,
                    )
                    for row, candidate in visit_points
                )
                bank = fit_trajectory_bank(observations, _trajectory_configuration())
                for trajectory in bank.trajectories:
                    trajectory_time = np.linspace(trajectory.start_s, trajectory.end_s, 80)
                    axis.plot(
                        trajectory_time,
                        trajectory.frequency_hz(trajectory_time),
                        color=edge_colors[edge],
                        linewidth=1.4,
                        alpha=0.8,
                    )
        axis.set_ylim(*limits)
        axis.set_ylabel(f"CH{channel}\nCFO (Hz)")
        axis.grid(alpha=0.2)
        handles, labels = axis.get_legend_handles_labels()
        axis.legend(
            dict(zip(labels, handles, strict=True)).values(),
            dict(zip(labels, handles, strict=True)).keys(),
            loc="upper right",
            fontsize=7,
            ncol=4,
        )
    axes[-1].set_xlim(0, _session_elapsed_seconds(receipt))
    axes[-1].set_xlabel("Fractional device time since session start (s)")
    figure.suptitle(
        "Passed fractional GLRT64 CFO windows by channel, edge, and receiver\n"
        "GLRT scores and CFO recomputed at fractional epochs; integer anchors retained "
        "for audit; lines are CFO-gated associations",
        fontweight="bold",
    )
    return _save(figure)
