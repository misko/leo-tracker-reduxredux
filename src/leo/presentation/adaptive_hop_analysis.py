"""Bounded actual-time plots from sealed adaptive metrics; no IQ or fixed sweeps."""

from __future__ import annotations

import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
from matplotlib import rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from leo.analysis.starlink import PilotMethod, TrajectoryObservation, fit_trajectory_bank
from leo.analysis.starlink.trajectories import TrajectoryBankConfig, TrajectoryBankResult
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.presentation.persistent_hop_analysis import _RENDER_LOCK, _trajectory_configuration
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopFractionalCandidateV1,
    AdaptiveHopProbeAnalysisV1,
    AdaptiveHopVisitAnalysisV1,
)
from leo.scanner.adaptive_hop_presentation import RenderedAdaptiveOverview
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
)

_EDGE_COLORS = ("#287da1", "#bd3653")
_MARKERS = ("o", "x")
TestData = Literal["synthetic", "saved-rx1"]
_TEST_LABELS = {
    "synthetic": "SYNTHETIC TEST DATA - NOT RF",
    "saved-rx1": "SAVED RX1 TEST EXCERPT - SYNTHETIC RX0 / RECEIPT / OTHER VISITS",
}


def adaptive_trajectory_configuration(margin_gate: float) -> TrajectoryBankConfig:
    """Passed-only candidate associations cannot estimate a negative-tail noise gate.

    Use the same explicit fractional margin gate that admitted these candidates.
    This is an association visualization, not an additional detection or ID test.
    The fixed-scan fitter and its negative-tail calibration remain unchanged.
    """
    base = _trajectory_configuration()
    return replace(
        base,
        methods=tuple(
            replace(m, low_gate=margin_gate, high_gate=margin_gate) for m in base.methods
        ),
    )


@dataclass(frozen=True)
class AdaptiveOverviewData:
    # Compact preallocated arrays keep up to 880k candidates out of Python lists.
    # Columns: target, receiver, fractional time, margin/CFO respectively.
    winners: np.ndarray
    passed: np.ndarray
    observations: dict[tuple[int, int], tuple[TrajectoryObservation, ...]]


def project_adaptive_overview(
    binding: AdaptiveHopAnalysisBindingV1,
    manifest: AdaptiveHopMetricsManifestV1,
    visits: Iterable[AdaptiveHopVisitAnalysisV1],
) -> AdaptiveOverviewData:
    binding = AdaptiveHopAnalysisBindingV1.model_validate(binding.model_dump())
    manifest = AdaptiveHopMetricsManifestV1.model_validate(manifest.model_dump())
    if (
        manifest.binding_sha256 != binding.sha256
        or manifest.session_id != binding.session_id
        or manifest.configuration != binding.configuration
        or manifest.input_manifest_sha256 != binding.input_manifest_sha256
        or manifest.complete_visit_count != binding.receipt.complete_visit_count
    ):
        raise ValueError("adaptive overview source and metrics binding differ")
    winners = np.empty((sum(r.probe_count for r in manifest.visits), 4), dtype=np.float64)
    passed = np.empty(
        (sum(r.passed_fractional_candidate_count for r in manifest.visits), 4), dtype=np.float64
    )
    winner_cursor = passed_cursor = visited = 0
    groups = defaultdict(list)
    for product in visits:
        binding.validate_visit(product)
        if product.visit_index != visited or visited >= manifest.complete_visit_count:
            raise ValueError("adaptive overview requires every actual visit once in source order")
        reference = manifest.visits[visited]
        counts = (
            len(product.probes),
            sum(p.candidate_count for p in product.probes),
            sum(len(p.candidates) for p in product.probes),
            sum(c.passed_fractional_margin_gate for p in product.probes for c in p.candidates),
        )
        if counts != (
            reference.probe_count,
            reference.candidate_count,
            reference.fractional_candidate_count,
            reference.passed_fractional_candidate_count,
        ):
            raise ValueError("adaptive overview candidate counts differ from sealed metrics")
        strongest: dict[
            int, tuple[AdaptiveHopProbeAnalysisV1, AdaptiveHopFractionalCandidateV1]
        ] = {}
        for probe in product.probes:
            for candidate in probe.candidates:
                if candidate.candidate_rank == probe.winning_candidate_rank:
                    winners[winner_cursor] = (
                        product.target_index,
                        probe.receiver_id,
                        candidate.fractional_time_s,
                        candidate.fractional_margin,
                    )
                    winner_cursor += 1
                if not candidate.passed_fractional_margin_gate:
                    continue
                passed[passed_cursor] = (
                    product.target_index,
                    probe.receiver_id,
                    candidate.fractional_time_s,
                    candidate.fractional_tracking_cfo_hz,
                )
                passed_cursor += 1
                previous = strongest.get(probe.receiver_id)
                if previous is None or candidate.fractional_margin > previous[1].fractional_margin:
                    strongest[probe.receiver_id] = (probe, candidate)
        for receiver, (probe, candidate) in strongest.items():
            groups[(product.target_index, receiver)].append(
                TrajectoryObservation(
                    observation_id=f"{product.session_id}:visit:{visited}:rx:{receiver}:probe:{probe.probe_index}:candidate:{candidate.candidate_rank}",
                    method=PilotMethod.GLRT64,
                    sample_start=candidate.integer_session_sample,
                    time_s=candidate.fractional_time_s,
                    tracking_cfo_hz=candidate.fractional_tracking_cfo_hz,
                    score=candidate.fractional_exact_score,
                    control_score=candidate.fractional_control_score,
                    margin=candidate.fractional_margin,
                )
            )
        visited += 1
    if visited != manifest.complete_visit_count or passed_cursor != len(passed):
        raise ValueError("adaptive overview metrics stream is incomplete")
    winners = winners[:winner_cursor]
    winners.setflags(write=False)
    passed.setflags(write=False)
    return AdaptiveOverviewData(winners, passed, {key: tuple(rows) for key, rows in groups.items()})


