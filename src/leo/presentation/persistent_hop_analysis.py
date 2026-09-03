"""Deterministic overview PNGs for one persistent-hop analysis."""

from __future__ import annotations

import io
from collections import defaultdict
from threading import RLock

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from leo.analysis.starlink import (
    PilotMethod,
    TrajectoryBankConfig,
    TrajectoryMethodConfig,
    TrajectoryObservation,
    fit_trajectory_bank,
)
from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV1,
    PersistentHopProbeMetricV1,
)

_RENDER_LOCK = RLock()
_TARGET_COLORS = (
    "#00c2a8",
    "#2780e3",
    "#7c5cff",
    "#d65db1",
    "#ff6f91",
    "#ff9671",
    "#ffc75f",
    "#87c55f",
)
_RECEIVER_MARKERS = ("o", "x")


def render_persistent_hop_analysis_pngs(
    receipt: PersistentHopSessionReceiptV1,
    chunks: tuple[PersistentHopAnalysisChunkV1, ...],
) -> dict[str, bytes]:
    """Render all bounded UI artifacts after the final analysis chunk is sealed."""

    probes = tuple(probe for chunk in chunks for probe in chunk.probes)
    configuration = chunks[0].configuration if chunks else None
    with _RENDER_LOCK:
        return {
            "coverage": _render_coverage(receipt),
            "glrt64-response": _render_glrt(
                receipt,
                probes,
                gate=configuration.glrt64_margin_gate if configuration else 0.025,
                probe_ms=configuration.probe_ms if configuration else 20,
                probe_stride_ms=configuration.probe_stride_ms if configuration else 10,
            ),
            "cfo-trajectories": _render_cfo(receipt, probes),
        }


