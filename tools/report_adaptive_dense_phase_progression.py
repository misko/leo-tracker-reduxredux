#!/usr/bin/env python3
"""Associate a bounded dense dual-RX phase canary without using phase."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.adaptive_dual_rx_phase import circular_frequency_delta  # noqa: E402

MAXIMUM_VISIT_GAP = 32
MAXIMUM_TIME_GAP_S = 3.5
MAXIMUM_SIGNAL_STEP_HZ = 15_000.0
MAXIMUM_SEPARATION_STEP_HZ = 3_000.0
MAXIMUM_RECEIVER_OFFSET_STEP_HZ = 10_000.0
MINIMUM_TRACK_POINTS = 4


@dataclass(frozen=True, slots=True)
class DensePhaseState:
    hypothesis_id: int
    orientation: int
    visit_index: int
    target_index: int
    time_s: float
    frequencies_hz: tuple[float, float]
    separation_hz: float
    receiver_offset_hz: float
    phase_deg: float
    phase_sigma_deg: float
    quality: float


def states(document: dict[str, Any]) -> list[DensePhaseState]:
    """Expand hypotheses into both identities before phase-blind association."""
    output: list[DensePhaseState] = []
    hypothesis_id = 0
    for visit in document["visits"]:
        for row in visit["hypotheses"]:
            frequencies = (
                float(row["low_rx0_tracking_cfo_hz"]),
                float(row["high_rx0_tracking_cfo_hz"]),
            )
            phase_deg = math.degrees(float(row["wrapped_high_minus_low_rad"]))
            for orientation in (0, 1):
                sign = 1 if orientation == 0 else -1
                output.append(
                    DensePhaseState(
                        hypothesis_id=hypothesis_id,
                        orientation=orientation,
                        visit_index=int(visit["visit_index"]),
                        target_index=int(visit["target_index"]),
                        time_s=float(row["common_session_time_s"]),
                        frequencies_hz=(
                            frequencies if orientation == 0 else frequencies[::-1]
                        ),
                        separation_hz=float(row["alias_aware_signal_separation_hz"]),
                        receiver_offset_hz=float(row["receiver_offset_hz"]),
                        phase_deg=sign * phase_deg,
                        phase_sigma_deg=math.degrees(float(row["standard_error_rad"])),
                        quality=float(row["exact_to_control_power_ratio_floor"]),
                    )
                )
            hypothesis_id += 1
    return output


def transition_cost(left: DensePhaseState, right: DensePhaseState) -> float | None:
    """Apply the September 16 gates plus an explicit receiver-offset branch gate."""
    if left.target_index != right.target_index:
        return None
    visit_gap = right.visit_index - left.visit_index
    time_gap_s = right.time_s - left.time_s
    if not 1 <= visit_gap <= MAXIMUM_VISIT_GAP or not 0 < time_gap_s <= MAXIMUM_TIME_GAP_S:
        return None
    signal_steps = tuple(
        abs(circular_frequency_delta(left.frequencies_hz[index], right.frequencies_hz[index]))
        for index in (0, 1)
    )
    separation_step = abs(right.separation_hz - left.separation_hz)
    receiver_offset_step = abs(right.receiver_offset_hz - left.receiver_offset_hz)
    if (
        max(signal_steps) > MAXIMUM_SIGNAL_STEP_HZ
        or separation_step > MAXIMUM_SEPARATION_STEP_HZ
        or receiver_offset_step > MAXIMUM_RECEIVER_OFFSET_STEP_HZ
    ):
        return None
    return float(
        sum(signal_steps) / MAXIMUM_SIGNAL_STEP_HZ
        + separation_step / MAXIMUM_SEPARATION_STEP_HZ
        + receiver_offset_step / MAXIMUM_RECEIVER_OFFSET_STEP_HZ
        - 0.05 * min(left.quality, right.quality)
    )


def best_path(candidates: list[DensePhaseState]) -> list[DensePhaseState]:
    available = sorted(
        candidates, key=lambda row: (row.visit_index, row.hypothesis_id, row.orientation)
    )
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
    path: list[DensePhaseState] = []
    while end is not None:
        path.append(available[end])
        end = previous[end]
    return list(reversed(path))


def associate(document: dict[str, Any]) -> list[list[DensePhaseState]]:
    candidates = states(document)
    paths: list[list[DensePhaseState]] = []
    blocked: set[int] = set()
    while True:
        path = best_path([row for row in candidates if row.hypothesis_id not in blocked])
        if len(path) < MINIMUM_TRACK_POINTS:
            break
        paths.append(path)
        blocked.update(row.hypothesis_id for row in path)
    return paths


def _fit(path: list[DensePhaseState]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    time_s = np.asarray([row.time_s for row in path])
    wrapped_rad = np.radians([row.phase_deg for row in path])
    sigma_rad = np.radians([row.phase_sigma_deg for row in path])
    # Qin/BPSK leaves an independent half-cycle ambiguity. This chooses the
    # minimum-increment branch only for the explicitly conditional line fit.
    unwrapped_rad = 0.5 * np.unwrap(2.0 * wrapped_rad)
    weights = 1.0 / sigma_rad**2
    reference_time_s = float(np.average(time_s, weights=weights))
    design = np.column_stack((time_s - reference_time_s, np.ones(len(time_s))))
    normal = design.T @ (weights[:, None] * design)
    slope_rad_s, intercept_rad = np.linalg.solve(normal, design.T @ (weights * unwrapped_rad))
    predicted_rad = design @ np.asarray((slope_rad_s, intercept_rad))
    residual_rad = unwrapped_rad - predicted_rad
    reduced_chi_square = float(np.sum(weights * residual_rad**2) / (len(path) - 2))
    covariance = np.linalg.inv(normal) * max(1.0, reduced_chi_square)
    slopes = []
    for held_out in range(len(path)):
        keep = np.arange(len(path)) != held_out
        held_weights = weights[keep]
        held_time = time_s[keep]
        held_reference = float(np.average(held_time, weights=held_weights))
        held_design = np.column_stack(
            (held_time - held_reference, np.ones(len(held_time)))
        )
        held_fit = np.linalg.solve(
            held_design.T @ (held_weights[:, None] * held_design),
            held_design.T @ (held_weights * unwrapped_rad[keep]),
        )
        slopes.append(math.degrees(float(held_fit[0])))
    increments_rad = np.diff(unwrapped_rad)
    concentration = float(abs(np.mean(np.exp(2j * increments_rad))))
    rng = np.random.default_rng(20260921)
    permutations = np.empty(20_000)
    for index in range(len(permutations)):
        shuffled = rng.permutation(wrapped_rad)
        shuffled_unwrapped = 0.5 * np.unwrap(2.0 * shuffled)
        permutations[index] = abs(np.mean(np.exp(2j * np.diff(shuffled_unwrapped))))
    metrics = {
        "count": len(path),
        "first_visit_index": path[0].visit_index,
        "last_visit_index": path[-1].visit_index,
        "first_time_s": float(time_s[0]),
        "last_time_s": float(time_s[-1]),
        "span_s": float(time_s[-1] - time_s[0]),
        "conditional_modulo_pi_slope_deg_s": math.degrees(float(slope_rad_s)),
        "conditional_slope_standard_error_deg_s": math.degrees(
            math.sqrt(float(covariance[0, 0]))
        ),
        "leave_one_out_slope_range_deg_s": [min(slopes), max(slopes)],
        "unweighted_residual_rms_deg": math.degrees(
            math.sqrt(float(np.mean(residual_rad**2)))
        ),
        "weighted_residual_rms_deg": math.degrees(
            math.sqrt(float(np.average(residual_rad**2, weights=weights)))
        ),
        "normalized_residual_rms": math.sqrt(float(np.mean((residual_rad / sigma_rad) ** 2))),
        "reduced_chi_square": reduced_chi_square,
        "median_phase_standard_error_deg": float(np.median(np.degrees(sigma_rad))),
        "modulo_pi_increment_concentration": concentration,
        "phase_permutation_p": float(np.mean(permutations >= concentration)),
        "receiver_offset_range_hz": [
            min(row.receiver_offset_hz for row in path),
            max(row.receiver_offset_hz for row in path),
        ],
        "pilot_phase_ambiguity": "modulo_pi",
        "phase_continuity_across_retunes": False,
        "slope_interpretation": "conditional_minimum_increment_branch_only",
    }
    return unwrapped_rad, predicted_rad, metrics


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    paths = associate(document)
    tracks = []
    for path in paths:
        _, _, metrics = _fit(path)
        tracks.append({"metrics": metrics, "states": [asdict(row) for row in path]})
    return {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_dense_phase_progression_summary",
        "session_id": document["session_id"],
        "input_manifest_sha256": document["input_manifest_sha256"],
        "analysis_binding_sha256": document["analysis_binding_sha256"],
        "selected_visit_analyses_sha256": document["selected_visit_analyses_sha256"],
        "probe_stride_ms": document["probe_stride_ms"],
        "selected_visit_count": len(document["selected_visit_indexes"]),
        "qualified_visit_count": sum(bool(row["hypotheses"]) for row in document["visits"]),
        "hypothesis_count": sum(len(row["hypotheses"]) for row in document["visits"]),
        "association_uses_phase": False,
        "aliases_resolved": False,
        "pilot_phase_ambiguity": "modulo_pi",
        "phase_continuity_across_retunes": False,
        "association_limits": {
            "maximum_visit_gap": MAXIMUM_VISIT_GAP,
            "maximum_time_gap_s": MAXIMUM_TIME_GAP_S,
            "maximum_each_signal_step_hz": MAXIMUM_SIGNAL_STEP_HZ,
            "maximum_separation_step_hz": MAXIMUM_SEPARATION_STEP_HZ,
            "maximum_receiver_offset_step_hz": MAXIMUM_RECEIVER_OFFSET_STEP_HZ,
            "minimum_track_points": MINIMUM_TRACK_POINTS,
        },
        "tracks": tracks,
    }


def render(document: dict[str, Any], summary: dict[str, Any], output: Path) -> None:
    all_states = [row for row in states(document) if row.orientation == 0]
    tracks = associate(document)
    best = tracks[0] if tracks else []
    selected = {row.hypothesis_id for row in best}
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, layout="constrained")
    for row in all_states:
        color = "tab:blue" if row.hypothesis_id in selected else "0.65"
        axes[0].errorbar(
            row.time_s,
            ((row.phase_deg + 90.0) % 180.0) - 90.0,
            yerr=row.phase_sigma_deg,
            fmt="o",
            color=color,
            alpha=0.9 if row.hypothesis_id in selected else 0.6,
        )
    if best:
        unwrapped_rad, predicted_rad, metrics = _fit(best)
        time_s = np.asarray([row.time_s for row in best])
        axes[1].errorbar(
            time_s,
            np.degrees(unwrapped_rad),
            yerr=[row.phase_sigma_deg for row in best],
            fmt="o",
            color="tab:blue",
            label="minimum-increment 180° branch",
        )
        axes[1].plot(
            time_s,
            np.degrees(predicted_rad),
            "--",
            color="tab:orange",
            label=(
                f"conditional slope {metrics['conditional_modulo_pi_slope_deg_s']:+.2f} "
                f"± {metrics['conditional_slope_standard_error_deg_s']:.2f} deg/s"
            ),
        )
        axes[1].legend(loc="best")
        axes[1].text(
            0.01,
            0.03,
            (
                f"RMS {metrics['unweighted_residual_rms_deg']:.1f}°; "
                f"reduced χ² {metrics['reduced_chi_square']:.1f}; "
                f"permutation p={metrics['phase_permutation_p']:.3f}"
            ),
            transform=axes[1].transAxes,
            fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.8"},
        )
        axes[2].plot(
            time_s,
            [row.receiver_offset_hz / 1e3 for row in best],
            "o-",
            color="tab:green",
            label="selected receiver-offset branch",
        )
    axes[0].set_ylabel("wrapped DD phase mod 180°")
    axes[0].set_ylim(-100, 100)
    axes[0].set_title("Measured RX1−RX0 two-signal double difference; 180° ambiguity unresolved")
    axes[1].set_ylabel("conditional phase branch (deg)")
    axes[1].set_title("Line fit is descriptive; phase continuity across retunes is not established")
    axes[2].set_ylabel("receiver offset (kHz)")
    axes[2].set_xlabel("seconds from capture origin")
    axes[2].legend(loc="best")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.suptitle(f"{document['session_id']} — bounded 10 ms saved-IQ follow-up")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.input.read_text())
    result = summarize(document)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    render(document, result, args.png)


if __name__ == "__main__":
    main()