def _save(
    figure: Figure,
    binding: AdaptiveHopAnalysisBindingV1,
    metrics_sha256: str,
    test_data: TestData | None,
) -> bytes:
    output = io.BytesIO()
    FigureCanvasAgg(figure)
    if test_data is not None:
        # Explicit report/test context, never inferred from signal shape or IDs.
        label = _TEST_LABELS[test_data]
        figure.text(
            0.5,
            0.012,
            label,
            ha="center",
            va="bottom",
            fontsize=12,
            weight="bold",
            color="#9b1c20",
            bbox={"facecolor": "white", "edgecolor": "#9b1c20", "pad": 5},
        )
        figure.set_layout_engine("constrained", rect=(0, 0.05, 1, 0.95))
    figure.savefig(
        output,
        format="png",
        metadata={
            "Software": "leo-tracker adaptive actual-visit overview-v1",
            "Session": binding.session_id,
            "Metrics": metrics_sha256,
            **({"TestData": _TEST_LABELS[test_data]} if test_data is not None else {}),
        },
    )
    figure.clear()
    return output.getvalue()


def _axes_time(axis, binding: AdaptiveHopAnalysisBindingV1):
    receipt = binding.receipt
    span = receipt.duty_denominator_sample_count / binding.configuration.sample_rate_hz
    axis.set_xlim(0, span if span else 1)
    if not receipt.source_span_attested:
        axis.set_xticks([])
        axis.text(
            0.5,
            0.5,
            "No attested source interval",
            transform=axis.transAxes,
            horizontalalignment="center",
        )
    axis.set_xlabel("Device time since capture start (s); fractional candidate epochs")
    axis.grid(alpha=0.18)


