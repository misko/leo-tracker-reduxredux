#!/usr/bin/env python3
"""Associate and report adaptive dual-RX pilot phase without phase selection."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink import adaptive_dual_rx_phase as phase_primitives  # noqa: E402

SYMBOL_ALIAS_HZ = phase_primitives.SYMBOL_ALIAS_HZ
circular_frequency_delta = phase_primitives.circular_frequency_delta
circular_phase_standard_error_deg = phase_primitives.circular_phase_standard_error_deg
receiver_relative_frequency_hz = phase_primitives.receiver_relative_frequency_hz
restore_receiver_relative_phase = phase_primitives.restore_receiver_relative_phase
select_consistent_receiver_pairs = phase_primitives.select_consistent_receiver_pairs
simultaneous_double_difference = phase_primitives.simultaneous_double_difference

MAXIMUM_VISIT_GAP = 32
MAXIMUM_TIME_GAP_S = 3.5
MAXIMUM_SIGNAL_STEP_HZ = 15_000
MAXIMUM_SEPARATION_STEP_HZ = 3_000
MINIMUM_TRACK_POINTS = 4


@dataclass(frozen=True, slots=True)
class AssociationState:
    """One oriented two-signal hypothesis used for phase-blind association."""

    hypothesis_id: int
    orientation: int
    visit_index: int
    target_index: int
    time_s: float
    frequencies_hz: tuple[float, float]
    separation_hz: float
    phase_deg: float
    phase_rate_hz: float
    quality: float
    legacy_phase_deg: float | None = None
    phase_sigma_deg: float | None = None


def oriented_states(document: dict[str, Any]) -> list[AssociationState]:
    """Expand every unordered hypothesis into its two possible identities."""
    output: list[AssociationState] = []
    for hypothesis_id, row in enumerate(document["hypotheses"]):
        frequencies = tuple(map(float, row["signal_frequencies_hz"]))
        phase_deg = float(row["double_difference_deg"])
        phase_rate_hz = float(row["double_relative_frequency_hz"])
        for orientation in (0, 1):
            ordered = frequencies if orientation == 0 else frequencies[::-1]
            sign = 1 if orientation == 0 else -1
            output.append(
                AssociationState(
                    hypothesis_id=hypothesis_id,
                    orientation=orientation,
                    visit_index=int(row["visit_index"]),
                    target_index=int(row["target_index"]),
                    time_s=float(row["acquisition_time_s"]),
                    frequencies_hz=ordered,
                    separation_hz=float(row["signal_separation_hz"]),
                    phase_deg=sign * phase_deg,
                    phase_rate_hz=sign * phase_rate_hz,
                    quality=float(row.get("association_quality_floor", row["quality_floor"])),
                    legacy_phase_deg=(
                        sign * float(row["legacy_double_difference_deg"])
                        if "legacy_double_difference_deg" in row
                        else None
                    ),
                    phase_sigma_deg=(
                        float(row["double_phase_standard_error_deg"])
                        if "double_phase_standard_error_deg" in row
                        else None
                    ),
                )
            )
    return output


def transition_cost(left: AssociationState, right: AssociationState) -> float | None:
    """Score a phase-blind transition, or reject an implausible transition."""
    visit_gap = right.visit_index - left.visit_index
    time_gap_s = right.time_s - left.time_s
    if not 1 <= visit_gap <= MAXIMUM_VISIT_GAP:
        return None
    if not 0 < time_gap_s <= MAXIMUM_TIME_GAP_S:
        return None
    signal_steps = tuple(
        abs(circular_frequency_delta(left.frequencies_hz[index], right.frequencies_hz[index]))
        for index in (0, 1)
    )
    separation_step = abs(right.separation_hz - left.separation_hz)
    if max(signal_steps) > MAXIMUM_SIGNAL_STEP_HZ:
        return None
    if separation_step > MAXIMUM_SEPARATION_STEP_HZ:
        return None
    return float(
        sum(signal_steps) / MAXIMUM_SIGNAL_STEP_HZ
        + separation_step / MAXIMUM_SEPARATION_STEP_HZ
        - 0.05 * min(left.quality, right.quality)
    )


def best_path(
    candidates: list[AssociationState], blocked_hypotheses: set[int]
) -> list[AssociationState]:
    """Find the longest admissible path, breaking ties by transition cost."""
    available = [state for state in candidates if state.hypothesis_id not in blocked_hypotheses]
    available.sort(key=lambda state: (state.visit_index, state.hypothesis_id, state.orientation))
    if not available:
        return []
    lengths = [1] * len(available)
    costs = [0.0] * len(available)
    previous: list[int | None] = [None] * len(available)
    for right_index, right in enumerate(available):
        for left_index in range(right_index):
            cost = transition_cost(available[left_index], right)
            if cost is None:
                continue
            proposed_length = lengths[left_index] + 1
            proposed_cost = costs[left_index] + cost
            if proposed_length > lengths[right_index] or (
                proposed_length == lengths[right_index] and proposed_cost < costs[right_index]
            ):
                lengths[right_index] = proposed_length
                costs[right_index] = proposed_cost
                previous[right_index] = left_index
    end: int | None = max(range(len(available)), key=lambda index: (lengths[index], -costs[index]))
    path: list[AssociationState] = []
    while end is not None:
        path.append(available[end])
        end = previous[end]
    return list(reversed(path))


def associate(document: dict[str, Any]) -> list[list[AssociationState]]:
    """Associate every target while never consulting a state's phase fields."""
    states = oriented_states(document)
    paths: list[list[AssociationState]] = []
    for target_index in range(8):
        candidates = [state for state in states if state.target_index == target_index]
        blocked: set[int] = set()
        while True:
            path = best_path(candidates, blocked)
            if len(path) < MINIMUM_TRACK_POINTS:
                break
            paths.append(path)
            blocked.update(state.hypothesis_id for state in path)
    return paths


