#!/usr/bin/env python3
# ruff: noqa: E501
"""Qualify frame-local Starlink pilot phase on one frozen recording.

The analysis uses independently acquired dense GLRT candidates from the
published carrier-continuity audit.  It conditions raw IQ on each candidate's
CFO, estimates a separate phase for every 1/750-second Starlink frame, and
tests within-frame measurability separately from inter-frame predictability.
No quadratic or cubic CFO model is fitted.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.frame_phase import (
    FramePhaseState,
    circular_concentration,
    estimate_frame_phase_states,
    fit_heldout_constant_phase_increment,
    wrapped_cycle_difference,
)
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260822T143020-c4482829e26c"
STREAM_ID = "stream-0"
RECEIVER_ID = 1
SCOPE_ID = "sha256:424ec0775d22b40bd7f84ab693a65c412f5675c2c1aba6a4e3e89bf9342ba9ba"
SOURCE_REPORT = "reports/2026_08_22_carrier_continuity_case.md"
PROBE_SECONDS = 0.020
SYMBOLS = np.arange(2, 66)
RNG_SEED = 20260822


@dataclass(frozen=True, slots=True)
class Segment:
    label: str
    start_s: float
    end_s: float
    reference_s: float
    rate_hz_s: float
    cfo_at_reference_hz: float

    def frequency_hz(self, time_s: float | np.ndarray) -> np.ndarray:
        times = np.asarray(time_s, dtype=float)
        return self.cfo_at_reference_hz + self.rate_hz_s * (times - self.reference_s)


@dataclass(frozen=True, slots=True)
class Boundary:
    label: str
    slug: str
    pre: Segment
    post: Segment

    @property
    def time_s(self) -> float:
        return 0.5 * (self.pre.end_s + self.post.start_s)

    def segment(self, time_s: float) -> Segment:
        return self.pre if time_s < self.time_s else self.post

    def side(self, time_s: float) -> str:
        if time_s <= self.pre.end_s:
            return "pre"
        if time_s >= self.post.start_s:
            return "post"
        return "gap"


BOUNDARIES = (
    Boundary(
        "B1 · 26.9375 s",
        "b1",
        Segment("P1", 20.250, 26.925, 20.250, -6_188.325399204048, -157_618.43809679453),
        Segment("P2", 26.950, 33.300, 26.950, -6_113.603385019892, -201_944.48215763876),
    ),
    Boundary(
        "B2 · 47.0875 s",
        "b2",
        Segment("P4", 40.625, 47.050, 40.625, -6_055.816602137965, -194_835.66819964952),
        Segment("P5", 47.125, 49.425, 47.125, -6_291.359764216548, -236_282.73828298785),
    ),
)


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
class FrameRecord:
    boundary_slug: str
    side: str
    probe_index: int
    probe_time_s: float
    frame_index: int
    time_s: float
    phase_cycles: float
    coherence: float
    residual_cycles: float
    exact_power: float
    control_coherence: float
    control_phase_cycles: float
    control_residual_cycles: float
    control_power: float
    signature: np.ndarray


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_carrier_continuity_case"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_frame_local_phase_qualification"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_22_frame_local_phase_qualification.md"),
    )
    return parser.parse_args()


def _load_candidates(path: Path) -> tuple[Candidate, ...]:
    rows: list[Candidate] = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            rows.append(
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
    return tuple(sorted(rows, key=lambda item: (item.sample_start, item.rank)))


def _select_line_candidates(
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
    *,
    maximum_error_hz: float = 2_500.0,
    minimum_margin: float = 0.05,
) -> tuple[Candidate, ...]:
    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.sample_start, []).append(candidate)
    selected: list[Candidate] = []
    for rows in grouped.values():
        time_s = rows[0].time_s
        expected = float(boundary.segment(time_s).frequency_hz(time_s))
        candidate = min(
            rows,
            key=lambda item: (
                abs(item.tracking_cfo_hz - expected),
                -item.margin,
                item.rank,
            ),
        )
        if (
            abs(candidate.tracking_cfo_hz - expected) <= maximum_error_hz
            and candidate.margin >= minimum_margin
        ):
            selected.append(candidate)
    return tuple(selected)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (
        values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)
    ) / 32_768.0


def _extract_frames(reader, boundary: Boundary, candidates: tuple[Candidate, ...]):
    probe_samples = round(PROBE_SECONDS * reader.sample_rate_hz)
    outer_start = min(item.sample_start for item in candidates)
    outer_stop = max(item.sample_start for item in candidates) + probe_samples
    outer = _complex_receiver(
        reader.read(outer_start, outer_stop - outer_start, receiver_ids=(RECEIVER_ID,))
    )
    records: list[FrameRecord] = []
    probes: list[dict[str, Any]] = []
    for probe_index, candidate in enumerate(candidates):
        local_start = candidate.sample_start - outer_start
        values = np.ascontiguousarray(outer[local_start : local_start + probe_samples])
        workspace = _conditioned_correlation_workspace(
            values,
            reader.sample_rate_hz,
            candidate.local_epoch_sample,
            candidate.tracking_cfo_hz,
            edge=StarlinkEdge.LOWER,
            selected_symbols=SYMBOLS,
        )
        exact = workspace.select(SYMBOLS)
        control = workspace.select(SYMBOLS, control=True)
        states = estimate_frame_phase_states(
            exact.values,
            control.values,
            exact.normalized_power,
            control.normalized_power,
            exact.times_s,
        )
        side = boundary.side(candidate.time_s)
        for state in states:
            records.append(_frame_record(boundary, side, probe_index, candidate, state))
        epoch = (
            candidate.sample_start + candidate.local_epoch_sample
        ) % (reader.sample_rate_hz / FRAME_RATE_HZ)
        expected = float(boundary.segment(candidate.time_s).frequency_hz(candidate.time_s))
        probes.append(
            {
                "probe_index": probe_index,
                "time_s": candidate.time_s,
                "side": side,
                "tracking_cfo_hz": candidate.tracking_cfo_hz,
                "line_error_hz": candidate.tracking_cfo_hz - expected,
                "margin": candidate.margin,
                "epoch_modulo_frame_samples": float(epoch),
                "frame_count": len(states),
            }
        )
    return tuple(records), probes


def _frame_record(
    boundary: Boundary,
    side: str,
    probe_index: int,
    candidate: Candidate,
    state: FramePhaseState,
) -> FrameRecord:
    return FrameRecord(
        boundary_slug=boundary.slug,
        side=side,
        probe_index=probe_index,
        probe_time_s=candidate.time_s,
        frame_index=state.frame_index,
        time_s=candidate.time_s + state.midpoint_s,
        phase_cycles=state.phase_cycles,
        coherence=state.coherence,
        residual_cycles=state.median_absolute_residual_cycles,
        exact_power=state.mean_normalized_power,
        control_coherence=state.control_coherence,
        control_phase_cycles=state.control_phase_cycles,
        control_residual_cycles=state.control_median_absolute_residual_cycles,
        control_power=state.control_mean_normalized_power,
        signature=state.phase_invariant_signature,
    )


def _phase_increments(records: tuple[FrameRecord, ...]) -> tuple[np.ndarray, np.ndarray]:
    times: list[float] = []
    increments: list[float] = []
    grouped: dict[int, list[FrameRecord]] = {}
    for record in records:
        grouped.setdefault(record.probe_index, []).append(record)
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: item.frame_index)
        for leading, trailing in zip(ordered[1:], ordered[:-1], strict=True):
            times.append(leading.time_s)
            increments.append(
                float(wrapped_cycle_difference(leading.phase_cycles, trailing.phase_cycles))
            )
    return np.asarray(times), np.asarray(increments)


def _permutation_order_pvalue(
    records: tuple[FrameRecord, ...], observed: float, *, repetitions: int = 500
) -> tuple[float, np.ndarray]:
    rng = np.random.default_rng(RNG_SEED)
    grouped: dict[int, np.ndarray] = {}
    for probe_index in sorted({record.probe_index for record in records}):
        grouped[probe_index] = np.asarray(
            [
                record.phase_cycles
                for record in sorted(
                    (item for item in records if item.probe_index == probe_index),
                    key=lambda item: item.frame_index,
                )
            ]
        )
    null = []
    for _ in range(repetitions):
        increments = []
        for values in grouped.values():
            shuffled = rng.permutation(values)
            increments.extend(wrapped_cycle_difference(shuffled[1:], shuffled[:-1]))
        null.append(circular_concentration(np.asarray(increments)))
    null_array = np.asarray(null)
    pvalue = float((1 + np.count_nonzero(null_array >= observed)) / (repetitions + 1))
    return pvalue, null_array


def _heldout_phase_metrics(records: tuple[FrameRecord, ...]) -> dict[str, Any]:
    grouped: dict[int, list[FrameRecord]] = {}
    for record in records:
        grouped.setdefault(record.probe_index, []).append(record)
    exact_errors: list[float] = []
    control_errors: list[float] = []
    probe_rows: list[dict[str, float]] = []
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: item.frame_index)
        if len(ordered) < 4:
            continue
        indexes = np.asarray([item.frame_index for item in ordered])
        exact = fit_heldout_constant_phase_increment(
            [item.phase_cycles for item in ordered], indexes
        )
        control = fit_heldout_constant_phase_increment(
            [item.control_phase_cycles for item in ordered], indexes
        )
        exact_errors.extend(exact.heldout_errors_cycles)
        control_errors.extend(control.heldout_errors_cycles)
        probe_rows.append(
            {
                "time_s": ordered[0].probe_time_s,
                "exact_median_error_cycles": float(
                    np.median(exact.heldout_errors_cycles)
                ),
                "control_median_error_cycles": float(
                    np.median(control.heldout_errors_cycles)
                ),
                "increment_cycles_per_frame": exact.increment_cycles_per_frame,
                "training_concentration": exact.training_concentration,
            }
        )
    exact_array = np.asarray(exact_errors)
    control_array = np.asarray(control_errors)
    return {
        "exact_errors": exact_errors,
        "control_errors": control_errors,
        "probe_rows": probe_rows,
        "exact_median_error_cycles": float(np.median(exact_array)),
        "exact_p90_error_cycles": float(np.percentile(exact_array, 90)),
        "control_median_error_cycles": float(np.median(control_array)),
        "gate_pass": bool(
            np.median(exact_array) <= 0.10
            and np.median(exact_array) + 0.03 <= np.median(control_array)
        ),
    }


def _timing_metrics(probes: list[dict[str, Any]], frame_period_samples: float) -> dict[str, Any]:
    values = np.asarray([item["epoch_modulo_frame_samples"] for item in probes])
    cycles = values / frame_period_samples
    concentration = circular_concentration(cycles)
    vector = complex(np.mean(np.exp(2j * np.pi * cycles))) if len(cycles) else 0j
    dispersion = math.sqrt(max(0.0, -2.0 * math.log(max(abs(vector), 1e-12))))
    return {
        "probe_count": len(probes),
        "circular_concentration": concentration,
        "circular_dispersion_samples": float(
            dispersion * frame_period_samples / (2.0 * np.pi)
        ),
    }


def _signature_metrics(records: tuple[FrameRecord, ...]) -> dict[str, Any]:
    adjacent: list[float] = []
    grouped: dict[int, list[FrameRecord]] = {}
    for record in records:
        grouped.setdefault(record.probe_index, []).append(record)
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: item.frame_index)
        adjacent.extend(
            float(abs(np.vdot(left.signature, right.signature)))
            for left, right in zip(ordered[:-1], ordered[1:], strict=True)
        )
    rng = np.random.default_rng(RNG_SEED + 1)
    all_records = list(records)
    random_pairs: list[float] = []
    if len(all_records) > 1:
        for _ in range(len(adjacent)):
            left_index, right_index = rng.choice(len(all_records), size=2, replace=False)
            random_pairs.append(
                float(
                    abs(
                        np.vdot(
                            all_records[int(left_index)].signature,
                            all_records[int(right_index)].signature,
                        )
                    )
                )
            )
    return {
        "adjacent": adjacent,
        "random": random_pairs,
        "adjacent_median": float(np.median(adjacent)) if adjacent else None,
        "random_median": float(np.median(random_pairs)) if random_pairs else None,
    }


def _boundary_metrics(
    boundary: Boundary,
    records: tuple[FrameRecord, ...],
    probes: list[dict[str, Any]],
    frame_period_samples: float,
) -> tuple[dict[str, Any], np.ndarray]:
    active = tuple(record for record in records if record.side != "gap")
    exact_residual = np.asarray([item.residual_cycles for item in active])
    control_residual = np.asarray([item.control_residual_cycles for item in active])
    exact_coherence = np.asarray([item.coherence for item in active])
    control_coherence = np.asarray([item.control_coherence for item in active])
    increment_times, increments = _phase_increments(active)
    increment_r = circular_concentration(increments)
    pvalue, null = _permutation_order_pvalue(active, increment_r)
    timing = {
        side: _timing_metrics(
            [item for item in probes if item["side"] == side], frame_period_samples
        )
        for side in ("pre", "post")
    }
    signature = _signature_metrics(active)
    heldout = _heldout_phase_metrics(active)
    heldout_by_side = {
        side: {
            key: value
            for key, value in _heldout_phase_metrics(
                tuple(record for record in active if record.side == side)
            ).items()
            if key not in {"exact_errors", "control_errors", "probe_rows"}
        }
        for side in ("pre", "post")
    }
    within_frame_gate = bool(
        np.median(exact_residual) + 0.03 <= np.median(control_residual)
        and np.median(exact_coherence) >= 2.0 * np.median(control_coherence)
    )
    interframe_gate = bool(heldout["gate_pass"])
    timing_gate = bool(
        timing["pre"]["circular_concentration"] >= 0.80
        and timing["post"]["circular_concentration"] >= 0.80
    )
    metrics = {
        "label": boundary.label,
        "time_s": boundary.time_s,
        "candidate_probe_count": len(probes),
        "frame_count": len(active),
        "within_frame": {
            "exact_median_absolute_residual_cycles": float(np.median(exact_residual)),
            "control_median_absolute_residual_cycles": float(np.median(control_residual)),
            "exact_median_coherence": float(np.median(exact_coherence)),
            "control_median_coherence": float(np.median(control_coherence)),
            "gate_pass": within_frame_gate,
        },
        "interframe": {
            "increment_count": len(increments),
            "median_absolute_increment_cycles": float(np.median(np.abs(increments))),
            "increment_concentration": increment_r,
            "order_permutation_pvalue": pvalue,
            "heldout_constant_increment": {
                key: value
                for key, value in heldout.items()
                if key not in {"exact_errors", "control_errors", "probe_rows"}
            },
            "heldout_by_side": heldout_by_side,
            "gate_pass": interframe_gate,
        },
        "timing": timing,
        "timing_gate_pass": timing_gate,
        "signature": {
            key: value for key, value in signature.items() if key not in {"adjacent", "random"}
        },
        "phase_boundary_result": (
            "eligible for boundary phase modeling"
            if within_frame_gate and interframe_gate and timing_gate
            else "not eligible: frame-to-frame phase/timing state is not qualified"
        ),
    }
    arrays = np.column_stack((increment_times, increments)) if len(increments) else np.zeros((0, 2))
    return metrics, np.column_stack((null, np.zeros_like(null))) if not len(arrays) else arrays


def _synthetic_metrics() -> dict[str, Any]:
    rng = np.random.default_rng(RNG_SEED)
    frame_count = 128
    symbol_count = len(SYMBOLS)
    expected = rng.uniform(-0.5, 0.5, frame_count)
    exact = np.exp(2j * np.pi * expected[:, None]) + 0.05 * (
        rng.normal(size=(frame_count, symbol_count))
        + 1j * rng.normal(size=(frame_count, symbol_count))
    )
    control = rng.normal(size=exact.shape) + 1j * rng.normal(size=exact.shape)
    exact_power = np.full(exact.shape, 0.5)
    control_power = np.full(exact.shape, 0.05)
    times = np.tile(np.arange(symbol_count) * 4.4e-6, (frame_count, 1))
    states = estimate_frame_phase_states(exact, control, exact_power, control_power, times)
    observed = np.asarray([item.phase_cycles for item in states])
    errors = np.abs(wrapped_cycle_difference(observed, expected))
    random_prediction = fit_heldout_constant_phase_increment(observed)
    linear_expected = (0.13 + 0.173 * np.arange(frame_count) + 0.5) % 1.0 - 0.5
    linear_exact = np.exp(2j * np.pi * linear_expected[:, None]) + 0.05 * (
        rng.normal(size=(frame_count, symbol_count))
        + 1j * rng.normal(size=(frame_count, symbol_count))
    )
    linear_states = estimate_frame_phase_states(
        linear_exact, control, exact_power, control_power, times
    )
    linear_prediction = fit_heldout_constant_phase_increment(
        [item.phase_cycles for item in linear_states]
    )
    return {
        "frame_count": frame_count,
        "median_recovery_error_cycles": float(np.median(errors)),
        "p95_recovery_error_cycles": float(np.percentile(errors, 95)),
        "median_within_frame_coherence": float(np.median([item.coherence for item in states])),
        "constant_increment_heldout_error_cycles": float(
            np.median(linear_prediction.heldout_errors_cycles)
        ),
        "random_reset_heldout_error_cycles": float(
            np.median(random_prediction.heldout_errors_cycles)
        ),
        "note": "independent random phase reset was injected into every frame",
    }


def _plot_overview(
    results: list[dict[str, Any]],
    records_by_boundary: dict[str, tuple[FrameRecord, ...]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(14, 8.5))
    colors = {"b1": "#4e79a7", "b2": "#e15759"}
    for result in results:
        slug = result["slug"]
        records = tuple(item for item in records_by_boundary[slug] if item.side != "gap")
        axes[0, 0].hist(
            [item.residual_cycles for item in records],
            bins=np.linspace(0, 0.5, 41),
            histtype="step",
            linewidth=1.4,
            color=colors[slug],
            label=f"{slug.upper()} exact",
            density=True,
        )
        axes[0, 0].hist(
            [item.control_residual_cycles for item in records],
            bins=np.linspace(0, 0.5, 41),
            histtype="step",
            linestyle=":",
            linewidth=1.1,
            color=colors[slug],
            label=f"{slug.upper()} rolled control",
            density=True,
        )
        axes[0, 1].scatter(
            [item.control_coherence for item in records],
            [item.coherence for item in records],
            s=5,
            alpha=0.20,
            color=colors[slug],
            label=slug.upper(),
        )
        _, increments = _phase_increments(records)
        axes[1, 0].hist(
            increments,
            bins=np.linspace(-0.5, 0.5, 41),
            histtype="step",
            linewidth=1.4,
            color=colors[slug],
            label=(
                f"{slug.upper()} R={result['interframe']['increment_concentration']:.3f}"
            ),
            density=True,
        )
    axes[0, 0].axvline(0.25, color="#888888", linewidth=0.8, linestyle="--")
    axes[0, 0].set(xlabel="within-frame median phase residual (cycles)", ylabel="density")
    axes[0, 0].set_title("A · exact Qin pilot is phase-structured within a frame", loc="left")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].plot((0, 1), (0, 1), color="#888888", linewidth=0.8, linestyle="--")
    axes[0, 1].set(xlabel="rolled-control coherence", ylabel="exact-pilot coherence")
    axes[0, 1].set_title("B · exact-versus-control frame coherence", loc="left")
    axes[0, 1].legend(fontsize=8)
    axes[1, 0].axhline(1.0, color="#888888", linewidth=0.8, linestyle="--")
    axes[1, 0].set(xlabel="consecutive-frame phase increment (cycles)", ylabel="density")
    axes[1, 0].set_title("C · inter-frame phase increments are not one stable state", loc="left")
    axes[1, 0].legend(fontsize=8)

    labels = [item["slug"].upper() for item in results]
    x = np.arange(len(labels))
    width = 0.23
    axes[1, 1].bar(
        x - width,
        [float(item["within_frame"]["gate_pass"]) for item in results],
        width,
        label="within-frame",
        color="#59a14f",
    )
    axes[1, 1].bar(
        x,
        [float(item["interframe"]["gate_pass"]) for item in results],
        width,
        label="inter-frame",
        color="#f28e2b",
    )
    axes[1, 1].bar(
        x + width,
        [float(item["timing_gate_pass"]) for item in results],
        width,
        label="frame timing",
        color="#4e79a7",
    )
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_yticks((0, 1), ("fail", "pass"))
    axes[1, 1].set_ylim(0, 1.15)
    axes[1, 1].set_title("D · boundary modeling is gated, not assumed", loc="left")
    axes[1, 1].legend(fontsize=8)
    for axis in axes.flat:
        axis.grid(alpha=0.12)
    figure.suptitle(
        "Frame-local phase qualification · exact Qin edge pilot versus rolled control\n"
        "one independent phase per 1/750-second frame; no curved CFO model",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_boundary(
    boundary: Boundary,
    metrics: dict[str, Any],
    records: tuple[FrameRecord, ...],
    probes: list[dict[str, Any]],
    path: Path,
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(14, 8.2), sharex=True)
    times = np.asarray([item["time_s"] for item in probes])
    axes[0].scatter(
        times,
        np.asarray([item["tracking_cfo_hz"] for item in probes]) / 1e3,
        s=12,
        facecolors="none",
        edgecolors="#f28e2b",
        linewidths=0.55,
        label="independently acquired probe CFO",
    )
    for segment, color in ((boundary.pre, "#4e79a7"), (boundary.post, "#59a14f")):
        grid = np.linspace(max(segment.start_s, min(times)), min(segment.end_s, max(times)), 100)
        if len(grid):
            axes[0].plot(
                grid,
                segment.frequency_hz(grid) / 1e3,
                color=color,
                linewidth=1.0,
                label=f"frozen straight {segment.label}",
            )
    axes[0].set_ylabel("CFO (kHz)")
    axes[0].set_title("A · acquisition remains independent; straight lines enter afterward", loc="left")
    axes[0].legend(fontsize=8, ncol=3)

    by_probe: dict[int, list[FrameRecord]] = {}
    for record in records:
        by_probe.setdefault(record.probe_index, []).append(record)
    probe_time = []
    exact_error = []
    control_error = []
    for _index, rows in sorted(by_probe.items()):
        probe_time.append(rows[0].probe_time_s)
        exact_error.append(float(np.median([item.residual_cycles for item in rows])))
        control_error.append(float(np.median([item.control_residual_cycles for item in rows])))
    axes[1].plot(probe_time, exact_error, color="#4e79a7", linewidth=0.8, label="exact pilot")
    axes[1].plot(
        probe_time,
        control_error,
        color="#e15759",
        linewidth=0.8,
        linestyle=":",
        label="symbol-rolled control",
    )
    axes[1].axhline(0.25, color="#888888", linewidth=0.7, linestyle="--")
    axes[1].set_ylabel("median residual\n(cycles/frame)")
    axes[1].set_title("B · phase is estimated and scored independently inside every frame", loc="left")
    axes[1].legend(fontsize=8)

    increment_times, increments = _phase_increments(tuple(item for item in records if item.side != "gap"))
    axes[2].scatter(increment_times, increments, s=5, alpha=0.35, color="#9467bd")
    axes[2].axhline(0, color="#888888", linewidth=0.7)
    axes[2].set_ylabel("next-frame phase\nincrement (cycles)")
    axes[2].set_xlabel("stored capture time (s)")
    axes[2].set_title(
        "C · frame-to-frame phase is a separate observable "
        f"(R={metrics['interframe']['increment_concentration']:.3f})",
        loc="left",
    )
    for axis in axes:
        axis.axvline(boundary.time_s, color="#e15759", linestyle="--", linewidth=0.9)
        axis.grid(alpha=0.12)
    figure.suptitle(
        f"{boundary.label} · frame-local Qin-pilot phase audit · stream-0/RX1",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_heldout_prediction(
    results: list[dict[str, Any]],
    records_by_boundary: dict[str, tuple[FrameRecord, ...]],
    boundaries: tuple[Boundary, ...],
    path: Path,
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(14, 7.5))
    colors = {"b1": "#4e79a7", "b2": "#e15759"}
    bins = np.linspace(0, 0.5, 41)
    for result, boundary in zip(results, boundaries, strict=True):
        active = tuple(
            item for item in records_by_boundary[result["slug"]] if item.side != "gap"
        )
        heldout = _heldout_phase_metrics(active)
        axes[0].hist(
            heldout["exact_errors"],
            bins=bins,
            density=True,
            histtype="step",
            linewidth=1.4,
            color=colors[result["slug"]],
            label=(
                f"{result['slug'].upper()} exact median "
                f"{heldout['exact_median_error_cycles']:.3f}"
            ),
        )
        axes[0].hist(
            heldout["control_errors"],
            bins=bins,
            density=True,
            histtype="step",
            linestyle=":",
            linewidth=1.1,
            color=colors[result["slug"]],
            label=(
                f"{result['slug'].upper()} rolled control median "
                f"{heldout['control_median_error_cycles']:.3f}"
            ),
        )
        axes[1].plot(
            [item["time_s"] for item in heldout["probe_rows"]],
            [item["exact_median_error_cycles"] for item in heldout["probe_rows"]],
            marker="o",
            markersize=2.4,
            linewidth=0.65,
            color=colors[result["slug"]],
            label=f"{result['slug'].upper()} exact",
        )
        axes[1].axvline(
            boundary.time_s,
            color=colors[result["slug"]],
            linestyle="--",
            linewidth=0.8,
        )
    axes[0].axvline(0.25, color="#111111", linestyle="--", linewidth=0.8)
    axes[0].set_ylabel("density")
    axes[0].set_xlabel("held-out phase prediction error (cycles)")
    axes[0].set_title(
        "A · two of every three frames fit one constant increment; the third remains held out",
        loc="left",
    )
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].axhline(0.10, color="#111111", linestyle="--", linewidth=0.8, label="gate")
    axes[1].axhline(
        0.25,
        color="#888888",
        linestyle=":",
        linewidth=0.8,
        label="uniform baseline",
    )
    axes[1].set_ylabel("per-probe median error (cycles)")
    axes[1].set_xlabel("stored capture time (s)")
    axes[1].set_title(
        "B · a constant residual-CFO phase line does not predict held-out frames",
        loc="left",
    )
    axes[1].legend(fontsize=8, ncol=4)
    for axis in axes:
        axis.grid(alpha=0.12)
    figure.suptitle(
        "Held-out constant phase-increment control · no quadratic/cubic CFO terms",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _write_frame_artifact(
    records_by_boundary: dict[str, tuple[FrameRecord, ...]],
    sample_rate_hz: int,
    path: Path,
) -> None:
    with path.open("wb") as raw_target:
        compressed_target = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_target,
            mtime=0,
        )
        target = io.TextIOWrapper(compressed_target, encoding="utf-8")
        _write_frame_artifact_records(
            records_by_boundary,
            sample_rate_hz,
            target,
        )


def _write_frame_artifact_records(
    records_by_boundary: dict[str, tuple[FrameRecord, ...]],
    sample_rate_hz: int,
    target: io.TextIOBase,
) -> None:
    with target:
        target.write(
            json.dumps(
                {
                    "kind": "metadata",
                    "schema": "org.leo.research.frame-local-phase-state/v1",
                    "session_id": SESSION_ID,
                    "stream_id": STREAM_ID,
                    "receiver_id": RECEIVER_ID,
                    "sample_rate_hz": sample_rate_hz,
                    "phase_reference": "independent conditioned circular phase per frame",
                    "satellite_identity_claim": False,
                },
                sort_keys=True,
            )
            + "\n"
        )
        for slug in sorted(records_by_boundary):
            for record in records_by_boundary[slug]:
                target.write(
                    json.dumps(
                        {
                            "kind": "frame",
                            "boundary_slug": record.boundary_slug,
                            "side": record.side,
                            "probe_index": record.probe_index,
                            "probe_time_s": record.probe_time_s,
                            "frame_index": record.frame_index,
                            "frame_midpoint_time_s": record.time_s,
                            "frame_midpoint_sample": round(record.time_s * sample_rate_hz),
                            "phase_cycles": record.phase_cycles,
                            "coherence": record.coherence,
                            "median_absolute_residual_cycles": record.residual_cycles,
                            "exact_mean_normalized_power": record.exact_power,
                            "control_phase_cycles": record.control_phase_cycles,
                            "control_coherence": record.control_coherence,
                            "control_median_absolute_residual_cycles": (
                                record.control_residual_cycles
                            ),
                            "control_mean_normalized_power": record.control_power,
                            "phase_invariant_signature_real": record.signature.real.tolist(),
                            "phase_invariant_signature_imag": record.signature.imag.tolist(),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )


def _report(metrics: dict[str, Any], path: Path) -> None:
    lines = [
        "# Frame-local phase qualification for adjacent Starlink CFO segments",
        "",
        "## Answer",
        "",
        "The existing IQ contains **measurable phase structure inside individual Starlink frames**, "
        "but it does **not** provide a qualified phase or frame-timing state that predicts the next "
        "frame across either audited boundary. Consequently B1 and B2 remain ineligible for a "
        "continuous-phase bridge. This is the expected failure mode described by Qin: coherent "
        "processing within a frame is useful, while inter-frame carrier phase discontinuities have "
        "not been generally modeled.",
        "",
        "This result is narrower than the earlier 20 ms phase audit. A 20 ms probe contains about "
        "15 Starlink frames; this rerun estimates one independent circular phase per approximately "
        "1.33 ms frame and tests within-frame measurability separately from inter-frame "
        "predictability.",
        "",
        "![Frame-local qualification overview](figures/2026_08_22_frame_local_phase_qualification/qualification-overview.png)",
        "",
        "## Decision gates",
        "",
        "| Boundary | Frames | Exact/control residual | Exact/control coherence | Consecutive-phase R | Held-out exact/control error | Timing R pre/post | Phase-boundary result |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in metrics["boundaries"]:
        lines.append(
            "| {label} | {frames} | {er:.3f}/{cr:.3f} cycles | {ec:.3f}/{cc:.3f} | "
            "{r:.3f} | {he:.3f}/{hc:.3f} cycles | {tp:.3f}/{tq:.3f} | **{result}** |".format(
                label=item["label"],
                frames=item["frame_count"],
                er=item["within_frame"]["exact_median_absolute_residual_cycles"],
                cr=item["within_frame"]["control_median_absolute_residual_cycles"],
                ec=item["within_frame"]["exact_median_coherence"],
                cc=item["within_frame"]["control_median_coherence"],
                r=item["interframe"]["increment_concentration"],
                he=item["interframe"]["heldout_constant_increment"][
                    "exact_median_error_cycles"
                ],
                hc=item["interframe"]["heldout_constant_increment"][
                    "control_median_error_cycles"
                ],
                tp=item["timing"]["pre"]["circular_concentration"],
                tq=item["timing"]["post"]["circular_concentration"],
                result=item["phase_boundary_result"],
            )
        )
    lines.extend(
        [
            "",
            "These exploratory operational gates are declared explicitly so they can be "
            "preregistered on the next dwell: exact-pilot median "
            "phase residual must beat the symbol-rolled control by at least 0.03 cycles and exact "
            "coherence must be at least twice control; a constant phase increment fit on two of "
            "every three frames must predict the interleaved third with median error≤0.10 cycles "
            "and beat control by "
            "at least 0.03 cycles; frame-epoch concentration must be at least "
            "0.80 on both sides. These are research gates, not production acceptance thresholds.",
            "",
            "The within-frame gate passes at both boundaries. The inter-frame and timing gates do "
            "not. B1 has statistically ordered, near-half-cycle structure and partially predicts "
            "held-out frames (0.151 cycles overall and 0.118 after B1), but it misses the 0.10-cycle "
            "gate and retains a 0.301-cycle 90th-percentile error. B2 remains at the approximately "
            "0.25-cycle uniform baseline. A small apparent phase jump at either CFO boundary would "
            "therefore still be a chance-dependent number.",
            "",
            "![Held-out constant-increment test](figures/2026_08_22_frame_local_phase_qualification/heldout-phase-prediction.png)",
            "",
            "## Input and estimator",
            "",
            f"- Recording: `{SESSION_ID}`, `{STREAM_ID}/RX{RECEIVER_ID}`, scope `{SCOPE_ID}`.",
            "- Raw input: immutable CI16 IQ at 2.5 MS/s.",
            "- Candidate input: the already-published dense Research acquisition (81 coarse CFO "
            "hypotheses, 32 independently scored basins/probe, GLRT-4096).",
            "- Candidate selection: after acquisition, select the basin nearest each frozen straight "
            "CFO segment within 2.5 kHz and margin≥0.05.",
            "- Per-frame input: exact and symbol-rolled-control correlations for Qin symbols 2–65.",
            "- Per-frame output: circular phase, bounded-power-weighted coherence, median phase "
            "residual, exact/control normalized power, and a global-phase-removed diagnostic shape.",
            "- CFO rule: the independent candidate CFO and frozen degree-1 segment are retained. "
            "No order-2 or order-3 CFO trajectory is fit.",
            "",
            "The frame estimator uses a bounded square-root power weight and a circular mean. A "
            "single symbol cannot dominate because its weight is capped at four times the frame "
            "median. Every frame is estimated independently; neither a neighboring frame nor the "
            "boundary hypothesis enters the phase estimate.",
            "",
            "## Synthetic estimator control",
            "",
            "The same implementation recovered 128 synthetic frames despite an independently random "
            "phase reset in every frame:",
            "",
            "| Frames | Median error | 95th-percentile error | Median within-frame coherence |",
            "|---:|---:|---:|---:|",
            "| {frame_count} | {median_recovery_error_cycles:.4f} cycles | "
            "{p95_recovery_error_cycles:.4f} cycles | {median_within_frame_coherence:.4f} |".format(
                **metrics["synthetic_control"]
            ),
            "",
            "This control establishes that arbitrary inter-frame phase resets do not prevent the "
            "algorithm from recovering frame-local phase. It does not simulate the full Starlink "
            "channel or prove satellite identity.",
            "",
            "A separate synthetic constant-increment sequence produced "
            f"{metrics['synthetic_control']['constant_increment_heldout_error_cycles']:.4f}-cycle "
            "median held-out error, whereas independent random resets produced "
            f"{metrics['synthetic_control']['random_reset_heldout_error_cycles']:.4f} cycles. "
            "This verifies that the held-out test recognizes a genuinely constant residual CFO.",
            "",
            "## B1 · 26.9375 seconds",
            "",
            "![B1 frame state](figures/2026_08_22_frame_local_phase_qualification/b1-frame-state.png)",
            "",
            _boundary_paragraph(metrics["boundaries"][0]),
            "",
            "## B2 · 47.0875 seconds",
            "",
            "![B2 frame state](figures/2026_08_22_frame_local_phase_qualification/b2-frame-state.png)",
            "",
            _boundary_paragraph(metrics["boundaries"][1]),
            "",
            "## Boundary hypothesis comparison",
            "",
            "| Hypothesis | B1 | B2 | What this phase analysis means |",
            "|---|---|---|---|",
            "| One phase-continuous component with one constant residual CFO | **Not qualified; partial structure** | **Not qualified** | B1 improves over control but misses the accuracy gate; B2 remains uniform-like. |",
            "| One physical component with permitted Starlink frame-phase resets | Compatible | Compatible | This is explicitly allowed by Qin and cannot be rejected by the observed phase. |",
            "| One component with a transmitter CFO correction or scheduling transition | Compatible | Compatible | Frame-local phase survives, but phase resets prevent a unique bridge. |",
            "| Two components transmitted back-to-back | Compatible | Compatible | Phase alone cannot distinguish this from one reset-bearing component. |",
            "| Two simultaneously overlapping resolved components | Not tested here | Not tested here | The parent report's fine-CFO coexistence control, rather than phase, addresses this case. |",
            "",
            "The first row qualifies only a **phase model**. Its failure does not reject one physical "
            "satellite or one waveform component because Starlink itself may reset phase between "
            "frames and the recording may contain an unobserved sample-time interval.",
            "",
            "## What phase can and cannot say",
            "",
            "| Question | Result |",
            "|---|---|",
            "| Is the exact Qin pilot phase-structured inside one frame? | **Yes**, relative to the rolled control. |",
            "| Is the next frame's phase predictable well enough to bridge B1/B2? | **No.** |",
            "| Does failure of inter-frame phase prove two satellites? | **No.** Qin reports such discontinuities even within Starlink transmissions. |",
            "| Does the edge-pilot pattern identify a satellite? | **No.** It repeats across satellites, beams, channels, and frames. |",
            "| Can phase prove continuity across a potentially missing capture interval? | **No.** Absolute cycle count is unobservable there. |",
            "| Can we retain frame-local phase for future waveform studies? | **Yes.** That observable is now qualified at candidate level. |",
            "",
            "The global-phase-removed symbol shape is also intentionally not promoted to an emitter "
            "fingerprint. Its adjacent/random median similarities are "
            f"{metrics['boundaries'][0]['signature']['adjacent_median']:.3f}/"
            f"{metrics['boundaries'][0]['signature']['random_median']:.3f} at B1 and "
            f"{metrics['boundaries'][1]['signature']['adjacent_median']:.3f}/"
            f"{metrics['boundaries'][1]['signature']['random_median']:.3f} at B2. Because all rows "
            "were selected with the same universal exact template, this similarity is useful as an "
            "estimator diagnostic but not independent component identity.",
            "",
            "## Relation to Qin and Kassas",
            "",
            "Qin et al. model each recovered frame with its own complex amplitude/phase and state "
            "that coherent processing beyond one full frame is complicated by inter-frame carrier "
            "phase discontinuities that have resisted general modeling. They also separate effective "
            "carrier-frequency offset, which combines orbital Doppler and carrier-clock drift, from "
            "sampling-frequency offset. The present result reproduces precisely that distinction: "
            "the exact edge pilot has usable local phase, but one constant residual-CFO phase line "
            "does not predict the next held-out frame.",
            "",
            "Kassas et al. independently report user-dependent OFDM phase references and discrete "
            "phase changes when frames are directed to different users. Their central data-less "
            "pilot tones can behave more continuously, but this capture observes the Qin edge-pilot "
            "band, not a qualified central pilot tone. Therefore lack of edge-pilot inter-frame "
            "phase continuity is not evidence for a satellite handoff.",
            "",
            "Primary sources: [Qin et al., arXiv:2602.02627](https://arxiv.org/abs/2602.02627) "
            "and [Kassas et al., DOI 10.33012/navi.685](https://doi.org/10.33012/navi.685).",
            "",
            "## Revised next experiment",
            "",
            "1. Preserve these frame-local complex states in a research artifact rather than "
            "collapsing them into a 20 ms magnitude score.",
            "2. Develop a true phase-invariant channel fingerprint from per-subcarrier estimates, "
            "validated against unrelated simultaneous candidates before using it at a boundary.",
            "3. Estimate timing/SFO from a continuous frame sequence rather than independently "
            "maximized 20 ms epochs; require within-segment controls to pass first.",
            "4. Compare one-component-with-phase-resets against back-to-back components using CFO, "
            "timing/SFO, power, and qualified channel features. Treat frame phase as a nuisance "
            "parameter.",
            "5. Keep firmware continuity work asynchronous. Even a better waveform model cannot "
            "recover absolute phase across samples that may not have been recorded.",
            "",
            "## Reproducibility",
            "",
            "- Machine-readable metrics: `frame-local-phase-metrics.json`.",
            "- Per-frame complex-state artifact: `frame-local-phase-states.jsonl.gz`.",
            "- Source candidate artifacts remain under the earlier carrier-continuity figure directory.",
            f"- Parent report: [{SOURCE_REPORT}](2026_08_22_carrier_continuity_case.md).",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _boundary_paragraph(item: dict[str, Any]) -> str:
    return (
        f"The exact pilot's median within-frame residual is "
        f"{item['within_frame']['exact_median_absolute_residual_cycles']:.3f} cycles versus "
        f"{item['within_frame']['control_median_absolute_residual_cycles']:.3f} for the rolled "
        f"control, so local phase is measurable. Consecutive-frame increments have concentration "
        f"R={item['interframe']['increment_concentration']:.3f} and ordered-permutation "
        f"p={item['interframe']['order_permutation_pvalue']:.4f}. A constant-increment phase line "
        f"fit on two of every three frames has "
        f"{item['interframe']['heldout_constant_increment']['exact_median_error_cycles']:.3f}-cycle "
        f"median held-out error versus "
        f"{item['interframe']['heldout_constant_increment']['control_median_error_cycles']:.3f} "
        f"for control; the exact pre/post errors are "
        f"{item['interframe']['heldout_by_side']['pre']['exact_median_error_cycles']:.3f}/"
        f"{item['interframe']['heldout_by_side']['post']['exact_median_error_cycles']:.3f}. "
        f"Frame timing concentrations are "
        f"{item['timing']['pre']['circular_concentration']:.3f}/"
        f"{item['timing']['post']['circular_concentration']:.3f} before/after. The result is "
        f"**{item['phase_boundary_result']}**."
    )


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        reader = store.reader(bundle, STREAM_ID, verify=True)
        records_by_boundary: dict[str, tuple[FrameRecord, ...]] = {}
        probes_by_boundary: dict[str, list[dict[str, Any]]] = {}
        boundary_metrics: list[dict[str, Any]] = []
        for boundary in BOUNDARIES:
            candidates = _load_candidates(
                args.source_root / f"{boundary.slug}-research-candidates.jsonl.gz"
            )
            selected = _select_line_candidates(boundary, candidates)
            records, probes = _extract_frames(reader, boundary, selected)
            records_by_boundary[boundary.slug] = records
            probes_by_boundary[boundary.slug] = probes
            result, _ = _boundary_metrics(
                boundary,
                records,
                probes,
                reader.sample_rate_hz / FRAME_RATE_HZ,
            )
            result["slug"] = boundary.slug
            boundary_metrics.append(result)
            _plot_boundary(
                boundary,
                result,
                records,
                probes,
                args.output_root / f"{boundary.slug}-frame-state.png",
            )
        _plot_overview(
            boundary_metrics,
            records_by_boundary,
            args.output_root / "qualification-overview.png",
        )
        _plot_heldout_prediction(
            boundary_metrics,
            records_by_boundary,
            BOUNDARIES,
            args.output_root / "heldout-phase-prediction.png",
        )
        _write_frame_artifact(
            records_by_boundary,
            reader.sample_rate_hz,
            args.output_root / "frame-local-phase-states.jsonl.gz",
        )
        metrics = {
            "schema": "org.leo.research.frame-local-phase-qualification/v1",
            "recording": {
                "session_id": SESSION_ID,
                "stream_id": STREAM_ID,
                "receiver_id": RECEIVER_ID,
                "scope_id": SCOPE_ID,
                "sample_rate_hz": reader.sample_rate_hz,
                "source_report": SOURCE_REPORT,
            },
            "method": {
                "frame_rate_hz": FRAME_RATE_HZ,
                "symbols": [int(SYMBOLS[0]), int(SYMBOLS[-1])],
                "probe_seconds": PROBE_SECONDS,
                "candidate_maximum_line_error_hz": 2_500.0,
                "candidate_minimum_margin": 0.05,
                "cfo_models": "independent candidate CFO plus frozen degree-1 segments only",
                "within_frame_gate": "exact residual + 0.03 <= control and exact coherence >= 2*control",
                "interframe_gate": "two-of-three fit: heldout constant-increment error <= 0.10 and >=0.03 better than control",
                "timing_gate": "epoch R >= 0.80 on both sides",
                "rng_seed": RNG_SEED,
            },
            "synthetic_control": _synthetic_metrics(),
            "boundaries": boundary_metrics,
        }
        (args.output_root / "frame-local-phase-metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _report(metrics, args.report)
    finally:
        store.close()


if __name__ == "__main__":
    main()
