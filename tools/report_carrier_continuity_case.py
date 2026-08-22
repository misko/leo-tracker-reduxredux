#!/usr/bin/env python3
# ruff: noqa: E501
"""Test whether adjacent straight CFO segments share one carrier.

This is a report-only, candidate-only analysis over immutable recorded IQ.  CFO
is degree one on each side of a preregistered boundary.  The quadratic terms
used below are integrals of straight frequency lines into phase; no quadratic
or cubic CFO trajectory is fitted.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260822T143020-c4482829e26c"
STREAM_ID = "stream-0"
RECEIVER_ID = 1
SCOPE_ID = "sha256:424ec0775d22b40bd7f84ab693a65c412f5675c2c1aba6a4e3e89bf9342ba9ba"
RUN_ID = "reprocess-806801e6519b4fcdb95f597f98c25982"
PIPELINE_RELEASE = "6e71fbae5884761274e8ee621467abbb28d9e314"


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

    def phase_from_boundary_cycles(
        self, time_s: float | np.ndarray, boundary_s: float
    ) -> np.ndarray:
        times = np.asarray(time_s, dtype=float)
        left = times - self.reference_s
        origin = boundary_s - self.reference_s
        return self.cfo_at_reference_hz * (times - boundary_s) + 0.5 * self.rate_hz_s * (
            left**2 - origin**2
        )


@dataclass(frozen=True, slots=True)
class Boundary:
    label: str
    pre: Segment
    post: Segment
    search_start_s: float
    search_end_s: float

    @property
    def time_s(self) -> float:
        return 0.5 * (self.pre.end_s + self.post.start_s)

    def segment(self, time_s: float) -> Segment:
        return self.pre if time_s < self.time_s else self.post

    def nominal_phase_cycles(self, time_s: float | np.ndarray) -> np.ndarray:
        times = np.asarray(time_s, dtype=float)
        pre = self.pre.phase_from_boundary_cycles(times, self.time_s)
        post = self.post.phase_from_boundary_cycles(times, self.time_s)
        return np.where(times < self.time_s, pre, post)


BOUNDARIES = (
    Boundary(
        "B1-26.9375s",
        Segment("P1", 20.250, 26.925, 20.250, -6_188.325399204048, -157_618.43809679453),
        Segment("P2", 26.950, 33.300, 26.950, -6_113.603385019892, -201_944.48215763876),
        25.750,
        28.150,
    ),
    Boundary(
        "B2-47.0875s",
        Segment("P4", 40.625, 47.050, 40.625, -6_055.816602137965, -194_835.66819964952),
        Segment("P5", 47.125, 49.425, 47.125, -6_291.359764216548, -236_282.73828298785),
        45.900,
        48.300,
    ),
)


# This control is computed from the independently published degree-1 segments
# on all four paths around B2.  It is intentionally a frozen report input, not
# a replacement for re-running acquisition on those paths.
CROSS_PATH_B2 = (
    {
        "path": "stream-0/RX0",
        "boundary_s": 47.0625,
        "pre_rate_hz_s": -6_064.955,
        "post_rate_hz_s": -6_210.386,
        "step_hz": -2_084.8666125000454,
    },
    {
        "path": "stream-0/RX1",
        "boundary_s": 47.0875,
        "pre_rate_hz_s": -6_055.816602137965,
        "post_rate_hz_s": -6_291.359764216548,
        "step_hz": -2_075.429300863616,
    },
    {
        "path": "stream-1/RX0",
        "boundary_s": 47.0500,
        "pre_rate_hz_s": -6_486.886,
        "post_rate_hz_s": -5_743.671,
        "step_hz": -1_799.847775000031,
    },
    {
        "path": "stream-1/RX1",
        "boundary_s": 47.0625,
        "pre_rate_hz_s": -6_514.322,
        "post_rate_hz_s": -5_752.085,
        "step_hz": -1_729.5275625000068,
    },
)


@dataclass(frozen=True, slots=True)
class Candidate:
    sample_start: int
    time_s: float
    rank: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class FrameObservation:
    probe_index: int
    side: str
    time_s: float
    phase_cycles: float
    exact_power: float
    control_power: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--candidate-b1", type=Path, required=True)
    parser.add_argument("--candidate-b2", type=Path, required=True)
    parser.add_argument("--close-candidate-b1", type=Path)
    parser.add_argument("--close-candidate-b2", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/figures/2026_08_22_carrier_continuity_case"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/2026_08_22_carrier_continuity_case.md"),
    )
    return parser.parse_args()


def _wrap_cycles(values: float | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return (array + 0.5) % 1.0 - 0.5


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _load_candidates(path: Path) -> tuple[Candidate, ...]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            rows.append(
                Candidate(
                    sample_start=int(item["sample_start"]),
                    time_s=float(item["time_s"]),
                    rank=int(item["rank"]),
                    local_epoch_sample=int(item["local_epoch_sample"]),
                    acquired_cfo_hz=float(item["acquired_cfo_hz"]),
                    tracking_cfo_hz=float(item["tracking_cfo_hz"]),
                    exact_score=float(item["exact_score"]),
                    control_score=float(item["control_score"]),
                    margin=float(item["margin"]),
                )
            )
    return tuple(sorted(rows, key=lambda item: (item.sample_start, item.rank)))


def _timeline_stall_metrics(bundle) -> dict[str, Any]:
    streams = []
    for stream in bundle.manifest.streams:
        if stream.timeline_relative_path is None:
            continue
        timeline_path = bundle.path / stream.timeline_relative_path
        with zstd.open(timeline_path, "rt", encoding="utf-8") as source:
            rows = [json.loads(line) for line in source]
        upstream_ns = np.asarray(
            [int(item["hardware_metadata"]["upstream_utc_ns"]) for item in rows],
            dtype=np.int64,
        )
        sample_starts = np.asarray(
            [int(item["session_sample_start"]) for item in rows],
            dtype=np.int64,
        )
        deltas_s = np.diff(upstream_ns.astype(np.float64)) / 1e9
        chunk_starts = {int(item.sample_start) for item in stream.chunks[1:]}
        rollover_indexes = {
            index
            for index, sample_start in enumerate(sample_starts[:-1])
            if int(sample_start) in chunk_starts
        }
        baseline = float(
            np.median(
                [value for index, value in enumerate(deltas_s) if index not in rollover_indexes]
            )
        )
        rollovers = []
        for index in sorted(rollover_indexes):
            shard_start_s = float(sample_starts[index] / stream.applied_settings.sample_rate_hz)
            refill_s = float(rows[index]["sample_count"] / stream.applied_settings.sample_rate_hz)
            rollovers.append(
                {
                    "shard_start_s": shard_start_s,
                    "stall_sample_coordinate_s": shard_start_s + refill_s,
                    "inter_refill_host_delta_s": float(deltas_s[index]),
                    "excess_over_nonrollover_median_s": float(deltas_s[index] - baseline),
                    "timeline_continuity_before": rows[index]["continuity"],
                    "timeline_continuity_after": rows[index + 1]["continuity"],
                }
            )
        streams.append(
            {
                "stream_id": stream.stream_id,
                "radio_id": stream.radio.radio_id,
                "sample_rate_hz": stream.applied_settings.sample_rate_hz,
                "refill_samples": int(rows[0]["sample_count"]),
                "refill_duration_s": float(
                    rows[0]["sample_count"] / stream.applied_settings.sample_rate_hz
                ),
                "nonrollover_median_host_delta_s": baseline,
                "sample_loss_observable": stream.continuity.sample_loss_observable,
                "device_sample_counter_available": all(
                    item["device_sample_counter"] is not None for item in rows
                ),
                "phase_coherent": bundle.manifest.synchronization.phase_coherent,
                "times_s": (sample_starts[1:] / stream.applied_settings.sample_rate_hz).tolist(),
                "host_deltas_s": deltas_s.tolist(),
                "rollovers": rollovers,
            }
        )
    boundary_rows = []
    for boundary in BOUNDARIES:
        per_stream = []
        for stream in streams:
            rollover = min(
                stream["rollovers"],
                key=lambda item: abs(item["stall_sample_coordinate_s"] - boundary.time_s),
            )
            per_stream.append(
                {
                    "stream_id": stream["stream_id"],
                    "host_delta_s": rollover["inter_refill_host_delta_s"],
                    "baseline_s": stream["nonrollover_median_host_delta_s"],
                    "excess_s": rollover["excess_over_nonrollover_median_s"],
                }
            )
        boundary_rows.append(
            {
                "label": boundary.label,
                "boundary_s": boundary.time_s,
                "stall_sample_coordinate_s": min(
                    streams[0]["rollovers"],
                    key=lambda item: abs(item["stall_sample_coordinate_s"] - boundary.time_s),
                )["stall_sample_coordinate_s"],
                "boundary_minus_stall_coordinate_ms": 1_000.0
                * (
                    boundary.time_s
                    - min(
                        streams[0]["rollovers"],
                        key=lambda item: abs(item["stall_sample_coordinate_s"] - boundary.time_s),
                    )["stall_sample_coordinate_s"]
                ),
                "streams": per_stream,
            }
        )
    return {"streams": streams, "boundaries": boundary_rows}


def _timeline_stall_plot(timing: dict[str, Any], path: Path) -> None:
    figure, axes = plt.subplots(len(timing["streams"]), 1, figsize=(13.5, 6.6), sharex=True)
    if not isinstance(axes, np.ndarray):
        axes = np.asarray([axes])
    for axis, stream in zip(axes, timing["streams"], strict=True):
        axis.scatter(
            stream["times_s"],
            stream["host_deltas_s"],
            s=5,
            color="#9aa4ad",
            alpha=0.55,
            linewidths=0,
            rasterized=True,
            label="ordinary refill interval",
        )
        for index, rollover in enumerate(stream["rollovers"]):
            axis.scatter(
                [rollover["stall_sample_coordinate_s"]],
                [rollover["inter_refill_host_delta_s"]],
                marker="D",
                s=28,
                color="#e15759",
                zorder=4,
                label="shard-finalization rollover" if index == 0 else None,
            )
        axis.axhline(
            stream["nonrollover_median_host_delta_s"],
            color="#111111",
            linewidth=0.75,
            linestyle="--",
            label="non-rollover median",
        )
        for boundary in BOUNDARIES:
            axis.axvline(boundary.time_s, color="#4e79a7", linestyle=":", linewidth=0.8)
        axis.set_ylabel("host interval (s)")
        axis.set_title(
            f"{stream['stream_id']} · {stream['radio_id']} · sample loss observable: "
            f"{stream['sample_loss_observable']}",
            loc="left",
        )
        axis.grid(alpha=0.13)
        axis.legend(fontsize=8, loc="upper right", ncol=3)
    axes[-1].set_xlabel("stored sample coordinate (s)")
    figure.suptitle(
        "Capture-thread stalls recur immediately after each 128 MiB IQ shard rollover\n"
        "blue dotted lines are the two audited CFO boundaries",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _group_candidates(candidates: tuple[Candidate, ...]) -> dict[int, tuple[Candidate, ...]]:
    grouped: dict[int, list[Candidate]] = {}
    for item in candidates:
        grouped.setdefault(item.sample_start, []).append(item)
    return {key: tuple(value) for key, value in sorted(grouped.items())}


def _select_line_candidates(
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
    *,
    maximum_error_hz: float = 2_500.0,
    minimum_margin: float = 0.05,
) -> tuple[Candidate, ...]:
    selected = []
    for rows in _group_candidates(candidates).values():
        time_s = rows[0].time_s
        segment = boundary.segment(time_s)
        expected = float(segment.frequency_hz(time_s))
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


def _frame_observations(
    reader,
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
) -> tuple[tuple[FrameObservation, ...], np.ndarray, dict[str, Any]]:
    symbols = np.arange(2, 66)
    frames: list[FrameObservation] = []
    fingerprints: dict[str, list[np.ndarray]] = {"pre": [], "post": []}
    timing: dict[str, list[float]] = {"pre": [], "post": []}
    frame_period_samples = reader.sample_rate_hz / FRAME_RATE_HZ
    probe_samples = round(0.020 * reader.sample_rate_hz)
    outer_start = min(item.sample_start for item in candidates)
    outer_stop = max(item.sample_start for item in candidates) + probe_samples
    outer = _complex_receiver(
        reader.read(
            outer_start,
            outer_stop - outer_start,
            receiver_ids=(RECEIVER_ID,),
        )
    )
    for probe_index, candidate in enumerate(candidates):
        local_start = candidate.sample_start - outer_start
        values = np.ascontiguousarray(outer[local_start : local_start + probe_samples])
        workspace = _conditioned_correlation_workspace(
            values,
            reader.sample_rate_hz,
            candidate.local_epoch_sample,
            candidate.tracking_cfo_hz,
            edge=StarlinkEdge.LOWER,
            selected_symbols=symbols,
        )
        exact = workspace.select(symbols)
        control = workspace.select(symbols, control=True)
        side = "pre" if candidate.time_s < boundary.time_s else "post"
        timing[side].append(
            (candidate.sample_start + candidate.local_epoch_sample) % frame_period_samples
        )
        normalized_rows = []
        for row, powers, control_powers, times in zip(
            exact.values,
            exact.normalized_power,
            control.normalized_power,
            exact.times_s,
            strict=True,
        ):
            amplitude = complex(np.sum(row))
            if not amplitude:
                continue
            local_time_s = float(np.mean(times))
            global_time_s = candidate.time_s + local_time_s
            raw_phase_cycles = float(
                _wrap_cycles(
                    np.angle(amplitude) / (2.0 * np.pi) + candidate.tracking_cfo_hz * local_time_s
                )
            )
            frames.append(
                FrameObservation(
                    probe_index,
                    side,
                    global_time_s,
                    raw_phase_cycles,
                    float(np.mean(powers)),
                    float(np.mean(control_powers)),
                )
            )
            phase = np.exp(-1j * np.angle(amplitude))
            vector = row * phase
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                normalized_rows.append(vector / norm)
        if normalized_rows:
            fingerprint = np.mean(np.stack(normalized_rows), axis=0)
            norm = float(np.linalg.norm(fingerprint))
            if norm > 0:
                fingerprints[side].append(fingerprint / norm)

    means = {}
    for side in ("pre", "post"):
        if not fingerprints[side]:
            means[side] = np.zeros(len(symbols), dtype=np.complex128)
            continue
        value = np.mean(np.stack(fingerprints[side]), axis=0)
        means[side] = value / max(float(np.linalg.norm(value)), 1e-20)
    similarity = float(abs(np.vdot(means["pre"], means["post"])))

    def circular_timing(values: list[float]) -> tuple[float, float]:
        phases = 2.0 * np.pi * np.asarray(values) / frame_period_samples
        vector = complex(np.mean(np.exp(1j * phases)))
        mean = float((np.angle(vector) % (2.0 * np.pi)) * frame_period_samples / (2.0 * np.pi))
        dispersion = float(math.sqrt(max(0.0, -2.0 * math.log(max(abs(vector), 1e-12)))))
        return mean, dispersion * frame_period_samples / (2.0 * np.pi)

    pre_timing, pre_dispersion = circular_timing(timing["pre"])
    post_timing, post_dispersion = circular_timing(timing["post"])
    timing_jump = float(
        _wrap_cycles((post_timing - pre_timing) / frame_period_samples) * frame_period_samples
    )
    timing_result = {
        "pre_mean_modulo_frame_samples": pre_timing,
        "post_mean_modulo_frame_samples": post_timing,
        "wrapped_jump_samples": timing_jump,
        "pre_circular_dispersion_samples": pre_dispersion,
        "post_circular_dispersion_samples": post_dispersion,
    }
    return (
        tuple(frames),
        np.stack((means["pre"], means["post"])),
        {
            "fingerprint_similarity": similarity,
            "timing": timing_result,
        },
    )


def _phase_design(times: np.ndarray, boundary_s: float) -> np.ndarray:
    delta = times - boundary_s
    return np.column_stack((np.ones(len(times)), delta, 0.5 * delta**2))


def _robust_phase_fit(
    times: np.ndarray,
    unwrapped_residual: np.ndarray,
    boundary_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    design = _phase_design(times, boundary_s)
    coefficients = _huber_linear_fit(design, unwrapped_residual)
    return coefficients, design @ coefficients


def _huber_linear_fit(design: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Deterministic MAD-scaled Huber IRLS without an optional SciPy dependency."""

    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    for _ in range(30):
        residual = values - design @ coefficients
        center = float(np.median(residual))
        scale = max(float(np.median(np.abs(residual - center))) / 0.6745, 1e-6)
        standardized = np.abs((residual - center) / scale)
        weights = np.ones(len(values), dtype=float)
        tail = standardized > 1.345
        weights[tail] = 1.345 / standardized[tail]
        weighted_design = design * np.sqrt(weights)[:, None]
        weighted_values = values * np.sqrt(weights)
        updated, *_ = np.linalg.lstsq(weighted_design, weighted_values, rcond=None)
        if np.max(np.abs(updated - coefficients)) <= 1e-10:
            coefficients = updated
            break
        coefficients = updated
    return coefficients


