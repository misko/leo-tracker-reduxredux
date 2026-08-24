#!/usr/bin/env python3
"""Prototype dense Hough proposals as inputs to replay-qualified linear tracks.

This report-only tool keeps the independently searched 20 ms/10 ms-stride GLRT
windows as the source evidence.  It closes and deduplicates degree-one Hough
geometry, transports the acquisition CFO through conditioned replay, derives a
finite interval from replay-positive support, and robustly refits one straight
line.  It publishes no Standard product and makes no satellite attribution.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.robust_linear import fit_huber_linear_irls  # noqa: E402
from leo.analysis.standard.analyzers import (  # noqa: E402
    _receiver_standard_config,
    production_standard_v2_configuration,
)
from leo.analysis.standard.full_capture_glrt20ms import (  # noqa: E402
    WindowResult,
    _threshold_winners,
    _window_winners,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score  # noqa: E402
from leo.analysis.starlink.trajectories import (  # noqa: E402
    PolynomialTrajectory,
    TrajectoryObservation,
    correct_polynomial_cfo,
)
from leo.analysis.starlink.trajectory_accounting import (  # noqa: E402
    associate_trajectory_baseline,
)
from leo.analysis.starlink.trajectory_feedback import (  # noqa: E402
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    trajectory_observations,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402


def _load_tool(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


support = _load_tool(
    "full_capture_support_extension_tool",
    "report_full_capture_support_extension.py",
)
geometry = _load_tool(
    "support_extension_geometry_retention_tool",
    "report_support_extension_geometry_retention.py",
)
seed_policy = _load_tool(
    "hough_replay_seed_policy_tool",
    "report_h1_replay_seed_policy.py",
)

SOURCE_JSON = support.SOURCE_JSON
SEED_REPLAY_JSON = support.SEED_REPLAY_JSON
OUTPUT_ROOT = Path("reports/figures/2026_08_23_full_capture_hough_downstream_prototype")
REPORT_PATH = Path("reports/2026_08_23_full_capture_hough_downstream_prototype.md")
REPLAY_MAXIMUM_GAP_S = 0.10
REPLAY_MINIMUM_SUPPORT = 8


@dataclass(frozen=True, slots=True)
class ReplayProbe:
    label: str
    sample_start: int
    time_s: float
    baseline_margin: float
    transported_margin: float
    baseline_exact: float
    transported_exact: float
    baseline_control: float
    transported_control: float
    association_error_hz: float
    transported_residual_hz: float

    def positive(self, threshold: float) -> bool:
        return self.baseline_margin >= threshold and self.transported_margin >= threshold


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--seed-replay-json", type=Path, default=SEED_REPLAY_JSON)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def connected_replay_runs(
    rows: tuple[ReplayProbe, ...],
    *,
    threshold: float,
    maximum_gap_s: float,
) -> tuple[tuple[ReplayProbe, ...], ...]:
    """Return replay-positive runs, splitting where validation evidence disappears."""

    if not math.isfinite(threshold) or not math.isfinite(maximum_gap_s) or maximum_gap_s <= 0:
        raise ValueError("replay run bounds must be finite and the gap must be positive")
    positive = tuple(
        sorted((row for row in rows if row.positive(threshold)), key=lambda x: x.time_s)
    )
    if not positive:
        return ()
    runs: list[list[ReplayProbe]] = [[positive[0]]]
    for row in positive[1:]:
        if row.time_s - runs[-1][-1].time_s > maximum_gap_s:
            runs.append([])
        runs[-1].append(row)
    return tuple(tuple(run) for run in runs)


def select_seed_anchored_replay_run(
    rows: tuple[ReplayProbe, ...],
    *,
    threshold: float,
    maximum_gap_s: float,
    minimum_support: int,
    seed_start_s: float,
    seed_end_s: float,
) -> tuple[ReplayProbe, ...]:
    """Select the strongest replay-positive run anchored to the Hough seed interval."""

    if minimum_support < 1 or seed_start_s > seed_end_s:
        raise ValueError("replay support selection bounds are invalid")
    runs = connected_replay_runs(rows, threshold=threshold, maximum_gap_s=maximum_gap_s)
    anchored = tuple(
        run for run in runs if any(seed_start_s <= row.time_s <= seed_end_s for row in run)
    )
    if not anchored:
        return ()
    selected = max(
        anchored,
        key=lambda run: (
            sum(seed_start_s <= row.time_s <= seed_end_s for row in run),
            len(run),
            run[-1].time_s - run[0].time_s,
            -run[0].time_s,
        ),
    )
    return selected if len(selected) >= minimum_support else ()


def refit_replay_supported_line(
    closed: PolynomialTrajectory,
    observations: tuple[TrajectoryObservation, ...],
    run: tuple[ReplayProbe, ...],
    *,
    alias_spacing_hz: float,
) -> PolynomialTrajectory | None:
    """Robustly refit one degree-one line using only replay-positive Hough observations."""

    if closed.polynomial_degree != 1:
        raise ValueError("replay-supported refinement accepts degree-one tracks only")
    positive_samples = {row.sample_start for row in run}
    by_id = {item.observation_id: item for item in observations}
    selected = tuple(
        by_id[item]
        for item in closed.observation_ids
        if by_id[item].sample_start in positive_samples
    )
    if len(selected) < 3:
        return None
    times = np.asarray([item.time_s for item in selected], dtype=np.float64)
    raw = np.asarray([item.tracking_cfo_hz for item in selected], dtype=np.float64)
    predicted = closed.frequency_hz(times)
    aliases = np.rint((raw - predicted) / alias_spacing_hz)
    canonical = raw - aliases * alias_spacing_hz
    fit = fit_huber_linear_irls(
        times,
        canonical,
        initial_coefficients_hz=closed.coefficients_hz,
        reference_time_s=closed.reference_time_s,
    )
    coefficients = tuple(float(value) for value in fit.coefficients_hz)
    residual = canonical - np.polyval(coefficients, times - closed.reference_time_s)
    rss = max(float(np.sum(residual**2)), np.finfo(float).tiny)
    count = len(selected)
    identity = {
        "algorithm": "replay-supported-huber-d1-prototype-v1",
        "source": closed.trajectory_id,
        "observations": tuple(item.observation_id for item in selected),
        "coefficients_hz": coefficients,
    }
    return PolynomialTrajectory(
        trajectory_id=canonical_digest(identity),
        method=closed.method,
        polynomial_degree=1,
        reference_time_s=closed.reference_time_s,
        coefficients_hz=coefficients,
        start_s=float(times[0]),
        end_s=float(times[-1]),
        observation_ids=tuple(item.observation_id for item in selected),
        point_count=count,
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        bic=float(count * math.log(rss / count) + 2.0 * math.log(count)),
        high_gate=0.0,
        em_iterations=0,
    )


def replay_qualified_segments(
    closed: PolynomialTrajectory,
    observations: tuple[TrajectoryObservation, ...],
    rows: tuple[ReplayProbe, ...],
    *,
    threshold: float,
    minimum_support: int,
    alias_spacing_hz: float,
    maximum_negative_fraction: float = 0.05,
) -> tuple[PolynomialTrajectory, ...]:
    """Return one replay-supported line while preserving explicit evidence holes.

    An unassociated window is missing evidence, not negative evidence.  Splitting
    at every association gap severely fragments the two visible CFO families in
    this capture.  The finite envelope therefore comes from the first and last
    replay-positive members; downstream phase tracking must still receive the
    member mask and must not interpret the envelope as phase continuity.
    """

    if not 0.0 <= maximum_negative_fraction <= 1.0:
        raise ValueError("maximum negative replay fraction must lie in [0, 1]")
    positive = tuple(row for row in rows if row.positive(threshold))
    negative = tuple(
        row
        for row in rows
        if row.baseline_margin >= threshold and row.transported_margin < threshold
    )
    if (
        len(positive) < minimum_support
        or not any(closed.start_s <= row.time_s <= closed.end_s for row in positive)
        or (
            negative and len(negative) / (len(positive) + len(negative)) > maximum_negative_fraction
        )
    ):
        return ()
    refined = refit_replay_supported_line(
        closed,
        observations,
        positive,
        alias_spacing_hz=alias_spacing_hz,
    )
    return () if refined is None else (refined,)


def _geometry_tracks(
    windows: tuple[WindowResult, ...], config: Any
) -> tuple[
    tuple[TrajectoryObservation, ...],
    tuple[tuple[str, PolynomialTrajectory], ...],
    tuple[Any, ...],
]:
    detections = _threshold_winners(windows)
    _, representatives = fit_residual_hough_pilot_trajectories(
        detections, config.feedback, config.segmentation
    )
    ordered = tuple(sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s)))
    current = tuple(
        (f"H{index}", trajectory) for index, (_, trajectory) in enumerate(ordered, start=1)
    )
    observations = trajectory_observations(detections)
    hough = config.segmentation.initial_hough
    closed = tuple(
        support.close_degree_one_support(
            label=f"H{index}",
            family_id=family_id,
            seed=trajectory,
            observations=observations,
            alias_spacing_hz=hough.alias_spacing_hz,
            residual_gate_hz=hough.residual_gate_hz,
            maximum_gap_s=hough.maximum_gap_s,
            minimum_extension_support=hough.minimum_support,
        )
        for index, (family_id, trajectory) in enumerate(ordered, start=1)
    )
    groups = support.overlap_groups(closed, minimum_jaccard=0.80)
    retained = tuple(geometry.geometry_representative(group) for group in groups)
    retained = tuple(sorted(retained, key=lambda item: item.trajectory.start_s))
    return observations, current, retained


def _score_transport_replay(
    *,
    source: dict[str, Any],
    bulk_root: Path,
    detections: tuple[Any, ...],
    retained: tuple[Any, ...],
    observations: tuple[TrajectoryObservation, ...],
    config: Any,
) -> tuple[dict[str, tuple[ReplayProbe, ...]], dict[str, int]]:
    representatives = tuple((item.family_id, item.trajectory) for item in retained)
    alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
    aliases = infer_hough_replay_alias_indices(
        representatives, observations, alias_spacing_hz=alias_spacing_hz
    )
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    result: dict[str, tuple[ReplayProbe, ...]] = {}
    try:
        bundle = store.inspect(source["session_id"])
        reader = store.reader(bundle, source["stream_id"], verify=True)
        receiver_id = int(source["receiver_id"])
        probe_samples = round(source["window_ms"] * reader.sample_rate_hz / 1_000)
        for item in retained:
            trajectory = item.trajectory
            alias_index = aliases[trajectory.trajectory_id]
            offset_hz = alias_index * alias_spacing_hz
            rows: list[ReplayProbe] = []
            for detection in detections:
                if not trajectory.start_s <= detection.time_s <= trajectory.end_s:
                    continue
                match = associate_trajectory_baseline(
                    detection,
                    trajectory,
                    frequency_offset_hz=offset_hz,
                    association_gate_hz=config.trajectory_accounting.association_gate_hz,
                )
                if match is None:
                    continue
                ci16 = reader.read(
                    detection.sample_start,
                    probe_samples,
                    receiver_ids=(receiver_id,),
                )
                samples = (
                    ci16[:, 0, 0].astype(np.float64) + 1j * ci16[:, 0, 1].astype(np.float64)
                ) / 32_768.0
                corrected = correct_polynomial_cfo(
                    samples,
                    reader.sample_rate_hz,
                    detection.sample_start,
                    trajectory,
                    frequency_offset_hz=offset_hz,
                )
                lifted_hz = float(trajectory.frequency_hz(detection.time_s)) + offset_hz
                transported_seed = seed_policy.conditioned_seed_hz(
                    acquired_cfo_hz=match.candidate_acquired_cfo_hz,
                    tracking_cfo_hz=match.trajectory_tracking_cfo_hz,
                    lifted_trajectory_hz=lifted_hz,
                    policy="acquired",
                )
                score = conditioned_glrt64_score(
                    corrected,
                    reader.sample_rate_hz,
                    epoch_sample=match.candidate_epoch_sample,
                    acquired_cfo_hz=transported_seed,
                    edge=source["edge"],
                    glrt_size=config.feedback.glrt_size,
                )
                baseline = match.scores[0]
                rows.append(
                    ReplayProbe(
                        label=item.label,
                        sample_start=detection.sample_start,
                        time_s=detection.time_s,
                        baseline_margin=baseline.margin,
                        transported_margin=score.margin,
                        baseline_exact=baseline.exact_score,
                        transported_exact=score.exact_score,
                        baseline_control=float(baseline.control_score or 0.0),
                        transported_control=float(score.control_score or 0.0),
                        association_error_hz=match.association_error_hz,
                        transported_residual_hz=score.residual_cfo_hz,
                    )
                )
            result[item.label] = tuple(rows)
    finally:
        store.close()
    return result, {item.label: aliases[item.trajectory.trajectory_id] for item in retained}


def _raw_branch(
    axis: Any,
    *,
    trajectory: PolynomialTrajectory,
    observations: tuple[TrajectoryObservation, ...],
    alias_spacing_hz: float,
    color: str,
    linewidth: float,
    linestyle: str = "-",
    label: str | None = None,
) -> None:
    by_id = {item.observation_id: item for item in observations}
    members = tuple(by_id[item] for item in trajectory.observation_ids)
    if not members:
        return
    time = np.asarray([item.time_s for item in members], dtype=np.float64)
    raw = np.asarray([item.tracking_cfo_hz for item in members], dtype=np.float64)
    aliases = np.rint((raw - trajectory.frequency_hz(time)) / alias_spacing_hz).astype(int)
    first = True
    for alias in sorted(set(aliases)):
        member_time = time[aliases == alias]
        interval = np.asarray([float(np.min(member_time)), float(np.max(member_time))])
        axis.plot(
            interval,
            (trajectory.frequency_hz(interval) + alias * alias_spacing_hz) / 1e3,
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
            label=label if first else None,
            zorder=5,
        )
        first = False


def _plot_lifecycle(
    output: Path,
    *,
    source: dict[str, Any],
    observations: tuple[TrajectoryObservation, ...],
    current: tuple[tuple[str, PolynomialTrajectory], ...],
    retained: tuple[Any, ...],
    final: dict[str, tuple[PolynomialTrajectory, ...]],
    replay: dict[str, tuple[ReplayProbe, ...]],
    positive_margin: float,
    alias_spacing_hz: float,
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(16, 14), sharex=True, sharey=True)
    colors = support._probe_colors(observations)
    time = [item.time_s for item in observations]
    raw = [item.tracking_cfo_hz / 1e3 for item in observations]
    for axis in axes:
        axis.scatter(time, raw, marker="x", s=20, linewidths=0.8, color=colors, zorder=2)
        axis.set_ylabel("winning 20 ms CFO (kHz)")
        axis.set_xlim(20.0, 47.0)
        axis.grid(alpha=0.18)
    support._plot_raw_branches(axes[0], current, observations, alias_spacing_hz)
    support._plot_raw_branches(
        axes[1],
        tuple((item.label, item.trajectory) for item in retained),
        observations,
        alias_spacing_hz,
    )
    for index, item in enumerate(retained):
        color = support.COLORS[index % len(support.COLORS)]
        trajectories = final.get(item.label, ())
        if not trajectories:
            _raw_branch(
                axes[2],
                trajectory=item.trajectory,
                observations=observations,
                alias_spacing_hz=alias_spacing_hz,
                color="#8f969c",
                linewidth=1.0,
                linestyle="--",
                label=f"{item.label} geometry only",
            )
            continue
        for child_index, trajectory in enumerate(trajectories, start=1):
            _raw_branch(
                axes[2],
                trajectory=trajectory,
                observations=observations,
                alias_spacing_hz=alias_spacing_hz,
                color=color,
                linewidth=2.2,
                label=(
                    f"{item.label}.{child_index} {trajectory.coefficients_hz[0] / 1e3:+.2f} kHz/s"
                ),
            )
        final_samples = {
            next(obs.sample_start for obs in observations if obs.observation_id == observation_id)
            for trajectory in trajectories
            for observation_id in trajectory.observation_ids
        }
        positive = tuple(
            row
            for row in replay[item.label]
            if row.positive(positive_margin) and row.sample_start in final_samples
        )
        if positive:
            reference_track = trajectories[0]
            first_observation = next(
                obs for obs in observations if obs.sample_start == positive[0].sample_start
            )
            axis_alias = round(
                (
                    first_observation.tracking_cfo_hz
                    - float(reference_track.frequency_hz(positive[0].time_s))
                )
                / alias_spacing_hz
            )
            axes[2].scatter(
                [row.time_s for row in positive],
                [
                    (
                        float(
                            next(
                                track.frequency_hz(row.time_s)
                                for track in trajectories
                                if track.start_s <= row.time_s <= track.end_s
                            )
                        )
                        + axis_alias * alias_spacing_hz
                    )
                    / 1e3
                    for row in positive
                ],
                s=13,
                facecolors="none",
                edgecolors=color,
                linewidths=0.65,
                zorder=6,
            )
    axes[0].set_title(f"A · Initial residual-Hough proposals ({len(current)} fragments)")
    axes[1].set_title(
        f"B · Connected support and 0.80-Jaccard deduplication ({len(retained)} tracks)"
    )
    axes[2].set_title(
        "C · Acquisition-coordinate replay-qualified endpoints "
        f"({sum(len(value) for value in final.values())} final segments)"
    )
    axes[2].set_xlabel("capture time (s)")
    axes[2].legend(loc="lower left", fontsize=8, ncol=3)
    figure.suptitle(
        "Dense Hough → support closure → conditioned replay → final linear tracks\n"
        f"{source['session_id']} · {source['stream_id']}/RX{source['receiver_id']} "
        f"{source['edge']} · degree-one only",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_replay(
    output: Path,
    *,
    source: dict[str, Any],
    retained: tuple[Any, ...],
    replay: dict[str, tuple[ReplayProbe, ...]],
    final: dict[str, tuple[PolynomialTrajectory, ...]],
    threshold: float,
) -> None:
    columns = 2
    rows_count = math.ceil(len(retained) / columns)
    figure, axes = plt.subplots(
        rows_count,
        columns,
        figsize=(16, 3.9 * rows_count),
        sharey=True,
        squeeze=False,
    )
    for axis, item in zip(axes.flat, retained, strict=False):
        rows = replay[item.label]
        axis.scatter(
            [row.time_s for row in rows],
            [row.baseline_margin for row in rows],
            marker="x",
            s=18,
            linewidths=0.75,
            color="#f28e2b",
            alpha=0.60,
            label="baseline",
        )
        axis.scatter(
            [row.time_s for row in rows],
            [row.transported_margin for row in rows],
            s=14,
            color="#2a9d6f",
            alpha=0.62,
            label="conditioned replay",
        )
        axis.axhline(threshold, color="#111827", linewidth=0.9, linestyle="--")
        axis.axvspan(item.seed.start_s, item.seed.end_s, color="#8f969c", alpha=0.08)
        tracks = final.get(item.label, ())
        if tracks:
            for track in tracks:
                axis.axvspan(track.start_s, track.end_s, color="#2a9d6f", alpha=0.08)
            rates = ", ".join(f"{track.coefficients_hz[0] / 1e3:+.3f}" for track in tracks)
            low_support = sum(track.point_count for track in tracks) < 20
            status = (
                f"{len(tracks)} final segment(s) · rates {rates} kHz/s"
                f"{' · LOW SUPPORT' if low_support else ''}"
            )
        else:
            status = "geometry only; replay run did not qualify"
        axis.set_title(f"{item.label} · {status}", loc="left", fontsize=10)
        axis.set_xlabel("capture time (s)")
        axis.grid(alpha=0.18)
    for axis in axes[:, 0]:
        axis.set_ylabel("exact − rolled-control margin")
    for axis in axes.flat[len(retained) :]:
        axis.set_visible(False)
    axes.flat[0].legend(fontsize=8, ncol=2)
    figure.suptitle(
        "Conditioned replay determines final time support\n"
        f"{source['session_id']} · transported acquisition coordinate; green span is final",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_accounting(output: Path, *, rows: list[dict[str, Any]]) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(16, 6.2), constrained_layout=True)
    labels = [item["label"] for item in rows]
    y = np.arange(len(labels))
    height = 0.23
    axes[0].barh(
        y - height,
        [item["seed_support_count"] for item in rows],
        height=height,
        label="initial Hough support",
        color="#8f969c",
    )
    axes[0].barh(
        y,
        [item["closed_support_count"] for item in rows],
        height=height,
        label="closed geometry support",
        color="#2678a8",
    )
    axes[0].barh(
        y + height,
        [item["final_support_count"] for item in rows],
        height=height,
        label="replay-qualified support",
        color="#2a9d6f",
    )
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("probe observations")
    axes[0].set_title("A · Membership accounting")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="x", alpha=0.18)

    for index, item in enumerate(rows):
        color = support.COLORS[index % len(support.COLORS)]
        axes[1].plot(
            [item["seed_start_s"], item["seed_end_s"]],
            [index - 0.16, index - 0.16],
            color="#8f969c",
            linewidth=3.0,
        )
        axes[1].plot(
            [item["closed_start_s"], item["closed_end_s"]],
            [index, index],
            color="#2678a8",
            linewidth=4.0,
        )
        for interval_index, interval in enumerate(item["final_intervals"]):
            axes[1].plot(
                [interval["start_s"], interval["end_s"]],
                [index + 0.16, index + 0.16],
                color=color,
                linewidth=5.0,
                label="replay child" if index == 0 and interval_index == 0 else None,
            )
    axes[1].set_yticks(y, labels)
    axes[1].invert_yaxis()
    axes[1].set_xlim(20.0, 47.0)
    axes[1].set_xlabel("capture time (s)")
    axes[1].set_title("B · Gray seed, blue geometry, colored replay interval")
    axes[1].grid(axis="x", alpha=0.18)
    figure.suptitle(
        "Track lifecycle accounting · no polynomial order above one",
        fontsize=15,
        fontweight="bold",
    )
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _write_report(
    report: Path,
    *,
    source: dict[str, Any],
    rows: list[dict[str, Any]],
    lifecycle: Path,
    replay_figure: Path,
    accounting: Path,
    result_json: Path,
) -> None:
    final_count = sum(item["status"].startswith("replay_qualified") for item in rows)
    low_support_count = sum(item["status"] == "replay_qualified_low_support" for item in rows)
    lines = [
        "# Dense Hough downstream-analysis prototype",
        "",
        "## Result",
        "",
        "The updated dense Hough tracks can drive conditioned IQ replay without losing H1. "
        "The prototype keeps geometry and correction qualification separate, transports the "
        "acquisition CFO rather than the residual-adjusted tracking CFO, derives endpoints from "
        "connected replay-positive support, and refits degree-one lines only.",
        "",
        f"It reduced 12 initial Hough fragments to {len(rows)} geometry tracks and retained "
        f"{final_count} replay-qualified final tracks. {low_support_count} of those tracks is "
        "explicitly marked low-support and should remain Research-only.",
        "",
        f"![Track lifecycle]({lifecycle.relative_to(report.parent)})",
        "",
        f"![Conditioned replay by track]({replay_figure.relative_to(report.parent)})",
        "",
        f"![Membership and endpoint accounting]({accounting.relative_to(report.parent)})",
        "",
        "## Track results",
        "",
        "| Track | Seed interval | Closed geometry | Final replay interval | Seed / closed / "
        "final support | Seed rate | Final rate | Alias | Current P→N | Transport P→N | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in rows:
        final_interval = (
            ", ".join(
                f"{value['start_s']:.2f}–{value['end_s']:.2f} s"
                for value in item["final_intervals"]
            )
            or "—"
        )
        final_rate = ", ".join(
            f"{value['slope_hz_s'] / 1e3:+.3f}" for value in item["final_intervals"]
        )
        final_rate = "—" if not final_rate else f"{final_rate} kHz/s"
        lines.append(
            f"| {item['label']} | {item['seed_start_s']:.2f}–{item['seed_end_s']:.2f} s | "
            f"{item['closed_start_s']:.2f}–{item['closed_end_s']:.2f} s | "
            f"{final_interval} | {item['seed_support_count']} / "
            f"{item['closed_support_count']} / {item['final_support_count']} | "
            f"{item['seed_slope_hz_s'] / 1e3:+.3f} kHz/s | {final_rate} | "
            f"{item['alias_index']:+d} | {item['current_positive_to_negative']} | "
            f"{item['transport_positive_to_negative']} | {item['status'].replace('_', ' ')} |"
        )
    lines.extend(
        [
            "",
            "## Exact prototype rule",
            "",
            "1. Start from independently searched 20 ms windows at 10 ms stride.",
            "2. Fit residual-Hough straight lines, close alias-aware support using the ±2.5 kHz "
            "gate, and split after a 0.75 s geometry gap.",
            "3. Remove no endpoint merely because its new tail spans less than 0.75 s; require "
            "eight connected compatible probes instead.",
            "4. Deduplicate tracks at 0.80 support Jaccard without consulting replay outcome.",
            "5. Correct IQ with each lifted line and seed conditioned GLRT at `acquired CFO − "
            "lifted line`; GLRT re-estimates its own residual.",
            "6. Define the correction-eligible envelope from the first and last replay-positive "
            f"geometric members and require {REPLAY_MINIMUM_SUPPORT} such probes. Preserve "
            "internal no-evidence windows as an explicit mask; absence of an associated winner "
            "is not treated as a replay failure or a phase-continuous bridge.",
            "7. Robustly refit one Huber degree-one line to replay-positive geometric members.",
            "",
            "## Interpretation and limits",
            "",
            "Hough proposes geometry; replay validates use of that geometry as a correction. "
            "The integer alias is a component-relative canonical lift, not an absolute RF "
            "frequency determination. The 10 ms-stride windows overlap by 10 ms, so probe "
            "counts are support counts rather than independent statistical trials.",
            "",
            "H2 technically passes the prototype's eight-probe replay gate, but its final "
            "support is only 15 observations. It is retained as low-support candidate evidence, "
            "not treated as equivalent to H1/H4/H3/H7/H10.",
            "",
            "This remains a post-hoc single-path prototype. It is candidate-only, makes no "
            "satellite attribution or phase-continuity claim, and changes no Standard product.",
            "",
            f"Machine-readable results: [`{result_json.name}`]"
            f"({result_json.relative_to(report.parent)})",
            "",
        ]
    )
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    seed_replay = {
        item["label"]: item
        for item in json.loads(args.seed_replay_json.read_text(encoding="utf-8"))["tracks"]
    }
    windows = tuple(WindowResult(**item) for item in source["windows"])
    replay_detections = _window_winners(windows, require_margin_pass=False)
    config = _receiver_standard_config(production_standard_v2_configuration()["path-standard"])
    observations, current_hough, retained = _geometry_tracks(windows, config)
    replay, aliases = _score_transport_replay(
        source=source,
        bulk_root=args.bulk_root,
        detections=replay_detections,
        retained=retained,
        observations=observations,
        config=config,
    )
    threshold = config.trajectory_accounting.positive_margin
    alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
    final: dict[str, tuple[PolynomialTrajectory, ...]] = {}
    rows: list[dict[str, Any]] = []
    for item in retained:
        replay_rows = replay[item.label]
        refined = replay_qualified_segments(
            item.trajectory,
            observations,
            replay_rows,
            threshold=threshold,
            minimum_support=REPLAY_MINIMUM_SUPPORT,
            alias_spacing_hz=alias_spacing_hz,
        )
        if refined:
            final[item.label] = refined
        current_transitions = seed_replay[item.label]["conditioned_transitions"]
        transport_positive = tuple(row for row in replay_rows if row.positive(threshold))
        transport_pn = sum(
            row.baseline_margin >= threshold and row.transported_margin < threshold
            for row in replay_rows
        )
        final_support_count = sum(child.point_count for child in refined)
        evidence_runs = connected_replay_runs(
            replay_rows,
            threshold=threshold,
            maximum_gap_s=REPLAY_MAXIMUM_GAP_S,
        )
        rows.append(
            {
                "label": item.label,
                "status": (
                    "geometry_only"
                    if not refined
                    else (
                        "replay_qualified_low_support"
                        if final_support_count < 20
                        else "replay_qualified"
                    )
                ),
                "alias_index": aliases[item.label],
                "seed_start_s": item.seed.start_s,
                "seed_end_s": item.seed.end_s,
                "closed_start_s": item.trajectory.start_s,
                "closed_end_s": item.trajectory.end_s,
                "final_intervals": [
                    {
                        "start_s": child.start_s,
                        "end_s": child.end_s,
                        "slope_hz_s": child.coefficients_hz[0],
                        "support_count": child.point_count,
                        "residual_rms_hz": child.residual_rms_hz,
                    }
                    for child in refined
                ],
                "seed_slope_hz_s": item.seed.coefficients_hz[0],
                "closed_slope_hz_s": item.trajectory.coefficients_hz[0],
                "seed_support_count": item.seed.point_count,
                "closed_support_count": item.trajectory.point_count,
                "replay_associated_count": len(replay_rows),
                "replay_positive_count": len(transport_positive),
                "final_support_count": final_support_count,
                "final_observation_ids": [
                    observation_id for child in refined for observation_id in child.observation_ids
                ],
                "replay_positive_evidence_runs": [
                    {
                        "start_s": run[0].time_s,
                        "end_s": run[-1].time_s,
                        "support_count": len(run),
                    }
                    for run in evidence_runs
                ],
                "current_positive_to_positive": current_transitions["positive_to_positive"],
                "current_positive_to_negative": current_transitions["positive_to_negative"],
                "transport_positive_to_positive": len(transport_positive),
                "transport_positive_to_negative": transport_pn,
                "baseline_median_margin": (
                    None
                    if not replay_rows
                    else statistics.median(row.baseline_margin for row in replay_rows)
                ),
                "transport_median_margin": (
                    None
                    if not replay_rows
                    else statistics.median(row.transported_margin for row in replay_rows)
                ),
                "final_segment_count": len(refined),
            }
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    lifecycle = args.output_root / "hough-downstream-lifecycle.png"
    replay_figure = args.output_root / "conditioned-replay-endpoints.png"
    accounting = args.output_root / "track-support-accounting.png"
    result_json = args.output_root / "hough-downstream-prototype.json"
    _plot_lifecycle(
        lifecycle,
        source=source,
        observations=observations,
        current=current_hough,
        retained=retained,
        final=final,
        replay=replay,
        positive_margin=threshold,
        alias_spacing_hz=alias_spacing_hz,
    )
    _plot_replay(
        replay_figure,
        source=source,
        retained=retained,
        replay=replay,
        final=final,
        threshold=threshold,
    )
    _plot_accounting(accounting, rows=rows)
    document = {
        "schema_version": 1,
        "kind": "dense-hough-downstream-prototype",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "degree_one_only": True,
        "promoted_to_standard": False,
        "parameters": {
            "geometry_residual_gate_hz": config.segmentation.initial_hough.residual_gate_hz,
            "geometry_maximum_gap_s": config.segmentation.initial_hough.maximum_gap_s,
            "minimum_extension_support": config.segmentation.initial_hough.minimum_support,
            "minimum_extension_span_s": None,
            "deduplication_support_jaccard": 0.80,
            "replay_positive_margin": threshold,
            "replay_internal_gap_policy": "preserve_no_evidence_mask_without_splitting",
            "replay_minimum_support": REPLAY_MINIMUM_SUPPORT,
            "conditioned_seed_policy": "acquired_cfo_minus_lifted_line",
        },
        "summary": {
            "window_count": len(windows),
            "margin_passing_probe_count": len(observations),
            "initial_hough_fragment_count": len(current_hough),
            "closed_geometry_track_count": len(retained),
            "replay_qualified_parent_count": len(final),
            "replay_qualified_segment_count": sum(len(value) for value in final.values()),
            "replay_qualified_low_support_count": sum(
                item["status"] == "replay_qualified_low_support" for item in rows
            ),
            "seed_support_total": sum(item["seed_support_count"] for item in rows),
            "closed_support_total": sum(item["closed_support_count"] for item in rows),
            "final_support_total": sum(item["final_support_count"] for item in rows),
            "current_positive_to_negative_total": sum(
                item["current_positive_to_negative"] for item in rows
            ),
            "transport_positive_to_negative_total": sum(
                item["transport_positive_to_negative"] for item in rows
            ),
        },
        "tracks": rows,
    }
    result_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    _write_report(
        args.report,
        source=source,
        rows=rows,
        lifecycle=lifecycle,
        replay_figure=replay_figure,
        accounting=accounting,
        result_json=result_json,
    )
    print(json.dumps(document["summary"], indent=2), flush=True)
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {lifecycle}", flush=True)
    print(f"wrote {replay_figure}", flush=True)
    print(f"wrote {accounting}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