def render_adaptive_hop_overview(
    binding: AdaptiveHopAnalysisBindingV1,
    manifest: AdaptiveHopMetricsManifestV1,
    visits: Iterable[AdaptiveHopVisitAnalysisV1],
    *,
    test_data: TestData | None = None,
) -> RenderedAdaptiveOverview:
    if test_data is not None and test_data not in _TEST_LABELS:
        raise ValueError("unknown adaptive overview test-data context")
    data = project_adaptive_overview(binding, manifest, visits)
    config = adaptive_trajectory_configuration(binding.configuration.glrt64_margin_gate)
    banks: dict[tuple[int, int], TrajectoryBankResult] = {
        key: fit_trajectory_bank(observations, config)
        for key, observations in data.observations.items()
    }
    receipt, rate = binding.receipt, binding.configuration.sample_rate_hz
    origin = receipt.terminal.first_counter
    metrics_sha = sha256_digest(canonical_json_bytes(manifest.model_dump(mode="json")))
    figures = {}
    with _RENDER_LOCK, rc_context({"font.size": 12, "axes.titlesize": 14, "legend.fontsize": 10}):
        figure = Figure(figsize=(15.5, 6.5), dpi=160, constrained_layout=True)
        axis = figure.subplots()
        for target in range(8):
            intervals = [
                (
                    (e.valid_start_counter - origin) / rate,
                    (e.valid_start_counter + receipt.plan.geometry.valid_visit_samples - origin)
                    / rate,
                )
                for e in receipt.events[: receipt.complete_visit_count]
                if e.target_index == target
            ]
            if intervals:
                axis.add_collection(
                    LineCollection(
                        [((a, target), (b, target)) for a, b in intervals],
                        colors=_EDGE_COLORS[target // 4],
                        linewidths=5,
                    )
                )
        if len(receipt.events) > receipt.complete_visit_count:
            tail = receipt.events[-1]
            axis.scatter(
                [(tail.invalid_start_counter - origin) / rate],
                [tail.target_index],
                marker="o",
                s=40,
                facecolors="none",
                edgecolors="#555555",
                label="Incomplete hop start",
            )
        axis.set_yticks(range(8), [f"CH{i % 4 + 1}{'L' if i < 4 else 'U'}" for i in range(8)])
        axis.set_ylim(7.6, -0.6)
        _axes_time(axis, binding)
        axis.set_xlabel("Device time since capture start (s)")
        axis.set_title(
            f"Actual retained channel visits · {receipt.terminal.state}\n"
            f"{binding.session_id} · {receipt.complete_visit_count} complete 120 ms visits",
            loc="left",
        )
        if axis.get_legend_handles_labels()[0]:
            axis.legend(loc="upper right")
        figures["coverage"] = _save(figure, binding, metrics_sha, test_data)
        figure = Figure(figsize=(15.5, 7.2), dpi=160, constrained_layout=True)
        axis = figure.subplots()
        for rx in (0, 1):
            rows = data.winners[data.winners[:, 1] == rx]
            axis.scatter(
                rows[:, 2],
                rows[:, 3],
                s=12,
                marker=_MARKERS[rx],
                alpha=0.7,
                linewidths=0.8,
                color=("#287da1", "#b56c13")[rx],
                label=f"RX{rx} fractional winner",
            )
        axis.axhline(
            binding.configuration.glrt64_margin_gate,
            color="#333333",
            linestyle="--",
            label="Fractional margin gate",
        )
        _axes_time(axis, binding)
        axis.set_ylabel("Fractional GLRT64 exact − control margin")
        axis.set_title(
            "Fractionally rescored GLRT64 response\n"
            f"20 ms probes / {binding.configuration.probe_stride_ms} ms stride · "
            "no interpolation across unsampled intervals",
            loc="left",
        )
        axis.legend(loc="best")
        figures["glrt64-response"] = _save(figure, binding, metrics_sha, test_data)
        figure = Figure(figsize=(15.5, 11.5), dpi=160, constrained_layout=True)
        axes = figure.subplots(4, 1, sharex=True)
        for channel, axis in enumerate(axes):
            for edge in (0, 1):
                target = channel + edge * 4
                for rx in (0, 1):
                    rows = data.passed[(data.passed[:, 0] == target) & (data.passed[:, 1] == rx)]
                    if len(rows):
                        axis.scatter(
                            rows[:, 2],
                            rows[:, 3],
                            s=12,
                            alpha=0.7,
                            marker=_MARKERS[rx],
                            color=_EDGE_COLORS[edge],
                            linewidths=0.8,
                            label=f"{'LU'[edge]} RX{rx}",
                            rasterized=True,
                        )
                    bank = banks.get((target, rx))
                    if bank:
                        for track in bank.trajectories:
                            times = np.linspace(track.start_s, track.end_s, 80)
                            axis.plot(
                                times,
                                track.frequency_hz(times),
                                color=_EDGE_COLORS[edge],
                                linewidth=1.1,
                                linestyle="--",
                                alpha=0.8,
                            )
            _axes_time(axis, binding)
            axis.set_xlabel("")
            axis.set_ylabel(f"CH{channel + 1}\nCFO (Hz)")
            if not np.any((data.passed[:, 0] % 4) == channel):
                axis.set_yticks([])
                if receipt.source_span_attested:
                    axis.text(
                        0.5,
                        0.5,
                        "No passed fractional CFO candidates",
                        transform=axis.transAxes,
                        horizontalalignment="center",
                    )
            if axis.get_legend_handles_labels()[0]:
                axis.legend(loc="upper right", ncol=4)
        axes[-1].set_xlabel("Device time since capture start (s); fractional candidate epochs")
        figure.suptitle(
            "All passed fractional GLRT64 CFO candidates\n"
            "Dashed lines: strongest-per-visit candidate associations, not satellite IDs; "
            "no L/U or cross-channel joins",
            fontsize=14,
        )
        figures["cfo-trajectories"] = _save(figure, binding, metrics_sha, test_data)
    return RenderedAdaptiveOverview(
        artifacts=figures,
        trajectory_configuration_sha256=config.digest,
        selected_observation_count=sum(len(rows) for rows in data.observations.values()),
        association_count=sum(len(bank.trajectories) for bank in banks.values()),
        truncated_association_count=sum(bank.truncated_trajectory_count for bank in banks.values()),
    )
