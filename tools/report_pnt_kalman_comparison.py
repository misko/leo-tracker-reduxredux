#!/usr/bin/env python3
# ruff: noqa: E501
"""Replay and report the five-state PNT Kalman model on one recorded dwell."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.phase_doppler import CarrierFrameObservation
from leo.analysis.starlink.pnt_kalman import (
    CodePhaseObservation,
    PntKalmanConfig,
    PntKalmanResult,
    replay_pnt_kalman,
)

SESSION_ID = "cap-20260822T143020-c4482829e26c"
STREAM_ID = "stream-0"
RECEIVER_ID = 1
SAMPLE_RATE_HZ = 2_500_000
FRAME_PERIOD_S = 1.0 / 750.0
PHASE_GATES = (0.03, 0.05, 0.10, 0.20)


@dataclass(frozen=True, slots=True)
class Segment:
    label: str
    start_s: float
    end_s: float
    reference_s: float
    frozen_rate_hz_s: float
    cfo_at_reference_hz: float
    batch_rate_hz_s: float

    def frequency_hz(self, time_s: float | np.ndarray) -> np.ndarray:
        values = np.asarray(time_s, dtype=float)
        return self.cfo_at_reference_hz + self.frozen_rate_hz_s * (
            values - self.reference_s
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    sample_start: int
    time_s: float
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    margin: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--within-metrics",
        type=Path,
        default=Path(
            "reports/figures/2026_08_22_within_segment_frame_phase/"
            "within-segment-frame-phase-metrics.json"
        ),
    )
    parser.add_argument(
        "--batch-metrics",
        type=Path,
        default=Path(
            "reports/figures/2026_08_22_pnt_phase_doppler_comparison/"
            "pnt-phase-doppler-metrics.json"
        ),
    )
    parser.add_argument(
        "--carrier-observations",
        type=Path,
        default=Path(
            "reports/figures/2026_08_22_pnt_phase_doppler_comparison/"
            "pnt-phase-doppler-observations.jsonl.gz"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path(
            "reports/figures/2026_08_22_within_segment_frame_phase/candidates"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_pnt_kalman_comparison"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_22_pnt_kalman_comparison.md"),
    )
    return parser.parse_args()


def _segments(within_path: Path, batch_path: Path) -> tuple[Segment, ...]:
    within = json.loads(within_path.read_text(encoding="utf-8"))
    batch = {
        item["label"]: item
        for item in json.loads(batch_path.read_text(encoding="utf-8"))["segments"]
    }
    output = []
    for item in within["segments"]:
        first = item["probes"][0]
        reference = float(item["interval_s"][0])
        rate = float(item["rate_hz_s"])
        cfo_at_reference = (
            float(first["tracking_cfo_hz"])
            - float(first["line_error_hz"])
            + rate * (reference - float(first["time_s"]))
        )
        output.append(
            Segment(
                label=str(item["label"]),
                start_s=reference,
                end_s=float(item["interval_s"][1]),
                reference_s=reference,
                frozen_rate_hz_s=rate,
                cfo_at_reference_hz=cfo_at_reference,
                batch_rate_hz_s=float(batch[item["label"]]["pnt_frame_rate_hz_s"]),
            )
        )
    return tuple(output)


def _carrier_observations(
    path: Path, labels: tuple[str, ...]
) -> dict[str, tuple[CarrierFrameObservation, ...]]:
    grouped: dict[str, list[CarrierFrameObservation]] = {label: [] for label in labels}
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            if item.get("kind") != "observation":
                continue
            label = str(item.pop("segment"))
            item.pop("kind")
            grouped[label].append(CarrierFrameObservation(**item))
    return {
        label: tuple(sorted(rows, key=lambda item: item.time_s))
        for label, rows in grouped.items()
    }


def _load_candidates(path: Path) -> tuple[Candidate, ...]:
    output = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            output.append(
                Candidate(
                    sample_start=int(item["sample_start"]),
                    time_s=float(item["time_s"]),
                    rank=int(item["rank"]),
                    local_epoch_sample=int(item["local_epoch_sample"]),
                    tracking_cfo_hz=float(item["tracking_cfo_hz"]),
                    margin=float(item["margin"]),
                )
            )
    return tuple(sorted(output, key=lambda item: (item.sample_start, item.rank)))


def _select_candidates(
    segment: Segment,
    candidates: tuple[Candidate, ...],
) -> tuple[Candidate, ...]:
    grouped: dict[int, list[Candidate]] = {}
    for item in candidates:
        grouped.setdefault(item.sample_start, []).append(item)
    selected = []
    for rows in grouped.values():
        expected = float(segment.frequency_hz(rows[0].time_s))
        winner = min(
            rows,
            key=lambda item: (
                abs(item.tracking_cfo_hz - expected),
                -item.margin,
                item.rank,
            ),
        )
        if abs(winner.tracking_cfo_hz - expected) <= 2_500.0 and winner.margin >= 0.05:
            selected.append(winner)
    return tuple(sorted(selected, key=lambda item: item.sample_start))


def _code_observations(candidates: tuple[Candidate, ...]) -> tuple[CodePhaseObservation, ...]:
    return tuple(
        CodePhaseObservation(
            time_s=item.time_s,
            code_phase_s=(
                (item.sample_start + item.local_epoch_sample) / SAMPLE_RATE_HZ
            )
            % FRAME_PERIOD_S,
            container_id=item.sample_start,
        )
        for item in candidates
    )


def _longest_run(times: np.ndarray, accepted: np.ndarray, maximum_gap_s: float) -> float:
    longest = 0.0
    start: float | None = None
    previous: float | None = None
    for time_s, is_accepted in zip(times, accepted, strict=True):
        if (
            not is_accepted
            or (previous is not None and time_s - previous > maximum_gap_s)
        ):
            if start is not None and previous is not None:
                longest = max(longest, previous - start + maximum_gap_s)
            start = None
        if is_accepted and start is None:
            start = float(time_s)
        previous = float(time_s)
    if start is not None and previous is not None:
        longest = max(longest, previous - start + maximum_gap_s)
    return longest


def _paired_phase_p(exact: PntKalmanResult, control: PntKalmanResult) -> float:
    left = np.asarray([item.phase_accepted for item in exact.carrier_steps], dtype=bool)
    right = np.asarray([item.phase_accepted for item in control.carrier_steps], dtype=bool)
    exact_only = int(np.count_nonzero(left & ~right))
    control_only = int(np.count_nonzero(~left & right))
    total = exact_only + control_only
    if not total:
        return 1.0
    smaller = min(exact_only, control_only)
    tail = sum(math.comb(total, index) for index in range(smaller + 1)) / 2**total
    return min(1.0, 2.0 * tail)


def _summary(
    segment: Segment,
    exact: PntKalmanResult,
    control: PntKalmanResult,
    frequency_only: PntKalmanResult,
    sensitivity: dict[str, float],
) -> dict[str, Any]:
    carrier = exact.carrier_steps
    control_carrier = control.carrier_steps
    code = exact.code_steps
    phase_times = np.asarray([item.time_s for item in carrier])
    phase_accepted = np.asarray([item.phase_accepted for item in carrier])
    code_times = np.asarray([item.time_s for item in code])
    code_accepted = np.asarray([item.code_accepted for item in code])
    return {
        "label": segment.label,
        "interval_s": [segment.start_s, segment.end_s],
        "frozen_glrt_rate_hz_s": segment.frozen_rate_hz_s,
        "batch_pnt_rate_hz_s": segment.batch_rate_hz_s,
        "kalman_full_rate_hz_s": exact.final_state[2],
        "kalman_frequency_only_rate_hz_s": frequency_only.final_state[2],
        "control_phase_kalman_rate_hz_s": control.final_state[2],
        "full_minus_frozen_rate_hz_s": exact.final_state[2] - segment.frozen_rate_hz_s,
        "frequency_only_minus_frozen_rate_hz_s": frequency_only.final_state[2] - segment.frozen_rate_hz_s,
        "batch_minus_frozen_rate_hz_s": segment.batch_rate_hz_s - segment.frozen_rate_hz_s,
        "carrier_observation_count": len(carrier),
        "doppler_accepted_fraction": float(np.mean([item.doppler_accepted for item in carrier])),
        "phase_accepted_fraction": float(np.mean(phase_accepted)),
        "phase_control_accepted_fraction": float(np.mean([item.phase_accepted for item in control_carrier])),
        "phase_reset_count": int(sum(item.phase_reset for item in carrier)),
        "phase_longest_accepted_run_s": _longest_run(
            phase_times, phase_accepted, 2.25 * FRAME_PERIOD_S
        ),
        "phase_exact_vs_control_p": _paired_phase_p(exact, control),
        "phase_four_segment_bonferroni_p": min(1.0, 4.0 * _paired_phase_p(exact, control)),
        "code_observation_count": len(code),
        "code_accepted_fraction": float(np.mean(code_accepted)),
        "code_reset_count": int(sum(item.code_reset for item in code)),
        "code_longest_accepted_run_s": _longest_run(
            code_times, code_accepted, 0.021
        ),
        "code_median_absolute_innovation_us": float(
            np.median([abs(item.code_innovation_s) for item in code]) * 1e6
        ),
        "final_code_rate_ppm": exact.final_state[4] * 1e6,
        "phase_gate_sensitivity_rate_error_hz_s": sensitivity,
    }


def _plot_overview(
    segments: tuple[Segment, ...],
    exact: dict[str, PntKalmanResult],
    control: dict[str, PntKalmanResult],
    frequency_only: dict[str, PntKalmanResult],
    output: Path,
) -> None:
    figure, axes = plt.subplots(len(segments), 3, figsize=(17.0, 13.2), sharey="col")
    rate_residuals = []
    for segment in segments:
        rate_residuals.extend(
            item.filtered_doppler_rate_hz_s - segment.frozen_rate_hz_s
            for item in exact[segment.label].carrier_steps
        )
    rate_limit = min(1_500.0, max(350.0, 1.1 * float(np.quantile(np.abs(rate_residuals), 0.995))))
    for row, segment in enumerate(segments):
        rate_axis, phase_axis, code_axis = axes[row]
        full = exact[segment.label]
        null = control[segment.label]
        frequency = frequency_only[segment.label]
        carrier = full.carrier_steps
        elapsed = np.asarray([item.time_s - segment.start_s for item in carrier])
        rate = np.asarray([item.filtered_doppler_rate_hz_s for item in carrier])
        rate_axis.plot(elapsed, rate - segment.frozen_rate_hz_s, color="#b23a48", linewidth=0.8, label="full five-state KF")
        rate_axis.axhline(frequency.final_state[2] - segment.frozen_rate_hz_s, color="#2a6f97", linewidth=1.0, label="frequency-only KF final")
        rate_axis.axhline(segment.batch_rate_hz_s - segment.frozen_rate_hz_s, color="#111111", linewidth=0.9, linestyle="--", label="robust batch final")
        rate_axis.axhline(0.0, color="#888888", linewidth=0.6, linestyle=":", label="frozen GLRT")
        rate_axis.set_ylim(-rate_limit, rate_limit)
        rate_axis.set_ylabel(f"{segment.label}\nrate residual (Hz/s)")
        rate_axis.grid(alpha=0.18)

        for result, color, marker, label in (
            (full, "#b23a48", ".", "exact-pilot KF innovation"),
            (null, "#8d99ae", "x", "rolled-pilot control KF"),
        ):
            times = np.asarray([item.time_s - segment.start_s for item in result.carrier_steps])
            innovation = np.asarray([item.phase_innovation_cycles for item in result.carrier_steps])
            phase_axis.scatter(times, innovation, s=4.0, alpha=0.30, color=color, marker=marker, label=label)
        phase_axis.axhspan(-0.10, 0.10, color="#4c956c", alpha=0.10, label="±0.10-cycle update gate")
        phase_axis.set_ylim(-0.52, 0.52)
        phase_axis.set_ylabel(f"{segment.label}\nphase innovation (cycles)")
        phase_axis.grid(alpha=0.18)

        code_steps = full.code_steps
        code_time = np.asarray([item.time_s - segment.start_s for item in code_steps])
        code_innovation = np.asarray([item.code_innovation_s * 1e6 for item in code_steps])
        reset = np.asarray([item.code_reset for item in code_steps], dtype=bool)
        code_axis.scatter(code_time[~reset], code_innovation[~reset], s=8.0, color="#2a6f97", alpha=0.55, label="accepted code innovation")
        code_axis.scatter(code_time[reset], code_innovation[reset], s=18.0, marker="x", color="#d1495b", linewidths=0.8, label="explicit code reset")
        code_axis.axhspan(-50.0, 50.0, color="#4c956c", alpha=0.10, label="±50 µs hard gate")
        code_axis.set_ylim(-700.0, 700.0)
        code_axis.set_ylabel(f"{segment.label}\ncode innovation (µs)")
        code_axis.grid(alpha=0.18)
    axes[0, 0].set_title("A · causal Doppler-rate state", loc="left")
    axes[0, 1].set_title("B · wrapped carrier-phase update", loc="left")
    axes[0, 2].set_title("C · modulo-frame code-phase update", loc="left")
    for axis in axes[-1]:
        axis.set_xlabel("time from segment start (s)")
    for column in range(3):
        handles, labels = axes[0, column].get_legend_handles_labels()
        axes[0, column].legend(handles, labels, fontsize=7.5, loc="upper right")
    figure.suptitle("Five-state PNT Kalman measurement replay · constant Doppler/code rates", fontsize=15, fontweight="bold")
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _plot_summary(results: list[dict[str, Any]], output: Path) -> None:
    labels = [item["label"] for item in results]
    x = np.arange(len(labels), dtype=float)
    figure, axes = plt.subplots(1, 2, figsize=(13.8, 5.3))
    for offset, key, label, color in (
        (-0.24, "batch_minus_frozen_rate_hz_s", "robust batch", "#111111"),
        (0.0, "full_minus_frozen_rate_hz_s", "full five-state KF", "#b23a48"),
        (0.24, "frequency_only_minus_frozen_rate_hz_s", "frequency-only KF", "#2a6f97"),
    ):
        axes[0].bar(x + offset, [abs(item[key]) for item in results], 0.22, color=color, label=label)
    axes[0].set_yscale("log")
    axes[0].set_ylim(0.5, 2_000.0)
    axes[0].set_ylabel("absolute rate difference from frozen GLRT (Hz/s)")
    axes[0].set_title("A · phase feedback can corrupt the rate state", loc="left")
    axes[0].set_xticks(x, labels)
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].legend(fontsize=8)

    width = 0.25
    axes[1].bar(x - width, [item["phase_accepted_fraction"] for item in results], width, color="#b23a48", label="carrier phase exact")
    axes[1].bar(x, [item["phase_control_accepted_fraction"] for item in results], width, color="#8d99ae", label="carrier phase control")
    axes[1].bar(x + width, [item["code_accepted_fraction"] for item in results], width, color="#2a6f97", label="code phase")
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_ylabel("accepted innovation fraction")
    axes[1].set_title("B · most carrier-phase updates fail; code repeatedly resets", loc="left")
    axes[1].set_xticks(x, labels)
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _plot_sensitivity(results: list[dict[str, Any]], output: Path) -> None:
    figure, axis = plt.subplots(figsize=(10.8, 5.6))
    for item, color in zip(results, ("#355070", "#6d597a", "#b56576", "#e56b6f"), strict=True):
        values = item["phase_gate_sensitivity_rate_error_hz_s"]
        gates = np.asarray([float(key) for key in values])
        errors = np.asarray([values[f"{gate:.2f}"] for gate in gates])
        axis.plot(gates, errors, marker="o", linewidth=1.4, color=color, label=item["label"])
    axis.axhline(0.0, color="#777777", linewidth=0.7, linestyle="--")
    axis.set_xticks(PHASE_GATES)
    axis.set_xlabel("absolute wrapped phase gate (cycles)")
    axis.set_ylabel("final KF Doppler-rate error from frozen GLRT (Hz/s)")
    axis.set_title("Carrier-loop result is highly sensitive to the phase innovation gate", loc="left")
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _report(path: Path, results: list[dict[str, Any]]) -> None:
    lines = [
        "# Five-state PNT Kalman replay on the recorded Starlink dwell",
        "",
        "## Answer",
        "",
        "Yes: the paper's five-state carrier/code model is now implemented and replayed over P1/P2/P4/P5. The result is highly informative, but it does **not** support enabling carrier-phase feedback in the pipeline yet.",
        "",
        "With phase updates enabled, the causal filter's final Doppler-rate error reaches hundreds of Hz/s in P1 and P4 and depends strongly on the phase gate. With the identical transition, frequency observations, and initialization—but carrier phase prevented from updating Doppler—the final rates remain within about 5 Hz/s of the frozen GLRT lines. Code phase is locally precise when accepted, but roughly one fifth to one quarter of independently acquired container epochs require explicit code-reference resets.",
        "",
        "![Five-state Kalman overview](figures/2026_08_22_pnt_kalman_comparison/pnt-kalman-overview.png)",
        "",
        "## The implemented state and transition",
        "",
        "The state uses cycles rather than radians, but is otherwise the unit-scaled paper model:",
        "",
        "`x = [carrier phase φ, Doppler f_D, Doppler rate f_dot_D, code phase τ, code rate τ_dot]`",
        "",
        "For elapsed time `dt`:",
        "",
        "```text",
        "φ'       = φ + f_D·dt + 0.5·f_dot_D·dt²",
        "f_D'     = f_D + f_dot_D·dt",
        "f_dot_D' = f_dot_D",
        "τ'       = τ + τ_dot·dt",
        "τ_dot'   = τ_dot",
        "```",
        "",
        "There is no Doppler-rate or code-rate process noise in this experiment. They are constant physical states. The quadratic term is carrier phase—the exact integral of a linear frequency—not a quadratic Doppler fit. The PNT paper manually tunes process and measurement noise; this first implementation intentionally freezes both rate states so that it tests measurement compatibility without relaxing our constant-Doppler-rate constraint.",
        "",
        "## Measurements and robust reset policy",
        "",
        "- Carrier phase and Doppler come from the previously persisted actual-frame Qin edge-pilot prompt observations.",
        "- Code phase comes from each dense GLRT candidate's global frame epoch modulo the 1/750-second Starlink frame period.",
        "- Carrier innovations are wrapped into ±0.5 cycle and gated at ±0.10 cycle.",
        "- Code innovations are wrapped into ±0.667 ms and have a ±50 µs hard gate.",
        "- Doppler innovations have coherence-aware noise and a ±975 Hz hard gate.",
        "- A rejected carrier/code observation explicitly resets only that reference. A carrier reset cannot directly alter Doppler/rate; a code reset cannot alter the carrier block.",
        "- Exact and rolled-pilot control filters receive identical Doppler and code observations. Only their carrier-phase measurement differs.",
        "",
        "This is an **offline Kalman measurement replay**. It does not yet drive the next raw-IQ carrier and code wipe-off. Frame epoch and the initial Doppler-rate state still come from dense GLRT, making the comparison controlled and exposing whether feedback would help or hurt.",
        "",
        "## Doppler-rate comparison",
        "",
        "![Kalman comparison summary](figures/2026_08_22_pnt_kalman_comparison/pnt-kalman-summary.png)",
        "",
        "| Segment | Frozen GLRT | Robust batch PNT | Full five-state KF | Frequency-only KF | Full / frequency-only error | Doppler updates accepted |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['label']} | {item['frozen_glrt_rate_hz_s']:.1f} | {item['batch_pnt_rate_hz_s']:.1f} | {item['kalman_full_rate_hz_s']:.1f} | {item['kalman_frequency_only_rate_hz_s']:.1f} | {item['full_minus_frozen_rate_hz_s']:+.1f} / {item['frequency_only_minus_frozen_rate_hz_s']:+.1f} Hz/s | {100.0 * item['doppler_accepted_fraction']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "The frequency-only result is the clean ablation. It is not a different detector: it uses the same five-state transition and the same per-frame Doppler measurements, but phase observations are diagnostic only. Its stability shows that the Doppler discriminator and constant-rate state are compatible. The degradation in the full filter is introduced specifically when the presently discontinuous carrier phase is allowed to update the correlated Doppler/rate covariance.",
            "",
            "## Carrier and code continuity",
            "",
            "| Segment | Carrier exact/control accepted | Carrier resets | Longest accepted carrier run | Corrected exact-vs-control p | Code accepted / resets | Longest accepted code run | Final code rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in results:
        lines.append(
            f"| {item['label']} | {100.0 * item['phase_accepted_fraction']:.1f}% / {100.0 * item['phase_control_accepted_fraction']:.1f}% | {item['phase_reset_count']} | {1_000.0 * item['phase_longest_accepted_run_s']:.1f} ms | {item['phase_four_segment_bonferroni_p']:.4g} | {100.0 * item['code_accepted_fraction']:.1f}% / {item['code_reset_count']} | {item['code_longest_accepted_run_s']:.3f} s | {item['final_code_rate_ppm']:+.2f} ppm |"
        )
    lines.extend(
        [
            "",
            "Carrier exact-pilot acceptance can exceed the rolled control, especially in P1/P5, so real local phase structure exists. But the accepted subset is not a safe orbital carrier innovation: allowing it into the filter materially worsens the Doppler-rate estimate. This reconciles the earlier report with the new result—repeatable phase increments can be real without representing one continuously integrable carrier.",
            "",
            "Accepted code innovations have sub-microsecond median residuals, but the repeated resets are disqualifying for a continuous code bridge. They are consistent with GLRT epoch switching among timing basins/sources or genuine Starlink frame/code changes. Because these are reacquired GLRT epochs rather than a prompt early-minus-late code discriminator, they are evidence for the next timing tracker, not yet a pseudorange observable.",
            "",
            "## Phase-gate sensitivity",
            "",
            "![Phase-gate sensitivity](figures/2026_08_22_pnt_kalman_comparison/phase-gate-sensitivity.png)",
            "",
            "A valid carrier loop should not change its inferred orbital Doppler rate by roughly 1 kHz/s because the phase gate moved from 0.10 to 0.20 cycle. This sensitivity is direct evidence of phase-reference mixture/cycle ambiguity. Selecting a narrow gate that happens to agree with GLRT would be post-hoc tuning, not validation.",
            "",
            "## Comparison with what we had before",
            "",
            "| Method | State propagation | Carrier phase feeds Doppler? | Code state? | Result on this dwell |",
            "|---|---|---|---|---|",
            "| Dense GLRT + robust line | Independent 20 ms acquisitions followed by a batch degree-one line | No | No | Most precise and stable Doppler-rate baseline |",
            "| Previous PNT-style batch audit | Per-frame discriminator; robust degree-one frequency fit; integrate Doppler and audit phase | No | No | Rates agree within ~13 Hz/s; no seconds-long carrier phase |",
            "| Frequency-only Kalman ablation | Causal five-state transition; Doppler updates only in carrier block | No | Present but disabled | Rates agree within ~5 Hz/s |",
            "| Full five-state Kalman replay | Causal carrier/code propagation and wrapped innovations | Yes | Yes | Phase feedback destabilizes P1/P4; code repeatedly resets |",
            "",
            "## Recommendation",
            "",
            "1. Keep GLRT plus robust degree-one Doppler as the production observable.",
            "2. Add the five-state replay only to Research artifacts, initially with phase feedback disabled and all innovations persisted.",
            "3. Build the missing multi-hypothesis timing tracker: select the next dense basin using predicted frame epoch **and** Doppler before measuring carrier phase.",
            "4. Cluster phase references (the paper reports user-dependent π/4 and π/2 offsets) and require a stable cluster identity before enabling phase updates.",
            "5. Replace reacquired GLRT epoch measurements with a genuine prompt early/late code discriminator before interpreting code rate or pseudorange.",
            "6. Enable full phase feedback only after held-out dwells show that it improves—not merely matches—the Doppler-only Kalman control without gate-sensitive bias.",
            "",
            "## Reproducibility",
            "",
            "- Five-state implementation: `src/leo/analysis/starlink/pnt_kalman.py`.",
            "- Generator: `tools/report_pnt_kalman_comparison.py`.",
            "- Metrics: `figures/2026_08_22_pnt_kalman_comparison/pnt-kalman-metrics.json`.",
            "- Histories: `pnt-kalman-histories.json.gz`.",
            "- Inputs are the same frozen P1/P2/P4/P5 candidates and actual-frame observations as the two preceding phase reports.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_histories(path: Path, results: dict[str, PntKalmanResult]) -> None:
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8") as output,
    ):
        json.dump(
            {
                label: {
                    "carrier_steps": [asdict(item) for item in result.carrier_steps],
                    "code_steps": [asdict(item) for item in result.code_steps],
                    "final_state": result.final_state,
                    "final_covariance": result.final_covariance,
                }
                for label, result in sorted(results.items())
            },
            output,
            sort_keys=True,
            separators=(",", ":"),
        )
    path.write_bytes(buffer.getvalue())


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    segments = _segments(args.within_metrics, args.batch_metrics)
    carriers = _carrier_observations(
        args.carrier_observations, tuple(item.label for item in segments)
    )
    exact: dict[str, PntKalmanResult] = {}
    control: dict[str, PntKalmanResult] = {}
    frequency_only: dict[str, PntKalmanResult] = {}
    summaries = []
    frequency_only_config = replace(
        PntKalmanConfig(),
        apply_phase_updates=False,
        apply_code_updates=False,
        reset_rejected_phase=False,
        reset_rejected_code=False,
    )
    for segment in segments:
        candidates = _select_candidates(
            segment,
            _load_candidates(
                args.candidate_root
                / segment.label.lower()
                / "dense-independent-glrt-candidates.jsonl.gz"
            ),
        )
        code = _code_observations(candidates)
        exact_result = replay_pnt_kalman(
            carriers[segment.label],
            code,
            initial_doppler_rate_hz_s=segment.frozen_rate_hz_s,
        )
        control_result = replay_pnt_kalman(
            carriers[segment.label],
            code,
            initial_doppler_rate_hz_s=segment.frozen_rate_hz_s,
            phase_channel="control",
        )
        frequency_result = replay_pnt_kalman(
            carriers[segment.label],
            code,
            initial_doppler_rate_hz_s=segment.frozen_rate_hz_s,
            config=frequency_only_config,
        )
        sensitivity = {}
        for gate in PHASE_GATES:
            result = replay_pnt_kalman(
                carriers[segment.label],
                code,
                initial_doppler_rate_hz_s=segment.frozen_rate_hz_s,
                config=replace(PntKalmanConfig(), phase_gate_cycles=gate),
            )
            sensitivity[f"{gate:.2f}"] = (
                result.final_state[2] - segment.frozen_rate_hz_s
            )
        exact[segment.label] = exact_result
        control[segment.label] = control_result
        frequency_only[segment.label] = frequency_result
        summaries.append(
            _summary(
                segment,
                exact_result,
                control_result,
                frequency_result,
                sensitivity,
            )
        )
    metrics = {
        "schema": "org.leo.research.pnt-kalman-comparison/v1",
        "recording": {
            "session_id": SESSION_ID,
            "stream_id": STREAM_ID,
            "receiver_id": RECEIVER_ID,
        },
        "state": [
            "carrier_phase_cycles",
            "doppler_hz",
            "doppler_rate_hz_s",
            "code_phase_s",
            "code_rate_s_s",
        ],
        "model": {
            "doppler_rate": "constant; zero process noise",
            "code_rate": "constant; zero process noise",
            "phase_gate_cycles": 0.10,
            "code_gate_us": 50.0,
            "measurement_replay_not_raw_iq_closed_loop": True,
        },
        "segments": summaries,
    }
    (args.output_root / "pnt-kalman-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_histories(args.output_root / "pnt-kalman-histories.json.gz", exact)
    _plot_overview(
        segments,
        exact,
        control,
        frequency_only,
        args.output_root / "pnt-kalman-overview.png",
    )
    _plot_summary(summaries, args.output_root / "pnt-kalman-summary.png")
    _plot_sensitivity(summaries, args.output_root / "phase-gate-sensitivity.png")
    _report(args.report, summaries)


if __name__ == "__main__":
    main()