def circular_degrees(values_deg: np.ndarray) -> np.ndarray:
    return np.degrees(np.angle(np.exp(1j * np.radians(values_deg))))


def phase_metrics(path: list[AssociationState], rng: np.random.Generator) -> dict[str, Any]:
    """Evaluate phase only after an association has been frozen."""
    time_s = np.asarray([state.time_s for state in path])
    wrapped_rad = np.radians([state.phase_deg for state in path])
    unwrapped_rad = np.unwrap(wrapped_rad)
    increments_rad = np.diff(unwrapped_rad)
    concentration = float(abs(np.mean(np.exp(1j * increments_rad))))
    centered_time_s = time_s - np.mean(time_s)
    slope_rad_s, intercept_rad = np.polyfit(centered_time_s, unwrapped_rad, 1)
    residual_deg = np.degrees(unwrapped_rad - (slope_rad_s * centered_time_s + intercept_rad))

    phase_rate_hz = np.asarray([state.phase_rate_hz for state in path])
    predicted_increment_rad = (
        2 * np.pi * 0.5 * (phase_rate_hz[1:] + phase_rate_hz[:-1]) * np.diff(time_s)
    )
    rate_prediction_error_deg = np.degrees(
        np.angle(np.exp(1j * (np.diff(wrapped_rad) - predicted_increment_rad)))
    )

    random_increments = rng.uniform(-np.pi, np.pi, (200_000, len(increments_rad)))
    uniform_concentrations = abs(np.mean(np.exp(1j * random_increments), axis=1))
    permutation_concentrations = np.empty(20_000)
    for index in range(len(permutation_concentrations)):
        shuffled = rng.permutation(wrapped_rad)
        permutation_concentrations[index] = abs(np.mean(np.exp(1j * np.diff(shuffled))))

    training_count = max(3, (len(path) + 1) // 2)
    holdout_time_s = time_s[training_count:]
    holdout_median_error_deg: float | None = None
    holdout_rms_error_deg: float | None = None
    holdout_max_error_deg: float | None = None
    if len(holdout_time_s):
        training_time_s = time_s[:training_count]
        training_phase_rad = np.unwrap(wrapped_rad[:training_count])
        training_relative_time_s = training_time_s - training_time_s[0]
        forward_slope, forward_intercept = np.polyfit(
            training_relative_time_s, training_phase_rad, 1
        )
        predicted_rad = forward_slope * (holdout_time_s - training_time_s[0]) + forward_intercept
        error_rad = np.angle(np.exp(1j * (wrapped_rad[training_count:] - predicted_rad)))
        error_deg = np.degrees(error_rad)
        holdout_median_error_deg = float(np.median(abs(error_deg)))
        holdout_rms_error_deg = float(np.sqrt(np.mean(error_deg**2)))
        holdout_max_error_deg = float(np.max(abs(error_deg)))

    separations_hz = np.asarray([state.separation_hz for state in path])
    separation_time_correlation: float | None = None
    if np.std(time_s) > 0 and np.std(separations_hz) > 0:
        separation_time_correlation = float(np.corrcoef(time_s, separations_hz)[0, 1])

    legacy_metrics: dict[str, float] = {}
    if all(state.legacy_phase_deg is not None for state in path):
        legacy_unwrapped_rad = np.unwrap(
            np.radians([float(state.legacy_phase_deg) for state in path])
        )
        legacy_slope_rad_s, legacy_intercept_rad = np.polyfit(
            centered_time_s, legacy_unwrapped_rad, 1
        )
        legacy_residual_deg = np.degrees(
            legacy_unwrapped_rad - (legacy_slope_rad_s * centered_time_s + legacy_intercept_rad)
        )
        legacy_metrics = {
            "legacy_increment_concentration": float(
                abs(np.mean(np.exp(1j * np.diff(legacy_unwrapped_rad))))
            ),
            "legacy_linear_slope_deg_s": float(np.degrees(legacy_slope_rad_s)),
            "legacy_linear_residual_rms_deg": float(np.sqrt(np.mean(legacy_residual_deg**2))),
        }
    uncertainty_metrics: dict[str, float] = {}
    if all(state.phase_sigma_deg is not None and state.phase_sigma_deg > 0 for state in path):
        sigma_deg = np.asarray([float(state.phase_sigma_deg) for state in path])
        weights = 1 / sigma_deg**2
        design = np.column_stack((centered_time_s, np.ones(len(path))))
        weighted_design = design * np.sqrt(weights)[:, None]
        weighted_phase = np.degrees(unwrapped_rad) * np.sqrt(weights)
        weighted_slope, weighted_intercept = np.linalg.lstsq(
            weighted_design, weighted_phase, rcond=None
        )[0]
        weighted_residual_deg = np.degrees(unwrapped_rad) - (
            weighted_slope * centered_time_s + weighted_intercept
        )
        uncertainty_metrics = {
            "median_phase_standard_error_deg": float(np.median(sigma_deg)),
            "weighted_linear_slope_deg_s": float(weighted_slope),
            "weighted_linear_residual_rms_deg": float(
                np.sqrt(np.average(weighted_residual_deg**2, weights=weights))
            ),
            "normalized_residual_rms": float(
                np.sqrt(np.mean((weighted_residual_deg / sigma_deg) ** 2))
            ),
        }
    return {
        "count": len(path),
        "target_index": path[0].target_index,
        "first_time_s": float(time_s[0]),
        "last_time_s": float(time_s[-1]),
        "increment_concentration": concentration,
        "uniform_increment_p": float(np.mean(uniform_concentrations >= concentration)),
        "phase_permutation_p": float(np.mean(permutation_concentrations >= concentration)),
        "linear_slope_deg_s": float(np.degrees(slope_rad_s)),
        "linear_residual_rms_deg": float(np.sqrt(np.mean(residual_deg**2))),
        "median_abs_rate_prediction_error_deg": float(np.median(abs(rate_prediction_error_deg))),
        "median_abs_within_dwell_phase_rate_hz": float(np.median(abs(phase_rate_hz))),
        "forward_holdout_count": len(holdout_time_s),
        "forward_holdout_median_abs_error_deg": holdout_median_error_deg,
        "forward_holdout_rms_error_deg": holdout_rms_error_deg,
        "forward_holdout_max_abs_error_deg": holdout_max_error_deg,
        "separation_time_correlation": separation_time_correlation,
        "median_signal_separation_hz": float(np.median([state.separation_hz for state in path])),
        **legacy_metrics,
        **uncertainty_metrics,
    }


def summarize_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rng = np.random.default_rng(20260916)
    summary = []
    for document in sorted(documents, key=lambda item: item["session_id"]):
        tracks = associate(document)
        summary.append(
            {
                "session_id": document["session_id"],
                "radio_id": document["radio_id"],
                "association_uses_phase": False,
                "association_limits": {
                    "maximum_visit_gap": MAXIMUM_VISIT_GAP,
                    "maximum_time_gap_s": MAXIMUM_TIME_GAP_S,
                    "maximum_each_signal_step_hz": MAXIMUM_SIGNAL_STEP_HZ,
                    "maximum_separation_step_hz": MAXIMUM_SEPARATION_STEP_HZ,
                    "minimum_track_points": MINIMUM_TRACK_POINTS,
                },
                "tracks": [phase_metrics(track, rng) for track in tracks],
                "track_states": [[asdict(state) for state in track] for track in tracks],
            }
        )
    return summary


def plot_all_five(
    documents: list[dict[str, Any]], summary: list[dict[str, Any]], output: Path
) -> None:
    by_session = {row["session_id"]: row for row in summary}
    ordered = sorted(documents, key=lambda item: item["session_id"])
    labels = [f"{item['session_id'][-4:]}\n{item['radio_id'][-4:]}" for item in ordered]
    qualified = [int(item["qualified_double_difference_visits"]) for item in ordered]
    attempted = [int(item["attempted_two_pair_visits"]) for item in ordered]
    fractions = [
        100 * accepted / tested for accepted, tested in zip(qualified, attempted, strict=True)
    ]
    best_tracks = [
        max(by_session[item["session_id"]]["tracks"], key=lambda row: row["count"], default=None)
        for item in ordered
    ]
    counts = [0 if track is None else track["count"] for track in best_tracks]
    concentrations = [
        0.0 if track is None else track["increment_concentration"] for track in best_tracks
    ]

    figure, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    positions = np.arange(len(ordered))
    bars = axes[0].bar(positions, fractions, color="tab:blue", alpha=0.8)
    axes[0].set_ylabel("Qualified two-signal visits (%)")
    axes[0].set_ylim(0, 70)
    axes[0].set_title("Simultaneous two-signal double-difference availability")
    for bar, accepted, tested in zip(bars, qualified, attempted, strict=True):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.2,
            f"{accepted}/{tested}",
            ha="center",
            va="bottom",
        )

    bars = axes[1].bar(positions, counts, color="tab:orange", alpha=0.8)
    axes[1].set_ylabel("Longest phase-blind track (visits)")
    axes[1].set_ylim(0, max(counts) + 3)
    axes[1].set_title("Track length and post-association phase-increment concentration")
    for bar, count, concentration in zip(bars, counts, concentrations, strict=True):
        label = "none" if count == 0 else f"R={concentration:.2f}"
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.25,
            label,
            ha="center",
            va="bottom",
        )
    for axis in axes:
        axis.set_xticks(positions, labels)
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Adaptive dual-RX phase recovery across five 300-second scans")
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_best_recovery(summary: list[dict[str, Any]], output: Path) -> None:
    session = next(item for item in summary if item["session_id"] == "scan-hop-bfc60ea18ace593b")
    candidates = [
        (track, states)
        for track, states in zip(session["tracks"], session["track_states"], strict=True)
        if track["target_index"] == 0
    ]
    candidates.sort(key=lambda item: item[0]["first_time_s"])
    selected = candidates[:2]
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    colors = ("tab:blue", "tab:orange")
    for index, ((metrics, states), color) in enumerate(
        zip(selected, colors[: len(selected)], strict=True), start=1
    ):
        time_s = np.asarray([row["time_s"] for row in states])
        relative_time_s = time_s - time_s[0]
        phase_deg = np.degrees(np.unwrap(np.radians([row["phase_deg"] for row in states])))
        centered_time_s = relative_time_s - np.mean(relative_time_s)
        slope_deg_s, intercept_deg = np.polyfit(centered_time_s, phase_deg, 1)
        fitted_deg = slope_deg_s * centered_time_s + intercept_deg
        label = f"Track {index}"
        sigma_deg = np.asarray(
            [np.nan if row["phase_sigma_deg"] is None else row["phase_sigma_deg"] for row in states]
        )
        if np.all(np.isfinite(sigma_deg)):
            axes[0, 0].errorbar(
                relative_time_s,
                phase_deg,
                yerr=sigma_deg,
                fmt="o-",
                capsize=2,
                color=color,
                label=label,
            )
        else:
            axes[0, 0].plot(relative_time_s, phase_deg, "o-", color=color, label=label)
        axes[0, 0].plot(relative_time_s, fitted_deg, "--", color=color, alpha=0.75)
        axes[1, 0].plot(relative_time_s, phase_deg - fitted_deg, "o-", color=color, label=label)
        axes[0, 1].plot(
            relative_time_s,
            np.asarray([row["separation_hz"] for row in states]) / 1000,
            "o-",
            color=color,
            label=label,
        )
        rates_hz = np.asarray([row["phase_rate_hz"] for row in states])
        predicted_deg = 360 * 0.5 * (rates_hz[:-1] + rates_hz[1:]) * np.diff(time_s)
        observed_deg = circular_degrees(np.diff(phase_deg))
        error_deg = circular_degrees(observed_deg - predicted_deg)
        axes[1, 1].plot(
            0.5 * (relative_time_s[:-1] + relative_time_s[1:]),
            error_deg,
            "o-",
            color=color,
            label=label,
        )
        axes[0, 0].annotate(
            (
                f"{label}: n={metrics['count']}, "
                f"slope={metrics['linear_slope_deg_s']:.1f}°/s, "
                f"RMS={metrics['linear_residual_rms_deg']:.1f}°\n"
                f"increment R={metrics['increment_concentration']:.3f}, "
                f"shuffle p={metrics['phase_permutation_p']:.4f}\n"
                f"median σ={metrics.get('median_phase_standard_error_deg', float('nan')):.1f}°, "
                f"normalized RMS={metrics.get('normalized_residual_rms', float('nan')):.2f}"
            ),
            xy=(relative_time_s[-1], phase_deg[-1]),
            xytext=(8, 12 if index == 1 else 20),
            textcoords="offset points",
            color=color,
            fontsize=9,
        )
    axes[0, 0].set_title("Recovered double-difference phase")
    axes[0, 0].set_ylabel("Unwrapped phase (deg)")
    axes[0, 1].set_title("Phase-blind association observable")
    axes[0, 1].set_ylabel("Two-signal separation (kHz)")
    axes[1, 0].set_title("Residual after a linear phase model")
    axes[1, 0].set_ylabel("Phase residual (deg)")
    axes[1, 1].set_title("Short-dwell rate does not bridge revisit gaps")
    axes[1, 1].set_ylabel("One-step prediction error (deg)")
    for axis in axes[1]:
        axis.set_xlabel("Time from first associated visit (s)")
    for axis in axes.ravel():
        axis.axhline(0, color="0.55", linewidth=0.8)
        axis.grid(alpha=0.2)
    axes[0, 0].legend(loc="best")
    axes[0, 1].legend(loc="best")
    figure.suptitle(
        "Improved adaptive recovery: identity linked without phase\n"
        "scan-hop-bfc60ea18ace593b / radio_pluto_19f2 / target 0"
    )
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_reference_correction(summary: list[dict[str, Any]], output: Path) -> None:
    """Compare legacy and reference-consistent phase on identical associations."""
    session = next(item for item in summary if item["session_id"] == "scan-hop-bfc60ea18ace593b")
    candidates = [
        (track, states)
        for track, states in zip(session["tracks"], session["track_states"], strict=True)
        if track["target_index"] == 0 and "legacy_linear_residual_rms_deg" in track
    ]
    candidates.sort(key=lambda item: item[0]["count"], reverse=True)
    selected = candidates[:2]
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for axis, (metrics, states) in zip(axes[: len(selected)], selected, strict=True):
        time_s = np.asarray([row["time_s"] for row in states])
        relative_time_s = time_s - time_s[0]
        corrected_deg = np.degrees(np.unwrap(np.radians([row["phase_deg"] for row in states])))
        legacy_deg = np.degrees(np.unwrap(np.radians([row["legacy_phase_deg"] for row in states])))
        axis.plot(
            relative_time_s,
            legacy_deg,
            "x--",
            color="tab:gray",
            label=(
                "Legacy residual counted twice "
                f"(RMS {metrics['legacy_linear_residual_rms_deg']:.1f}°)"
            ),
        )
        axis.plot(
            relative_time_s,
            corrected_deg,
            "o-",
            color="tab:blue",
            label=(
                f"Reference-consistent restoration (RMS {metrics['linear_residual_rms_deg']:.1f}°)"
            ),
        )
        axis.set_ylabel("Unwrapped double difference (deg)")
        axis.set_title(
            f"{metrics['count']} visits, target {metrics['target_index']}, "
            f"{metrics['last_time_s'] - metrics['first_time_s']:.2f} s"
        )
        axis.grid(alpha=0.2)
        axis.legend(loc="best")
    for axis in axes[len(selected) :]:
        axis.set_visible(False)
    if selected:
        axes[len(selected) - 1].set_xlabel("Time from first associated visit (s)")
    figure.suptitle(
        "Phase-reference correction on identical phase-blind associations\n"
        "scan-hop-bfc60ea18ace593b / radio_pluto_19f2"
    )
    figure.savefig(output, dpi=190)
    plt.close(figure)