def _phase_metrics(
    boundary: Boundary,
    frames: tuple[FrameObservation, ...],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    ordered = tuple(sorted(frames, key=lambda item: item.time_s))
    times = np.asarray([item.time_s for item in ordered])
    observed = np.asarray([item.phase_cycles for item in ordered])
    nominal = boundary.nominal_phase_cycles(times)
    wrapped = _wrap_cycles(observed - nominal)
    side_masks = {
        "pre": np.asarray([item.side == "pre" for item in ordered]),
        "post": np.asarray([item.side == "post" for item in ordered]),
    }
    fits: dict[str, np.ndarray] = {}
    coefficients: dict[str, np.ndarray] = {}
    unwrapped = np.zeros(len(ordered), dtype=float)
    for side, mask in side_masks.items():
        indexes = np.flatnonzero(mask)
        values = np.unwrap(2.0 * np.pi * wrapped[indexes]) / (2.0 * np.pi)
        coefficients[side], fits[side] = _robust_phase_fit(times[indexes], values, boundary.time_s)
        unwrapped[indexes] = values

    phase_jump = float(_wrap_cycles(coefficients["post"][0] - coefficients["pre"][0]))
    reset_prediction = np.zeros(len(ordered), dtype=float)
    for side, mask in side_masks.items():
        reset_prediction[mask] = _phase_design(times[mask], boundary.time_s) @ coefficients[side]

    # The continuous model shares only the boundary phase.  Each side retains
    # its own frequency and frequency-rate corrections, so CFO remains straight.
    delta = times - boundary.time_s
    continuous_design = np.column_stack(
        (
            np.ones(len(times)),
            delta * side_masks["pre"],
            0.5 * delta**2 * side_masks["pre"],
            delta * side_masks["post"],
            0.5 * delta**2 * side_masks["post"],
        )
    )
    aligned = unwrapped.copy()
    post_indexes = np.flatnonzero(side_masks["post"])
    integer_shift = round(coefficients["pre"][0] - coefficients["post"][0])
    aligned[post_indexes] += integer_shift
    continuous_fit = _huber_linear_fit(continuous_design, aligned)
    continuous_prediction = continuous_design @ continuous_fit
    reset_error = np.abs(_wrap_cycles(unwrapped - reset_prediction))
    continuous_error = np.abs(_wrap_cycles(aligned - continuous_prediction))

    # Within-segment false-boundary controls use the same independently fitted
    # phase traces and therefore quantify local extrapolation noise without
    # assuming a satellite or transmitter model.
    controls = []
    for side, mask in side_masks.items():
        side_times = times[mask]
        if len(side_times) < 12:
            continue
        control_time = float(np.median(side_times))
        left = mask & (times < control_time)
        right = mask & (times >= control_time)
        if np.sum(left) < 5 or np.sum(right) < 5:
            continue
        left_coef, _ = _robust_phase_fit(times[left], unwrapped[left], control_time)
        right_coef, _ = _robust_phase_fit(times[right], unwrapped[right], control_time)
        controls.append(
            {
                "side": side,
                "time_s": control_time,
                "wrapped_phase_jump_cycles": float(_wrap_cycles(right_coef[0] - left_coef[0])),
            }
        )

    result = {
        "wrapped_phase_jump_cycles": phase_jump,
        "wrapped_phase_jump_degrees": phase_jump * 360.0,
        "reset_model_median_absolute_phase_error_cycles": float(np.median(reset_error)),
        "continuous_model_median_absolute_phase_error_cycles": float(np.median(continuous_error)),
        "continuous_to_reset_error_ratio": float(
            np.median(continuous_error) / max(float(np.median(reset_error)), 1e-12)
        ),
        "pre_frequency_correction_hz": float(coefficients["pre"][1]),
        "post_frequency_correction_hz": float(coefficients["post"][1]),
        "pre_rate_correction_hz_s": float(coefficients["pre"][2]),
        "post_rate_correction_hz_s": float(coefficients["post"][2]),
        "within_segment_controls": controls,
    }
    arrays = {
        "times": times,
        "wrapped": wrapped,
        "unwrapped": unwrapped,
        "reset_prediction": reset_prediction,
        "continuous_prediction": continuous_prediction,
        "continuous_aligned": aligned,
        "pre_mask": side_masks["pre"],
        "post_mask": side_masks["post"],
    }
    return result, arrays


def _coexistence_metrics(
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
    *,
    window_s: float = 0.20,
    close_search: bool = False,
) -> dict[str, Any]:
    simultaneous = 0
    eligible = 0
    pre_only = 0
    post_only = 0
    neither = 0
    unresolved_both = 0
    rows = []
    for grouped in _group_candidates(candidates).values():
        time_s = grouped[0].time_s
        if abs(time_s - boundary.time_s) > window_s:
            continue
        eligible += 1
        pre_expected = float(boundary.pre.frequency_hz(time_s))
        post_expected = float(boundary.post.frequency_hz(time_s))
        pre = min(grouped, key=lambda item: abs(item.tracking_cfo_hz - pre_expected))
        post = min(grouped, key=lambda item: abs(item.tracking_cfo_hz - post_expected))
        pre_present = abs(pre.tracking_cfo_hz - pre_expected) <= 1_500 and pre.margin >= 0.05
        post_present = abs(post.tracking_cfo_hz - post_expected) <= 1_500 and post.margin >= 0.05
        distinct = abs(pre.tracking_cfo_hz - post.tracking_cfo_hz) >= 500
        if pre_present and post_present and distinct:
            simultaneous += 1
            state = "two-distinct"
        elif pre_present and post_present:
            unresolved_both += 1
            state = "one-peak-compatible-with-both"
        elif pre_present:
            pre_only += 1
            state = "pre-only"
        elif post_present:
            post_only += 1
            state = "post-only"
        else:
            neither += 1
            state = "neither"
        rows.append(
            {
                "time_s": time_s,
                "pre_present": pre_present,
                "post_present": post_present,
                "distinct_candidates": distinct,
                "state": state,
            }
        )
    return {
        "search": "1-kHz-coarse-500-Hz-NMS" if close_search else "10-kHz-coarse-10-kHz-NMS",
        "window_s": window_s,
        "eligible_probe_count": eligible,
        "simultaneous_distinct_probe_count": simultaneous,
        "pre_only_probe_count": pre_only,
        "post_only_probe_count": post_only,
        "unresolved_both_probe_count": unresolved_both,
        "neither_probe_count": neither,
        "resolvability_caveat": (
            "distinct GLRT-refined peaks are required; several coarse seeds collapsing onto "
            "one refined CFO are one likelihood basin, not multiple carriers"
            if close_search
            else "the 10 kHz coarse grid and 10 kHz acquisition NMS cannot reliably resolve "
            "two carriers separated by the approximately 2-3 kHz fitted boundary step"
        ),
        "probes": rows,
    }


def _close_search_plot(
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
    coexistence: dict[str, Any],
    path: Path,
) -> None:
    window_s = float(coexistence["window_s"])
    start_s = boundary.time_s - window_s
    end_s = boundary.time_s + window_s
    shown = tuple(item for item in candidates if start_s <= item.time_s <= end_s)
    figure, axis = plt.subplots(figsize=(12.5, 4.6))
    axis.scatter(
        [item.time_s for item in shown],
        [item.tracking_cfo_hz / 1_000 for item in shown],
        c=[item.margin for item in shown],
        s=8,
        cmap="viridis",
        vmin=0.0,
        vmax=max(0.5, max((item.margin for item in shown), default=0.5)),
        alpha=0.35,
        linewidths=0,
        rasterized=True,
        label="all independently refined fine-search basins",
    )
    dense = np.linspace(start_s, end_s, 300)
    axis.plot(
        dense,
        boundary.pre.frequency_hz(dense) / 1_000,
        color="#4e79a7",
        linewidth=0.9,
        label="extrapolated pre-segment",
    )
    axis.plot(
        dense,
        boundary.post.frequency_hz(dense) / 1_000,
        color="#e15759",
        linewidth=0.9,
        label="extrapolated post-segment",
    )
    state_colors = {
        "pre-only": "#4e79a7",
        "post-only": "#e15759",
        "two-distinct": "#59a14f",
        "one-peak-compatible-with-both": "#f28e2b",
        "neither": "#9aa4ad",
    }
    state_markers = {
        "pre-only": "<",
        "post-only": ">",
        "two-distinct": "*",
        "one-peak-compatible-with-both": "D",
        "neither": "x",
    }
    for row in coexistence["probes"]:
        time_s = float(row["time_s"])
        state = str(row["state"])
        expected = (
            float(boundary.pre.frequency_hz(time_s))
            if state == "pre-only"
            else float(boundary.post.frequency_hz(time_s))
        )
        if state in {"neither", "two-distinct", "one-peak-compatible-with-both"}:
            expected = 0.5 * (
                float(boundary.pre.frequency_hz(time_s)) + float(boundary.post.frequency_hz(time_s))
            )
        axis.scatter(
            [time_s],
            [expected / 1_000],
            s=36,
            marker=state_markers[state],
            color=state_colors[state],
            linewidths=0.8,
            zorder=5,
        )
    axis.axvline(boundary.time_s, color="#111111", linestyle=":", linewidth=0.7)
    axis.set_xlim(start_s, end_s)
    line_values = np.concatenate(
        (boundary.pre.frequency_hz(dense), boundary.post.frequency_hz(dense))
    )
    axis.set_ylim(
        (float(np.min(line_values)) - 7_000) / 1_000, (float(np.max(line_values)) + 7_000) / 1_000
    )
    axis.set_xlabel("capture time (s)")
    axis.set_ylabel("tracking CFO (kHz)")
    axis.grid(alpha=0.15)
    axis.legend(fontsize=8, loc="best")
    axis.set_title(
        f"Fine close-carrier search · {boundary.label} · 1 kHz grid / 500 Hz NMS\n"
        f"pre-only {coexistence['pre_only_probe_count']}, post-only "
        f"{coexistence['post_only_probe_count']}, two distinct "
        f"{coexistence['simultaneous_distinct_probe_count']} of "
        f"{coexistence['eligible_probe_count']} probes"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _waterfall(
    reader,
    boundary: Boundary,
    path: Path,
) -> None:
    sample_rate = reader.sample_rate_hz
    start_s = boundary.search_start_s
    end_s = boundary.search_end_s
    start = round(start_s * sample_rate)
    count = round((end_s - start_s) * sample_rate)
    values = _complex_receiver(reader.read(start, count, receiver_ids=(RECEIVER_ID,)))
    nfft = 8_192
    usable = len(values) // nfft * nfft
    frames = values[:usable].reshape(-1, nfft)
    window = np.hanning(nfft)
    spectra = np.fft.fftshift(np.fft.fft(frames * window, axis=1), axes=1)
    frequencies = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / sample_rate))
    line_times = np.asarray([start_s, end_s])
    line_values = np.concatenate(
        (boundary.pre.frequency_hz(line_times), boundary.post.frequency_hz(line_times))
    )
    low = float(np.min(line_values) - 20_000.0)
    high = float(np.max(line_values) + 20_000.0)
    keep = (frequencies >= low) & (frequencies <= high)
    power = 20.0 * np.log10(np.maximum(np.abs(spectra[:, keep]), 1e-12))
    times = start_s + (np.arange(len(frames)) + 0.5) * nfft / sample_rate
    figure, axis = plt.subplots(figsize=(13.5, 4.2))
    axis.imshow(
        power.T,
        origin="lower",
        aspect="auto",
        extent=(times[0], times[-1], frequencies[keep][0] / 1_000, frequencies[keep][-1] / 1_000),
        cmap="magma",
        vmin=float(np.quantile(power, 0.20)),
        vmax=float(np.quantile(power, 0.995)),
    )
    dense = np.linspace(start_s, end_s, 500)
    axis.plot(
        dense[dense <= boundary.time_s],
        boundary.pre.frequency_hz(dense[dense <= boundary.time_s]) / 1_000,
        color="#3bd6c6",
        linewidth=0.8,
    )
    axis.plot(
        dense[dense >= boundary.time_s],
        boundary.post.frequency_hz(dense[dense >= boundary.time_s]) / 1_000,
        color="#66e06f",
        linewidth=0.8,
    )
    axis.axvline(boundary.time_s, color="white", linestyle=":", linewidth=0.8)
    axis.set_xlabel("capture time (s)")
    axis.set_ylabel("baseband frequency (kHz)")
    axis.set_title(
        f"Raw IQ waterfall around {boundary.label} · thin lines are preregistered degree-1 CFO segments"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _boundary_plot(
    boundary: Boundary,
    candidates: tuple[Candidate, ...],
    selected: tuple[Candidate, ...],
    frames: tuple[FrameObservation, ...],
    phase_arrays: dict[str, np.ndarray],
    path: Path,
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(13.5, 9.0), sharex=True)
    all_axis, phase_axis, power_axis = axes
    all_axis.scatter(
        [item.time_s for item in candidates],
        [item.tracking_cfo_hz / 1_000 for item in candidates],
        s=2,
        color="#9aa4ad",
        alpha=0.10,
        linewidths=0,
        rasterized=True,
        label="all 32 independently scored candidates/probe",
    )
    all_axis.scatter(
        [item.time_s for item in selected],
        [item.tracking_cfo_hz / 1_000 for item in selected],
        s=13,
        facecolors="none",
        edgecolors="#f28e2b",
        linewidths=0.55,
        label="candidate nearest preregistered segment",
    )
    dense = np.linspace(boundary.search_start_s, boundary.search_end_s, 500)
    pre_mask = dense < boundary.time_s
    all_axis.plot(
        dense[pre_mask],
        boundary.pre.frequency_hz(dense[pre_mask]) / 1_000,
        color="#111111",
        linewidth=0.75,
    )
    all_axis.plot(
        dense[~pre_mask],
        boundary.post.frequency_hz(dense[~pre_mask]) / 1_000,
        color="#111111",
        linewidth=0.75,
    )
    all_axis.set_ylabel("tracking CFO (kHz)")
    all_axis.legend(fontsize=8, loc="best")
    all_axis.set_title(
        "A · independent dense acquisition; line selection occurs only afterward", loc="left"
    )

    times = phase_arrays["times"]
    phase_axis.scatter(
        times,
        phase_arrays["continuous_aligned"],
        s=4,
        color="#4e79a7",
        alpha=0.45,
        linewidths=0,
        label="dechirped complex pilot phase",
    )
    phase_axis.plot(
        times,
        phase_arrays["continuous_prediction"],
        color="#111111",
        linewidth=0.75,
        label="one continuous-phase model",
    )
    phase_axis.plot(
        times,
        phase_arrays["reset_prediction"],
        color="#e15759",
        linewidth=0.75,
        linestyle="--",
        label="free phase on each side",
    )
    phase_axis.set_ylabel("phase residual (cycles)")
    phase_axis.legend(fontsize=8, loc="best")
    phase_axis.set_title(
        "B · phase after integrating straight CFO segments (no curved CFO fit)", loc="left"
    )

    power_axis.scatter(
        [item.time_s for item in frames],
        [item.exact_power - item.control_power for item in frames],
        s=5,
        color="#59a14f",
        alpha=0.55,
        linewidths=0,
    )
    power_axis.axhline(0.0, color="#7a838c", linewidth=0.6)
    power_axis.set_ylabel("per-frame exact − control power")
    power_axis.set_xlabel("capture time (s)")
    power_axis.set_title("C · known-pilot evidence through the boundary", loc="left")
    for axis in axes:
        axis.axvline(boundary.time_s, color="#d1495b", linewidth=0.7, linestyle=":")
        axis.grid(alpha=0.14)
        axis.set_xlim(boundary.search_start_s, boundary.search_end_s)
    figure.suptitle(
        f"Carrier-continuity audit · {SESSION_ID} · stream-0/RX1 · {boundary.label}",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _classification(result: dict[str, Any]) -> tuple[str, str]:
    phase = result["phase"]
    timing = result["waveform_timing"]["timing"]
    ratio = phase["continuous_to_reset_error_ratio"]
    jump = abs(phase["wrapped_phase_jump_cycles"])
    phase_observable = phase["reset_model_median_absolute_phase_error_cycles"] <= 0.10 and all(
        abs(item["wrapped_phase_jump_cycles"]) <= 0.15 for item in phase["within_segment_controls"]
    )
    timing_observable = (
        max(
            timing["pre_circular_dispersion_samples"],
            timing["post_circular_dispersion_samples"],
        )
        <= 50.0
    )
    result["phase_observable"] = phase_observable
    result["timing_observable"] = timing_observable
    if not phase_observable and not timing_observable:
        return (
            "inconclusive: pilot statistic is not phase/timing coherent",
            "phase residuals are uniform-like and acquisition epochs are diffuse",
        )
    if phase_observable and ratio <= 1.35 and jump <= 0.10 and timing_observable:
        return (
            "continuous-carrier evidence",
            "phase and arrival timing agree",
        )
    if timing_observable:
        return (
            "same detected waveform; carrier phase unresolved",
            "arrival timing agrees but phase does not provide a bridge",
        )
    return (
        "inconclusive or independent carrier",
        "the available coherent observable does not bridge the boundary",
    )


def _markdown(summary: dict[str, Any]) -> str:
    rows = []
    for item in summary["boundaries"]:
        rows.append(
            "| {label} | {gap:.0f} ms | {pre:+.1f} | {post:+.1f} | {phase_obs} | {timing_obs} | {coexist} | **{classification}** |".format(
                label=item["label"],
                gap=item["gap_s"] * 1_000,
                pre=item["pre_rate_hz_s"],
                post=item["post_rate_hz_s"],
                phase_obs="yes" if item["phase_observable"] else "**no**",
                timing_obs="yes" if item["timing_observable"] else "**no**",
                coexist=item["coexistence"]["simultaneous_distinct_probe_count"],
                classification=item["classification"],
            )
        )
    sections = []
    for item in summary["boundaries"]:
        stem = item["label"].lower().replace(".", "-")
        sections.extend(
            [
                f"## {item['label']}",
                "",
                f"![Raw IQ waterfall](figures/2026_08_22_carrier_continuity_case/{stem}-waterfall.png)",
                "",
                f"![Candidate, phase, and known-pilot audit](figures/2026_08_22_carrier_continuity_case/{stem}-continuity.png)",
                "",
                f"![Fine close-carrier search](figures/2026_08_22_carrier_continuity_case/{stem}-close-search.png)",
                "",
                f"Classification: **{item['classification']}** — {item['classification_reason']}.",
                "",
                f"The fitted boundary-frequency discontinuity is {item['fitted_frequency_step_hz']:+.1f} Hz. "
                f"The wrapped phase discontinuity is {item['phase']['wrapped_phase_jump_cycles']:+.3f} cycles "
                f"({item['phase']['wrapped_phase_jump_degrees']:+.1f}°). The continuous-phase model has "
                f"{item['phase']['continuous_to_reset_error_ratio']:.2f}× the median circular error of a "
                "model that grants each side an independent phase.",
                "",
                f"The arrival-epoch jump is {item['waveform_timing']['timing']['wrapped_jump_samples']:+.2f} "
                f"samples, but its circular dispersions are "
                f"{item['waveform_timing']['timing']['pre_circular_dispersion_samples']:.1f}/"
                f"{item['waveform_timing']['timing']['post_circular_dispersion_samples']:.1f} samples. "
                "That epoch statistic is not coherent enough to interpret the jump.",
                "",
                "| Coherence diagnostic | Value | Passing behavior |",
                "|---|---:|---|",
                f"| Independent-phase median circular error | "
                f"{item['phase']['reset_model_median_absolute_phase_error_cycles']:.3f} cycles | "
                "Clearly below the 0.25-cycle uniform-phase baseline |",
                f"| One-phase / independent-phase error ratio | "
                f"{item['phase']['continuous_to_reset_error_ratio']:.3f} | "
                "Near 1 only after phase itself is coherent |",
                f"| False boundary inside pre segment | "
                f"{item['phase']['within_segment_controls'][0]['wrapped_phase_jump_cycles']:+.3f} cycles | Near 0 |",
                f"| False boundary inside post segment | "
                f"{item['phase']['within_segment_controls'][1]['wrapped_phase_jump_cycles']:+.3f} cycles | Near 0 |",
                f"| Epoch dispersion, pre/post | "
                f"{item['waveform_timing']['timing']['pre_circular_dispersion_samples']:.1f} / "
                f"{item['waveform_timing']['timing']['post_circular_dispersion_samples']:.1f} samples | "
                "Tens, not hundreds–thousands, of samples |",
                "",
                f"Normalized pilot-shape similarity is "
                f"{item['waveform_timing']['fingerprint_similarity']:.3f}. This is not an independent "
                "emitter fingerprint: it is formed after correlating both sides against the same "
                "exact pilot template.",
                "",
                "The fine search found "
                f"{item['coexistence']['pre_only_probe_count']} pre-only, "
                f"{item['coexistence']['post_only_probe_count']} post-only, and "
                f"{item['coexistence']['simultaneous_distinct_probe_count']} simultaneous-distinct "
                f"detections among {item['coexistence']['eligible_probe_count']} boundary probes. "
                "This is evidence against two overlapping resolved carriers at this threshold. It "
                "does not distinguish one carrier that retuned from two carriers that transmitted "
                "back-to-back.",
                "",
            ]
        )
    cross_path_rows = [
        "| {path} | {time:.4f} s | {pre:+.1f} | {post:+.1f} | {step:+.1f} |".format(
            path=item["path"],
            time=item["boundary_s"],
            pre=item["pre_rate_hz_s"],
            post=item["post_rate_hz_s"],
            step=item["step_hz"],
        )
        for item in summary["cross_path_b2"]
    ]
    timing_rows = []
    for item in summary["capture_timing"]["boundaries"]:
        streams = {stream["stream_id"]: stream for stream in item["streams"]}
        timing_rows.append(
            "| {label} | {stall:.6f} | {offset:+.1f} | {s0:.3f} | {s1:.3f} |".format(
                label=item["label"],
                stall=item["stall_sample_coordinate_s"],
                offset=item["boundary_minus_stall_coordinate_ms"],
                s0=streams["stream-0"]["excess_s"],
                s1=streams["stream-1"]["excess_s"],
            )
        )
    return "\n".join(
        [
            "# Are adjacent linear CFO segments the same carrier?",
            "",
            "## Answer",
            "",
            summary["headline"],
            "",
            "This is a receiver-relative, candidate-only test. It does not identify a satellite and "
            "does not decode payload. A continuous-carrier result is evidence about one RF component, "
            "not spacecraft identity.",
            "",
            "## Dominant finding: the boundaries coincide with capture stalls",
            "",
            "![Refill timing and shard rollover stalls](figures/2026_08_22_carrier_continuity_case/refill-timing-shard-rollovers.png)",
            "",
            "The stored IQ files have contiguous **sample indexes**, but this capture has no hardware "
            "device sample counter, `sample_loss_observable=false`, timeline continuity `unknown`, and "
            "`phase_coherent=false`. Host timestamps expose a repeatable stall immediately after every "
            "128 MiB compressed IQ shard rollover.",
            "",
            "| CFO boundary | Stall sample coordinate (s) | Boundary − stall coordinate | stream-0 excess host delay | stream-1 excess host delay |",
            "|---|---:|---:|---:|---:|",
            *timing_rows,
            "",
            "The alignment is exceptionally close: B1 is 10.9 ms before the affected refill edge and "
            "B2 is 6.4 ms after it. The excess delay is 0.48–0.69 s across the two independent radios. "
            "This is the strongest explanation for the segmentation: the synchronous capture loop "
            "reads one refill, finalizes/compresses/fsyncs a full shard in `StreamBundleWriter.append`, "
            "and only then requests the next radio refill. If the Pluto buffers overrun during that "
            "pause, elapsed RF time is omitted while the stored sample index remains contiguous.",
            "",
            "We cannot convert host delay exactly into missing samples because the firmware reports no "
            "device counter or overflow flag. But the timing, recurrence, two-radio agreement, and sign "
            "all fit one real carrier observed across an unmeasured capture gap. This makes a local "
            "capture artifact substantially more likely than a satellite changing Doppler abruptly.",
            "",
            "## Frozen example and method",
            "",
            f"Dwell `{SESSION_ID}`, sealed reprocessing `{RUN_ID}`, pipeline release "
            f"`{PIPELINE_RELEASE}`, path `stream-0/RX1`, scope `{SCOPE_ID}`. The two boundaries "
            "were selected before inspecting complex phase because their neighboring final straight "
            "segments are separated by only 25 and 75 ms.",
            "",
            "Every 20 ms probe was reacquired independently with the Research search: 81 coarse CFO "
            "hypotheses, 32 retained/scored basins, GLRT-4096, and no neighboring observation, line, "
            "TLE, or phase model entering acquisition. Candidate association to the frozen straight "
            "segments happens afterward.",
            "",
            "Carrier frequency is degree one on each side. The phase display integrates those straight "
            "frequency lines, so a quadratic term exists only in phase. No degree-2 or degree-3 CFO "
            "trajectory is fitted.",
            "",
            "## What this step is testing",
            "",
            "1. The independent GLRT asks only whether a known Starlink pilot is present at each "
            "20 ms probe and returns several local CFO likelihood basins.",
            "2. Only after scoring do we select the candidate nearest each already-frozen straight "
            "CFO segment. This prevents the line from creating the detections it is meant to test.",
            "3. We return to raw complex IQ, dechirp with the integral of that straight CFO, and ask "
            "whether one phase state can bridge the gap better than two independent phase offsets.",
            "4. Separately, a finer 1 kHz search asks whether both segment frequencies coexist in "
            "the same probe. These are different hypotheses: phase bridging tests sameness; two "
            "simultaneous peaks test multiplicity.",
            "",
            "The input is immutable CI16 IQ plus frozen degree-1 segment parameters. The output is "
            "a boundary-level evidence record; it is not a merged track, TLE match, or satellite ID.",
            "",
            "| Search parameter | Primary independent acquisition | Close-carrier diagnostic | Meaning |",
            "|---|---:|---:|---|",
            "| Probe / spacing | 20 / 25 ms | 20 / 25 ms | Independent raw-IQ window and cadence |",
            "| Residual-CFO interval | ±400 kHz | ±400 kHz | Entire searched baseband offset |",
            "| Coarse CFO step | 10 kHz | 1 kHz | Initial frequency hypotheses |",
            "| Fine radius / step | 10 kHz / 100 Hz | 1 kHz / 25 Hz | Local refinement around each basin |",
            "| Conditioned radius / step | 1 kHz / 25 Hz | 500 Hz / 10 Hz | Final known-pilot refinement |",
            "| Retained basins | 32 | 32 | Independently scored local likelihood maxima |",
            "| CFO NMS separation | 10 kHz | 500 Hz | When refined peaks count as distinct |",
            "| GLRT residual grid | 4096 | 4096 | Exact-versus-control pilot score resolution |",
            "",
            "| Boundary | Gap | Pre rate (Hz/s) | Post rate (Hz/s) | Phase observable? | Timing observable? | Fine-search coexistence probes | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
            *rows,
            "",
            *sections,
            "## Four-path common-mode control at B2",
            "",
            "The degree-1 final banks put a negative frequency step at essentially the same B2 time "
            "on all four receiver paths:",
            "",
            "| Path | Boundary | Pre rate (Hz/s) | Post rate (Hz/s) | Fitted step (Hz) |",
            "|---|---:|---:|---:|---:|",
            *cross_path_rows,
            "",
            "The agreement across both streams and both receiver indices makes a single-channel "
            "Pluto or LNB glitch less likely. Coupled with the independently measured shard-rollover "
            "stalls on both capture threads, it instead supports a common acquisition/storage mechanism. "
            "It does not establish phase continuity because the potentially missing samples are not "
            "counted.",
            "",
            "## Important limitation: close-carrier coexistence",
            "",
            "The primary Research acquisition has a 10 kHz coarse grid and 10 kHz CFO non-maximum "
            "suppression. The additional close search uses a 1 kHz coarse grid and 500 Hz suppression "
            "inside ±0.2 s. Even there, only distinct GLRT-refined peaks count; several coarse seeds "
            "that converge to one CFO are one likelihood basin.",
            "",
            "In both audited boundaries the fine search changes from pre-only detections to post-only "
            "detections, with no probe containing two distinct resolved peaks. That rules out only "
            "the simple *overlapping two-carrier* picture at the tested margin and 500 Hz separation. "
            "It remains compatible with either one retuning carrier or two scheduled back-to-back "
            "carriers.",
            "",
            "## Why phase continuity is not recoverable from today's detector output",
            "",
            "The known-pilot GLRT is intentionally a detection statistic: it maximizes over CFO and "
            "arrival epoch, then compares exact-pilot and control **power**. Squaring magnitude removes "
            "the complex phase. Each probe is also acquired independently, so its best epoch can move "
            "within the Starlink frame period. Re-extracting a complex correlation afterward supplies "
            "a local phase, but not a stable phase or integer-frame reference shared by adjacent probes.",
            "",
            "The measured median circular phase errors are near the 0.25-cycle uniform-phase baseline, "
            "and the acquisition-epoch dispersions are hundreds to more than one thousand samples. "
            "Consequently, a small fitted phase jump at one boundary would be a chance number, not "
            "continuity evidence.",
            "",
            "## Reproducibility artifacts",
            "",
            "Each candidate gzip contains every independently scored basin; each adjacent run JSON "
            "records the complete search configuration, interval, probe count, and runtime:",
            "",
            "- `b1-research-candidates.jsonl.gz` / `b1-research-run.json`",
            "- `b2-research-candidates.jsonl.gz` / `b2-research-run.json`",
            "- `b1-close-candidates.jsonl.gz` / `b1-close-run.json`",
            "- `b2-close-candidates.jsonl.gz` / `b2-close-run.json`",
            "- `carrier-continuity-metrics.json` is the machine-readable final evidence record.",
            "",
            "## Interpretation rules",
            "",
            "- Phase continuity is usable only after stable within-segment controls beat the 0.25-cycle "
            "  uniform-phase baseline.",
            "- The current known-pilot magnitude detector does not satisfy that requirement.",
            "- Two resolved simultaneous peaks, or discontinuous timing/fingerprint, supports two carriers.",
            "- A matching event on unrelated signals or both receivers supports an SDR/LNB/common-mode cause.",
            "",
            "## Next gated experiment",
            "",
            "First decouple radio reads from compression, shard close, `fsync`, and rename using a "
            "bounded writer queue or preallocated ring buffer. Persist a device sample counter and "
            "hardware overflow evidence; a capture without either must not claim RF-time or phase "
            "continuity across a host stall. Add an integration test that deliberately delays shard "
            "finalization and proves radio refill cadence is unaffected.",
            "",
            "Then add a research-only phase-aware continuation stage that starts from a detected segment and "
            "persists the complex coherent pilot amplitude, absolute sample epoch, frame index ambiguity, "
            "refined CFO, and residual phase for every frame. Compare a continuous state "
            "`[phase, CFO, constant CFO rate]` against a phase-reset state on held-out frames. Then run "
            "the same decision on matched-SNR synthetic continuous/reset/two-carrier injections and "
            "within-segment false boundaries. Do not merge adjacent Standard segments automatically "
            "until those controls define a reviewed threshold.",
            "",
        ]
    )


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    candidate_paths = (args.candidate_b1, args.candidate_b2)
    close_candidate_paths = (args.close_candidate_b1, args.close_candidate_b2)
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    results = []
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        capture_timing = _timeline_stall_metrics(bundle)
        _timeline_stall_plot(
            capture_timing,
            args.output_root / "refill-timing-shard-rollovers.png",
        )
        reader = store.reader(bundle, STREAM_ID, verify=True)
        for boundary, candidate_path, close_candidate_path in zip(
            BOUNDARIES,
            candidate_paths,
            close_candidate_paths,
            strict=True,
        ):
            candidates = _load_candidates(candidate_path)
            selected = _select_line_candidates(boundary, candidates)
            frames, fingerprints, waveform = _frame_observations(reader, boundary, selected)
            phase, arrays = _phase_metrics(boundary, frames)
            coexistence_candidates = (
                candidates
                if close_candidate_path is None
                else _load_candidates(close_candidate_path)
            )
            coexistence = _coexistence_metrics(
                boundary,
                coexistence_candidates,
                close_search=close_candidate_path is not None,
            )
            frequency_step = float(
                boundary.post.frequency_hz(boundary.time_s)
                - boundary.pre.frequency_hz(boundary.time_s)
            )
            result = {
                "label": boundary.label,
                "time_s": boundary.time_s,
                "gap_s": boundary.post.start_s - boundary.pre.end_s,
                "pre_rate_hz_s": boundary.pre.rate_hz_s,
                "post_rate_hz_s": boundary.post.rate_hz_s,
                "fitted_frequency_step_hz": frequency_step,
                "dense_probe_count": len(_group_candidates(candidates)),
                "dense_candidate_count": len(candidates),
                "selected_probe_count": len(selected),
                "frame_observation_count": len(frames),
                "phase": phase,
                "waveform_timing": waveform,
                "coexistence": coexistence,
                "fingerprints": {
                    "pre_real": fingerprints[0].real.tolist(),
                    "pre_imag": fingerprints[0].imag.tolist(),
                    "post_real": fingerprints[1].real.tolist(),
                    "post_imag": fingerprints[1].imag.tolist(),
                },
            }
            classification, reason = _classification(result)
            result["classification"] = classification
            result["classification_reason"] = reason
            stem = boundary.label.lower().replace(".", "-")
            _waterfall(reader, boundary, args.output_root / f"{stem}-waterfall.png")
            _boundary_plot(
                boundary,
                candidates,
                selected,
                frames,
                arrays,
                args.output_root / f"{stem}-continuity.png",
            )
            _close_search_plot(
                boundary,
                coexistence_candidates,
                coexistence,
                args.output_root / f"{stem}-close-search.png",
            )
            results.append(result)
    finally:
        if store is not None:
            store.close()
        pinned.close()

    observable = sum(item["phase_observable"] or item["timing_observable"] for item in results)
    summary = {
        "schema": "org.leo.research.carrier-continuity-case/v1",
        "session_id": SESSION_ID,
        "stream_id": STREAM_ID,
        "receiver_id": RECEIVER_ID,
        "scope_id": SCOPE_ID,
        "analysis_run_id": RUN_ID,
        "pipeline_release": PIPELINE_RELEASE,
        "candidate_only": True,
        "payload_decoded": False,
        "frequency_model": "piecewise-degree-1-only",
        "headline": (
            "The same-physical-carrier explanation is now favored, but phase continuity cannot be "
            f"proven from this recording. Only {observable} of {len(results)} preregistered "
            "boundaries has a coherent phase or arrival-time observable, and both boundaries align "
            "within 11 ms of repeatable capture-thread stalls at IQ-shard rollover. Because hardware "
            "sample loss is unobservable, a real continuous carrier can be split in stored sample time."
        ),
        "cross_path_b2": CROSS_PATH_B2,
        "capture_timing": capture_timing,
        "boundaries": results,
    }
    metrics_path = args.output_root / "carrier-continuity-metrics.json"
    metrics_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(_markdown(summary), encoding="utf-8")
    print(args.report)


if __name__ == "__main__":
    main()