def _render_coverage(receipt: PersistentHopSessionReceiptV1) -> bytes:
    figure = Figure(figsize=(15.5, 6.8), dpi=160, constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.subplots(1, 1)
    sample_rate = receipt.plan.sample_rate_hz
    origin = receipt.session_start_device_sample_counter
    valid_segments = []
    invalid_segments = []
    for visit in receipt.visits:
        start = (visit.valid_device_sample_counter - origin) / sample_rate
        end = (visit.valid_device_sample_counter_end_exclusive - origin) / sample_rate
        valid_segments.append(((start, visit.target_index), (end, visit.target_index)))
        invalid = visit.transition_invalid_before
        invalid_segments.append(
            (
                ((invalid.device_sample_counter - origin) / sample_rate, -0.45),
                ((invalid.device_sample_counter_end_exclusive - origin) / sample_rate, 7.45),
            )
        )
    if invalid_segments:
        axis.add_collection(
            LineCollection(invalid_segments, colors="#b7bdc5", linewidths=1.0, alpha=0.25)
        )
    for target_index in range(8):
        selected = [
            segment
            for index, segment in enumerate(valid_segments)
            if receipt.visits[index].target_index == target_index
        ]
        if selected:
            axis.add_collection(
                LineCollection(
                    selected,
                    colors=_TARGET_COLORS[target_index],
                    linewidths=5.0,
                    alpha=0.95,
                )
            )
    labels = [
        f"CH{profile.target.channel}{profile.target.edge.value[0].upper()}"
        for profile in receipt.plan.profiles
    ]
    elapsed = _session_elapsed_seconds(receipt)
    axis.set_xlim(0, elapsed)
    axis.set_ylim(7.7, -0.7)
    axis.set_yticks(range(8), labels)
    axis.set_xlabel("Device time since session start (s)")
    axis.set_ylabel("Hop target")
    axis.grid(axis="x", alpha=0.2)
    axis.set_title(
        "Capture coverage and retune-invalid windows\n"
        f"{receipt.session_id} · {receipt.valid_duty_ppm / 10_000:.2f}% valid duty · "
        f"{len(receipt.visits)} visits",
        loc="left",
        fontweight="bold",
    )
    return _save(figure)


def _render_glrt(
    receipt: PersistentHopSessionReceiptV1,
    probes: tuple[PersistentHopProbeMetricV1, ...],
    *,
    gate: float,
    probe_ms: int,
    probe_stride_ms: int,
) -> bytes:
    figure = Figure(figsize=(15.5, 7.2), dpi=160, constrained_layout=True)
    FigureCanvasAgg(figure)
    axis = figure.subplots(1, 1)
    receivers = receipt.plan.receiver_ids
    for receiver_index, receiver_id in enumerate(receivers):
        selected = [
            item.best
            for item in probes
            if item.receiver_id == receiver_id and item.best is not None
        ]
        axis.scatter(
            [item.effective_time_s for item in selected],
            [item.margin for item in selected],
            s=6,
            alpha=0.38,
            marker=_RECEIVER_MARKERS[receiver_index % len(_RECEIVER_MARKERS)],
            color=("#00a6d6", "#f28e2b")[receiver_index % 2],
            linewidths=0.5,
            rasterized=True,
            label=f"RX{receiver_id} strongest candidate",
        )
    axis.axhline(
        gate, color="#263238", linestyle="--", linewidth=1.1, label=f"margin gate {gate:.3f}"
    )
    axis.set_xlim(0, _session_elapsed_seconds(receipt))
    axis.set_xlabel("Effective device time since session start (s)")
    axis.set_ylabel("GLRT64 exact − control margin")
    axis.grid(alpha=0.2)
    axis.legend(loc="best", fontsize=8)
    axis.set_title(
        "GLRT64 response across the full persistent-hop session\n"
        f"{probe_ms} ms probes / {probe_stride_ms} ms stride · "
        "strongest retained candidate per receiver/probe",
        loc="left",
        fontweight="bold",
    )
    return _save(figure)


def _render_cfo(
    receipt: PersistentHopSessionReceiptV1,
    probes: tuple[PersistentHopProbeMetricV1, ...],
) -> bytes:
    figure = Figure(figsize=(15.5, 11.0), dpi=160, constrained_layout=True)
    FigureCanvasAgg(figure)
    axes = figure.subplots(4, 1, sharex=True, squeeze=False)[:, 0]
    grouped: dict[tuple[int, str, int], list[tuple[float, float]]] = defaultdict(list)
    strongest_by_visit: dict[tuple[int, str, int, int], PersistentHopProbeMetricV1] = {}
    all_cfo: list[float] = []
    for item in probes:
        if item.best is None or not item.best.passed_margin_gate:
            continue
        key = (item.target.channel, item.target.edge.value, item.receiver_id)
        grouped[key].append((item.best.effective_time_s, item.best.tracking_cfo_hz))
        all_cfo.append(item.best.tracking_cfo_hz)
        visit_key = (*key, item.visit_index)
        previous = strongest_by_visit.get(visit_key)
        if previous is None or (
            previous.best is not None and item.best.margin > previous.best.margin
        ):
            strongest_by_visit[visit_key] = item
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
                    row
                    for (row_channel, row_edge, row_receiver, _visit), row in sorted(
                        strongest_by_visit.items()
                    )
                    if (row_channel, row_edge, row_receiver) == (channel, edge, receiver_id)
                )
                observations = tuple(
                    TrajectoryObservation(
                        observation_id=(
                            f"{receipt.session_id}:visit:{row.visit_index}:{edge}:rx:{receiver_id}"
                        ),
                        method=PilotMethod.GLRT64,
                        sample_start=row.best.integer_session_sample,
                        time_s=row.best.effective_time_s,
                        tracking_cfo_hz=row.best.tracking_cfo_hz,
                        score=row.best.exact_score,
                        control_score=row.best.control_score,
                        margin=row.best.margin,
                    )
                    for row in visit_points
                    if row.best is not None
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
    axes[-1].set_xlabel("Effective device time since session start (s)")
    figure.suptitle(
        "Passed GLRT64 CFO windows by channel, edge, and receiver\n"
        "Integer epochs plus separately retained fractional offsets; "
        "no phase continuity carried across retunes; lines are CFO-gated associations",
        fontweight="bold",
    )
    return _save(figure)


def _session_elapsed_seconds(receipt: PersistentHopSessionReceiptV1) -> float:
    if not receipt.visits:
        return float(receipt.plan.nominal_duration_seconds)
    return max(
        float(receipt.plan.nominal_duration_seconds),
        (
            receipt.visits[-1].valid_device_sample_counter_end_exclusive
            - receipt.session_start_device_sample_counter
        )
        / receipt.plan.sample_rate_hz,
    )


def _trajectory_configuration() -> TrajectoryBankConfig:
    return TrajectoryBankConfig(
        methods=(
            TrajectoryMethodConfig(
                method=PilotMethod.GLRT64,
                low_gate=0.0,
                local_residual_gate_hz=2_500.0,
                final_residual_gate_hz=2_500.0,
                minimum_local_points=3,
                minimum_high_points=2,
                maximum_merge_gap_s=2.0,
                endpoint_gate_hz=4_000.0,
                endpoint_growth_hz_per_s=3_000.0,
                maximum_slope_difference_hz_per_s=20_000.0,
            ),
        ),
        polynomial_degrees=(1, 2),
        local_window_s=3.0,
        minimum_final_duration_s=1.5,
        maximum_trajectories=64,
    )


def _robust_limits(values: list[float], *, minimum_span: float) -> tuple[float, float]:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if not finite.size:
        return (-minimum_span / 2, minimum_span / 2)
    lower, upper = (float(value) for value in np.quantile(finite, (0.005, 0.995)))
    center = (lower + upper) / 2
    span = max(minimum_span, (upper - lower) * 1.15)
    return center - span / 2, center + span / 2


def _save(figure: Figure) -> bytes:
    output = io.BytesIO()
    figure.savefig(
        output,
        format="png",
        dpi=160,
        metadata={"Software": "leo-tracker persistent-hop analysis"},
    )
    return output.getvalue()