def window_sensitivity_row(
    radius: int,
    documents: list[dict[str, Any]],
    summary: list[dict[str, Any]],
) -> dict[str, Any]:
    bfc60 = next(item for item in summary if item["session_id"] == "scan-hop-bfc60ea18ace593b")
    longest = max(bfc60["tracks"], key=lambda item: item["count"], default=None)
    attempted = sum(int(item["attempted_two_pair_visits"]) for item in documents)
    qualified = sum(int(item["qualified_double_difference_visits"]) for item in documents)
    return {
        "frame_radius": radius,
        "nominal_support_ms": (2 * radius - 1) / 750 * 1000,
        "attempted_two_signal_visits": attempted,
        "qualified_two_signal_visits": qualified,
        "qualified_percent": 100 * qualified / attempted,
        "bfc60_longest_track": longest,
    }


def plot_window_sensitivity(rows: list[dict[str, Any]], output: Path) -> None:
    support_ms = np.asarray([row["nominal_support_ms"] for row in rows])
    qualified_percent = np.asarray([row["qualified_percent"] for row in rows])
    counts = np.asarray([row["bfc60_longest_track"]["count"] for row in rows], dtype=float)
    rms_deg = np.asarray([row["bfc60_longest_track"]["linear_residual_rms_deg"] for row in rows])
    rate_error_deg = np.asarray(
        [row["bfc60_longest_track"]["median_abs_rate_prediction_error_deg"] for row in rows]
    )
    figure, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True, layout="constrained")
    axes[0].plot(support_ms, qualified_percent, "o-", color="tab:blue")
    axes[0].set_ylabel("Qualified visits (%)")
    axes[0].set_title("Two-signal availability across all five scans")
    axes[1].plot(support_ms, counts, "o-", color="tab:orange", label="Track visits")
    axes[1].set_ylabel("Longest track (visits)")
    twin = axes[1].twinx()
    twin.plot(support_ms, rms_deg, "s--", color="tab:green", label="Linear RMS")
    twin.set_ylabel("Phase residual RMS (deg)")
    lines = axes[1].get_lines() + twin.get_lines()
    axes[1].legend(lines, [line.get_label() for line in lines], loc="best")
    axes[1].set_title("Strongest bfc60 target-0 association")
    axes[2].plot(support_ms, rate_error_deg, "o-", color="tab:red")
    axes[2].set_ylabel("Median prediction error (deg)")
    axes[2].set_xlabel("Nominal pilot support per visit (ms)")
    axes[2].set_title("Within-dwell rate propagated to the next visit")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.suptitle("Adaptive phase estimator window-length sensitivity")
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--sensitivity-input",
        action="append",
        default=[],
        metavar="RADIUS=DIR",
        help="Additional frozen input directory for a frame-radius sensitivity plot",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    paths = sorted(arguments.input_dir.glob("scan-hop-*-adaptive-double-difference.json"))
    if len(paths) != 5:
        raise ValueError(f"expected five adaptive inputs, found {len(paths)}")
    documents = [json.loads(path.read_text()) for path in paths]
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_documents(documents)
    (arguments.output_dir / "adaptive-phase-association-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    plot_all_five(
        documents,
        summary,
        arguments.output_dir / "all-five-recovery-summary.png",
    )
    plot_best_recovery(
        summary,
        arguments.output_dir / "improved-double-difference-recovery.png",
    )
    plot_reference_correction(
        summary,
        arguments.output_dir / "reference-consistent-phase-comparison.png",
    )
    if arguments.sensitivity_input:
        sensitivity_rows = []
        for value in arguments.sensitivity_input:
            radius_text, separator, directory_text = value.partition("=")
            if not separator:
                raise ValueError("sensitivity input must have the form RADIUS=DIR")
            directory = Path(directory_text)
            sensitivity_paths = sorted(directory.glob("scan-hop-*-adaptive-double-difference.json"))
            if len(sensitivity_paths) != 5:
                raise ValueError(
                    f"expected five sensitivity inputs in {directory}, "
                    f"found {len(sensitivity_paths)}"
                )
            sensitivity_documents = [json.loads(path.read_text()) for path in sensitivity_paths]
            sensitivity_summary = summarize_documents(sensitivity_documents)
            sensitivity_rows.append(
                window_sensitivity_row(int(radius_text), sensitivity_documents, sensitivity_summary)
            )
        sensitivity_rows.sort(key=lambda item: item["frame_radius"])
        (arguments.output_dir / "adaptive-phase-window-sensitivity.json").write_text(
            json.dumps(sensitivity_rows, indent=2) + "\n"
        )
        plot_window_sensitivity(
            sensitivity_rows,
            arguments.output_dir / "adaptive-phase-window-sensitivity.png",
        )


if __name__ == "__main__":
    main()
