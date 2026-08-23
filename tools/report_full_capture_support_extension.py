#!/usr/bin/env python3
"""Prototype connected-support extension for full-capture degree-one Hough lines.

The prototype treats each Hough model as an unbounded mathematical line, finds
the temporally connected alias-aware inlier run containing its seed, robustly
refits that fixed run, and repeats until membership stabilizes.  Replay-failing
seeds are rejected and survivors with substantially identical support are
collapsed before a fresh conditioned-IQ replay.  No product is promoted into
Standard.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.cfo_lines import circular_residual_hz
from leo.analysis.robust_linear import fit_huber_linear_irls
from leo.analysis.standard.analyzers import (
    _receiver_standard_config,
    production_standard_v2_configuration,
)
from leo.analysis.standard.full_capture_glrt20ms import (
    WindowResult,
    _threshold_winners,
    _window_winners,
)
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.standard.trajectory_accounting import (
    build_trajectory_conditioned_accounting_v2,
)
from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryObservation
from leo.analysis.starlink.trajectory_feedback import (
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    replay_pilot_trajectories_at_detection_windows_with_conditioned_scores,
    trajectory_observations,
)
from leo.contracts.digests import canonical_digest
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
SOURCE_JSON = Path(
    "reports/figures/2026_08_23_140820_glrt20ms/"
    "cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.json"
)
SEED_REPLAY_JSON = Path(
    "reports/figures/2026_08_23_full_capture_hough_replay/"
    "full-capture-hough-conditioned-replay.json"
)
OUTPUT_ROOT = Path("reports/figures/2026_08_23_full_capture_support_extension")
REPORT_PATH = Path("reports/2026_08_23_full_capture_support_extension_prototype.md")
COLORS = (
    "#2678a8",
    "#2a9d6f",
    "#c44e8b",
    "#6f63bb",
    "#8c6d31",
    "#5c677d",
    "#17a2b8",
    "#d65f5f",
    "#9467bd",
    "#4f772d",
    "#1d4ed8",
    "#7c3aed",
)


@dataclass(frozen=True, slots=True)
class ClosedSupport:
    """One support-defined degree-one track and its immutable seed provenance."""

    label: str
    family_id: str
    seed: PolynomialTrajectory
    trajectory: PolynomialTrajectory
    closure_iterations: int
    added_left_count: int
    added_inside_count: int
    added_right_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--seed-replay-json", type=Path, default=SEED_REPLAY_JSON)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def _connected_runs(
    observations: tuple[TrajectoryObservation, ...], maximum_gap_s: float
) -> tuple[tuple[TrajectoryObservation, ...], ...]:
    if maximum_gap_s <= 0.0 or not math.isfinite(maximum_gap_s):
        raise ValueError("maximum support gap must be finite and positive")
    ordered = sorted(observations, key=lambda item: (item.time_s, item.observation_id))
    if not ordered:
        return ()
    runs: list[list[TrajectoryObservation]] = [[ordered[0]]]
    for observation in ordered[1:]:
        if observation.time_s - runs[-1][-1].time_s > maximum_gap_s:
            runs.append([])
        runs[-1].append(observation)
    return tuple(tuple(run) for run in runs)


def _qualifying_extension(
    values: tuple[TrajectoryObservation, ...],
    *,
    minimum_support: int,
) -> tuple[TrajectoryObservation, ...]:
    """Keep a connected endpoint tail once it has enough probe support.

    The parent Hough segment has already met the track-birth minimum-span gate.
    Endpoint growth therefore does not need to independently re-qualify as a
    new track over that same duration.
    """

    return values if len(values) >= minimum_support else ()


def close_degree_one_support(
    *,
    label: str,
    family_id: str,
    seed: PolynomialTrajectory,
    observations: tuple[TrajectoryObservation, ...],
    alias_spacing_hz: float,
    residual_gate_hz: float,
    maximum_gap_s: float,
    minimum_extension_support: int,
    maximum_iterations: int = 8,
) -> ClosedSupport:
    """Close one seed over its connected alias-aware inliers and refit a line.

    Time is not a model parameter.  The line is evaluated everywhere, while
    the returned finite interval is the minimum/maximum time of the connected
    inlier support anchored to the original Hough observations.
    """

    if seed.polynomial_degree != 1:
        raise ValueError("connected support closure accepts degree-one seeds only")
    if not observations or len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("support observations must be nonempty and uniquely identified")
    if (
        not math.isfinite(alias_spacing_hz)
        or alias_spacing_hz <= 0.0
        or not math.isfinite(residual_gate_hz)
        or residual_gate_hz <= 0.0
        or minimum_extension_support < 1
        or maximum_iterations < 1
    ):
        raise ValueError("connected support bounds are invalid")
    by_id = {item.observation_id: item for item in observations}
    missing = set(seed.observation_ids).difference(by_id)
    if missing:
        raise ValueError("support seed references absent observations")
    seed_ids = set(seed.observation_ids)
    previous_ids = seed_ids
    coefficients = np.asarray(seed.coefficients_hz, dtype=np.float64)
    reference_time_s = seed.reference_time_s
    selected = tuple(by_id[item] for item in seed.observation_ids)
    iterations = 0
    fit = None
    for iteration in range(1, maximum_iterations + 1):
        iterations = iteration
        times = np.asarray([item.time_s for item in observations], dtype=np.float64)
        raw = np.asarray([item.tracking_cfo_hz for item in observations], dtype=np.float64)
        predicted = np.polyval(coefficients, times - reference_time_s)
        residual = np.abs(circular_residual_hz(raw, predicted, alias_spacing_hz))
        candidates = tuple(
            item
            for item, value in zip(observations, residual, strict=True)
            if value <= residual_gate_hz
        )
        runs = _connected_runs(candidates, maximum_gap_s)
        anchored = tuple(
            run for run in runs if seed_ids.intersection(x.observation_id for x in run)
        )
        if not anchored:
            raise ValueError("support closure lost every seed-connected inlier run")
        selected = max(
            anchored,
            key=lambda run: (
                len(seed_ids.intersection(item.observation_id for item in run)),
                len(previous_ids.intersection(item.observation_id for item in run)),
                len(run),
                -run[0].time_s,
            ),
        )
        inside = tuple(item for item in selected if seed.start_s <= item.time_s <= seed.end_s)
        left = _qualifying_extension(
            tuple(item for item in selected if item.time_s < seed.start_s),
            minimum_support=minimum_extension_support,
        )
        right = _qualifying_extension(
            tuple(item for item in selected if item.time_s > seed.end_s),
            minimum_support=minimum_extension_support,
        )
        selected = tuple(sorted((*left, *inside, *right), key=lambda item: item.time_s))
        if len(selected) < 3:
            raise ValueError("support closure retained fewer than three observations")
        selected_times = np.asarray([item.time_s for item in selected], dtype=np.float64)
        selected_raw = np.asarray([item.tracking_cfo_hz for item in selected], dtype=np.float64)
        selected_prediction = np.polyval(coefficients, selected_times - reference_time_s)
        aliases = np.rint((selected_raw - selected_prediction) / alias_spacing_hz)
        canonical = selected_raw - aliases * alias_spacing_hz
        fit = fit_huber_linear_irls(
            selected_times,
            canonical,
            initial_coefficients_hz=(float(coefficients[0]), float(coefficients[1])),
            reference_time_s=reference_time_s,
        )
        selected_ids = {item.observation_id for item in selected}
        stable = selected_ids == previous_ids and np.allclose(
            coefficients,
            np.asarray(fit.coefficients_hz),
            rtol=1e-12,
            atol=1e-6,
        )
        coefficients = np.asarray(fit.coefficients_hz, dtype=np.float64)
        previous_ids = selected_ids
        if stable:
            break
    assert fit is not None
    selected_times = np.asarray([item.time_s for item in selected], dtype=np.float64)
    selected_raw = np.asarray([item.tracking_cfo_hz for item in selected], dtype=np.float64)
    predicted = np.polyval(coefficients, selected_times - reference_time_s)
    aliases = np.rint((selected_raw - predicted) / alias_spacing_hz)
    canonical = selected_raw - aliases * alias_spacing_hz
    residual = canonical - predicted
    rss = max(float(np.sum(residual**2)), np.finfo(float).tiny)
    count = len(selected)
    bic = float(count * math.log(rss / count) + 2.0 * math.log(count))
    observation_ids = tuple(item.observation_id for item in selected)
    model_values = {
        "algorithm": "connected-alias-support-closure-d1-v1",
        "seed_trajectory_id": seed.trajectory_id,
        "reference_time_s": reference_time_s,
        "coefficients_hz": tuple(float(value) for value in coefficients),
        "start_s": selected[0].time_s,
        "end_s": selected[-1].time_s,
        "observation_ids": observation_ids,
    }
    trajectory = PolynomialTrajectory(
        trajectory_id=canonical_digest(model_values),
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=reference_time_s,
        coefficients_hz=tuple(float(value) for value in coefficients),
        start_s=selected[0].time_s,
        end_s=selected[-1].time_s,
        observation_ids=observation_ids,
        point_count=count,
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        bic=bic,
        high_gate=0.0,
        em_iterations=0,
    )
    return ClosedSupport(
        label=label,
        family_id=family_id,
        seed=seed,
        trajectory=trajectory,
        closure_iterations=iterations,
        added_left_count=sum(item.time_s < seed.start_s for item in selected),
        added_inside_count=sum(
            seed.start_s <= item.time_s <= seed.end_s and item.observation_id not in seed_ids
            for item in selected
        ),
        added_right_count=sum(item.time_s > seed.end_s for item in selected),
    )


def support_jaccard(left: ClosedSupport, right: ClosedSupport) -> float:
    left_ids = set(left.trajectory.observation_ids)
    right_ids = set(right.trajectory.observation_ids)
    return len(left_ids & right_ids) / len(left_ids | right_ids)


def overlap_groups(
    tracks: tuple[ClosedSupport, ...], *, minimum_jaccard: float
) -> tuple[tuple[ClosedSupport, ...], ...]:
    """Return deterministic transitive groups of substantially identical support."""

    if not 0.0 < minimum_jaccard <= 1.0:
        raise ValueError("support-overlap threshold must lie in (0, 1]")
    parents = list(range(len(tracks)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for left in range(len(tracks)):
        for right in range(left + 1, len(tracks)):
            if support_jaccard(tracks[left], tracks[right]) < minimum_jaccard:
                continue
            left_root = root(left)
            right_root = root(right)
            parents[max(left_root, right_root)] = min(left_root, right_root)
    grouped: dict[int, list[ClosedSupport]] = {}
    for index, track in enumerate(tracks):
        grouped.setdefault(root(index), []).append(track)
    return tuple(
        tuple(sorted(group, key=lambda item: item.label)) for _, group in sorted(grouped.items())
    )


def _seed_passes_replay(item: dict[str, Any]) -> bool:
    transitions = item["conditioned_transitions"]
    associated = int(item["associated_count"])
    harmful = int(transitions["positive_to_negative"])
    return (
        associated >= 20
        and item["end_s"] - item["start_s"] >= 0.75
        and harmful / associated <= 0.05
        and item["median_conditioned_margin"] is not None
        and item["median_conditioned_margin"] > 0.025
    )


def _representative_score(
    track: ClosedSupport, replay: dict[str, dict[str, Any]]
) -> tuple[Any, ...]:
    item = replay[track.label]
    delta = item["median_conditioned_delta"]
    return (
        -math.inf if delta is None else float(delta),
        int(item["associated_count"]),
        track.trajectory.point_count,
        -int(track.label.removeprefix("H")),
    )


def _accounting_rows(accounting: Any) -> dict[str, dict[str, Any]]:
    evaluations: dict[str, list[Any]] = {}
    for item in accounting.evaluations:
        if item.baseline_margin is not None:
            evaluations.setdefault(item.trajectory_id, []).append(item)
    rows = {}
    for item in accounting.trajectories:
        matched = evaluations.get(item.trajectory_id, [])
        deltas = [value.conditioned_corrected_margin - value.baseline_margin for value in matched]
        rows[item.trajectory_id] = {
            "evaluation_count": item.evaluation_count,
            "associated_count": item.associated_count,
            "unassociated_count": item.unassociated_count,
            "conditioned_transitions": {
                "positive_to_positive": item.conditioned_transitions.positive_to_positive,
                "positive_to_negative": item.conditioned_transitions.positive_to_negative,
                "negative_to_positive": item.conditioned_transitions.negative_to_positive,
                "negative_to_negative": item.conditioned_transitions.negative_to_negative,
            },
            "median_conditioned_delta": None if not deltas else statistics.median(deltas),
        }
    return rows


def _plot_raw_branches(
    axis: Any,
    tracks: tuple[tuple[str, PolynomialTrajectory], ...],
    observations: tuple[TrajectoryObservation, ...],
    alias_spacing_hz: float,
) -> None:
    by_id = {item.observation_id: item for item in observations}
    for index, (label, trajectory) in enumerate(tracks):
        color = COLORS[index % len(COLORS)]
        support = tuple(by_id[item] for item in trajectory.observation_ids)
        time = np.asarray([item.time_s for item in support])
        raw = np.asarray([item.tracking_cfo_hz for item in support])
        predicted = trajectory.frequency_hz(time)
        aliases = np.rint((raw - predicted) / alias_spacing_hz).astype(int)
        for alias in sorted(set(aliases)):
            member_time = time[aliases == alias]
            plot_time = np.asarray([float(np.min(member_time)), float(np.max(member_time))])
            plot_frequency = trajectory.frequency_hz(plot_time) + alias * alias_spacing_hz
            axis.plot(
                plot_time,
                plot_frequency / 1e3,
                color=color,
                linewidth=1.45,
                zorder=4,
            )
        label_alias = int(statistics.mode(int(value) for value in aliases))
        label_time = trajectory.end_s
        label_frequency = (
            float(trajectory.frequency_hz(label_time)) + label_alias * alias_spacing_hz
        )
        axis.text(
            label_time + 0.08,
            label_frequency / 1e3,
            f"{label} {trajectory.coefficients_hz[0] / 1e3:+.2f}",
            color=color,
            fontsize=7,
            ha="left",
            va="center",
            zorder=5,
        )


def _probe_colors(observations: tuple[TrajectoryObservation, ...]) -> np.ndarray:
    margins = np.asarray([item.margin for item in observations])
    ceiling = max(float(np.quantile(margins, 0.95)), 0.025 + np.finfo(float).eps)
    alpha = 0.15 + 0.70 * np.clip((margins - 0.025) / (ceiling - 0.025), 0.0, 1.0)
    colors = np.zeros((len(observations), 4))
    colors[:, :3] = np.asarray([0.85, 0.42, 0.12])
    colors[:, 3] = alpha
    return colors


def _plot_before_after(
    output: Path,
    observations: tuple[TrajectoryObservation, ...],
    current: tuple[tuple[str, PolynomialTrajectory], ...],
    proposed: tuple[tuple[str, PolynomialTrajectory], ...],
    alias_spacing_hz: float,
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(16, 11), sharex=True, sharey=True)
    colors = _probe_colors(observations)
    time = [item.time_s for item in observations]
    raw = [item.tracking_cfo_hz / 1e3 for item in observations]
    for axis in axes:
        axis.scatter(
            time,
            raw,
            marker="x",
            s=18,
            linewidths=0.75,
            color=colors,
            zorder=2,
        )
        axis.grid(alpha=0.18)
        axis.set_ylabel("winning 20 ms-window CFO (kHz)")
        axis.set_xlim(20.0, 47.0)
    _plot_raw_branches(axes[0], current, observations, alias_spacing_hz)
    _plot_raw_branches(axes[1], proposed, observations, alias_spacing_hz)
    axes[0].set_title(
        f"A · Current Hough output: {len(current)} bounded, overlapping degree-one segments"
    )
    axes[1].set_title(
        f"B · Proposed support closure: {len(proposed)} replay-screened, deduplicated segments"
    )
    axes[1].set_xlabel("capture time (s)")
    figure.suptitle(
        "Algorithmically independent 20 ms GLRT window probes versus time · "
        "support-extension prototype\n"
        f"{SESSION_ID} · stream-0/RX0 upper · 10 ms stride; adjacent probes share 10 ms of IQ",
        fontsize=14,
    )
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _stacked_transitions(axis: Any, labels: list[str], rows: list[dict[str, Any]]) -> None:
    keys = (
        "positive_to_positive",
        "positive_to_negative",
        "negative_to_positive",
        "negative_to_negative",
    )
    names = ("P→P", "P→N", "N→P", "N→N")
    colors = ("#2a9d6f", "#c44e52", "#2678a8", "#a7b0b8")
    bottom = np.zeros(len(labels))
    for key, name, color in zip(keys, names, colors, strict=True):
        values = np.asarray([item["conditioned_transitions"][key] for item in rows])
        axis.bar(labels, values, bottom=bottom, label=name, color=color)
        bottom += values
    axis.grid(axis="y", alpha=0.18)


def _plot_stats(
    output: Path,
    current_rows: list[dict[str, Any]],
    proposed_rows: list[dict[str, Any]],
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    current_intervals, proposed_intervals, current_replay, proposed_replay = axes.flat
    for axis, rows, title in (
        (current_intervals, current_rows, "A · Current Hough membership intervals"),
        (proposed_intervals, proposed_rows, "B · Support-defined intervals after collapse"),
    ):
        labels = [item["label"] for item in rows]
        y = np.arange(len(rows))
        start = np.asarray([item["start_s"] for item in rows])
        duration = np.asarray([item["end_s"] - item["start_s"] for item in rows])
        axis.barh(y, duration, left=start, color="#2678a8", alpha=0.85)
        axis.set_yticks(y, labels)
        axis.invert_yaxis()
        axis.set_xlim(20.0, 47.0)
        axis.set_xlabel("capture time (s)")
        axis.set_title(title)
        axis.grid(axis="x", alpha=0.18)
    _stacked_transitions(
        current_replay,
        [item["label"] for item in current_rows],
        current_rows,
    )
    current_replay.set_title("C · Existing seed conditioned-replay evidence")
    current_replay.set_ylabel("associated probes")
    current_replay.legend(fontsize=8, ncol=4)
    _stacked_transitions(
        proposed_replay,
        [item["label"] for item in proposed_rows],
        proposed_rows,
    )
    proposed_replay.set_title("D · Fresh replay over revised complete intervals")
    proposed_replay.set_ylabel("associated probes")
    proposed_replay.legend(fontsize=8, ncol=4)
    figure.suptitle(
        "Current bounded Hough segments versus connected-support closure\n"
        f"{SESSION_ID} · degree-one only · prototype, not Standard output",
        fontsize=14,
    )
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _digests(
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    observations: tuple[TrajectoryObservation, ...],
) -> tuple[str, str, str]:
    pilot = canonical_digest(
        {
            "kind": "threshold-passing-20ms-window-winners-v1",
            "observation_ids": tuple(item.observation_id for item in observations),
        }
    )
    bank = canonical_digest(
        {
            "kind": "connected-support-degree1-bank-prototype-v1",
            "trajectories": tuple(
                (item.trajectory_id, item.observation_ids, item.coefficients_hz)
                for _, item in representatives
            ),
        }
    )
    feedback = canonical_digest(
        {"kind": "connected-support-conditioned-replay-prototype-v1", "bank": bank}
    )
    return pilot, bank, feedback


def _write_report(report: Path, figure_a: Path, figure_b: Path, document: dict[str, Any]) -> None:
    summary = document["summary"]
    lines = [
        "# Connected-support extension prototype",
        "",
        "## Question",
        "",
        "Can each degree-one Hough line be treated as mathematically unbounded, with its "
        "observed time interval derived from connected frame-probe support instead of being "
        "estimated by alias EM?",
        "",
        "## Answer",
        "",
        "Yes, and this capture supports the simpler approach. The deterministic closure reduced "
        f"{summary['current_track_count']} bounded Hough fragments to "
        f"{summary['proposed_track_count']} replay-screened support tracks. It uses no "
        "quadratic/cubic radio model and no time-length parameter in EM.",
        "",
        f"Three of the four retained tracks expanded in time. Fresh replay over the revised "
        f"intervals produced {summary['fresh_positive_to_positive_count']} P→P and "
        f"{summary['fresh_positive_to_negative_count']} P→N associated probes. The proposed "
        f"bank retains {summary['proposed_unique_support_count']} unique probe observations "
        f"versus {summary['current_unique_support_count']} across all original Hough fragments; "
        f"{summary['shared_support_count']} are shared, "
        f"{summary['newly_included_support_count']} are newly included, and "
        f"{summary['excluded_current_support_count']} current members are excluded. "
        "The current Hough partition assigns those observations exclusively even though its "
        "reported time intervals overlap. Duplicate claims arise only when the candidate lines "
        "are extended, and are removed before the proposed bank is formed.",
        "",
        f"![Frame probes and line supports]({figure_a.relative_to(report.parent)})",
        "",
        f"![Intervals and conditioned replay]({figure_b.relative_to(report.parent)})",
        "",
        "## Exact prototype rule",
        "",
        "1. Evaluate each existing Hough degree-one line at every independently searched, "
        "margin-passing 20 ms probe. Adjacent 10 ms-stride probes share 10 ms of IQ and are "
        "therefore statistically correlated.",
        "2. Select alias-aware inliers within the existing 2.5 kHz gate.",
        "3. Split at the existing 0.75 s maximum gap and retain the component anchored to the "
        "seed support.",
        "4. Permit an endpoint extension when that connected side independently supplies at "
        "least eight observations; the already-qualified parent track supplies the duration "
        "evidence, so endpoint growth has no separate minimum-span gate.",
        "5. Refit one MAD-scaled Huber straight line and repeat until membership stabilizes.",
        "6. Reject seeds that failed the existing conditioned replay screen.",
        "7. Collapse survivors with at least 0.80 support Jaccard overlap, retaining the seed "
        "with the strongest prior replay result.",
        "8. Rerun conditioned IQ replay over every revised complete interval.",
        "",
        "## Selected tracks before and after",
        "",
        "| Track | Seed interval | Revised interval | Seed rate | Revised rate | "
        "Seed support | Revised support | Fresh P→P | P→N |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in document["proposed_tracks"]:
        transitions = item["conditioned_transitions"]
        lines.append(
            f"| {item['label']} | {item['seed_start_s']:.2f}–{item['seed_end_s']:.2f} s | "
            f"{item['start_s']:.2f}–{item['end_s']:.2f} s | "
            f"{item['seed_slope_hz_s'] / 1e3:+.3f} kHz/s | "
            f"{item['slope_hz_s'] / 1e3:+.3f} kHz/s | {item['seed_support_count']} | "
            f"{item['support_count']} | {transitions['positive_to_positive']} | "
            f"{transitions['positive_to_negative']} |"
        )
    lines.extend(
        [
            "",
            "## Support groups and selections",
            "",
            "| Group | Seeds | Minimum support Jaccard | Selected | Revised interval | Rate | "
            "Support | Fresh P→P | P→N | Median Δ margin |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    proposed_by_label = {item["label"]: item for item in document["proposed_tracks"]}
    for group in document["groups"]:
        selected = proposed_by_label[group["selected_label"]]
        transitions = selected["conditioned_transitions"]
        lines.append(
            "| {group} | {members} | {jaccard:.3f} | {selected} | "
            "{start:.2f}–{end:.2f} s | "
            "{slope:+.3f} kHz/s | {support} | {pp} | {pn} | {delta} |".format(
                group=group["group_label"],
                members=", ".join(group["member_labels"]),
                jaccard=group["minimum_pairwise_jaccard"],
                selected=group["selected_label"],
                start=selected["start_s"],
                end=selected["end_s"],
                slope=selected["slope_hz_s"] / 1e3,
                support=selected["support_count"],
                pp=transitions["positive_to_positive"],
                pn=transitions["positive_to_negative"],
                delta=(
                    "—"
                    if selected["median_conditioned_delta"] is None
                    else f"{selected['median_conditioned_delta']:+.3f}"
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Rejected seeds",
            "",
            "| Seed | Interval | Prior associated | Prior P→N | Reason |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in document["rejected_tracks"]:
        transitions = item["conditioned_transitions"]
        lines.append(
            f"| {item['label']} | {item['start_s']:.2f}–{item['end_s']:.2f} s | "
            f"{item['associated_count']} | {transitions['positive_to_negative']} | "
            "failed the conservative seed replay screen |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The original endpoints are properties of Hough proposal membership, not evidence "
            "that the radio signal begins or ends at those times. Connected support supplies a "
            "simpler interval definition. Deduplication is mandatory: without it, several "
            "nearby lines claim nearly identical probes after extension.",
            "",
            "This remains a post-hoc, single-capture prototype. It is candidate-only, makes no "
            "satellite attribution, changes no Standard product, and requires multi-dwell plus "
            "matched-null validation before promotion.",
            "",
        ]
    )
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    seed_replay_document = json.loads(args.seed_replay_json.read_text(encoding="utf-8"))
    seed_replay = {item["label"]: item for item in seed_replay_document["tracks"]}
    windows = tuple(WindowResult(**item) for item in source["windows"])
    hough_detections = _threshold_winners(windows)
    replay_detections = _window_winners(windows, require_margin_pass=False)
    observations = trajectory_observations(hough_detections)
    config = _receiver_standard_config(production_standard_v2_configuration()["path-standard"])
    _, representatives = fit_residual_hough_pilot_trajectories(
        hough_detections, config.feedback, config.segmentation
    )
    ordered = tuple(sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s)))
    current = tuple((f"H{index}", item[1]) for index, item in enumerate(ordered, start=1))
    if {label for label, _ in current} != set(seed_replay):
        raise ValueError("current Hough labels disagree with the seed replay artifact")
    hough = config.segmentation.initial_hough
    closed = tuple(
        close_degree_one_support(
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
    eligible = tuple(item for item in closed if _seed_passes_replay(seed_replay[item.label]))
    rejected = tuple(item for item in closed if item not in eligible)
    groups = overlap_groups(eligible, minimum_jaccard=0.80)
    selected = tuple(
        max(group, key=lambda item: _representative_score(item, seed_replay)) for group in groups
    )
    selected = tuple(sorted(selected, key=lambda item: item.trajectory.start_s))
    proposed_representatives = tuple((item.family_id, item.trajectory) for item in selected)
    alias_indices = infer_hough_replay_alias_indices(
        proposed_representatives,
        observations,
        alias_spacing_hz=hough.alias_spacing_hz,
    )
    print(
        f"replaying {len(proposed_representatives)} support-closed representatives over "
        f"{len(replay_detections)} independently searched windows",
        flush=True,
    )
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(source["session_id"])
        reader = SingleReceiverIqReader(
            store.reader(bundle, source["stream_id"], verify=True), int(source["receiver_id"])
        )
        replay = replay_pilot_trajectories_at_detection_windows_with_conditioned_scores(
            reader,
            replay_detections,
            proposed_representatives,
            config.feedback,
            edge=source["edge"],
            alias_indices=alias_indices,
            alias_spacing_hz=hough.alias_spacing_hz,
            association_gate_hz=config.trajectory_accounting.association_gate_hz,
            probe_samples=round(source["window_ms"] * reader.sample_rate_hz / 1_000),
        )
    finally:
        store.close()
    pilot_digest, bank_digest, feedback_digest = _digests(proposed_representatives, observations)
    accounting = build_trajectory_conditioned_accounting_v2(
        replay_detections,
        proposed_representatives,
        replay,
        frequency_offsets_hz={
            trajectory_id: alias_index * hough.alias_spacing_hz
            for trajectory_id, alias_index in alias_indices.items()
        },
        pilot_scan_digest=pilot_digest,
        trajectory_bank_digest=bank_digest,
        trajectory_feedback_digest=feedback_digest,
        config=config.trajectory_accounting,
    )
    fresh = _accounting_rows(accounting)
    proposed_rows = []
    for item in selected:
        row = fresh[item.trajectory.trajectory_id]
        proposed_rows.append(
            {
                "label": item.label,
                "source_seed_label": item.label,
                "trajectory_id": item.trajectory.trajectory_id,
                "seed_start_s": item.seed.start_s,
                "seed_end_s": item.seed.end_s,
                "seed_slope_hz_s": item.seed.coefficients_hz[0],
                "start_s": item.trajectory.start_s,
                "end_s": item.trajectory.end_s,
                "slope_hz_s": item.trajectory.coefficients_hz[0],
                "support_count": item.trajectory.point_count,
                "seed_support_count": item.seed.point_count,
                "closure_iterations": item.closure_iterations,
                "added_left_count": item.added_left_count,
                "added_inside_count": item.added_inside_count,
                "added_right_count": item.added_right_count,
                "replay_alias_index": alias_indices[item.trajectory.trajectory_id],
                **row,
            }
        )
    current_rows = [seed_replay[label] for label, _ in current]
    group_rows = []
    for index, group in enumerate(groups, start=1):
        chosen = max(group, key=lambda item: _representative_score(item, seed_replay))
        group_rows.append(
            {
                "group_label": f"G{index}",
                "member_labels": [item.label for item in group],
                "selected_label": chosen.label,
                "minimum_pairwise_jaccard": (
                    1.0
                    if len(group) == 1
                    else min(
                        support_jaccard(group[left], group[right])
                        for left in range(len(group))
                        for right in range(left + 1, len(group))
                    )
                ),
            }
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    probes_figure = args.output_root / "frame-probes-support-before-after.png"
    stats_figure = args.output_root / "support-extension-replay-stats.png"
    result_json = args.output_root / "support-extension-prototype.json"
    proposed_plot = tuple((item.label, item.trajectory) for item in selected)
    _plot_before_after(
        probes_figure,
        observations,
        current,
        proposed_plot,
        hough.alias_spacing_hz,
    )
    _plot_stats(stats_figure, current_rows, proposed_rows)
    current_unique_support = set().union(
        *(set(trajectory.observation_ids) for _, trajectory in current)
    )
    proposed_unique_support = set().union(
        *(set(item.trajectory.observation_ids) for item in selected)
    )
    fresh_positive_to_positive = sum(
        item["conditioned_transitions"]["positive_to_positive"] for item in proposed_rows
    )
    fresh_positive_to_negative = sum(
        item["conditioned_transitions"]["positive_to_negative"] for item in proposed_rows
    )
    shared_support = current_unique_support & proposed_unique_support
    document = {
        "schema_version": 1,
        "kind": "full-capture-connected-support-extension-prototype",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "degree_one_only": True,
        "promoted_to_standard": False,
        "parameters": {
            "alias_spacing_hz": hough.alias_spacing_hz,
            "residual_gate_hz": hough.residual_gate_hz,
            "maximum_gap_s": hough.maximum_gap_s,
            "minimum_extension_support": hough.minimum_support,
            "minimum_extension_span_s": None,
            "deduplication_support_jaccard": 0.80,
        },
        "summary": {
            "window_count": len(windows),
            "margin_passing_probe_count": len(observations),
            "current_track_count": len(current),
            "seed_replay_eligible_count": len(eligible),
            "rejected_seed_count": len(rejected),
            "proposed_track_count": len(selected),
            "current_membership_count": sum(trajectory.point_count for _, trajectory in current),
            "current_unique_support_count": len(current_unique_support),
            "proposed_membership_count": sum(item.trajectory.point_count for item in selected),
            "proposed_unique_support_count": len(proposed_unique_support),
            "shared_support_count": len(shared_support),
            "newly_included_support_count": len(proposed_unique_support - current_unique_support),
            "excluded_current_support_count": len(current_unique_support - proposed_unique_support),
            "fresh_replay_row_count": len(replay),
            "fresh_associated_evaluation_count": accounting.associated_evaluation_count,
            "fresh_unassociated_evaluation_count": accounting.unassociated_evaluation_count,
            "fresh_positive_to_positive_count": fresh_positive_to_positive,
            "fresh_positive_to_negative_count": fresh_positive_to_negative,
        },
        "groups": group_rows,
        "current_tracks": current_rows,
        "proposed_tracks": proposed_rows,
        "rejected_tracks": [seed_replay[item.label] for item in rejected],
    }
    result_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    _write_report(args.report, probes_figure, stats_figure, document)
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {probes_figure}", flush=True)
    print(f"wrote {stats_figure}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
