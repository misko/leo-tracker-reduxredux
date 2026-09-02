#!/usr/bin/env python3
"""Render the 6f8ad3b4fb91 native-PSS versus dual-GLRT deep-dive figures.

The tool consumes only persisted Standard-analysis products.  It does not read IQ,
rerun acquisition, or use one observable to select the other.  Its cross-stream
operations are presentation and diagnostic fits on already-persisted evidence.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

CAPTURE_ID = "cap-20260902T134107-6f8ad3b4fb91"
ANALYSIS_RUN_ID = "reprocess-31d8aeb5a7f547b9a29aa04949c9d88c"
FRAME_RATE_HZ = 750.0
PSS_COLOR = "#f97316"
RX_COLORS = {0: "#0891b2", 1: "#2563eb"}
LOCKLET_COLORS = (
    "#2563eb",
    "#7c3aed",
    "#0891b2",
    "#be123c",
    "#16a34a",
    "#d97706",
    "#db2777",
    "#4f46e5",
)

Json = dict[str, Any]
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class QuadraticFit:
    reference_s: float
    coefficients_descending: tuple[float, float, float]
    residuals_s: FloatArray

    def evaluate(self, times_s: FloatArray | float) -> FloatArray:
        values = np.asarray(times_s, dtype=float)
        return np.polyval(self.coefficients_descending, values - self.reference_s)

    @property
    def rms_us(self) -> float:
        return float(np.sqrt(np.mean(self.residuals_s**2)) * 1e6)


@dataclass(frozen=True, slots=True)
class PiecewiseFit:
    split_index: int
    split_time_s: float
    left: QuadraticFit
    right: QuadraticFit

    @property
    def rms_us(self) -> float:
        residuals = np.concatenate((self.left.residuals_s, self.right.residuals_s))
        return float(np.sqrt(np.mean(residuals**2)) * 1e6)

    @property
    def step_us(self) -> float:
        right = float(self.right.evaluate(self.split_time_s))
        left = float(self.left.evaluate(self.split_time_s))
        return (right - left) * 1e6


@dataclass(frozen=True, slots=True)
class PssTrackData:
    product: Json
    track: Json
    modes: tuple[Json, ...]
    times_s: FloatArray
    phases_s: FloatArray


@dataclass(frozen=True, slots=True)
class EventLocklet:
    product: Json
    locklet: Json
    high_times_s: FloatArray
    phases_s: FloatArray
    piecewise: PiecewiseFit


def _load_json(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return value


def select_primary_pss_track(product: Json) -> Json:
    """Apply the production blind-track presentation ranking."""

    candidates = [
        track for track in product["tracks"] if track.get("origin") == "independent_blind"
    ]
    if not candidates:
        raise ValueError("PSS product has no independent blind timing track")
    return max(
        candidates,
        key=lambda track: (
            len(track["mode_ids"]),
            track["time_stop_s"] - track["time_start_s"],
            -track["rms_residual_us"],
            track["track_id"],
        ),
    )


def reconstruct_pss_track(product: Json, track: Json) -> PssTrackData:
    modes_by_id = {mode["mode_id"]: mode for mode in product["modes"]}
    modes = tuple(modes_by_id[mode_id] for mode_id in track["mode_ids"])
    times_s = np.asarray([mode["center_time_s"] for mode in modes], dtype=float)
    if np.any(np.diff(times_s) <= 0):
        raise ValueError("PSS track modes are not strictly time ordered")
    model_s = np.polyval(
        np.asarray(track["coefficients_descending_s"], dtype=float),
        times_s - float(track["time_origin_s"]),
    )
    phases_s = model_s + np.asarray(track["residuals_us"], dtype=float) * 1e-6
    return PssTrackData(product, track, modes, times_s, phases_s)


def quadratic_fit(times_s: FloatArray, values_s: FloatArray) -> QuadraticFit:
    if len(times_s) < 3 or len(times_s) != len(values_s):
        raise ValueError("quadratic fit requires at least three paired values")
    reference_s = float(np.mean(times_s))
    coefficients = np.polyfit(times_s - reference_s, values_s, 2)
    residuals = values_s - np.polyval(coefficients, times_s - reference_s)
    return QuadraticFit(
        reference_s=reference_s,
        coefficients_descending=tuple(float(value) for value in coefficients),
        residuals_s=residuals,
    )


def best_piecewise_quadratic(
    times_s: FloatArray,
    values_s: FloatArray,
    *,
    minimum_side_points: int,
) -> PiecewiseFit:
    """Find the minimum-RSS discontinuous two-quadratic description."""

    if len(times_s) < 2 * minimum_side_points:
        raise ValueError("piecewise fit has insufficient samples")
    best: tuple[float, PiecewiseFit] | None = None
    for split_index in range(minimum_side_points, len(times_s) - minimum_side_points + 1):
        left = quadratic_fit(times_s[:split_index], values_s[:split_index])
        right = quadratic_fit(times_s[split_index:], values_s[split_index:])
        split_time_s = float((times_s[split_index - 1] + times_s[split_index]) / 2.0)
        candidate = PiecewiseFit(split_index, split_time_s, left, right)
        rss = float(np.sum(left.residuals_s**2) + np.sum(right.residuals_s**2))
        if best is None or rss < best[0]:
            best = (rss, candidate)
    if best is None:  # pragma: no cover - guarded by the length check
        raise AssertionError("piecewise search produced no candidate")
    return best[1]


def _fit_at_boundary(
    times_s: FloatArray,
    values_s: FloatArray,
    boundary_s: float,
    *,
    minimum_side_points: int,
) -> PiecewiseFit:
    split_index = int(np.searchsorted(times_s, boundary_s))
    if split_index < minimum_side_points or len(times_s) - split_index < minimum_side_points:
        raise ValueError("fixed boundary leaves insufficient support")
    return PiecewiseFit(
        split_index=split_index,
        split_time_s=boundary_s,
        left=quadratic_fit(times_s[:split_index], values_s[:split_index]),
        right=quadratic_fit(times_s[split_index:], values_s[split_index:]),
    )


def _complete_locklets(product: Json) -> list[Json]:
    return [
        locklet
        for locklet in product["locklets"]
        if locklet["status"] == "complete"
        and locklet.get("linear_fit") is not None
        and locklet.get("quadratic_fit") is not None
    ]


def _inlier_observations(locklet: Json) -> list[Json]:
    return sorted(
        [row for row in locklet["observations"] if row["epoch_fit_inlier"]],
        key=lambda row: row["global_center_time_s"],
    )


def _first_estimate_s(product: Json) -> float:
    return float(product["source"]["timing"]["first_estimate_utc_ns"]) * 1e-9


def _high_time_offset_s(product: Json, pss: Json) -> float:
    return _first_estimate_s(product) - _first_estimate_s(pss)


def _find_event_locklet(product: Json, pss: Json, event_high_s: float) -> EventLocklet:
    local_boundary_s = event_high_s - _high_time_offset_s(product, pss)
    candidates: list[tuple[int, Json, list[Json]]] = []
    for locklet in _complete_locklets(product):
        observations = _inlier_observations(locklet)
        if not observations:
            continue
        if (
            observations[0]["global_center_time_s"]
            < local_boundary_s
            < observations[-1]["global_center_time_s"]
        ):
            candidates.append((len(observations), locklet, observations))
    if not candidates:
        raise ValueError(
            f"RX{product['source']['receiver_id']} has no complete locklet spanning the event"
        )
    _, locklet, observations = max(candidates, key=lambda item: item[0])
    local_times_s = np.asarray([row["global_center_time_s"] for row in observations], dtype=float)
    high_times_s = local_times_s + _high_time_offset_s(product, pss)
    phases_s = np.asarray([row["unwrapped_frame_phase_s"] for row in observations])
    piecewise = _fit_at_boundary(
        high_times_s,
        phases_s,
        event_high_s,
        minimum_side_points=12,
    )
    return EventLocklet(product, locklet, high_times_s, phases_s, piecewise)


def _timing_uncertainty_us(product: Json) -> float:
    timing = product["source"]["timing"]
    return (float(timing["first_latest_utc_ns"]) - float(timing["first_earliest_utc_ns"])) / 2e3


def _alias_statistics(product: Json) -> Json:
    transitions: list[tuple[float, float, float]] = []
    steady_timing_jumps_us: list[float] = []
    by_locklet: list[Json] = []
    for locklet in _complete_locklets(product):
        observations = _inlier_observations(locklet)
        locklet_transitions = 0
        for before, after in zip(observations, observations[1:], strict=False):
            timing_jump_us = abs(
                (after["quadratic_residual_s"] - before["quadratic_residual_s"]) * 1e6
            )
            if before["hough_alias_index"] != after["hough_alias_index"]:
                transitions.append(
                    (
                        abs(after["raw_cfo_hz"] - before["raw_cfo_hz"]),
                        abs(after["canonical_cfo_hz"] - before["canonical_cfo_hz"]),
                        timing_jump_us,
                    )
                )
                locklet_transitions += 1
            else:
                steady_timing_jumps_us.append(timing_jump_us)
        by_locklet.append(
            {
                "hough_label": locklet["source_hough_track_label"],
                "locklet_index": locklet["locklet_index"],
                "transition_count": locklet_transitions,
            }
        )
    transition_values = np.asarray(transitions, dtype=float)
    return {
        "transition_count": len(transitions),
        "median_absolute_raw_cfo_jump_hz": (
            None if not transitions else float(np.median(transition_values[:, 0]))
        ),
        "median_absolute_canonical_cfo_jump_hz": (
            None if not transitions else float(np.median(transition_values[:, 1]))
        ),
        "median_absolute_timing_residual_jump_us": (
            None if not transitions else float(np.median(transition_values[:, 2]))
        ),
        "median_steady_absolute_timing_residual_jump_us": (
            None if not steady_timing_jumps_us else float(np.median(steady_timing_jumps_us))
        ),
        "by_locklet": by_locklet,
        "_transition_values": transitions,
    }


def _rate_statistics(product: Json, pss: Json, start_s: float, stop_s: float) -> Json:
    rates_hz_s: list[float] = []
    for locklet in _complete_locklets(product):
        selection = locklet["cfo_selection"]
        coefficients = selection.get("quadratic_coefficients_hz")
        reference_s = selection.get("reference_time_s")
        if coefficients is None or reference_s is None:
            continue
        _, linear_rate, curvature = (float(value) for value in coefficients)
        for row in _inlier_observations(locklet):
            high_time_s = row["global_center_time_s"] + _high_time_offset_s(product, pss)
            if start_s <= high_time_s <= stop_s:
                rates_hz_s.append(
                    linear_rate + curvature * (float(row["global_center_time_s"]) - reference_s)
                )
    if not rates_hz_s:
        raise ValueError("no GLRT rate support overlaps the PSS track")
    return {
        "support_point_count": len(rates_hz_s),
        "mean_hz_s": float(np.mean(rates_hz_s)),
        "median_hz_s": float(np.median(rates_hz_s)),
    }


def _continuity_at_event(pss: Json, event_s: float) -> Json:
    sample_rate_hz = float(pss["source"]["sample_rate_hz"])
    for segment in pss["source"]["continuity_segments"]:
        start_s = float(segment["device_sample_start"]) / sample_rate_hz
        stop_s = float(segment["device_sample_stop"]) / sample_rate_hz
        if start_s <= event_s <= stop_s:
            return {
                "segment_index": segment["segment_index"],
                "start_s": start_s,
                "stop_s": stop_s,
                "distance_from_start_s": event_s - start_s,
                "distance_to_stop_s": stop_s - event_s,
            }
    raise ValueError("PSS event does not lie in an observed continuity segment")


def _adjacent_event_state(event: EventLocklet, event_s: float) -> Json:
    observations = _inlier_observations(event.locklet)
    # EventLocklet.high_times_s already carries the cross-stream first-sample offset.  Preserve
    # the observation pairing here instead of recomputing it from rounded UTC floats.
    paired = list(zip(event.high_times_s, observations, strict=True))
    before_time_s, before = max(
        (pair for pair in paired if pair[0] < event_s),
        key=lambda pair: pair[0],
    )
    after_time_s, after = min(
        (pair for pair in paired if pair[0] >= event_s),
        key=lambda pair: pair[0],
    )
    return {
        "before_time_s": float(before_time_s),
        "after_time_s": float(after_time_s),
        "before_alias_index": before["hough_alias_index"],
        "after_alias_index": after["hough_alias_index"],
        "raw_cfo_jump_hz": float(after["raw_cfo_hz"] - before["raw_cfo_hz"]),
        "canonical_cfo_jump_hz": float(after["canonical_cfo_hz"] - before["canonical_cfo_hz"]),
        "quadratic_timing_residual_jump_us": float(
            (after["quadratic_residual_s"] - before["quadratic_residual_s"]) * 1e6
        ),
    }


def build_summary(
    pss: Json,
    glrt_products: list[Json],
) -> tuple[Json, PssTrackData, list[EventLocklet]]:
    session_ids = {
        pss["source"]["session_id"],
        *(product["source"]["session_id"] for product in glrt_products),
    }
    if session_ids != {CAPTURE_ID}:
        raise ValueError(f"unexpected or crossed sessions: {sorted(session_ids)}")
    if int(pss["source"]["sample_rate_hz"]) != 25_000_000:
        raise ValueError("PSS evidence is not native 25 MS/s")
    receiver_ids = {int(product["source"]["receiver_id"]) for product in glrt_products}
    if receiver_ids != {0, 1}:
        raise ValueError("exactly one RX0 and one RX1 GLRT epoch product are required")
    if any(int(product["source"]["sample_rate_hz"]) != 2_500_000 for product in glrt_products):
        raise ValueError("GLRT epoch evidence is not 2.5 MS/s")

    pss_data = reconstruct_pss_track(pss, select_primary_pss_track(pss))
    piecewise = best_piecewise_quadratic(
        pss_data.times_s,
        pss_data.phases_s,
        minimum_side_points=24,
    )
    event_locklets = [
        _find_event_locklet(product, pss, piecewise.split_time_s)
        for product in sorted(glrt_products, key=lambda value: value["source"]["receiver_id"])
    ]
    rf_reference_hz = float(np.median([product["rf_reference_hz"] for product in glrt_products]))
    pss_curvature_s_s2 = 2.0 * float(pss_data.track["coefficients_descending_s"][0])
    pss_physical_rate_hz_s = -rf_reference_hz * pss_curvature_s_s2
    event_utc_s = _first_estimate_s(pss) + piecewise.split_time_s
    event_left_utc_s = _first_estimate_s(pss) + float(pss_data.times_s[piecewise.split_index - 1])
    event_right_utc_s = _first_estimate_s(pss) + float(pss_data.times_s[piecewise.split_index])

    block_lengths = {
        int(block["input_device_sample_stop"]) - int(block["input_device_sample_start"])
        for block in pss["blocks"]
    }
    if len(block_lengths) != 1:
        raise ValueError(f"PSS blocks have inconsistent input lengths: {sorted(block_lengths)}")
    starts = sorted(int(block["input_device_sample_start"]) for block in pss["blocks"])
    positive_strides = [
        right - left for left, right in zip(starts, starts[1:], strict=False) if right > left
    ]
    nominal_stride_samples = min(positive_strides)
    alias_by_receiver: Json = {}
    rate_by_receiver: Json = {}
    locklet_inventory: Json = {}
    quantization_rms_us = 1e6 / (2_500_000.0 * math.sqrt(12.0))
    for product in sorted(glrt_products, key=lambda value: value["source"]["receiver_id"]):
        receiver_id = int(product["source"]["receiver_id"])
        key = f"RX{receiver_id}"
        alias = _alias_statistics(product)
        alias_by_receiver[key] = {name: value for name, value in alias.items() if name[0] != "_"}
        rate_by_receiver[key] = _rate_statistics(
            product,
            pss,
            float(pss_data.times_s[0]),
            float(pss_data.times_s[-1]),
        )
        locklet_inventory[key] = [
            {
                "hough_label": locklet["source_hough_track_label"],
                "locklet_index": locklet["locklet_index"],
                "point_count": locklet["quadratic_fit"]["point_count"],
                "start_s": locklet["global_start_time_s"],
                "stop_s": locklet["global_end_time_s"],
                "quadratic_rms_us": locklet["quadratic_fit"]["residual_rms_s"] * 1e6,
                "rms_over_integer_quantization_floor": (
                    locklet["quadratic_fit"]["residual_rms_s"] * 1e6 / quantization_rms_us
                ),
            }
            for locklet in _complete_locklets(product)
        ]

    event_by_receiver = {
        f"RX{event.product['source']['receiver_id']}": {
            "hough_label": event.locklet["source_hough_track_label"],
            "locklet_index": event.locklet["locklet_index"],
            "point_count": len(event.high_times_s),
            "global_quadratic_rms_us": event.locklet["quadratic_fit"]["residual_rms_s"] * 1e6,
            "fixed_event_piecewise_quadratic_rms_us": event.piecewise.rms_us,
            "fitted_step_us": event.piecewise.step_us,
            "adjacent_observations": _adjacent_event_state(event, piecewise.split_time_s),
        }
        for event in event_locklets
    }
    adjacent_pss_modes = (
        pss_data.modes[piecewise.split_index - 1],
        pss_data.modes[piecewise.split_index],
    )
    summary: Json = {
        "schema_version": 1,
        "analysis_kind": "6f8ad3b4fb91-pss-glrt-deep-dive",
        "capture_id": CAPTURE_ID,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "source_product_digests": {
            "pss_result": pss["result_digest"],
            **{
                f"glrt_epoch_RX{product['source']['receiver_id']}": product["result_digest"]
                for product in glrt_products
            },
        },
        "configuration": {
            "pss_sample_rate_hz": pss["source"]["sample_rate_hz"],
            "pss_decimation_factor": pss["projections"][0]["decimation_factor"],
            "pss_window_ms": next(iter(block_lengths)) / 25_000.0,
            "pss_stride_ms": nominal_stride_samples / 25_000.0,
            "glrt_sample_rate_hz": 2_500_000,
            "glrt_window_ms": 20,
            "glrt_stride_ms": 10,
            "glrt_epoch_sample_spacing_us": 0.4,
            "glrt_integer_epoch_uniform_quantization_rms_us": quantization_rms_us,
        },
        "pss_track_inventory": {
            "track_count": len(pss["tracks"]),
            "mode_counts": [len(track["mode_ids"]) for track in pss["tracks"]],
            "selected_track_id": pss_data.track["track_id"],
            "selected_mode_count": len(pss_data.modes),
            "selected_start_s": float(pss_data.times_s[0]),
            "selected_stop_s": float(pss_data.times_s[-1]),
            "global_quadratic_rms_us": pss_data.track["rms_residual_us"],
        },
        "frequency_sign": {
            "common_rf_reference_hz": rf_reference_hz,
            "pss_timing_curvature_s_s2": pss_curvature_s_s2,
            "pss_physical_minus_sign_rate_hz_s": pss_physical_rate_hz_s,
            "pss_same_coordinate_rate_hz_s": -pss_physical_rate_hz_s,
            "glrt_overlap_rate": rate_by_receiver,
            "interpretation": (
                "The current physical arrival-delay minus sign mirrors the observed IQ CFO sign. "
                "The same-coordinate PSS derivative agrees in sign and scale, but absolute RF/IQ "
                "sign remains uncalibrated."
            ),
        },
        "timing_event": {
            "pss_split_left_s": float(pss_data.times_s[piecewise.split_index - 1]),
            "pss_split_right_s": float(pss_data.times_s[piecewise.split_index]),
            "pss_split_midpoint_s": piecewise.split_time_s,
            "utc_bracket": [
                datetime.fromtimestamp(event_left_utc_s, UTC).isoformat(timespec="microseconds"),
                datetime.fromtimestamp(event_right_utc_s, UTC).isoformat(timespec="microseconds"),
            ],
            "utc_midpoint": datetime.fromtimestamp(event_utc_s, UTC).isoformat(
                timespec="microseconds"
            ),
            "pss_global_quadratic_rms_us": pss_data.track["rms_residual_us"],
            "pss_piecewise_quadratic_rms_us": piecewise.rms_us,
            "pss_fitted_step_us": piecewise.step_us,
            "pss_adjacent_mode_state": [
                {
                    "center_time_s": mode["center_time_s"],
                    "nominal_frequency_offset_hz": mode["nominal_frequency_offset_hz"],
                    "selected_frequency_offset_hz": mode["selected_frequency_offset_hz"],
                    "robust_z": mode["robust_z"],
                    "strong_window_count": mode["strong_window_count"],
                    "window_count": mode["window_count"],
                }
                for mode in adjacent_pss_modes
            ],
            "glrt": event_by_receiver,
            "native25_continuity": _continuity_at_event(pss, piecewise.split_time_s),
            "first_sample_half_width_uncertainty_us": {
                "native25": _timing_uncertainty_us(pss),
                **{
                    f"RX{product['source']['receiver_id']}": _timing_uncertainty_us(product)
                    for product in glrt_products
                },
            },
        },
        "glrt_locklets": locklet_inventory,
        "cfo_alias_transitions": alias_by_receiver,
        "conclusions": [
            "The apparent frequency-sign opposition is a convention/calibration issue, not a "
            "timing-fit sign reversal.",
            "Most GLRT quadratic residual RMS values sit at the 2.5 MS/s integer-epoch "
            "quantization floor.",
            "Raw CFO alias jumps are removed by canonicalization and do not create comparable "
            "epoch jumps.",
            "A common approximately 1.0 to 1.1 microsecond timing-state step appears in PSS and "
            "both GLRT receivers inside continuous capture support.",
            "Multiple GLRT arcs are separately fitted Hough locklets; the production comparison "
            "shows only one selected PSS track even though five were persisted.",
        ],
    }
    return summary, pss_data, event_locklets


def _plot_sign_audit(
    destination: Path,
    pss_data: PssTrackData,
    glrt_products: list[Json],
    summary: Json,
) -> None:
    figure, axis = plt.subplots(figsize=(13, 6), constrained_layout=True)
    start_s = float(pss_data.times_s[0])
    stop_s = float(pss_data.times_s[-1])
    seen_receivers: set[int] = set()
    for product in sorted(glrt_products, key=lambda value: value["source"]["receiver_id"]):
        receiver_id = int(product["source"]["receiver_id"])
        color = RX_COLORS[receiver_id]
        for locklet in _complete_locklets(product):
            selection = locklet["cfo_selection"]
            coefficients = selection.get("quadratic_coefficients_hz")
            reference_s = selection.get("reference_time_s")
            if coefficients is None or reference_s is None:
                continue
            observations = _inlier_observations(locklet)
            high_times = np.asarray(
                [
                    row["global_center_time_s"] + _high_time_offset_s(product, pss_data.product)
                    for row in observations
                ]
            )
            keep = (high_times >= start_s) & (high_times <= stop_s)
            if np.count_nonzero(keep) < 3:
                continue
            local = np.asarray([row["global_center_time_s"] for row in observations], dtype=float)[
                keep
            ]
            rates = float(coefficients[1]) + float(coefficients[2]) * (local - reference_s)
            label = (
                f"2.5 MS/s GLRT RX{receiver_id} locklets"
                if receiver_id not in seen_receivers
                else None
            )
            axis.plot(high_times[keep], rates / 1e3, color=color, alpha=0.35, lw=1.2, label=label)
            seen_receivers.add(receiver_id)
    physical = summary["frequency_sign"]["pss_physical_minus_sign_rate_hz_s"] / 1e3
    same = summary["frequency_sign"]["pss_same_coordinate_rate_hz_s"] / 1e3
    axis.hlines(
        physical,
        start_s,
        stop_s,
        color=PSS_COLOR,
        lw=2.5,
        label=f"PSS physical arrival-delay sign: {physical:+.3f} kHz/s",
    )
    axis.hlines(
        same,
        start_s,
        stop_s,
        color=PSS_COLOR,
        lw=2.5,
        ls="--",
        label=f"PSS same observed-coordinate sign: {same:+.3f} kHz/s",
    )
    for receiver in (0, 1):
        stats = summary["frequency_sign"]["glrt_overlap_rate"][f"RX{receiver}"]
        axis.text(
            0.012,
            0.04 + receiver * 0.055,
            f"RX{receiver} support-weighted mean {stats['mean_hz_s'] / 1e3:+.3f} kHz/s; "
            f"median {stats['median_hz_s'] / 1e3:+.3f} kHz/s",
            color=RX_COLORS[receiver],
            transform=axis.transAxes,
        )
    axis.axhline(0, color="#111827", lw=0.8)
    axis.grid(True, alpha=0.25)
    axis.set_xlim(start_s, stop_s)
    axis.set_xlabel("Seconds from native 25 MS/s stream start")
    axis.set_ylabel("Instantaneous frequency rate (kHz/s)")
    axis.set_title("Frequency-sign audit: persisted PSS physical sign mirrors observed-IQ GLRT CFO")
    axis.legend(loc="upper right", fontsize=9)
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _prefit_residual(
    times_s: FloatArray,
    values_s: FloatArray,
    event_s: float,
    *,
    lookback_s: float = 4.0,
) -> FloatArray:
    pre = (times_s >= event_s - lookback_s) & (times_s < event_s)
    fit = quadratic_fit(times_s[pre], values_s[pre])
    return (values_s - fit.evaluate(times_s)) * 1e6


def _plot_timing_event(
    destination: Path,
    pss_data: PssTrackData,
    event_locklets: list[EventLocklet],
    summary: Json,
) -> None:
    event_s = float(summary["timing_event"]["pss_split_midpoint_s"])
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        constrained_layout=True,
        gridspec_kw={"height_ratios": (1.1, 1.4, 0.7)},
    )
    axes[0].scatter(
        pss_data.times_s,
        np.asarray(pss_data.track["residuals_us"]),
        s=18,
        marker="x",
        color=PSS_COLOR,
    )
    axes[0].axvspan(
        summary["timing_event"]["pss_split_left_s"],
        summary["timing_event"]["pss_split_right_s"],
        color="#fbbf24",
        alpha=0.25,
        label="best PSS split bracket",
    )
    axes[0].set_ylabel("PSS global-quadratic\nresidual (µs)")
    axes[0].set_title(
        f"A · Global PSS fit bridges a timing step; RMS "
        f"{summary['timing_event']['pss_global_quadratic_rms_us']:.3f} µs"
    )
    axes[0].legend(loc="upper left")

    zoom = 2.5
    pss_keep = (pss_data.times_s >= event_s - zoom) & (pss_data.times_s <= event_s + zoom)
    pss_detrended = _prefit_residual(pss_data.times_s, pss_data.phases_s, event_s)
    axes[1].scatter(
        pss_data.times_s[pss_keep],
        pss_detrended[pss_keep],
        s=28,
        marker="x",
        color=PSS_COLOR,
        label=(
            f"native-25 PSS · fitted step {summary['timing_event']['pss_fitted_step_us']:+.3f} µs"
        ),
        zorder=4,
    )
    for event in event_locklets:
        receiver_id = int(event.product["source"]["receiver_id"])
        keep = (event.high_times_s >= event_s - zoom) & (event.high_times_s <= event_s + zoom)
        detrended = _prefit_residual(event.high_times_s, event.phases_s, event_s)
        event_summary = summary["timing_event"]["glrt"][f"RX{receiver_id}"]
        axes[1].scatter(
            event.high_times_s[keep],
            detrended[keep],
            s=9,
            alpha=0.55,
            color=RX_COLORS[receiver_id],
            label=(
                f"2.5 GLRT RX{receiver_id} {event.locklet['source_hough_track_label']}/"
                f"L{event.locklet['locklet_index']} · step "
                f"{event_summary['fitted_step_us']:+.3f} µs"
            ),
        )
    axes[1].set_xlim(event_s - zoom, event_s + zoom)
    axes[1].set_ylabel("Residual from independent\npre-event quadratic (µs)")
    axes[1].set_title(
        "B · Separately fitted observable paths show the same approximately 1.1 µs state step"
    )
    axes[1].legend(loc="upper left", fontsize=8)

    pss = pss_data.product
    high_rate = float(pss["source"]["sample_rate_hz"])
    rows = [("native-25 PSS", pss, 2.0)] + [
        (f"2.5 GLRT RX{product['source']['receiver_id']}", product, 1.0 - index)
        for index, product in enumerate(
            sorted(
                [event.product for event in event_locklets],
                key=lambda value: value["source"]["receiver_id"],
            )
        )
    ]
    for label, product, y in rows:
        sample_rate = float(product["source"]["sample_rate_hz"])
        offset = _high_time_offset_s(product, pss)
        first = True
        for segment in product["source"]["continuity_segments"]:
            start = float(segment["device_sample_start"]) / sample_rate + offset
            stop = float(segment["device_sample_stop"]) / sample_rate + offset
            if stop < event_s - zoom or start > event_s + zoom:
                continue
            axes[2].plot(
                [start, stop],
                [y, y],
                lw=9,
                solid_capstyle="butt",
                color=(
                    PSS_COLOR
                    if sample_rate == high_rate
                    else RX_COLORS[int(product["source"]["receiver_id"])]
                ),
                label=label if first else None,
            )
            first = False
    continuity = summary["timing_event"]["native25_continuity"]
    axes[2].scatter(
        [continuity["start_s"], continuity["stop_s"]],
        [2.0, 2.0],
        marker="|",
        s=180,
        color="#111827",
        label=(
            f"native-25 segment {continuity['segment_index']} boundaries "
            f"({continuity['distance_from_start_s']:.3f} s before / "
            f"{continuity['distance_to_stop_s']:.3f} s after event)"
        ),
    )
    axes[2].set_yticks([])
    axes[2].set_xlim(event_s - zoom, event_s + zoom)
    axes[2].set_xlabel("Seconds from native 25 MS/s stream start")
    axes[2].set_title("C · The event is inside counter-continuous support, not at a block boundary")
    axes[2].legend(loc="lower left", fontsize=8, ncol=2)
    for axis in axes:
        axis.axvline(event_s, color="#111827", ls="--", lw=1.1)
        axis.grid(True, alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · common timing-state discontinuity near "
        f"{summary['timing_event']['utc_midpoint']}"
    )
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_quantization_and_alias(
    destination: Path,
    pss: Json,
    glrt_products: list[Json],
    summary: Json,
) -> None:
    quantization_floor = summary["configuration"]["glrt_integer_epoch_uniform_quantization_rms_us"]
    normal_candidates: list[tuple[float, Json, Json]] = []
    for product in glrt_products:
        for locklet in _complete_locklets(product):
            point_count = int(locklet["quadratic_fit"]["point_count"])
            rms_us = float(locklet["quadratic_fit"]["residual_rms_s"]) * 1e6
            if point_count >= 200:
                normal_candidates.append((abs(rms_us - quantization_floor), product, locklet))
    _, representative_product, representative = min(normal_candidates, key=lambda item: item[0])
    observations = _inlier_observations(representative)
    times_s = np.asarray(
        [
            row["global_center_time_s"] + _high_time_offset_s(representative_product, pss)
            for row in observations
        ]
    )
    residuals_us = np.asarray([row["quadratic_residual_s"] * 1e6 for row in observations])
    parity = np.asarray([row["opportunity_index"] % 2 for row in observations])

    figure = plt.figure(figsize=(14, 10), constrained_layout=True)
    grid = figure.add_gridspec(2, 2, height_ratios=(1.2, 1.0))
    top = figure.add_subplot(grid[0, :])
    lower_left = figure.add_subplot(grid[1, 0])
    lower_right = figure.add_subplot(grid[1, 1])
    receiver_id = int(representative_product["source"]["receiver_id"])
    parity_styles = (
        (0, "#2563eb", "even 10 ms epoch"),
        (1, "#a855f7", "odd 10 ms epoch"),
    )
    for value, color, label in parity_styles:
        keep = parity == value
        top.scatter(times_s[keep], residuals_us[keep], s=11, alpha=0.72, color=color, label=label)
    top.axhspan(-0.2, 0.2, color="#94a3b8", alpha=0.12, label="±0.5 input sample")
    top.axhline(0, color="#111827", lw=0.8)
    top.set_ylabel("Quadratic timing residual (µs)")
    top.set_xlabel("Seconds from native 25 MS/s stream start")
    top.set_title(
        f"A · Representative quantization-limited locklet: RX{receiver_id} "
        f"{representative['source_hough_track_label']}/L{representative['locklet_index']} · "
        f"RMS {representative['quadratic_fit']['residual_rms_s'] * 1e6:.3f} µs"
    )
    top.legend(loc="upper right")
    top.grid(True, alpha=0.22)

    labels: list[str] = []
    rms_values: list[float] = []
    colors: list[str] = []
    for receiver in (0, 1):
        for row in summary["glrt_locklets"][f"RX{receiver}"]:
            labels.append(f"RX{receiver}\n{row['hough_label']}/L{row['locklet_index']}")
            rms_values.append(row["quadratic_rms_us"])
            colors.append(RX_COLORS[receiver])
    indexes = np.arange(len(labels))
    lower_left.bar(indexes, rms_values, color=colors, alpha=0.8)
    lower_left.axhline(
        quantization_floor,
        color="#111827",
        ls="--",
        label=f"integer-sample uniform floor {quantization_floor:.3f} µs",
    )
    lower_left.set_xticks(indexes, labels, fontsize=7)
    lower_left.set_ylabel("Quadratic residual RMS (µs)")
    lower_left.set_title("B · 12 of 14 complete locklets are at or near the quantization floor")
    lower_left.legend(loc="upper left", fontsize=8)
    lower_left.grid(True, axis="y", alpha=0.22)

    offsets = {0: -0.08, 1: 0.08}
    for receiver in (0, 1):
        product = next(
            value for value in glrt_products if value["source"]["receiver_id"] == receiver
        )
        alias = _alias_statistics(product)
        values = np.asarray(alias["_transition_values"], dtype=float)
        if not len(values):
            continue
        x_raw = np.full(len(values), 0.0 + offsets[receiver])
        x_canonical = np.full(len(values), 1.0 + offsets[receiver])
        lower_right.scatter(
            x_raw,
            values[:, 0],
            s=8,
            alpha=0.18,
            color=RX_COLORS[receiver],
            label=f"RX{receiver} ({len(values)} transitions)",
        )
        lower_right.scatter(x_canonical, values[:, 1], s=8, alpha=0.18, color=RX_COLORS[receiver])
        lower_right.plot(
            [offsets[receiver], 1.0 + offsets[receiver]],
            [np.median(values[:, 0]), np.median(values[:, 1])],
            color=RX_COLORS[receiver],
            lw=2.0,
        )
    lower_right.axhline(
        float(glrt_products[0]["cfo_alias_spacing_hz"]),
        color="#111827",
        ls="--",
        label="2.5M/11 alias spacing",
    )
    lower_right.set_yscale("log")
    lower_right.set_xticks((0, 1), ("raw CFO jump", "canonical CFO jump"))
    lower_right.set_ylabel("Absolute adjacent jump (Hz, log scale)")
    lower_right.set_title(
        "C · CFO alias transitions collapse after integer-branch canonicalization"
    )
    lower_right.legend(loc="best", fontsize=8)
    lower_right.grid(True, axis="y", alpha=0.22)
    figure.suptitle(
        f"{CAPTURE_ID} · GLRT residual lattice is sample quantization; raw CFO aliasing is separate"
    )
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_track_multiplicity(
    destination: Path,
    pss_data: PssTrackData,
    glrt_products: list[Json],
    summary: Json,
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True, constrained_layout=True)
    start_s = float(pss_data.times_s[0])
    stop_s = float(pss_data.times_s[-1])
    for axis_index, receiver_id in enumerate((1, 0)):
        axis = axes[axis_index]
        product = next(
            value for value in glrt_products if value["source"]["receiver_id"] == receiver_id
        )
        for color_index, locklet in enumerate(_complete_locklets(product)):
            observations = _inlier_observations(locklet)
            times = np.asarray(
                [
                    row["global_center_time_s"] + _high_time_offset_s(product, pss_data.product)
                    for row in observations
                ]
            )
            residuals = np.asarray([row["linear_residual_s"] * 1e6 for row in observations])
            keep = (times >= start_s) & (times <= stop_s)
            if np.count_nonzero(keep) < 3:
                continue
            axis.scatter(
                times[keep],
                residuals[keep],
                s=8,
                alpha=0.55,
                color=LOCKLET_COLORS[color_index % len(LOCKLET_COLORS)],
                label=(
                    f"RX{receiver_id} {locklet['source_hough_track_label']}/"
                    f"L{locklet['locklet_index']} · n={np.count_nonzero(keep)}"
                ),
            )
        axis.set_ylabel(f"RX{receiver_id} linear\nresidual (µs)")
        axis.set_title(
            f"{'A' if axis_index == 0 else 'B'} · Every colored GLRT arc is a separate "
            "independently fitted Hough locklet"
        )
        axis.legend(loc="upper left", fontsize=7, ncol=3)

    pss_axis = axes[2]
    for index, track in enumerate(pss_data.product["tracks"]):
        data = reconstruct_pss_track(pss_data.product, track)
        reference = float(np.mean(data.times_s))
        affine = np.polyfit(data.times_s - reference, data.phases_s, 1)
        residuals_us = (data.phases_s - np.polyval(affine, data.times_s - reference)) * 1e6
        selected = track["track_id"] == pss_data.track["track_id"]
        pss_axis.scatter(
            data.times_s,
            residuals_us,
            marker="x",
            s=26 if selected else 18,
            alpha=0.9 if selected else 0.35,
            color=PSS_COLOR if selected else "#64748b",
            label=(
                f"selected PSS track · n={len(data.modes)}"
                if selected
                else f"other PSS track {index} · n={len(data.modes)}"
            ),
            zorder=4 if selected else 2,
        )
    pss_axis.set_ylabel("PSS linear\nresidual (µs)")
    pss_axis.set_title(
        "C · Five PSS tracks were persisted; production renders only the 278-mode primary track"
    )
    pss_axis.set_xlabel("Seconds from native 25 MS/s stream start")
    pss_axis.legend(loc="upper left", fontsize=8, ncol=3)
    event_s = float(summary["timing_event"]["pss_split_midpoint_s"])
    for axis in axes:
        axis.axhline(0, color="#111827", lw=0.8)
        axis.axvline(event_s, color="#111827", ls="--", lw=1.0)
        axis.grid(True, alpha=0.22)
        axis.set_xlim(start_s, stop_s)
    figure.suptitle(
        f"{CAPTURE_ID} · track multiplicity explains the many GLRT arcs versus one PSS bow"
    )
    figure.savefig(destination, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def generate_report_artifacts(
    pss_path: Path,
    glrt_paths: list[Path],
    output_dir: Path,
) -> Json:
    pss = _load_json(pss_path)
    glrt_products = [_load_json(path) for path in glrt_paths]
    summary, pss_data, event_locklets = build_summary(pss, glrt_products)
    output_dir.mkdir(parents=True, exist_ok=True)
    _plot_sign_audit(output_dir / "frequency-sign-audit.png", pss_data, glrt_products, summary)
    _plot_timing_event(
        output_dir / "common-timing-discontinuity.png", pss_data, event_locklets, summary
    )
    _plot_quantization_and_alias(
        output_dir / "glrt-quantization-versus-cfo-alias.png", pss, glrt_products, summary
    )
    _plot_track_multiplicity(
        output_dir / "track-multiplicity-and-linear-arcs.png", pss_data, glrt_products, summary
    )
    summary_path = output_dir / "analysis-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pss", type=Path, required=True, help="persisted PSS frame-timing JSON")
    parser.add_argument(
        "--glrt-epoch",
        type=Path,
        action="append",
        required=True,
        help="persisted GLRT epoch JSON; pass once for each receiver",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if len(args.glrt_epoch) != 2:
        raise SystemExit("exactly two --glrt-epoch inputs are required")
    summary = generate_report_artifacts(args.pss, args.glrt_epoch, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
