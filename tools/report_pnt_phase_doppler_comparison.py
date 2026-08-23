#!/usr/bin/env python3
# ruff: noqa: E501
"""Compare PNT-style phase/Doppler tracking with GLRT on one recorded dwell.

This is a research report generator.  It uses one prompt phase and one local
frequency discriminator per actual Starlink frame, but fits only a degree-one
Doppler trajectory.  Phase-reference failures are explicit reset events.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.robust_linear import fit_huber_linear_irls
from leo.analysis.starlink.phase_doppler import (
    CarrierFrameObservation,
    ConstantRatePhaseDopplerTrack,
    estimate_frame_carrier_observations,
    fit_constant_rate_phase_doppler,
)
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260822T143020-c4482829e26c"
STREAM_ID = "stream-0"
RECEIVER_ID = 1
SCOPE_ID = "sha256:424ec0775d22b40bd7f84ab693a65c412f5675c2c1aba6a4e3e89bf9342ba9ba"
PROBE_SECONDS = 0.020
SYMBOLS = np.arange(2, 66)
PHASE_GATE_CYCLES = 0.10


@dataclass(frozen=True, slots=True)
class Candidate:
    sample_start: int
    time_s: float
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class Segment:
    label: str
    start_s: float
    end_s: float
    reference_s: float
    rate_hz_s: float
    cfo_at_reference_hz: float

    def frequency_hz(self, time_s: float | np.ndarray) -> np.ndarray:
        values = np.asarray(time_s, dtype=float)
        return self.cfo_at_reference_hz + self.rate_hz_s * (values - self.reference_s)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        default=Path(
            "reports/figures/2026_08_22_within_segment_frame_phase/"
            "within-segment-frame-phase-metrics.json"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_within_segment_frame_phase/candidates"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_pnt_phase_doppler_comparison"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_22_pnt_phase_doppler_comparison.md"),
    )
    return parser.parse_args()


def _segments(path: Path) -> tuple[Segment, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    output = []
    for item in document["segments"]:
        first_probe = item["probes"][0]
        cfo_at_reference = (
            float(first_probe["tracking_cfo_hz"])
            - float(first_probe["line_error_hz"])
            + float(item["rate_hz_s"])
            * (float(item["interval_s"][0]) - float(first_probe["time_s"]))
        )
        output.append(
            Segment(
                label=str(item["label"]),
                start_s=float(item["interval_s"][0]),
                end_s=float(item["interval_s"][1]),
                reference_s=float(item["interval_s"][0]),
                rate_hz_s=float(item["rate_hz_s"]),
                cfo_at_reference_hz=cfo_at_reference,
            )
        )
    return tuple(output)


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
                    exact_score=float(item["exact_score"]),
                    control_score=float(item["control_score"]),
                    margin=float(item["margin"]),
                )
            )
    return tuple(sorted(output, key=lambda item: (item.sample_start, item.rank)))


def _select_candidates(
    segment: Segment,
    candidates: tuple[Candidate, ...],
    *,
    maximum_line_error_hz: float = 2_500.0,
    minimum_margin: float = 0.05,
) -> tuple[Candidate, ...]:
    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.sample_start, []).append(candidate)
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
        if (
            abs(winner.tracking_cfo_hz - expected) <= maximum_line_error_hz
            and winner.margin >= minimum_margin
        ):
            selected.append(winner)
    return tuple(sorted(selected, key=lambda item: item.sample_start))


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _extract_observations(
    reader,
    segment: Segment,
    candidates: tuple[Candidate, ...],
    acquisition_fit,
):
    probe_samples = round(PROBE_SECONDS * reader.sample_rate_hz)
    by_second: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_second.setdefault(int(candidate.time_s), []).append(candidate)
    output = []
    for second in sorted(by_second):
        rows = by_second[second]
        outer_start = min(item.sample_start for item in rows)
        outer_stop = max(item.sample_start for item in rows) + probe_samples
        outer = _complex_receiver(
            reader.read(
                outer_start,
                outer_stop - outer_start,
                receiver_ids=(RECEIVER_ID,),
            )
        )
        for candidate in rows:
            local_start = candidate.sample_start - outer_start
            samples = np.ascontiguousarray(outer[local_start : local_start + probe_samples])
            nco_frequency_hz = (
                acquisition_fit.intercept_at_reference_hz
                + acquisition_fit.slope_hz_per_s
                * (candidate.time_s - acquisition_fit.reference_time_s)
            )
            workspace = _conditioned_correlation_workspace(
                samples,
                reader.sample_rate_hz,
                candidate.local_epoch_sample,
                nco_frequency_hz,
                edge=StarlinkEdge.LOWER,
                selected_symbols=SYMBOLS,
            )
            exact = workspace.select(SYMBOLS)
            control = workspace.select(SYMBOLS, control=True)
            observations = estimate_frame_carrier_observations(
                exact.values,
                control.values,
                exact.normalized_power,
                control.normalized_power,
                exact.times_s,
                nco_frequency_hz=nco_frequency_hz,
                absolute_time_offset_s=candidate.time_s,
                container_id=candidate.sample_start,
            )
            output.extend(
                item for item in observations if segment.start_s <= item.time_s <= segment.end_s
            )
    return tuple(sorted(output, key=lambda item: item.time_s))


def _robust_glrt_fit(candidates: tuple[Candidate, ...]):
    times = np.asarray([item.time_s for item in candidates], dtype=float)
    values = np.asarray([item.tracking_cfo_hz for item in candidates], dtype=float)
    reference = float(np.median(times))
    initial = np.polyfit(times - reference, values, 1)
    return fit_huber_linear_irls(
        times,
        values,
        initial_coefficients_hz=(float(initial[0]), float(initial[1])),
        reference_time_s=reference,
        scale_floor_hz=25.0,
    )


def _transition_metrics(track: ConstantRatePhaseDopplerTrack) -> dict[str, Any]:
    maximum_gap = track.maximum_continuous_gap_s

    def summarize(same_container: bool) -> dict[str, Any]:
        selected = [
            item
            for item in track.transitions
            if item.same_container is same_container and item.gap_s <= maximum_gap
        ]
        innovations = np.asarray([item.innovation_cycles for item in selected], dtype=float)
        accepted = np.asarray([item.accepted_continuity for item in selected], dtype=bool)
        eighth = np.asarray([item.eighth_cycle_error for item in selected], dtype=float)
        return {
            "count": len(selected),
            "median_absolute_innovation_cycles": float(np.median(np.abs(innovations)))
            if len(selected)
            else None,
            "p90_absolute_innovation_cycles": float(np.quantile(np.abs(innovations), 0.9))
            if len(selected)
            else None,
            "accepted_fraction": float(np.mean(accepted)) if len(selected) else None,
            "rejected_near_eighth_fraction": float(np.mean(eighth[~accepted] <= 0.03))
            if np.any(~accepted)
            else None,
        }

    episodes: dict[int, list[CarrierFrameObservation]] = {}
    for observation, episode in zip(track.observations, track.episode_ids, strict=True):
        episodes.setdefault(episode, []).append(observation)
    durations = [
        rows[-1].time_s - rows[0].time_s + 1.0 / FRAME_RATE_HZ for rows in episodes.values()
    ]
    return {
        "within_container": summarize(True),
        "cross_container": summarize(False),
        "episode_count": len(episodes),
        "longest_episode_s": max(durations) if durations else 0.0,
        "median_episode_s": float(np.median(durations)) if durations else 0.0,
    }


def _paired_phase_comparison(
    exact: ConstantRatePhaseDopplerTrack,
    control: ConstantRatePhaseDopplerTrack,
) -> dict[str, Any]:
    output = {}
    for label, same_container in (("within_container", True), ("cross_container", False)):
        paired = [
            (leading, trailing)
            for leading, trailing in zip(exact.transitions, control.transitions, strict=True)
            if leading.same_container is same_container
            and leading.gap_s <= exact.maximum_continuous_gap_s
        ]
        exact_pass = np.asarray([left.accepted_continuity for left, _ in paired], dtype=bool)
        control_pass = np.asarray([right.accepted_continuity for _, right in paired], dtype=bool)
        exact_only = int(np.count_nonzero(exact_pass & ~control_pass))
        control_only = int(np.count_nonzero(~exact_pass & control_pass))
        discordant = exact_only + control_only
        if discordant:
            smaller = min(exact_only, control_only)
            tail = sum(math.comb(discordant, index) for index in range(smaller + 1)) / 2**discordant
            paired_p = min(1.0, 2.0 * tail)
        else:
            paired_p = 1.0
        output[label] = {
            "count": len(paired),
            "exact_minus_control_pass_fraction": float(np.mean(exact_pass) - np.mean(control_pass))
            if len(paired)
            else None,
            "exact_only_count": exact_only,
            "control_only_count": control_only,
            "mcnemar_exact_two_sided_p": paired_p,
            "four_segment_bonferroni_p": min(1.0, 4.0 * paired_p),
        }
    return output


def _segment_result(
    segment: Segment,
    candidates: tuple[Candidate, ...],
    observations: tuple[CarrierFrameObservation, ...],
) -> tuple[dict[str, Any], ConstantRatePhaseDopplerTrack, ConstantRatePhaseDopplerTrack]:
    exact = fit_constant_rate_phase_doppler(
        observations,
        initial_doppler_rate_hz_s=segment.rate_hz_s,
        phase_gate_cycles=PHASE_GATE_CYCLES,
    )
    control = fit_constant_rate_phase_doppler(
        observations,
        phase_channel="control",
        initial_doppler_rate_hz_s=segment.rate_hz_s,
        phase_gate_cycles=PHASE_GATE_CYCLES,
    )
    glrt = _robust_glrt_fit(candidates)
    exact_frequency = np.asarray([item.doppler_hz for item in observations])
    exact_time = np.asarray([item.time_s for item in observations])
    exact_residual = exact_frequency - exact.doppler_hz(exact_time)
    glrt_time = np.asarray([item.time_s for item in candidates])
    glrt_frequency = np.asarray([item.tracking_cfo_hz for item in candidates])
    glrt_predicted = glrt.intercept_at_reference_hz + glrt.slope_hz_per_s * (
        glrt_time - glrt.reference_time_s
    )
    acquisition_at_frames = glrt.intercept_at_reference_hz + glrt.slope_hz_per_s * (
        exact_time - glrt.reference_time_s
    )
    discriminator_residual = exact_frequency - acquisition_at_frames
    return (
        {
            "label": segment.label,
            "interval_s": [segment.start_s, segment.end_s],
            "frozen_glrt_rate_hz_s": segment.rate_hz_s,
            "robust_glrt_rate_hz_s": glrt.slope_hz_per_s,
            "pnt_frame_rate_hz_s": exact.doppler_fit.slope_hz_per_s,
            "pnt_minus_frozen_rate_hz_s": exact.doppler_fit.slope_hz_per_s - segment.rate_hz_s,
            "selected_glrt_probe_count": len(candidates),
            "pnt_frame_observation_count": len(observations),
            "nominal_observation_rate_hz": len(observations) / (segment.end_s - segment.start_s),
            "glrt_frequency_median_absolute_residual_hz": float(
                np.median(np.abs(glrt_frequency - glrt_predicted))
            ),
            "pnt_frequency_median_absolute_residual_hz": float(np.median(np.abs(exact_residual))),
            "pnt_frequency_p90_absolute_residual_hz": float(
                np.quantile(np.abs(exact_residual), 0.9)
            ),
            "pnt_discriminator_edge_fraction": float(
                np.mean(np.abs(discriminator_residual) >= 975.0)
            ),
            "exact_phase": _transition_metrics(exact),
            "control_phase": _transition_metrics(control),
            "phase_comparison": _paired_phase_comparison(exact, control),
        },
        exact,
        control,
    )


def _plot_overview(
    segments: tuple[Segment, ...],
    candidates: dict[str, tuple[Candidate, ...]],
    tracks: dict[str, ConstantRatePhaseDopplerTrack],
    controls: dict[str, ConstantRatePhaseDopplerTrack],
    output: Path,
) -> None:
    figure, axes = plt.subplots(len(segments), 2, figsize=(15.5, 12.2), sharey="col")
    all_frequency_residual = []
    for segment in segments:
        track = tracks[segment.label]
        times = np.asarray([item.time_s for item in track.observations])
        residual = np.asarray(
            [item.doppler_hz for item in track.observations]
        ) - segment.frequency_hz(times)
        all_frequency_residual.extend(residual)
    frequency_limit = max(500.0, float(np.quantile(np.abs(all_frequency_residual), 0.99))) / 1_000.0
    frequency_limit = min(1.5, 1.1 * frequency_limit)
    for row, segment in enumerate(segments):
        frequency_axis, phase_axis = axes[row]
        track = tracks[segment.label]
        control = controls[segment.label]
        observations = track.observations
        times = np.asarray([item.time_s for item in observations])
        elapsed = times - segment.start_s
        frame_residual = np.asarray(
            [item.doppler_hz for item in observations]
        ) - segment.frequency_hz(times)
        glrt = candidates[segment.label]
        glrt_times = np.asarray([item.time_s for item in glrt])
        glrt_residual = np.asarray([item.tracking_cfo_hz for item in glrt]) - segment.frequency_hz(
            glrt_times
        )
        frequency_axis.scatter(
            elapsed,
            frame_residual / 1_000.0,
            s=2.0,
            alpha=0.28,
            color="#2a6f97",
            label="actual-frame frequency discriminator",
        )
        frequency_axis.scatter(
            glrt_times - segment.start_s,
            glrt_residual / 1_000.0,
            s=9.0,
            facecolors="none",
            edgecolors="#e17c05",
            linewidths=0.55,
            label="20 ms GLRT CFO",
        )
        pnt_residual = track.doppler_hz(times) - segment.frequency_hz(times)
        frequency_axis.plot(
            elapsed,
            pnt_residual / 1_000.0,
            color="#111111",
            linewidth=1.0,
            label="PNT-style robust degree-1 Doppler",
        )
        frequency_axis.axhline(
            0.0, color="#777777", linewidth=0.7, linestyle="--", label="frozen GLRT degree-1 line"
        )
        frequency_axis.set_ylim(-frequency_limit, frequency_limit)
        frequency_axis.set_ylabel(f"{segment.label}\nresidual (kHz)")
        frequency_axis.grid(alpha=0.18)

        for selected, color, marker, label in (
            (track, "#b23a48", ".", "exact-pilot phase innovation"),
            (control, "#8d99ae", "x", "rolled-pilot control"),
        ):
            transition_times = np.asarray(
                [item.stop_time_s - segment.start_s for item in selected.transitions]
            )
            innovation = np.asarray([item.innovation_cycles for item in selected.transitions])
            phase_axis.scatter(
                transition_times,
                innovation,
                s=5.0,
                alpha=0.35,
                color=color,
                marker=marker,
                label=label,
            )
        phase_axis.axhspan(
            -PHASE_GATE_CYCLES,
            PHASE_GATE_CYCLES,
            color="#4c956c",
            alpha=0.10,
            label="continuity gate",
        )
        phase_axis.set_ylim(-0.52, 0.52)
        phase_axis.grid(alpha=0.18)
        phase_axis.set_ylabel(f"{segment.label}\ninnovation (cycles)")
    axes[0, 0].set_title("A · actual-frame frequency discriminator vs GLRT CFO", loc="left")
    axes[0, 1].set_title(
        "B · one-step carrier-phase prediction from integrated Doppler", loc="left"
    )
    axes[-1, 0].set_xlabel("time from segment start (s)")
    axes[-1, 1].set_xlabel("time from segment start (s)")
    for column in range(2):
        handles, labels = axes[0, column].get_legend_handles_labels()
        axes[0, column].legend(handles, labels, loc="upper right", fontsize=8)
    figure.suptitle(
        "PNT-style phase + constant-Doppler-rate tracking · recorded Starlink edge-pilot example",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _plot_phase_summary(results: list[dict[str, Any]], output: Path) -> None:
    labels = [item["label"] for item in results]
    x = np.arange(len(labels), dtype=float)
    figure, axes = plt.subplots(1, 2, figsize=(13.2, 5.3))
    for offset, key, title, color in (
        (-0.18, "exact_phase", "exact Qin pilot", "#b23a48"),
        (0.18, "control_phase", "rolled-pilot control", "#8d99ae"),
    ):
        within = [item[key]["within_container"]["accepted_fraction"] or 0.0 for item in results]
        cross = [item[key]["cross_container"]["accepted_fraction"] or 0.0 for item in results]
        axes[0].bar(
            x + offset, within, 0.34, color=color, alpha=0.85 if offset < 0 else 0.55, label=title
        )
        axes[1].bar(
            x + offset, cross, 0.34, color=color, alpha=0.85 if offset < 0 else 0.55, label=title
        )
    for axis, title in zip(
        axes,
        (
            "A · adjacent actual frames inside a 20 ms container",
            "B · adjacent actual frames across container boundaries",
        ),
        strict=True,
    ):
        axis.set_title(title, loc="left")
        axis.set_xticks(x, labels)
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("fraction within ±0.10 cycle prediction gate")
        axis.grid(axis="y", alpha=0.2)
        axis.legend(loc="upper right")
    figure.suptitle(
        "Does integrated Doppler predict the next carrier phase?", fontsize=14, fontweight="bold"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _write_observations(path: Path, tracks: dict[str, ConstantRatePhaseDopplerTrack]) -> None:
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8") as output,
    ):
        output.write(
            json.dumps(
                {
                    "kind": "metadata",
                    "schema": "org.leo.research.pnt-phase-doppler-observations/v1",
                    "session_id": SESSION_ID,
                },
                sort_keys=True,
            )
            + "\n"
        )
        for label in sorted(tracks):
            for item in tracks[label].observations:
                output.write(
                    json.dumps(
                        {"kind": "observation", "segment": label, **asdict(item)}, sort_keys=True
                    )
                    + "\n"
                )
    path.write_bytes(buffer.getvalue())


def _report(path: Path, results: list[dict[str, Any]]) -> None:
    lines = [
        "# PNT-style carrier phase + Doppler tracking versus the GLRT pipeline",
        "",
        "## Bottom line",
        "",
        "This research implementation successfully produces one prompt carrier-phase and local frequency observation per actual ~1.33 ms Starlink frame, then fits **only one linear Doppler trajectory (constant Doppler rate)**. It does not assume phase continuity: integrated Doppler must predict each next phase within ±0.10 cycle, or the transition is labeled as an explicit phase-reference reset.",
        "",
        "The comparison therefore separates two questions that the current GLRT pipeline combines poorly: (1) can the known pilot provide a stable frequency discriminator, and (2) is its carrier phase continuous enough to integrate? The first can remain useful even when the second fails.",
        "",
        "![PNT-style tracking overview](figures/2026_08_22_pnt_phase_doppler_comparison/pnt-phase-doppler-overview.png)",
        "",
        "## What the papers actually motivate",
        "",
        "Kozhaya, Saroufim, and Kassas acquire a Starlink beacon in delay/Doppler, then track beat carrier phase, Doppler, Doppler rate, code phase, and code rate in a Kalman loop. Their prompt/early/late correlators provide phase, frequency, and timing innovations. Crucially, their paper also reports OFDM user clusters with distinct power and phase references and π/4 or π/2 carrier-phase jumps. Qin et al. independently caution that coherent processing beyond one full frame is complicated by inter-frame carrier-phase discontinuities.",
        "",
        "Our experiment is deliberately narrower: the local replica is the published Qin lower edge pilot (symbols 2–65) in a 2.5 MHz recording, not Kassas's blindly estimated full-OFDM beacon. We implement the same carrier-state logic but omit code tracking and positioning. That makes this a **PNT-style edge-pilot tracker**, not a reproduction of the paper's receiver.",
        "",
        "## Step by step: input, estimator, and output",
        "",
        "1. Start from the same independently scored dense GLRT candidates and the same frozen P1/P2/P4/P5 degree-one associations used by the within-segment report.",
        "2. For every selected 20 ms container, correlate each actual Starlink frame separately against the exact Qin pilot and a symbol-rolled control.",
        "3. Fit one robust degree-one acquisition line to the selected GLRT CFOs. Evaluate that single line at each container start, then run a ±1 kHz, 25 Hz prompt-frequency discriminator independently in every actual frame. The per-probe GLRT winner CFO is **not** used to refresh this NCO. Restore the local NCO phase at the raw sample-clock midpoint so phases from different containers have a common mathematical reference.",
        "4. Robustly fit frequency versus time with MAD-scaled Huber IRLS. The model is `f(t)=f_ref+f_dot(t-t_ref)` and nothing higher order.",
        "5. Integrate that linear frequency between adjacent frames. The phase prediction is quadratic only because it is the integral of constant Doppler rate; no curved frequency model is present.",
        "6. Compare predicted and measured wrapped phase increments. Errors beyond ±0.10 cycle, or gaps beyond 2.25 frame periods, start a new explicit phase episode.",
        "",
        "The output is a robust constant-rate Doppler line, per-frame discriminator observations, one-step phase innovations, and explicit continuity episodes/reset events. Phase never silently changes the Doppler curvature.",
        "",
        "## Quantitative comparison",
        "",
        "| Segment | Frozen GLRT rate | Robust GLRT rate | PNT per-frame rate | PNT−frozen | GLRT / PNT freq MAD | ±1 kHz edge hits | PNT frame updates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['label']} | {item['frozen_glrt_rate_hz_s']:.1f} Hz/s | {item['robust_glrt_rate_hz_s']:.1f} Hz/s | {item['pnt_frame_rate_hz_s']:.1f} Hz/s | {item['pnt_minus_frozen_rate_hz_s']:+.1f} Hz/s | {item['glrt_frequency_median_absolute_residual_hz']:.1f} / {item['pnt_frequency_median_absolute_residual_hz']:.1f} Hz | {100.0 * item['pnt_discriminator_edge_fraction']:.1f}% | {item['pnt_frame_observation_count']} ({item['nominal_observation_rate_hz']:.0f}/s) |"
        )
    lines.extend(
        [
            "",
            "The per-frame discriminator trades precision per observation for a much higher update rate. Its residual MAD must therefore be read together with the robust line and phase-consistency tests; it is not expected to beat a 20 ms coherent GLRT estimate frame by frame. An edge hit means the local maximum landed in the outermost 25 Hz of the ±1 kHz bank. A high fraction is an explicit loss-of-lock/insufficient-pilot warning, not a trustworthy ±1 kHz measurement.",
            "",
            "## Phase continuity result",
            "",
            "![Phase prediction acceptance](figures/2026_08_22_pnt_phase_doppler_comparison/phase-continuity-summary.png)",
            "",
            "| Segment | Within-container exact/control pass | Cross-container exact/control pass | Cross pass advantage / corrected p | Exact cross-boundary median error | Explicit episodes / longest |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in results:
        exact = item["exact_phase"]
        control = item["control_phase"]
        within_exact = exact["within_container"]["accepted_fraction"]
        within_control = control["within_container"]["accepted_fraction"]
        cross_exact = exact["cross_container"]["accepted_fraction"]
        cross_control = control["cross_container"]["accepted_fraction"]
        cross_error = exact["cross_container"]["median_absolute_innovation_cycles"]
        comparison = item["phase_comparison"]["cross_container"]
        lines.append(
            f"| {item['label']} | {_percent(within_exact)} / {_percent(within_control)} | {_percent(cross_exact)} / {_percent(cross_control)} | {_signed_percent(comparison['exact_minus_control_pass_fraction'])} / {_number(comparison['four_segment_bonferroni_p'], 4)} | {_number(cross_error, 3)} cycles | {exact['episode_count']} / {exact['longest_episode_s'] * 1_000:.1f} ms |"
        )
    lines.extend(
        [
            "",
            "The earlier report showed that some frame-to-frame phase increments repeat locally. This stronger test asks whether those increments equal the physical phase advance predicted by Doppler. A pass rate near the rolled-pilot control means that local correlation is not sufficient for carrier-phase integration. The paired two-sided McNemar p-value compares exact and control decisions on identical transitions; the table applies a four-segment Bonferroni correction.",
            "",
            "The episode count is intentionally strict and should not be mistaken for a satellite count. A new episode can be caused by a different transmitting user/beam phase reference, a selected GLRT basin belonging to another source, a missed container, or a real carrier cycle slip.",
            "",
            "Across this dwell, the PNT-style frequency lines agree with the frozen GLRT rates to within about 13 Hz/s, but their individual ~1.33 ms estimates are noisier than 20 ms GLRT CFOs. That agreement is a tracking-consistency result, not an independent acquisition result: frame epoch and the initial degree-one NCO still come from GLRT. Carrier phase does **not** remain continuously integrable for seconds. P2 and P5 show the most exact-over-control phase advantage, yet the longest strict episode is only tens of milliseconds.",
            "",
            "## Comparison with the two existing analyses",
            "",
            "| Analysis | Unit and observable | Uses neighboring data during acquisition? | Frequency model | What it can establish |",
            "|---|---|---|---|---|",
            "| Current dense GLRT | One independent 20 ms container; maximized known-pilot CFO/epoch | No | Candidate inventory, then robust degree-one association | Pilot-like energy and a CFO line; no carrier-phase continuity |",
            "| Within-segment actual-frame report | ~15 independently phase-estimated actual frames inside each selected container | No cross-container use | One constant container CFO; frozen degree-one line only for association/display | Local frame-phase correlation and held-out prediction inside containers |",
            "| This PNT-style tracker | One prompt phase + frequency discriminator per actual frame, with sample-clock phase restoration | GLRT supplies acquisition; tracking comparison occurs afterward | One robust degree-one Doppler line; integrated phase checked separately | Whether frequency tracking survives and exactly where carrier phase can/cannot bridge |",
            "",
            "### Exact relationship to the deployed GLRT lanes",
            "",
            "| Setting | Production Standard | Production Research | This offline comparison |",
            "|---|---:|---:|---:|",
            "| 20 ms probes per complete second | 40 | 60 | 50 back-to-back |",
            "| Retained/scored timing-CFO basins | 10 | 32 | 32 |",
            "| Coarse CFO step | 80 kHz | 10 kHz | 10 kHz |",
            "| Fine CFO radius / step | 80 kHz / 500 Hz | 10 kHz / 100 Hz | 10 kHz / 100 Hz |",
            "| GLRT transform | 512 | 4096 | 4096 |",
            "| Actual-frame phase/frequency output | none | none | prompt discriminator + reset audit |",
            "",
            "Thus the acquisition evidence in this report is Research-like but not a byte-for-byte production Research schedule: it uses back-to-back 20 ms windows created for the frozen segment study. The new estimator itself is reusable and isolated from either production lane.",
            "",
            "## What this does not yet claim",
            "",
            "- It does not identify a Starlink satellite or improve the TLE association by itself.",
            "- It does not decode payload, user, beam, or satellite identity.",
            "- It does not implement Kassas's blind full-beacon estimator, code loop, or positioning WNLS.",
            "- It does not prove that all CFO-aligned GLRT containers belong to one transmitter.",
            "- It does not use quadratic/cubic Doppler estimates. A quadratic phase expression is only the exact integral of a linear Doppler shift.",
            "",
            "## Pipeline recommendation",
            "",
            "Keep this tracker in Research. Persist the per-frame frequency/phase innovations and phase-reset audit beside dense GLRT candidates. Do not gate Standard detections on carrier continuity yet: the papers predict legitimate OFDM phase-reference changes, and the edge pilot may be less phase-stable than the paper's full beacon. Promotion should require repeatable cross-container phase acceptance above the rolled-pilot control on multiple dwells, plus source association that also respects frame epoch/timing.",
            "",
            "The most valuable next extension is a multi-hypothesis delay/CFO tracker that chooses among dense GLRT basins using both predicted frame epoch and Doppler before phase is examined. That would test whether current CFO-only association is switching sources and would add the code/timing half of the PNT receiver state without changing the constant-rate Doppler constraint.",
            "",
            "## Reproducibility",
            "",
            "- Generator: `tools/report_pnt_phase_doppler_comparison.py`.",
            "- Reusable estimator: `src/leo/analysis/starlink/phase_doppler.py`.",
            "- Metrics: `figures/2026_08_22_pnt_phase_doppler_comparison/pnt-phase-doppler-metrics.json`.",
            "- Compact observations: `pnt-phase-doppler-observations.jsonl.gz`.",
            "- Recording, dense candidate artifacts, and frozen segments are identical to the within-segment actual-frame report.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{100.0 * value:.1f}%"


def _number(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _signed_percent(value: float | None) -> str:
    return "—" if value is None else f"{100.0 * value:+.1f} pp"


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    segments = _segments(args.baseline_metrics)
    selected: dict[str, tuple[Candidate, ...]] = {}
    observations: dict[str, tuple[CarrierFrameObservation, ...]] = {}
    tracks: dict[str, ConstantRatePhaseDopplerTrack] = {}
    controls: dict[str, ConstantRatePhaseDopplerTrack] = {}
    results = []
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        reader = store.reader(bundle, STREAM_ID, verify=True)
        for segment in segments:
            candidates = _load_candidates(
                args.candidate_root
                / segment.label.lower()
                / "dense-independent-glrt-candidates.jsonl.gz"
            )
            chosen = _select_candidates(segment, candidates)
            acquisition_fit = _robust_glrt_fit(chosen)
            frame_observations = _extract_observations(reader, segment, chosen, acquisition_fit)
            result, track, control = _segment_result(segment, chosen, frame_observations)
            selected[segment.label] = chosen
            observations[segment.label] = frame_observations
            tracks[segment.label] = track
            controls[segment.label] = control
            results.append(result)
    finally:
        store.close()

    metrics = {
        "schema": "org.leo.research.pnt-phase-doppler-comparison/v1",
        "recording": {
            "session_id": SESSION_ID,
            "stream_id": STREAM_ID,
            "receiver_id": RECEIVER_ID,
            "scope_id": SCOPE_ID,
        },
        "method": {
            "pilot": "Qin lower edge, symbols 2..65",
            "frequency_model": "degree one only (constant Doppler rate)",
            "phase_model": "integral of degree-one frequency; explicit reset on failed innovation",
            "residual_frequency_span_hz": 1_000.0,
            "residual_frequency_step_hz": 25.0,
            "carrier_nco": "one robust degree-one GLRT acquisition line; no per-probe CFO refresh",
            "phase_gate_cycles": PHASE_GATE_CYCLES,
            "maximum_continuous_gap_s": 2.25 / FRAME_RATE_HZ,
        },
        "segments": results,
    }
    (args.output_root / "pnt-phase-doppler-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_observations(args.output_root / "pnt-phase-doppler-observations.jsonl.gz", tracks)
    _plot_overview(
        segments,
        selected,
        tracks,
        controls,
        args.output_root / "pnt-phase-doppler-overview.png",
    )
    _plot_phase_summary(results, args.output_root / "phase-continuity-summary.png")
    _report(args.report, results)


if __name__ == "__main__":
    main()
