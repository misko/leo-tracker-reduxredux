#!/usr/bin/env python3
"""Evaluate Starlink Doppler models against one frozen radio-only lane bank.

This is an explicitly exploratory, artifact-to-artifact evaluation.  It does
not publish an association contract and it does not rediscover radio lanes.
Satellite selection starts from a chronological 60/40 split of each lane, then
closes holdout globally over shared source-observation and sample-epoch groups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.doppler import doppler_shift_hz  # type: ignore[import-untyped]
from leo.sky.propagation import (  # type: ignore[import-untyped]
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import (  # type: ignore[import-untyped]
    MAX_ANGULAR_RATE_DEG_S,
    SamplingGrid,
)
from leo.sky.screening import observe_grid  # type: ignore[import-untyped]

CAPTURE_ID = "cap-20260824T192531-491832825b97"
STREAM_ID = "stream-1"
RADIO_ID = "radio_pluto_19f2"
RECEIVER_ID = 1
RF_HZ = 11_190_312_500.0
EXPECTED_TLE_SHA256 = "ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee"
DEFAULT_MANIFEST = Path(
    "/srv/bulk/leo/recordings/2026/08/24/cap-20260824T192531-491832825b97/manifest.json"
)
DEFAULT_LANES = Path(
    "/srv/bulk/leo/analysis/cap-20260824T192531-491832825b97/"
    "capture-f75a853e526844e29893f125d4a58940/scientific/path-standard/"
    "sha256:0e14f83ecfa8cab0a9d01a2b4ba1167c8a37ff1f815908b6dae8a5451fdcdb7f/"
    "standard.dealiased-trajectory-bank.v4.json"
)
DEFAULT_TLE = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/22/"
    "01a02af8-cec4-7703-a883-75760f132c40/"
    "radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle"
)
DEFAULT_JSON = Path("reports/figures/2026_08_25_frozen_lane_satellite_models/results.json")
DEFAULT_REPORT = Path("reports/2026_08_25_frozen_lane_satellite_models.md")
DEFAULT_DURATION_AUDIT = Path(
    "reports/figures/2026_08_25_duration_constrained_satellite_assignment/"
    "capture-input-summary.json"
)

SITE = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="sf-bay-reference-site",
)

type FloatArray = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class Lane:
    lane_id: str
    source_branch_id: str
    support_piece_index: int
    start_s: float
    end_s: float
    times_s: FloatArray
    cfo_hz: FloatArray
    observation_ids: tuple[str, ...]
    sample_starts: tuple[int, ...]
    source_observation_ids_by_observation: tuple[tuple[str, ...], ...]
    train_mask: BoolArray
    distinct_epoch_count: int
    occupancy_fraction: float
    maximum_gap_s: float

    @property
    def span_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def source_observation_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    source_id
                    for group in self.source_observation_ids_by_observation
                    for source_id in group
                }
            )
        )


@dataclass(frozen=True, slots=True)
class PredictionBank:
    time_s: FloatArray
    doppler_hz: FloatArray
    elevation_deg: FloatArray
    catalogue_indices: NDArray[np.intp]
    satellite_numbers: tuple[int, ...]
    names: tuple[str, ...]
    element_epoch_utc_ns: tuple[int, ...]
    catalogue_count: int
    plausible_count: int
    coarse_candidate_count: int


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _uniform_grid(start_utc_ns: int, end_utc_ns: int, spacing_s: float) -> SamplingGrid:
    if end_utc_ns <= start_utc_ns:
        raise ValueError("grid end must follow its start")
    count = max(3, int(math.ceil((end_utc_ns - start_utc_ns) / 1e9 / spacing_s)) + 1)
    step_ns = int(math.ceil((end_utc_ns - start_utc_ns) / (count - 1)))
    instants = tuple(start_utc_ns + index * step_ns for index in range(count))
    return SamplingGrid(instants, 0, step_ns / 1e9)


def capture_start_utc_ns(
    manifest: dict[str, Any], *, stream_id: str, radio_id: str, receiver_id: int
) -> int:
    if manifest.get("session_id") != CAPTURE_ID:
        raise ValueError(f"manifest session is not {CAPTURE_ID}")
    matches = [
        stream
        for stream in manifest["streams"]
        if stream["stream_id"] == stream_id and stream["radio"]["radio_id"] == radio_id
    ]
    if len(matches) != 1:
        raise ValueError("stream/radio selector did not identify exactly one stream")
    stream = matches[0]
    if receiver_id not in stream["applied_settings"]["receiver_ids"]:
        raise ValueError("receiver is not present in the selected stream")
    if stream["continuity"]["gap_count"] or stream["continuity"]["missing_sample_count"]:
        raise ValueError("selected stream is not gap-free")
    return int(stream["timing"]["first_sample"]["estimate_utc_ns"])


def _group_disjoint_train_holdout(
    lanes: list[Lane],
) -> tuple[list[Lane], dict[str, Any], set[str]]:
    """Close seeded holdout over shared sample epochs and exact source IDs."""

    seeded_holdout_samples = {
        sample_start
        for lane in lanes
        for sample_start, is_train in zip(lane.sample_starts, lane.train_mask, strict=True)
        if not bool(is_train)
    }
    seeded_holdout_sources = {
        source_id
        for lane in lanes
        for source_ids, is_train in zip(
            lane.source_observation_ids_by_observation,
            lane.train_mask,
            strict=True,
        )
        if not bool(is_train)
        for source_id in source_ids
    }
    holdout_samples = set(seeded_holdout_samples)
    holdout_sources = set(seeded_holdout_sources)
    closure_iterations = 0
    while True:
        prior_size = len(holdout_samples) + len(holdout_sources)
        for lane in lanes:
            for sample_start, source_ids in zip(
                lane.sample_starts,
                lane.source_observation_ids_by_observation,
                strict=True,
            ):
                if sample_start in holdout_samples or not holdout_sources.isdisjoint(source_ids):
                    holdout_samples.add(sample_start)
                    holdout_sources.update(source_ids)
        closure_iterations += 1
        if len(holdout_samples) + len(holdout_sources) == prior_size:
            break

    updated: list[Lane] = []
    rejected_lane_ids: set[str] = set()
    per_lane: list[dict[str, Any]] = []
    for lane in lanes:
        final_train: BoolArray = np.asarray(
            [
                sample_start not in holdout_samples and holdout_sources.isdisjoint(source_ids)
                for sample_start, source_ids in zip(
                    lane.sample_starts,
                    lane.source_observation_ids_by_observation,
                    strict=True,
                )
            ],
            dtype=np.bool_,
        )
        train_count = int(np.count_nonzero(final_train))
        holdout_count = int(final_train.size - train_count)
        retained = train_count >= 3 and holdout_count >= 3
        if retained:
            updated.append(replace(lane, train_mask=final_train))
        else:
            rejected_lane_ids.add(lane.lane_id)
        per_lane.append(
            {
                "lane_id": lane.lane_id,
                "initial_train_observation_count": int(np.count_nonzero(lane.train_mask)),
                "final_train_observation_count": train_count,
                "final_holdout_observation_count": holdout_count,
                "actual_train_fraction": train_count / int(final_train.size),
                "retained_after_split": retained,
                "failure_reason": (
                    None if retained else "fewer_than_three_train_or_holdout_observations"
                ),
            }
        )

    train_samples = {
        sample_start
        for lane in updated
        for sample_start, is_train in zip(lane.sample_starts, lane.train_mask, strict=True)
        if bool(is_train)
    }
    final_holdout_samples = {
        sample_start
        for lane in updated
        for sample_start, is_train in zip(lane.sample_starts, lane.train_mask, strict=True)
        if not bool(is_train)
    }
    train_sources = {
        source_id
        for lane in updated
        for source_ids, is_train in zip(
            lane.source_observation_ids_by_observation,
            lane.train_mask,
            strict=True,
        )
        if bool(is_train)
        for source_id in source_ids
    }
    final_holdout_sources = {
        source_id
        for lane in updated
        for source_ids, is_train in zip(
            lane.source_observation_ids_by_observation,
            lane.train_mask,
            strict=True,
        )
        if not bool(is_train)
        for source_id in source_ids
    }
    sample_overlap = sorted(train_samples & final_holdout_samples)
    source_overlap = sorted(train_sources & final_holdout_sources)
    if sample_overlap or source_overlap:
        raise AssertionError("global grouped split leaked sample or source identity")
    total_observations = sum(lane.times_s.size for lane in updated)
    total_train = sum(np.count_nonzero(lane.train_mask) for lane in updated)
    return (
        updated,
        {
            "method": (
                "seed each lane's chronological suffix, then close holdout transitively over "
                "sample_start and exact source_observation_id groups"
            ),
            "closure_iteration_count": closure_iterations,
            "seeded_holdout_sample_start_count": len(seeded_holdout_samples),
            "closed_holdout_sample_start_count": len(holdout_samples),
            "seeded_holdout_source_observation_id_count": len(seeded_holdout_sources),
            "closed_holdout_source_observation_id_count": len(holdout_sources),
            "retained_lane_count": len(updated),
            "rejected_lane_count": len(rejected_lane_ids),
            "actual_global_train_fraction": float(total_train / total_observations),
            "cross_split_sample_start_overlap_count": len(sample_overlap),
            "cross_split_source_observation_id_overlap_count": len(source_overlap),
            "cross_split_sample_start_overlap": sample_overlap,
            "cross_split_source_observation_id_overlap": source_overlap,
            "per_lane": per_lane,
        },
        rejected_lane_ids,
    )


def load_lanes_with_accounting(
    path: Path,
    *,
    minimum_span_s: float,
    minimum_distinct_epochs: int,
    minimum_occupancy_fraction: float,
    maximum_gap_s: float,
    expected_probe_rate_hz: float,
    train_fraction: float,
) -> tuple[list[Lane], dict[str, Any]]:
    artifact = _read_json(path)
    if artifact.get("status") != "complete":
        raise ValueError("dealiased trajectory bank is not usable")
    observations = {item["observation_id"]: item for item in artifact["observations"]}
    lanes: list[Lane] = []
    pieces: list[dict[str, Any]] = []
    for branch in artifact["branches"]:
        members = sorted(
            (observations[item] for item in branch["observation_ids"]),
            key=lambda item: (float(item["time_s"]), item["observation_id"]),
        )
        source_times = np.asarray([item["time_s"] for item in members], dtype=np.float64)
        if np.unique(source_times).size != source_times.size:
            pieces.append(
                {
                    "source_branch_id": branch["branch_id"],
                    "support_piece_index": None,
                    "retained": False,
                    "failure_reasons": ["duplicate_source_epoch"],
                }
            )
            continue
        cut_indices: NDArray[np.intp] = (
            np.flatnonzero(np.diff(source_times) > maximum_gap_s + 1e-9) + 1
        )
        for piece_index, member_indices in enumerate(
            np.split(np.arange(source_times.size), cut_indices)
        ):
            piece_members = [members[int(index)] for index in member_indices]
            times = np.asarray([item["time_s"] for item in piece_members], dtype=np.float64)
            values = np.asarray(
                [item["component_cfo_hz"] for item in piece_members], dtype=np.float64
            )
            start_s = float(times[0])
            end_s = float(times[-1])
            span_s = end_s - start_s
            distinct_epoch_count = int(np.unique(times).size)
            expected_epochs = max(1, int(round(span_s * expected_probe_rate_hz)) + 1)
            occupancy_fraction = distinct_epoch_count / expected_epochs
            observed_maximum_gap_s = 0.0 if times.size < 2 else float(np.max(np.diff(times)))
            failure_reasons = []
            if span_s < minimum_span_s:
                failure_reasons.append("span_below_minimum")
            if distinct_epoch_count < minimum_distinct_epochs:
                failure_reasons.append("distinct_epochs_below_minimum")
            if occupancy_fraction < minimum_occupancy_fraction:
                failure_reasons.append("occupancy_below_minimum")
            if observed_maximum_gap_s > maximum_gap_s + 1e-9:
                failure_reasons.append("gap_above_maximum")
            retained = not failure_reasons
            lane_id = f"{branch['branch_id']}#support-{piece_index:02d}"
            pieces.append(
                {
                    "lane_id": lane_id,
                    "source_branch_id": branch["branch_id"],
                    "support_piece_index": piece_index,
                    "start_s": start_s,
                    "end_s": end_s,
                    "span_s": span_s,
                    "distinct_epoch_count": distinct_epoch_count,
                    "expected_epoch_count": expected_epochs,
                    "occupancy_fraction": occupancy_fraction,
                    "maximum_gap_s": observed_maximum_gap_s,
                    "retained": retained,
                    "failure_reasons": failure_reasons,
                }
            )
            if not retained:
                continue
            split = int(math.ceil(train_fraction * times.size))
            split = max(3, min(times.size - 3, split))
            train_mask = np.zeros(times.size, dtype=np.bool_)
            train_mask[:split] = True
            lanes.append(
                Lane(
                    lane_id=lane_id,
                    source_branch_id=str(branch["branch_id"]),
                    support_piece_index=piece_index,
                    start_s=start_s,
                    end_s=end_s,
                    times_s=times,
                    cfo_hz=values,
                    observation_ids=tuple(item["observation_id"] for item in piece_members),
                    sample_starts=tuple(int(item["sample_start"]) for item in piece_members),
                    source_observation_ids_by_observation=tuple(
                        tuple(str(value) for value in item["source_observation_ids"])
                        for item in piece_members
                    ),
                    train_mask=train_mask,
                    distinct_epoch_count=distinct_epoch_count,
                    occupancy_fraction=occupancy_fraction,
                    maximum_gap_s=observed_maximum_gap_s,
                )
            )
    lanes, split_audit, split_rejected_lane_ids = _group_disjoint_train_holdout(lanes)
    for piece in pieces:
        if piece.get("lane_id") in split_rejected_lane_ids:
            piece["retained"] = False
            piece["failure_reasons"].append("global_split_insufficient_support")
    accounting = {
        "source_branch_count": len(artifact["branches"]),
        "support_piece_count": len(pieces),
        "retained_piece_count": sum(item["retained"] for item in pieces),
        "rejected_piece_count": sum(not item["retained"] for item in pieces),
        "split_boundary_count": sum(
            max(0, sum(item.get("source_branch_id") == branch["branch_id"] for item in pieces) - 1)
            for branch in artifact["branches"]
        ),
        "gates": {
            "minimum_span_s": minimum_span_s,
            "minimum_distinct_epochs": minimum_distinct_epochs,
            "minimum_occupancy_fraction": minimum_occupancy_fraction,
            "maximum_gap_s": maximum_gap_s,
            "expected_probe_rate_hz": expected_probe_rate_hz,
        },
        "train_holdout_split": split_audit,
        "pieces": pieces,
    }
    return (
        sorted(lanes, key=lambda item: (item.start_s, item.end_s, item.lane_id)),
        accounting,
    )


def load_lanes(
    path: Path,
    *,
    minimum_span_s: float,
    train_fraction: float,
    minimum_distinct_epochs: int = 28,
    minimum_occupancy_fraction: float = 0.70,
    maximum_gap_s: float = 0.10,
    expected_probe_rate_hz: float = 40.0,
) -> list[Lane]:
    """Load only independently supported contiguous pieces from frozen lanes."""

    lanes, _ = load_lanes_with_accounting(
        path,
        minimum_span_s=minimum_span_s,
        minimum_distinct_epochs=minimum_distinct_epochs,
        minimum_occupancy_fraction=minimum_occupancy_fraction,
        maximum_gap_s=maximum_gap_s,
        expected_probe_rate_hz=expected_probe_rate_hz,
        train_fraction=train_fraction,
    )
    return lanes


def strict_duration_gate_summary(path: Path, lane_bank_path: Path) -> dict[str, Any]:
    audit = _read_json(path)
    capture = audit.get("capture", {})
    if (
        capture.get("session_id"),
        capture.get("stream_id"),
        capture.get("radio_id"),
        capture.get("receiver_id"),
    ) != (CAPTURE_ID, STREAM_ID, RADIO_ID, RECEIVER_ID):
        raise ValueError("duration audit is not bound to the target capture path")
    expected_lane_digest = audit["source_products"]["dealiased_bank"]["file_digest"]
    if expected_lane_digest != f"sha256:{_sha256(lane_bank_path)}":
        raise ValueError("duration audit and lane bank digests disagree")
    qualified_windows = [
        window
        for branch in audit["branches"]
        for window in branch["frame_coherence_evidence"]["qualified_windows"]
    ]
    durations = [
        float(item["end_time_s"]) - float(item["start_time_s"]) for item in qualified_windows
    ]
    duration = audit["duration_constraint_summary"]
    return {
        "minimum_duration_s": float(duration["minimum_duration_s"]),
        "eligible_assignment_count": int(duration["qualified_frame_run_pass_branch_count"]),
        "deduplicated_qualified_window_count": len(qualified_windows),
        "longest_qualified_run_s": 0.0 if not durations else max(durations),
        "qualified_window_durations_s": durations,
        "frame_evidence_complete_across_final_inventory": bool(
            audit["frame_evidence_inventory"]["evidence_complete"]
        ),
        "source_path": str(path),
        "source_sha256": _sha256(path),
        "interpretation": (
            "strict known-pilot qualified-frame evidence; zero eligible assignments is the "
            "primary result, while the orbit sweep below is a relaxed trajectory-support surrogate"
        ),
    }


def build_prediction_bank(
    tle_path: Path,
    *,
    capture_start_ns: int,
    start_s: float,
    end_s: float,
    tau_bound_s: float,
    rf_hz: float,
    horizon_deg: float,
    coarse_spacing_s: float,
    fine_spacing_s: float,
) -> PredictionBank:
    catalogue = parse_element_sets(tle_path.read_text())
    lower_s = start_s - tau_bound_s - fine_spacing_s
    upper_s = end_s + tau_bound_s + fine_spacing_s
    coarse_grid = _uniform_grid(
        capture_start_ns + int(math.floor(lower_s * 1e9)),
        capture_start_ns + int(math.ceil(upper_s * 1e9)),
        coarse_spacing_s,
    )
    coarse_propagated = propagate_grid(catalogue, coarse_grid)
    coarse_tracks = observe_grid(coarse_propagated, SITE, coarse_grid)
    plausible = coarse_tracks.usable & (
        np.min(coarse_tracks.altitude_km, axis=1) >= MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    # The half-step angular margin prevents a between-knot horizon crossing from
    # being discarded by the coarse screen.
    angular_margin_deg = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    coarse_candidate = plausible & (
        np.max(coarse_tracks.elevation_deg, axis=1) >= horizon_deg - angular_margin_deg
    )
    coarse_indices = np.flatnonzero(coarse_candidate)

    fine_grid = _uniform_grid(
        capture_start_ns + int(math.floor(lower_s * 1e9)),
        capture_start_ns + int(math.ceil(upper_s * 1e9)),
        fine_spacing_s,
    )
    fine_propagated = propagate_grid(catalogue, fine_grid, coarse_indices)
    fine_tracks = observe_grid(fine_propagated, SITE, fine_grid)
    exact_visible = np.max(fine_tracks.elevation_deg, axis=1) >= horizon_deg
    selected_indices = coarse_indices[exact_visible]
    time_s = (np.asarray(fine_grid.utc_ns, dtype=np.float64) - float(capture_start_ns)) / 1e9
    return PredictionBank(
        time_s=time_s,
        doppler_hz=np.asarray(
            doppler_shift_hz(rf_hz, fine_tracks.range_rate_km_s[exact_visible]),
            dtype=np.float64,
        ),
        elevation_deg=np.asarray(fine_tracks.elevation_deg[exact_visible], dtype=np.float64),
        catalogue_indices=np.asarray(selected_indices, dtype=np.intp),
        satellite_numbers=tuple(catalogue.satellite_numbers[index] for index in selected_indices),
        names=tuple(catalogue.names[index] for index in selected_indices),
        element_epoch_utc_ns=tuple(
            catalogue.element_epoch_utc_ns()[index] for index in selected_indices
        ),
        catalogue_count=len(catalogue),
        plausible_count=int(np.count_nonzero(plausible)),
        coarse_candidate_count=int(coarse_indices.size),
    )


def _bounded_huber_fit(
    design: FloatArray,
    target: FloatArray,
    *,
    scale_floor: float,
    bounded_coefficient: tuple[int, float, float] | None = None,
    maximum_iterations: int = 32,
) -> tuple[FloatArray, FloatArray]:
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]

    def apply_bound(values: FloatArray, weights: FloatArray) -> FloatArray:
        if bounded_coefficient is None:
            return values
        index, lower, upper = bounded_coefficient
        if lower <= values[index] <= upper:
            return values
        values = values.copy()
        values[index] = float(np.clip(values[index], lower, upper))
        remaining = [column for column in range(design.shape[1]) if column != index]
        root = np.sqrt(weights)
        reduced_target = target - design[:, index] * values[index]
        values[remaining] = np.linalg.lstsq(
            design[:, remaining] * root[:, None], reduced_target * root, rcond=None
        )[0]
        return values

    weights = np.ones(target.size, dtype=np.float64)
    coefficients = apply_bound(coefficients, weights)
    for _ in range(maximum_iterations):
        residual = target - design @ coefficients
        center = float(np.median(residual))
        mad = float(np.median(np.abs(residual - center)))
        scale = max(scale_floor, 1.4826 * mad)
        standardized = np.abs(residual) / scale
        weights = np.ones_like(standardized)
        tail = standardized > 1.345
        weights[tail] = 1.345 / standardized[tail]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root[:, None], target * root, rcond=None)[0]
        updated = apply_bound(updated, weights)
        if np.max(np.abs(design @ (updated - coefficients))) <= 1e-6:
            coefficients = updated
            break
        coefficients = updated
    return coefficients, target - design @ coefficients


def _affine_slope(times_s: FloatArray, values_hz: FloatArray, scale_floor: float) -> float:
    reference = float(np.mean(times_s))
    design = np.column_stack((np.ones(times_s.size), times_s - reference))
    coefficients, _ = _bounded_huber_fit(design, values_hz, scale_floor=scale_floor)
    return float(coefficients[1])


def _visible_for_lane(
    bank_times_s: FloatArray,
    elevation_deg: FloatArray,
    lane: Lane,
    tau_s: float,
    horizon_deg: float,
) -> bool:
    lower = lane.start_s + tau_s
    upper = lane.end_s + tau_s
    first = int(np.searchsorted(bank_times_s, lower, side="left"))
    last = int(np.searchsorted(bank_times_s, upper, side="right"))
    if first == 0 or last >= bank_times_s.size:
        return False
    interior = elevation_deg[first:last]
    endpoint = np.interp([lower, upper], bank_times_s, elevation_deg)
    return bool(
        interior.size > 0 and np.min(interior) >= horizon_deg and np.min(endpoint) >= horizon_deg
    )


def fit_rate_only(
    lane: Lane,
    bank_times_s: FloatArray,
    doppler_hz: FloatArray,
    elevation_deg: FloatArray,
    *,
    horizon_deg: float,
    rate_scale_hz_s: float,
) -> dict[str, Any] | None:
    if not _visible_for_lane(bank_times_s, elevation_deg, lane, 0.0, horizon_deg):
        return None
    train = lane.train_mask
    holdout = ~train
    observed_train = _affine_slope(lane.times_s[train], lane.cfo_hz[train], 100.0)
    observed_holdout = _affine_slope(lane.times_s[holdout], lane.cfo_hz[holdout], 100.0)
    predicted = np.interp(lane.times_s, bank_times_s, doppler_hz)
    predicted_train = _affine_slope(lane.times_s[train], predicted[train], 1.0)
    predicted_holdout = _affine_slope(lane.times_s[holdout], predicted[holdout], 1.0)
    train_error = observed_train - predicted_train
    holdout_error = observed_holdout - predicted_holdout
    return {
        "train_standardized_mse": float((train_error / rate_scale_hz_s) ** 2),
        "holdout_standardized_mse": float((holdout_error / rate_scale_hz_s) ** 2),
        "train_error_hz_s": float(train_error),
        "holdout_error_hz_s": float(holdout_error),
        "observed_train_rate_hz_s": observed_train,
        "predicted_train_rate_hz_s": predicted_train,
        "observed_holdout_rate_hz_s": observed_holdout,
        "predicted_holdout_rate_hz_s": predicted_holdout,
        "composite_frequency_offset_hz": None,
        "offset_reference_time_s": None,
        "tau_s": None,
        "residual_acceleration_hz_s2": None,
    }


def fit_cfo_at_tau(
    lane: Lane,
    bank_times_s: FloatArray,
    doppler_hz: FloatArray,
    elevation_deg: FloatArray,
    tau_s: float,
    *,
    horizon_deg: float,
    cfo_scale_hz: float,
    acceleration_bound_hz_s2: float | None,
) -> dict[str, Any] | None:
    train = lane.train_mask
    holdout = ~train
    reference_s = float(np.mean(lane.times_s[train]))
    relative = lane.times_s - reference_s
    if not _visible_for_lane(bank_times_s, elevation_deg, lane, float(tau_s), horizon_deg):
        return None
    prediction = np.interp(lane.times_s + tau_s, bank_times_s, doppler_hz)
    target = lane.cfo_hz - prediction
    if acceleration_bound_hz_s2 is None:
        design = np.ones((lane.times_s.size, 1), dtype=np.float64)
        bound = None
    else:
        design = np.column_stack(
            (
                np.ones(lane.times_s.size, dtype=np.float64),
                0.5 * relative**2,
            )
        )
        bound = (1, -acceleration_bound_hz_s2, acceleration_bound_hz_s2)
    coefficients, _ = _bounded_huber_fit(
        design[train], target[train], scale_floor=cfo_scale_hz, bounded_coefficient=bound
    )
    residual = target - design @ coefficients
    train_rmse = float(np.sqrt(np.mean(residual[train] ** 2)))
    holdout_rmse = float(np.sqrt(np.mean(residual[holdout] ** 2)))
    acceleration = None if acceleration_bound_hz_s2 is None else float(coefficients[1])
    return {
        "tau_s": float(tau_s),
        "composite_frequency_offset_hz": float(coefficients[0]),
        "offset_reference_time_s": reference_s,
        "residual_acceleration_hz_s2": acceleration,
        "train_rmse_hz": train_rmse,
        "holdout_rmse_hz": holdout_rmse,
        "train_standardized_mse": float((train_rmse / cfo_scale_hz) ** 2),
        "holdout_standardized_mse": float((holdout_rmse / cfo_scale_hz) ** 2),
        "acceleration_at_bound": bool(
            acceleration_bound_hz_s2 is not None
            and acceleration is not None
            and math.isclose(abs(float(acceleration)), acceleration_bound_hz_s2)
        ),
    }


def fit_cfo_tau_grid(
    lane: Lane,
    bank_times_s: FloatArray,
    doppler_hz: FloatArray,
    elevation_deg: FloatArray,
    tau_grid_s: FloatArray,
    *,
    horizon_deg: float,
    cfo_scale_hz: float,
    acceleration_bound_hz_s2: float | None,
) -> list[dict[str, Any] | None]:
    profile = [
        fit_cfo_at_tau(
            lane,
            bank_times_s,
            doppler_hz,
            elevation_deg,
            float(tau_s),
            horizon_deg=horizon_deg,
            cfo_scale_hz=cfo_scale_hz,
            acceleration_bound_hz_s2=acceleration_bound_hz_s2,
        )
        for tau_s in tau_grid_s
    ]
    finite = [item for item in profile if item is not None]
    if not finite:
        return profile
    best_rmse = min(float(item["train_rmse_hz"]) for item in finite)
    near_tau = [
        float(item["tau_s"]) for item in finite if float(item["train_rmse_hz"]) <= best_rmse + 5.0
    ]
    near_width = float(max(near_tau) - min(near_tau))
    tau_bound = float(np.max(np.abs(tau_grid_s)))
    for item in finite:
        item["tau_near_optimal_width_s"] = near_width
        item["tau_at_bound"] = bool(math.isclose(abs(float(item["tau_s"])), tau_bound))
    return profile


def fit_cfo_profile(
    lane: Lane,
    bank_times_s: FloatArray,
    doppler_hz: FloatArray,
    elevation_deg: FloatArray,
    tau_grid_s: FloatArray,
    *,
    horizon_deg: float,
    cfo_scale_hz: float,
    acceleration_bound_hz_s2: float | None,
) -> dict[str, Any] | None:
    profile = fit_cfo_tau_grid(
        lane,
        bank_times_s,
        doppler_hz,
        elevation_deg,
        tau_grid_s,
        horizon_deg=horizon_deg,
        cfo_scale_hz=cfo_scale_hz,
        acceleration_bound_hz_s2=acceleration_bound_hz_s2,
    )
    finite = [item for item in profile if item is not None]
    if not finite:
        return None
    best = min(
        finite,
        key=lambda item: (item["train_standardized_mse"], abs(item["tau_s"]), item["tau_s"]),
    ).copy()
    return best


def radio_only_nulls(lane: Lane, *, cfo_scale_hz: float) -> dict[str, Any]:
    train = lane.train_mask
    holdout = ~train
    reference = float(np.mean(lane.times_s[train]))
    relative = lane.times_s - reference
    train_rate = _affine_slope(lane.times_s[train], lane.cfo_hz[train], cfo_scale_hz)
    holdout_rate = _affine_slope(lane.times_s[holdout], lane.cfo_hz[holdout], cfo_scale_hz)
    result: dict[str, Any] = {
        "constant_train_rate": {
            "train_rate_hz_s": train_rate,
            "holdout_rate_hz_s": holdout_rate,
            "holdout_error_hz_s": holdout_rate - train_rate,
        }
    }
    for label, design in (
        ("affine", np.column_stack((np.ones(relative.size), relative))),
        (
            "quadratic",
            np.column_stack((np.ones(relative.size), relative, 0.5 * relative**2)),
        ),
    ):
        coefficients, _ = _bounded_huber_fit(
            design[train], lane.cfo_hz[train], scale_floor=cfo_scale_hz
        )
        residual = lane.cfo_hz - design @ coefficients
        result[label] = {
            "reference_time_s": reference,
            "coefficients": [float(value) for value in coefficients],
            "train_rmse_hz": float(np.sqrt(np.mean(residual[train] ** 2))),
            "holdout_rmse_hz": float(np.sqrt(np.mean(residual[holdout] ** 2))),
        }
    return result


def aggregate_radio_only_nulls(lane_rows: list[dict[str, Any]]) -> dict[str, Any]:
    def equal_lane_rms(values: list[float]) -> float:
        return float(np.sqrt(np.mean(np.square(values))))

    rate_errors = [
        float(item["radio_only_nulls"]["constant_train_rate"]["holdout_error_hz_s"])
        for item in lane_rows
    ]
    result: dict[str, Any] = {
        "constant_train_rate": {
            "train_equal_lane_rms_hz_s": 0.0,
            "holdout_equal_lane_rms_hz_s": equal_lane_rms(rate_errors),
            "description": (
                "each lane's robust training-prefix slope is frozen and compared with its "
                "independently estimated holdout-prefix slope"
            ),
        }
    }
    for label in ("affine", "quadratic"):
        result[label] = {
            "train_equal_lane_rms_hz": equal_lane_rms(
                [float(item["radio_only_nulls"][label]["train_rmse_hz"]) for item in lane_rows]
            ),
            "holdout_equal_lane_rms_hz": equal_lane_rms(
                [float(item["radio_only_nulls"][label]["holdout_rmse_hz"]) for item in lane_rows]
            ),
            "description": (
                f"per-lane radio-only {label} model fit on training observations and frozen "
                "into holdout"
            ),
        }
    return result


def greedy_facility_sweep(
    lane_ids: list[str],
    satellite_ids: list[int],
    train_cost: FloatArray,
    holdout_cost: FloatArray,
    fit_parameters: list[list[dict[str, Any] | None]],
    *,
    maximum_k: int,
    unassigned_cost: float,
    lane_intervals_s: list[tuple[float, float]] | None = None,
    error_scale: float = 1.0,
    error_unit: str = "normalized",
    lane_observation_ids: list[tuple[str, ...]] | None = None,
    lane_source_observation_ids: list[tuple[str, ...]] | None = None,
    lane_sample_starts: list[tuple[int, ...]] | None = None,
) -> list[dict[str, Any]]:
    states = [
        {"satellite_number": satellite_number, "tau_s": None} for satellite_number in satellite_ids
    ]
    return greedy_shared_tau_facility_sweep(
        lane_ids,
        states,
        train_cost,
        holdout_cost,
        fit_parameters,
        maximum_k=maximum_k,
        unassigned_cost=unassigned_cost,
        lane_intervals_s=lane_intervals_s,
        error_scale=error_scale,
        error_unit=error_unit,
        lane_observation_ids=lane_observation_ids,
        lane_source_observation_ids=lane_source_observation_ids,
        lane_sample_starts=lane_sample_starts,
    )


def greedy_shared_tau_facility_sweep(
    lane_ids: list[str],
    facility_states: list[dict[str, Any]],
    train_cost: FloatArray,
    holdout_cost: FloatArray,
    fit_parameters: list[list[dict[str, Any] | None]],
    *,
    maximum_k: int,
    unassigned_cost: float,
    lane_intervals_s: list[tuple[float, float]] | None = None,
    error_scale: float = 1.0,
    error_unit: str = "normalized",
    lane_observation_ids: list[tuple[str, ...]] | None = None,
    lane_source_observation_ids: list[tuple[str, ...]] | None = None,
    lane_sample_starts: list[tuple[int, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Greedily select physical satellites with one shared delay per satellite.

    A facility column is ``(satellite_number, tau_s)``. Coordinate refinement
    may retune an already selected satellite after another satellite is added,
    but two delay states of the same physical satellite can never coexist.
    """

    if train_cost.shape != holdout_cost.shape or train_cost.shape != (
        len(lane_ids),
        len(facility_states),
    ):
        raise ValueError("facility cost matrices have inconsistent shapes")
    if lane_intervals_s is not None and len(lane_intervals_s) != len(lane_ids):
        raise ValueError("lane intervals do not match lane IDs")
    for values, label in (
        (lane_observation_ids, "lane observation IDs"),
        (lane_source_observation_ids, "lane source observation IDs"),
        (lane_sample_starts, "lane sample starts"),
    ):
        if values is not None and len(values) != len(lane_ids):
            raise ValueError(f"{label} do not match lane IDs")
    source_sets = (
        [set() for _ in lane_ids]
        if lane_source_observation_ids is None
        else [set(values) for values in lane_source_observation_ids]
    )
    source_conflict: BoolArray = np.zeros((len(lane_ids), len(lane_ids)), dtype=np.bool_)
    for left in range(len(lane_ids)):
        for right in range(left):
            conflict = not source_sets[left].isdisjoint(source_sets[right])
            source_conflict[left, right] = conflict
            source_conflict[right, left] = conflict
    satellite_for_state = [int(item["satellite_number"]) for item in facility_states]
    state_indices_by_satellite: dict[int, list[int]] = {}
    for state_index, satellite_number in enumerate(satellite_for_state):
        state_indices_by_satellite.setdefault(satellite_number, []).append(state_index)
    physical_satellites = sorted(state_indices_by_satellite)

    def state_key(index: int) -> tuple[int, float, float]:
        tau = facility_states[index].get("tau_s")
        tau_value = 0.0 if tau is None else float(tau)
        return satellite_for_state[index], abs(tau_value), tau_value

    def assignments(selected_states: list[int]) -> tuple[list[int | None], float, float]:
        chosen: list[int | None] = [None] * len(lane_ids)
        proposals = []
        for lane_index in range(len(lane_ids)):
            for state_index in selected_states:
                cost = float(train_cost[lane_index, state_index])
                improvement = unassigned_cost - cost
                if math.isfinite(cost) and improvement > 0.0:
                    proposals.append(
                        (
                            -improvement,
                            cost,
                            state_key(state_index),
                            lane_ids[lane_index],
                            lane_index,
                            state_index,
                        )
                    )
        for _, _, _, _, lane_index, state_index in sorted(proposals):
            if chosen[lane_index] is not None:
                continue
            conflicts = False
            for other_lane, other_state in enumerate(chosen):
                if other_state is None:
                    continue
                if source_conflict[lane_index, other_lane]:
                    conflicts = True
                    break
                if (
                    lane_intervals_s is not None
                    and satellite_for_state[other_state] == satellite_for_state[state_index]
                ):
                    start_s, end_s = lane_intervals_s[lane_index]
                    other_start_s, other_end_s = lane_intervals_s[other_lane]
                    if max(start_s, other_start_s) <= min(end_s, other_end_s) + 1e-9:
                        conflicts = True
                        break
            if conflicts:
                continue
            chosen[lane_index] = state_index
        train_total = 0.0
        holdout_total = 0.0
        for lane_index, assigned_state_index in enumerate(chosen):
            if assigned_state_index is None:
                train_total += unassigned_cost
                holdout_total += unassigned_cost
                continue
            train_total += float(train_cost[lane_index, assigned_state_index])
            heldout = float(holdout_cost[lane_index, assigned_state_index])
            holdout_total += heldout if math.isfinite(heldout) else unassigned_cost
        return chosen, train_total, holdout_total

    def coordinate_refine(selected_states: list[int]) -> tuple[list[int], float]:
        refined = list(selected_states)
        for _ in range(16):
            changed = False
            for position, current_state in enumerate(tuple(refined)):
                satellite_number = satellite_for_state[current_state]
                alternatives = []
                for candidate_state in state_indices_by_satellite[satellite_number]:
                    candidate = list(refined)
                    candidate[position] = candidate_state
                    _, total, _ = assignments(candidate)
                    alternatives.append((total, state_key(candidate_state), candidate_state))
                _, _, best_state = min(alternatives)
                if best_state != refined[position]:
                    refined[position] = best_state
                    changed = True
            if not changed:
                break
        _, total, _ = assignments(refined)
        return refined, total

    selected: list[int] = []
    rows: list[dict[str, Any]] = []
    prior_assignment: list[int | None] | None = None
    prior_selected_by_satellite: dict[int, int] = {}
    prior_details_by_lane: dict[str, dict[str, Any]] = {}
    for k in range(min(maximum_k, len(physical_satellites)) + 1):
        if k:
            selected_satellites = {satellite_for_state[index] for index in selected}
            remaining = [item for item in physical_satellites if item not in selected_satellites]
            alternatives = []
            for satellite_number in remaining:
                for seed_state in state_indices_by_satellite[satellite_number]:
                    refined, candidate_total = coordinate_refine([*selected, seed_state])
                    alternatives.append(
                        (
                            candidate_total,
                            satellite_number,
                            state_key(seed_state),
                            tuple(refined),
                        )
                    )
            _, _, _, selected_tuple = min(alternatives)
            selected = list(selected_tuple)
        assignment, train_total, holdout_total = assignments(selected)
        details: list[dict[str, Any]] = []
        for lane_index, assigned_state_index in enumerate(assignment):
            details.append(
                {
                    "lane_id": lane_ids[lane_index],
                    "canonical_observation_ids": (
                        []
                        if lane_observation_ids is None
                        else list(lane_observation_ids[lane_index])
                    ),
                    "source_observation_ids": (
                        []
                        if lane_source_observation_ids is None
                        else list(lane_source_observation_ids[lane_index])
                    ),
                    "sample_starts": (
                        [] if lane_sample_starts is None else list(lane_sample_starts[lane_index])
                    ),
                    "satellite_number": (
                        None
                        if assigned_state_index is None
                        else satellite_for_state[assigned_state_index]
                    ),
                    "shared_satellite_tau_s": (
                        None
                        if assigned_state_index is None
                        else facility_states[assigned_state_index].get("tau_s")
                    ),
                    "train_standardized_mse": (
                        unassigned_cost
                        if assigned_state_index is None
                        else float(train_cost[lane_index, assigned_state_index])
                    ),
                    "holdout_standardized_mse": (
                        unassigned_cost
                        if assigned_state_index is None
                        else float(holdout_cost[lane_index, assigned_state_index])
                    ),
                    "fit": (
                        None
                        if assigned_state_index is None
                        else fit_parameters[lane_index][assigned_state_index]
                    ),
                }
            )
        same_state_fraction = None
        same_satellite_fraction = None
        if prior_assignment is not None:
            same_state_fraction = float(
                np.mean(
                    [
                        current == previous
                        for current, previous in zip(assignment, prior_assignment, strict=True)
                    ]
                )
            )
            same_satellite_fraction = float(
                np.mean(
                    [
                        (None if current is None else satellite_for_state[current])
                        == (None if previous is None else satellite_for_state[previous])
                        for current, previous in zip(assignment, prior_assignment, strict=True)
                    ]
                )
            )
        selected_by_satellite = {satellite_for_state[index]: index for index in selected}
        common_selected = set(selected_by_satellite) & set(prior_selected_by_satellite)
        shared_tau_stability = None
        if common_selected:
            shared_tau_stability = float(
                np.mean(
                    [
                        facility_states[selected_by_satellite[satellite]].get("tau_s")
                        == facility_states[prior_selected_by_satellite[satellite]].get("tau_s")
                        for satellite in common_selected
                    ]
                )
            )
        composite_offset_changes_hz = []
        for detail in details:
            prior = prior_details_by_lane.get(detail["lane_id"])
            if (
                prior is not None
                and detail["satellite_number"] is not None
                and detail["satellite_number"] == prior["satellite_number"]
                and detail["fit"] is not None
                and prior["fit"] is not None
                and detail["fit"].get("composite_frequency_offset_hz") is not None
                and prior["fit"].get("composite_frequency_offset_hz") is not None
            ):
                composite_offset_changes_hz.append(
                    abs(
                        float(detail["fit"]["composite_frequency_offset_hz"])
                        - float(prior["fit"]["composite_frequency_offset_hz"])
                    )
                )
        selected_diagnostics = []
        for selected_state in selected:
            satellite_number = satellite_for_state[selected_state]
            assigned_lanes = [
                lane_index
                for lane_index, assigned_state in enumerate(assignment)
                if assigned_state == selected_state
            ]
            tau_value = facility_states[selected_state].get("tau_s")
            profile: list[tuple[float, float]] = []
            if tau_value is not None and assigned_lanes:
                for candidate_state in state_indices_by_satellite[satellite_number]:
                    costs = train_cost[assigned_lanes, candidate_state]
                    if np.isfinite(costs).all():
                        profile.append(
                            (
                                float(facility_states[candidate_state]["tau_s"]),
                                float(np.sqrt(np.mean(costs))),
                            )
                        )
            profile.sort(key=lambda item: (item[1], abs(item[0]), item[0]))
            best_tau = None if not profile else profile[0][0]
            best_rms = None if not profile else profile[0][1]
            selected_rms = None
            if assigned_lanes:
                costs = train_cost[assigned_lanes, selected_state]
                if np.isfinite(costs).all():
                    selected_rms = float(np.sqrt(np.mean(costs)))
            near = (
                [] if best_rms is None else [tau for tau, rms in profile if rms <= best_rms + 0.05]
            )
            unique_tau = [
                float(facility_states[index]["tau_s"])
                for index in state_indices_by_satellite[satellite_number]
                if facility_states[index].get("tau_s") is not None
            ]
            selected_diagnostics.append(
                {
                    "satellite_number": satellite_number,
                    "tau_s": tau_value,
                    "active": bool(assigned_lanes),
                    "assigned_lane_count": len(assigned_lanes),
                    "tau_at_bound": bool(
                        tau_value is not None
                        and unique_tau
                        and math.isclose(
                            abs(float(tau_value)), max(abs(item) for item in unique_tau)
                        )
                    ),
                    "conditional_assigned_lane_profile_best_tau_s": best_tau,
                    "conditional_assigned_lane_profile_best_normalized_rms": best_rms,
                    "selected_minus_profile_best_normalized_rms": (
                        None
                        if selected_rms is None or best_rms is None
                        else selected_rms - best_rms
                    ),
                    "aggregate_train_tau_profile_near_width_s": (
                        None if not near else max(near) - min(near)
                    ),
                    "aggregate_profile_near_tolerance_normalized_rms": (
                        None if tau_value is None else 0.05
                    ),
                    "aggregate_profile_runner_up_margin_normalized_rms": (
                        None if len(profile) < 2 else profile[1][1] - profile[0][1]
                    ),
                }
            )
        train_normalized_rms = float(math.sqrt(train_total / len(lane_ids)))
        holdout_normalized_rms = float(math.sqrt(holdout_total / len(lane_ids)))
        unit_suffix = (
            "hz_s" if error_unit == "Hz/s" else "hz" if error_unit == "Hz" else "normalized"
        )
        assigned_lane_indices = [
            index for index, state in enumerate(assignment) if state is not None
        ]
        assigned_source_counts = Counter(
            source_id
            for lane_index in assigned_lane_indices
            for source_id in source_sets[lane_index]
        )
        duplicate_assigned_source_ids = sorted(
            item for item, count in assigned_source_counts.items() if count > 1
        )
        assigned_canonical_counts = Counter(
            observation_id
            for lane_index in assigned_lane_indices
            for observation_id in (
                () if lane_observation_ids is None else lane_observation_ids[lane_index]
            )
        )
        duplicate_assigned_canonical_ids = sorted(
            item for item, count in assigned_canonical_counts.items() if count > 1
        )
        assigned_sample_counts = Counter(
            sample_start
            for lane_index in assigned_lane_indices
            for sample_start in (
                () if lane_sample_starts is None else lane_sample_starts[lane_index]
            )
        )
        shared_assigned_sample_starts = sorted(
            item for item, count in assigned_sample_counts.items() if count > 1
        )
        source_conflict_pairs = []
        temporal_same_satellite_conflict_pairs = []
        for position, left in enumerate(assigned_lane_indices):
            for right in assigned_lane_indices[:position]:
                if source_conflict[left, right]:
                    source_conflict_pairs.append([lane_ids[right], lane_ids[left]])
                left_state = assignment[left]
                right_state = assignment[right]
                if (
                    lane_intervals_s is not None
                    and left_state is not None
                    and right_state is not None
                    and satellite_for_state[left_state] == satellite_for_state[right_state]
                ):
                    left_start, left_end = lane_intervals_s[left]
                    right_start, right_end = lane_intervals_s[right]
                    if max(left_start, right_start) <= min(left_end, right_end) + 1e-9:
                        temporal_same_satellite_conflict_pairs.append(
                            [lane_ids[right], lane_ids[left]]
                        )
        rows.append(
            {
                "k": k,
                "selected_satellite_numbers": [satellite_for_state[index] for index in selected],
                "selected_satellite_states": [facility_states[index] for index in selected],
                "active_satellite_numbers": sorted(
                    {satellite_for_state[index] for index in assignment if index is not None}
                ),
                "active_satellite_states": [
                    facility_states[index]
                    for index in sorted(
                        {item for item in assignment if item is not None}, key=state_key
                    )
                ],
                "assigned_lane_count": sum(item is not None for item in assignment),
                "unassigned_lane_count": sum(item is None for item in assignment),
                "train_total_standardized_mse": train_total,
                "holdout_total_standardized_mse": holdout_total,
                "train_equal_lane_normalized_rms": train_normalized_rms,
                "holdout_equal_lane_normalized_rms": holdout_normalized_rms,
                f"train_equal_lane_rms_{unit_suffix}": train_normalized_rms * error_scale,
                f"holdout_equal_lane_rms_{unit_suffix}": holdout_normalized_rms * error_scale,
                "error_unit": error_unit,
                "same_assignment_fraction_vs_previous_k": same_state_fraction,
                "same_satellite_assignment_fraction_vs_previous_k": same_satellite_fraction,
                "same_shared_tau_fraction_for_retained_satellites_vs_previous_k": (
                    shared_tau_stability
                ),
                "median_composite_offset_change_hz_for_same_satellite_vs_previous_k": (
                    None
                    if not composite_offset_changes_hz
                    else float(np.median(composite_offset_changes_hz))
                ),
                "selected_satellite_diagnostics": selected_diagnostics,
                "overlap_violation_count": len(temporal_same_satellite_conflict_pairs),
                "temporal_same_satellite_conflict_pairs": (temporal_same_satellite_conflict_pairs),
                "source_observation_conflict_violation_count": len(source_conflict_pairs),
                "source_observation_conflict_pairs": source_conflict_pairs,
                "duplicate_assigned_source_observation_id_count": len(
                    duplicate_assigned_source_ids
                ),
                "duplicate_assigned_source_observation_ids": (duplicate_assigned_source_ids),
                "duplicate_assigned_canonical_observation_id_count": len(
                    duplicate_assigned_canonical_ids
                ),
                "duplicate_assigned_canonical_observation_ids": (duplicate_assigned_canonical_ids),
                "shared_assigned_sample_start_count": len(shared_assigned_sample_starts),
                "shared_assigned_sample_starts": shared_assigned_sample_starts,
                "shared_sample_starts_are_allowed_when_source_ids_differ": True,
                "assignments": details,
            }
        )
        prior_assignment = assignment
        prior_selected_by_satellite = selected_by_satellite
        prior_details_by_lane = {item["lane_id"]: item for item in details}
    return rows


def activation_penalty_sweep(
    facility_rows: list[dict[str, Any]], penalties: list[float]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for penalty in penalties:
        selected = min(
            facility_rows,
            key=lambda item: (
                float(item["train_total_standardized_mse"]) + penalty * int(item["k"]),
                int(item["k"]),
            ),
        )
        row = {
            "activation_penalty": penalty,
            "selected_k": selected["k"],
            "penalized_train_objective": (
                selected["train_total_standardized_mse"] + penalty * selected["k"]
            ),
            "train_equal_lane_normalized_rms": selected["train_equal_lane_normalized_rms"],
            "holdout_equal_lane_normalized_rms": selected["holdout_equal_lane_normalized_rms"],
            "selected_satellite_numbers": selected["selected_satellite_numbers"],
            "selected_satellite_states": selected.get(
                "selected_satellite_states",
                [
                    {"satellite_number": item, "tau_s": None}
                    for item in selected["selected_satellite_numbers"]
                ],
            ),
            "active_satellite_numbers": selected["active_satellite_numbers"],
            "active_satellite_states": selected.get(
                "active_satellite_states",
                [
                    {"satellite_number": item, "tau_s": None}
                    for item in selected["active_satellite_numbers"]
                ],
            ),
            "selected_satellite_diagnostics": selected.get("selected_satellite_diagnostics", []),
            "error_unit": selected.get("error_unit", "normalized"),
        }
        for key, value in selected.items():
            if key.startswith(("train_equal_lane_rms_", "holdout_equal_lane_rms_")):
                row[key] = value
        rows.append(row)
    return rows


def evaluate_model(
    model_name: str,
    lanes: list[Lane],
    bank: PredictionBank,
    *,
    tau_grid_s: FloatArray,
    horizon_deg: float,
    cfo_scale_hz: float,
    rate_scale_hz_s: float,
    acceleration_bound_hz_s2: float,
    maximum_k: int,
    unassigned_cost: float,
    activation_penalties: list[float],
) -> dict[str, Any]:
    if model_name == "rate_only":
        facility_states: list[dict[str, Any]] = [
            {
                "satellite_number": satellite_number,
                "name": bank.names[index],
                "tau_s": None,
            }
            for index, satellite_number in enumerate(bank.satellite_numbers)
        ]
    else:
        facility_states = [
            {
                "satellite_number": satellite_number,
                "name": bank.names[satellite_index],
                "tau_s": float(tau_s),
            }
            for satellite_index, satellite_number in enumerate(bank.satellite_numbers)
            for tau_s in tau_grid_s
        ]
    shape = (len(lanes), len(facility_states))
    train_cost: FloatArray = np.full(shape, np.inf, dtype=np.float64)
    holdout_cost: FloatArray = np.full(shape, np.inf, dtype=np.float64)
    parameters: list[list[dict[str, Any] | None]] = [[None for _ in facility_states] for _ in lanes]
    for lane_index, lane in enumerate(lanes):
        for satellite_index in range(len(bank.satellite_numbers)):
            if model_name == "rate_only":
                fit = fit_rate_only(
                    lane,
                    bank.time_s,
                    bank.doppler_hz[satellite_index],
                    bank.elevation_deg[satellite_index],
                    horizon_deg=horizon_deg,
                    rate_scale_hz_s=rate_scale_hz_s,
                )
                state_index = satellite_index
                parameters[lane_index][state_index] = fit
                if fit is not None:
                    train_cost[lane_index, state_index] = fit["train_standardized_mse"]
                    holdout_cost[lane_index, state_index] = fit["holdout_standardized_mse"]
            else:
                acceleration_bound = (
                    acceleration_bound_hz_s2 if model_name == "cfo_tau_quadratic" else None
                )
                profile = fit_cfo_tau_grid(
                    lane,
                    bank.time_s,
                    bank.doppler_hz[satellite_index],
                    bank.elevation_deg[satellite_index],
                    tau_grid_s,
                    horizon_deg=horizon_deg,
                    cfo_scale_hz=cfo_scale_hz,
                    acceleration_bound_hz_s2=acceleration_bound,
                )
                for tau_index, fit in enumerate(profile):
                    state_index = satellite_index * tau_grid_s.size + tau_index
                    parameters[lane_index][state_index] = fit
                    if fit is not None:
                        train_cost[lane_index, state_index] = fit["train_standardized_mse"]
                        holdout_cost[lane_index, state_index] = fit["holdout_standardized_mse"]

    independent: list[dict[str, Any]] = []
    for lane_index, lane in enumerate(lanes):
        best_by_satellite: dict[int, tuple[float, int]] = {}
        for state_index, state in enumerate(facility_states):
            cost = float(train_cost[lane_index, state_index])
            if not math.isfinite(cost):
                continue
            satellite_number = int(state["satellite_number"])
            candidate = (cost, state_index)
            current = best_by_satellite.get(satellite_number)
            if current is None or (
                candidate[0],
                abs(float(state.get("tau_s") or 0.0)),
                float(state.get("tau_s") or 0.0),
            ) < (
                current[0],
                abs(float(facility_states[current[1]].get("tau_s") or 0.0)),
                float(facility_states[current[1]].get("tau_s") or 0.0),
            ):
                best_by_satellite[satellite_number] = candidate
        candidates = sorted(
            (cost, satellite_number, state_index)
            for satellite_number, (cost, state_index) in best_by_satellite.items()
        )
        top = []
        for _, satellite_number, state_index in candidates[:2]:
            top.append(
                {
                    "satellite_number": satellite_number,
                    "name": facility_states[state_index]["name"],
                    "fit": parameters[lane_index][state_index],
                }
            )
        independent.append({"lane_id": lane.lane_id, "top_two": top})

    facility = greedy_shared_tau_facility_sweep(
        [lane.lane_id for lane in lanes],
        facility_states,
        train_cost,
        holdout_cost,
        parameters,
        maximum_k=maximum_k,
        unassigned_cost=unassigned_cost,
        lane_intervals_s=[(lane.start_s, lane.end_s) for lane in lanes],
        error_scale=(rate_scale_hz_s if model_name == "rate_only" else cfo_scale_hz),
        error_unit=("Hz/s" if model_name == "rate_only" else "Hz"),
        lane_observation_ids=[lane.observation_ids for lane in lanes],
        lane_source_observation_ids=[lane.source_observation_ids for lane in lanes],
        lane_sample_starts=[lane.sample_starts for lane in lanes],
    )
    return {
        "model_label": (
            "raw/dealiased trajectory-slope proxy; not reset-debiased ramp rate"
            if model_name == "rate_only"
            else "shared per-satellite delay with per-lane composite frequency intercepts"
        ),
        "facility_state_count": len(facility_states),
        "independent_top_two": independent,
        "facility_sweep": facility,
        "activation_penalty_sweep": activation_penalty_sweep(facility, activation_penalties),
    }


def assignment_stability(models: dict[str, Any]) -> list[dict[str, Any]]:
    by_model = {
        model: {row["k"]: row for row in result["facility_sweep"]}
        for model, result in models.items()
    }
    common_k = sorted(set.intersection(*(set(rows) for rows in by_model.values())))
    comparisons: list[dict[str, Any]] = []
    pairs = (("rate_only", "cfo_tau"), ("cfo_tau", "cfo_tau_quadratic"))
    for left, right in pairs:
        for k in common_k:
            left_assignments = {item["lane_id"]: item for item in by_model[left][k]["assignments"]}
            right_assignments = {
                item["lane_id"]: item for item in by_model[right][k]["assignments"]
            }
            shared = sorted(set(left_assignments) & set(right_assignments))
            same = [
                left_assignments[lane]["satellite_number"]
                == right_assignments[lane]["satellite_number"]
                for lane in shared
            ]
            tau_deltas = []
            for lane in shared:
                left_item = left_assignments[lane]
                right_item = right_assignments[lane]
                if (
                    left_item["satellite_number"] is not None
                    and left_item["satellite_number"] == right_item["satellite_number"]
                    and left_item["fit"] is not None
                    and right_item["fit"] is not None
                    and left_item["fit"].get("tau_s") is not None
                    and right_item["fit"].get("tau_s") is not None
                ):
                    tau_deltas.append(
                        abs(float(left_item["fit"]["tau_s"]) - float(right_item["fit"]["tau_s"]))
                    )
            comparisons.append(
                {
                    "left_model": left,
                    "right_model": right,
                    "k": k,
                    "same_assignment_fraction": float(np.mean(same)),
                    "median_tau_change_s_for_same_assignment": (
                        None if not tau_deltas else float(np.median(tau_deltas))
                    ),
                }
            )
    return comparisons


def holdout_acceptance_against_radio_nulls(
    models: dict[str, Any], radio_nulls: dict[str, Any]
) -> dict[str, Any]:
    comparisons = []
    definitions = (
        ("rate_only", "constant_train_rate", "hz_s"),
        ("cfo_tau", "affine", "hz"),
        ("cfo_tau_quadratic", "quadratic", "hz"),
    )
    for model_name, null_name, suffix in definitions:
        zero_penalty_selected = next(
            item
            for item in models[model_name]["activation_penalty_sweep"]
            if float(item["activation_penalty"]) == 0.0
        )
        evaluated = [item for item in models[model_name]["facility_sweep"] if int(item["k"]) > 0]
        oracle_minimum = min(
            evaluated,
            key=lambda item: float(item[f"holdout_equal_lane_rms_{suffix}"]),
        )
        orbit_error = float(zero_penalty_selected[f"holdout_equal_lane_rms_{suffix}"])
        null_error = float(radio_nulls[null_name][f"holdout_equal_lane_rms_{suffix}"])
        all_fail = all(
            float(item[f"holdout_equal_lane_rms_{suffix}"]) >= null_error for item in evaluated
        )
        comparisons.append(
            {
                "model": model_name,
                "zero_penalty_training_selected_k": int(zero_penalty_selected["selected_k"]),
                "zero_penalty_orbit_holdout_equal_lane_rms": orbit_error,
                "evaluated_training_greedy_k_values": [int(item["k"]) for item in evaluated],
                "oracle_minimum_holdout_k_for_rejection_diagnostic_only": int(oracle_minimum["k"]),
                "oracle_minimum_holdout_equal_lane_rms": float(
                    oracle_minimum[f"holdout_equal_lane_rms_{suffix}"]
                ),
                "radio_only_null": null_name,
                "radio_only_holdout_equal_lane_rms": null_error,
                "unit": "Hz/s" if suffix == "hz_s" else "Hz",
                "zero_penalty_orbit_minus_null_holdout_rms": orbit_error - null_error,
                "every_evaluated_k_fails_simpler_holdout_null": all_fail,
            }
        )
    all_rejected = all(item["every_evaluated_k_fails_simpler_holdout_null"] for item in comparisons)
    return {
        "selection_rule": (
            "compare every fixed-K training-greedy state with the matched radio-only model; "
            "zero-activation-penalty K is the training-selected headline, while the oracle "
            "minimum over K is reported only as a conservative rejection diagnostic"
        ),
        "comparisons": comparisons,
        "all_evaluated_training_greedy_k_states_rejected": all_rejected,
        "conclusion": (
            "every evaluated training-greedy K state is rejected because none improves grouped "
            "holdout error over its matched radio-only null"
            if all_rejected
            else "at least one evaluated training-greedy K state improves its matched radio-only "
            "holdout null; inspect per-model comparisons before any candidate interpretation"
        ),
    }


def _markdown(result: dict[str, Any], command: str) -> str:
    split_audit = result["lane_support_accounting"]["train_holdout_split"]
    all_k_rejected = result["holdout_acceptance"]["all_evaluated_training_greedy_k_states_rejected"]
    acceptance_summary = (
        "**Every evaluated training-greedy K state is rejected:** each has larger grouped "
        "holdout error than its matched simpler radio-only null. This does not enumerate or "
        "reject every possible identity set; the K sweeps below remain diagnostics, not accepted "
        "identities."
        if all_k_rejected
        else "**At least one evaluated training-greedy K state improves its matched radio-only "
        "holdout null.** Inspect the per-model comparison before interpreting candidates; this "
        "alone is not an identity claim."
    )
    lines = [
        "# Strict duration result and relaxed Starlink orbit sweep",
        "",
        "## Primary strict answer",
        "",
        (
            f"**Zero satellite assignments are eligible under the strict >= "
            f"{result['strict_primary_gate']['minimum_duration_s']:.1f} s fully qualified "
            "known-pilot-frame gate.** The persisted analyzed inventory contains only "
            f"{result['strict_primary_gate']['deduplicated_qualified_window_count']} isolated "
            "qualified windows, each approximately "
            f"{result['strict_primary_gate']['longest_qualified_run_s'] * 1e3:.0f} ms. "
            "They do not form a one-second coherent-rate run."
        ),
        "",
        (
            "Frame evidence is incomplete across the full final-track inventory, so this is a "
            "zero-eligible result under the currently persisted strict evidence—not proof that no "
            "one-second physical transmission existed."
        ),
        "",
        "## Relaxed raw/dealiased trajectory-support surrogate",
        "",
        "### Scope",
        "",
        (
            f"This exploratory run evaluates {result['lane_count']} continuity-supported pieces "
            f"split from {result['lane_support_accounting']['source_branch_count']} radio-only "
            "dealiased branches "
            f"from `{CAPTURE_ID}` / `{STREAM_ID}` / `{RADIO_ID}` RX{RECEIVER_ID} at "
            f"{result['rf_hz'] / 1e9:.9f} GHz. Satellite choice and nuisance parameters use only "
            "an initially chronological 60/40 split. The seeded holdout is then closed globally "
            "over shared sample epochs and exact source-observation IDs, leaving an actual global "
            f"training fraction of {split_audit['actual_global_train_fraction']:.1%}. "
            "The grouped holdout never selects satellites or fitted parameters."
        ),
        "",
        (
            "A piece must span at least "
            f"{result['lane_support_accounting']['gates']['minimum_span_s']:.2f} s, contain at "
            f"least {result['lane_support_accounting']['gates']['minimum_distinct_epochs']} "
            "distinct 20 ms probe epochs, occupy at least "
            f"{result['lane_support_accounting']['gates']['minimum_occupancy_fraction']:.0%} "
            "of the expected 40/s schedule, and have no inter-observation gap over "
            f"{result['lane_support_accounting']['gates']['maximum_gap_s']:.3f} s. "
            f"{result['lane_support_accounting']['rejected_piece_count']} split pieces failed "
            "one or more gates; the JSON accounts for each one."
        ),
        "",
        (
            "Grouped-split audit: "
            f"{split_audit['cross_split_sample_start_overlap_count']} "
            "sample-start overlaps and "
            f"{split_audit['cross_split_source_observation_id_overlap_count']} "
            "exact source-ID overlaps between training and holdout."
        ),
        "",
        (
            f"The causal catalogue contains {result['catalogue']['object_count']} objects; "
            f"{result['catalogue']['visible_candidate_count']} were above the "
            f"{result['horizon_deg']:.1f}° "
            "horizon somewhere in the fitted interval after propagation/plausibility screening."
        ),
        "",
        (
            "Observer geometry uses the external Sausalito preset "
            f"({result['observer_site']['latitude_deg']:.6f}, "
            f"{result['observer_site']['longitude_deg']:.6f}, "
            f"{result['observer_site']['altitude_m']:.0f} m) with a nominal "
            f"{result['observer_site']['horizontal_uncertainty_m']:.0f} m uncertainty. The capture "
            "does not contain a GPS/site binding, so this is an input assumption, not captured "
            "provenance."
        ),
        "",
    ]
    lines.extend(
        [
            "### Holdout acceptance against radio-only nulls",
            "",
            "| orbit model | zero-penalty K / holdout | oracle-min K / holdout | radio-only "
            "holdout | unit | every K fails |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for comparison in result["holdout_acceptance"]["comparisons"]:
        lines.append(
            f"| `{comparison['model']}` | "
            f"{comparison['zero_penalty_training_selected_k']} / "
            f"{comparison['zero_penalty_orbit_holdout_equal_lane_rms']:.1f} | "
            f"{comparison['oracle_minimum_holdout_k_for_rejection_diagnostic_only']} / "
            f"{comparison['oracle_minimum_holdout_equal_lane_rms']:.1f} | "
            f"{comparison['radio_only_holdout_equal_lane_rms']:.1f} | "
            f"{comparison['unit']} | "
            f"{'**yes**' if comparison['every_evaluated_k_fails_simpler_holdout_null'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            acceptance_summary,
            "",
            "### Greedy set-size sweep",
            "",
            (
                "K=0 pays the fixed unassigned cost; each later row greedily adds the satellite "
                "giving the smallest training cost. Holdout never chooses a satellite, K, "
                "composite frequency intercept, delay, or quadratic curvature. For the two delay "
                "models, every selected physical satellite has exactly one delay shared by all of "
                "its assigned pieces. A physical satellite is also forbidden from owning "
                "time-overlapping pieces."
                " Exact source-observation identity is also exclusive across all assigned pieces, "
                "independent of NORAD; different candidate IDs at one sample epoch remain allowed."
            ),
            "",
        ]
    )
    for model_name, model in result["models"].items():
        unit = "Hz/s" if model_name == "rate_only" else "Hz"
        unit_key = "hz_s" if model_name == "rate_only" else "hz"
        lines.extend(
            [
                f"#### `{model_name}`",
                "",
                model["model_label"],
                "",
                f"| K | selected NORAD@tau(s) | active | assigned | train ({unit}) | "
                f"holdout ({unit}) | same state vs K-1 |",
                "|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in model["facility_sweep"]:
            selected = (
                ", ".join(
                    str(item["satellite_number"])
                    if item.get("tau_s") is None
                    else f"{item['satellite_number']}@{item['tau_s']:+.2f}"
                    for item in row["selected_satellite_states"]
                )
                or "—"
            )
            stability = row["same_assignment_fraction_vs_previous_k"]
            stability_text = "—" if stability is None else f"{stability:.2f}"
            lines.append(
                f"| {row['k']} | {selected} | {len(row['active_satellite_numbers'])} | "
                f"{row['assigned_lane_count']} | {row[f'train_equal_lane_rms_{unit_key}']:.1f} | "
                f"{row[f'holdout_equal_lane_rms_{unit_key}']:.1f} | {stability_text} |"
            )
        lines.extend(
            [
                "",
                "Activation-penalty selection (training objective only):",
                "",
                f"| penalty / satellite | K | selected NORAD@tau(s) | train ({unit}) | "
                f"holdout ({unit}) |",
                "|---:|---:|---|---:|---:|",
            ]
        )
        for row in model["activation_penalty_sweep"]:
            selected = (
                ", ".join(
                    str(item["satellite_number"])
                    if item.get("tau_s") is None
                    else f"{item['satellite_number']}@{item['tau_s']:+.2f}"
                    for item in row["selected_satellite_states"]
                )
                or "—"
            )
            lines.append(
                f"| {row['activation_penalty']:.1f} | {row['selected_k']} | {selected} | "
                f"{row[f'train_equal_lane_rms_{unit_key}']:.1f} | "
                f"{row[f'holdout_equal_lane_rms_{unit_key}']:.1f} |"
            )
        lines.append("")

    lines.extend(
        [
            "### Zero-penalty per-piece nuisance fits",
            "",
            (
                "These are the training-selected K fits shown for auditability even though the "
                "grouped holdout rejects them. `t_ref` is seconds after capture start. The "
                "intercept is a composite receiver/path frequency offset at that reference time, "
                "not transmitter CFO."
            ),
            "",
        ]
    )
    for model_name in ("cfo_tau", "cfo_tau_quadratic"):
        model = result["models"][model_name]
        zero_penalty = next(
            row
            for row in model["activation_penalty_sweep"]
            if float(row["activation_penalty"]) == 0.0
        )
        selected_row = next(
            row
            for row in model["facility_sweep"]
            if int(row["k"]) == int(zero_penalty["selected_k"])
        )
        lines.extend(
            [
                f"#### `{model_name}` K={selected_row['k']}",
                "",
                "| lane piece | NORAD | shared tau (s) | composite offset (Hz) | "
                "t_ref (s) | residual curvature (Hz/s²) | train / holdout RMSE (Hz) |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for assignment in selected_row["assignments"]:
            fit = assignment["fit"]
            if fit is None:
                continue
            curvature = fit["residual_acceleration_hz_s2"]
            curvature_text = "—" if curvature is None else f"{curvature:+.2f}"
            lines.append(
                f"| `{assignment['lane_id']}` | {assignment['satellite_number']} | "
                f"{assignment['shared_satellite_tau_s']:+.2f} | "
                f"{fit['composite_frequency_offset_hz']:+.1f} | "
                f"{fit['offset_reference_time_s']:.3f} | {curvature_text} | "
                f"{fit['train_rmse_hz']:.1f} / {fit['holdout_rmse_hz']:.1f} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation limits",
            "",
            (
                "- These are candidate rankings, not satellite identifications. A scalar Doppler "
                "rate is crowded, and a bounded time shift is locally confounded with CFO through "
                "`D(t+tau) ~= D(t) + tau D'(t)`."
            ),
            (
                "- The quadratic term is residual Doppler curvature in Hz/s². It is a sensitivity "
                "parameter, not a fitted physical orbital acceleration or a TLE correction."
            ),
            (
                "- The reported intercept is a composite receiver/path frequency offset at its "
                "stated lane reference time; it must not be interpreted as transmitter CFO. "
                "Offset and quadratic terms are fit per lane, while one time delay is shared by "
                "all lanes assigned to a selected satellite. No pooled per-satellite CFO is "
                "attempted because its gauge against receiver/path resets is not identified here."
            ),
            (
                "- Assignment occurs at frozen radio-lane level. Each lane's existing 20 ms "
                "observations inherit its satellite label; this run does not solve independent "
                "20 ms or 1.333 ms probe assignments. No durable 1.333 ms observation product "
                "was used."
            ),
            (
                "- Every retained support piece passes the explicit span, distinct-epoch, "
                "occupancy, "
                "and maximum-gap gates, but that is continuity of CFO observations, not proof of "
                "phase coherence for the whole interval."
            ),
            (
                "- `rate_only` uses a raw/dealiased trajectory-slope proxy. It is not the "
                "reset-debiased ramp-rate observable used by the stronger continuity reports."
            ),
            (
                "- The lanes were constructed without TLE input, but they were discovered using "
                "the whole capture. The grouped split seeded from per-lane 60/40 prefixes "
                "therefore protects model selection only conditional on those frozen lanes."
            ),
            (
                "- Equal lane weighting prevents long lanes from dominating, but overlapping radio "
                "hypotheses are not statistically independent. Assignment is a deterministic "
                "conflict-aware greedy approximation, not a global mixed-integer optimum. The "
                "fixed five-sigma unassigned cost is a transparent gate, not a calibrated "
                "likelihood."
            ),
            (
                "- The RF frequency is explicitly supplied because the persisted pilot scan labels "
                "its frequency reference `uncalibrated_prior`."
            ),
            (
                "- Observer coordinates are an external Sausalito preset with nominal 50 m "
                "horizontal uncertainty; the capture has no GPS/site binding."
            ),
            "",
            "## Reproduce",
            "",
            "```bash",
            command,
            "```",
            "",
            f"Full machine-readable assignments and fitted parameters: `{result['output_json']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--lanes", type=Path, default=DEFAULT_LANES)
    parser.add_argument("--duration-audit", type=Path, default=DEFAULT_DURATION_AUDIT)
    parser.add_argument("--tle", type=Path, default=DEFAULT_TLE)
    parser.add_argument("--expected-tle-sha256", default=EXPECTED_TLE_SHA256)
    parser.add_argument("--rf-hz", type=float, default=RF_HZ)
    parser.add_argument("--horizon-deg", type=float, default=0.0)
    parser.add_argument("--minimum-lane-span-s", type=float, default=1.0)
    parser.add_argument("--minimum-distinct-epochs", type=int, default=28)
    parser.add_argument("--minimum-occupancy-fraction", type=float, default=0.70)
    parser.add_argument("--maximum-gap-s", type=float, default=0.10)
    parser.add_argument("--expected-probe-rate-hz", type=float, default=40.0)
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--tau-bound-s", type=float, default=0.3)
    parser.add_argument("--tau-step-s", type=float, default=0.05)
    parser.add_argument("--coarse-spacing-s", type=float, default=0.5)
    parser.add_argument("--fine-spacing-s", type=float, default=0.025)
    parser.add_argument("--cfo-scale-hz", type=float, default=100.0)
    parser.add_argument("--rate-scale-hz-s", type=float, default=100.0)
    parser.add_argument("--acceleration-bound-hz-s2", type=float, default=200.0)
    parser.add_argument("--unassigned-cost", type=float, default=25.0)
    parser.add_argument("--maximum-k", type=int, default=8)
    parser.add_argument(
        "--activation-penalties",
        type=float,
        nargs="+",
        default=[0.0, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0],
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.0 < args.train_fraction < 1.0:
        raise ValueError("train fraction must lie strictly between zero and one")
    tle_digest = _sha256(args.tle)
    if args.expected_tle_sha256 and tle_digest != args.expected_tle_sha256:
        raise ValueError("TLE digest does not match the requested causal snapshot")
    manifest = _read_json(args.manifest)
    strict_gate = strict_duration_gate_summary(args.duration_audit, args.lanes)
    capture_start_ns = capture_start_utc_ns(
        manifest, stream_id=STREAM_ID, radio_id=RADIO_ID, receiver_id=RECEIVER_ID
    )
    lanes, lane_support_accounting = load_lanes_with_accounting(
        args.lanes,
        minimum_span_s=args.minimum_lane_span_s,
        minimum_distinct_epochs=args.minimum_distinct_epochs,
        minimum_occupancy_fraction=args.minimum_occupancy_fraction,
        maximum_gap_s=args.maximum_gap_s,
        expected_probe_rate_hz=args.expected_probe_rate_hz,
        train_fraction=args.train_fraction,
    )
    if not lanes:
        raise ValueError("no lane survives the minimum duration gate")
    bank = build_prediction_bank(
        args.tle,
        capture_start_ns=capture_start_ns,
        start_s=min(lane.start_s for lane in lanes),
        end_s=max(lane.end_s for lane in lanes),
        tau_bound_s=args.tau_bound_s,
        rf_hz=args.rf_hz,
        horizon_deg=args.horizon_deg,
        coarse_spacing_s=args.coarse_spacing_s,
        fine_spacing_s=args.fine_spacing_s,
    )
    tau_count = int(round(2.0 * args.tau_bound_s / args.tau_step_s)) + 1
    tau_grid = np.linspace(-args.tau_bound_s, args.tau_bound_s, tau_count)
    models = {
        model_name: evaluate_model(
            model_name,
            lanes,
            bank,
            tau_grid_s=tau_grid,
            horizon_deg=args.horizon_deg,
            cfo_scale_hz=args.cfo_scale_hz,
            rate_scale_hz_s=args.rate_scale_hz_s,
            acceleration_bound_hz_s2=args.acceleration_bound_hz_s2,
            maximum_k=args.maximum_k,
            unassigned_cost=args.unassigned_cost,
            activation_penalties=args.activation_penalties,
        )
        for model_name in ("rate_only", "cfo_tau", "cfo_tau_quadratic")
    }
    lane_rows = [
        {
            "lane_id": lane.lane_id,
            "source_branch_id": lane.source_branch_id,
            "support_piece_index": lane.support_piece_index,
            "start_s": lane.start_s,
            "end_s": lane.end_s,
            "span_s": lane.span_s,
            "observation_count": int(lane.times_s.size),
            "canonical_observation_ids": list(lane.observation_ids),
            "source_observation_ids": list(lane.source_observation_ids),
            "sample_starts": list(lane.sample_starts),
            "train_canonical_observation_ids": [
                observation_id
                for observation_id, is_train in zip(
                    lane.observation_ids, lane.train_mask, strict=True
                )
                if bool(is_train)
            ],
            "holdout_canonical_observation_ids": [
                observation_id
                for observation_id, is_train in zip(
                    lane.observation_ids, lane.train_mask, strict=True
                )
                if not bool(is_train)
            ],
            "train_source_observation_ids": sorted(
                {
                    source_id
                    for source_ids, is_train in zip(
                        lane.source_observation_ids_by_observation,
                        lane.train_mask,
                        strict=True,
                    )
                    if bool(is_train)
                    for source_id in source_ids
                }
            ),
            "holdout_source_observation_ids": sorted(
                {
                    source_id
                    for source_ids, is_train in zip(
                        lane.source_observation_ids_by_observation,
                        lane.train_mask,
                        strict=True,
                    )
                    if not bool(is_train)
                    for source_id in source_ids
                }
            ),
            "distinct_epoch_count": lane.distinct_epoch_count,
            "occupancy_fraction": lane.occupancy_fraction,
            "maximum_gap_s": lane.maximum_gap_s,
            "train_observation_count": int(np.count_nonzero(lane.train_mask)),
            "holdout_observation_count": int(np.count_nonzero(~lane.train_mask)),
            "radio_only_nulls": radio_only_nulls(lane, cfo_scale_hz=args.cfo_scale_hz),
        }
        for lane in lanes
    ]
    aggregate_nulls = aggregate_radio_only_nulls(lane_rows)
    result = {
        "analysis": "frozen-lane-starlink-model-evaluation-v1",
        "candidate_only": True,
        "capture_id": CAPTURE_ID,
        "stream_id": STREAM_ID,
        "radio_id": RADIO_ID,
        "receiver_id": RECEIVER_ID,
        "rf_hz": args.rf_hz,
        "capture_start_utc_ns": capture_start_ns,
        "observer_site": {
            "latitude_deg": SITE.latitude_deg,
            "longitude_deg": SITE.longitude_deg,
            "altitude_m": SITE.altitude_m,
            "horizontal_uncertainty_m": 50.0,
            "provenance": (
                "external Sausalito preset assumption; no GPS/site binding in capture manifest"
            ),
        },
        "strict_primary_gate": strict_gate,
        "manifest_path": str(args.manifest),
        "manifest_sha256": _sha256(args.manifest),
        "lane_bank_path": str(args.lanes),
        "lane_bank_sha256": _sha256(args.lanes),
        "tle_path": str(args.tle),
        "tle_sha256": tle_digest,
        "horizon_deg": args.horizon_deg,
        "minimum_lane_span_s": args.minimum_lane_span_s,
        "lane_support_accounting": lane_support_accounting,
        "train_fraction": args.train_fraction,
        "tau_grid_s": [float(value) for value in tau_grid],
        "acceleration_bound_hz_s2": args.acceleration_bound_hz_s2,
        "cfo_scale_hz": args.cfo_scale_hz,
        "rate_scale_hz_s": args.rate_scale_hz_s,
        "unassigned_standardized_mse": args.unassigned_cost,
        "lane_count": len(lanes),
        "lanes": lane_rows,
        "aggregate_radio_only_nulls": aggregate_nulls,
        "catalogue": {
            "object_count": bank.catalogue_count,
            "plausible_count": bank.plausible_count,
            "coarse_candidate_count": bank.coarse_candidate_count,
            "visible_candidate_count": len(bank.satellite_numbers),
            "satellites": [
                {
                    "catalogue_index": int(index),
                    "satellite_number": satellite_number,
                    "name": name,
                    "element_epoch_utc_ns": epoch,
                    "peak_elevation_deg": float(np.max(bank.elevation_deg[row])),
                }
                for row, (index, satellite_number, name, epoch) in enumerate(
                    zip(
                        bank.catalogue_indices,
                        bank.satellite_numbers,
                        bank.names,
                        bank.element_epoch_utc_ns,
                        strict=True,
                    )
                )
            ],
        },
        "models": models,
        "holdout_acceptance": holdout_acceptance_against_radio_nulls(models, aggregate_nulls),
        "cross_model_stability": assignment_stability(models),
        "limitations": [
            "candidate rankings only, not satellite identity claims",
            "frozen lane assignment inherited by 20 ms observations; no 1.333 ms product",
            "shared per-satellite delay but per-lane composite intercept/quadratic parameters",
            (
                "rate-only scalar-slope proxy has no delay; a shared-delay rate-curve model is "
                "deferred"
            ),
            "composite frequency intercept is not transmitter CFO",
            "quadratic residual curvature is not physical orbit acceleration",
            "train/holdout split is conditional on lanes discovered from the whole capture",
            "minimum lane span is not proof of phase coherence",
            "overlap-exclusive assignment is greedy rather than globally optimal",
            "observer site is an external 50 m preset assumption without capture GPS binding",
        ],
        "output_json": str(args.output_json),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    command = (
        ".venv/bin/python tools/evaluate_duration_constrained_satellite_assignment.py "
        f"--summary-only --output {args.duration_audit}\n"
        ".venv/bin/python tools/evaluate_frozen_lane_satellite_models.py "
        f"--tle {args.tle} --output-json {args.output_json} "
        f"--output-report {args.output_report} --duration-audit {args.duration_audit}"
    )
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(_markdown(result, command))
    print(
        json.dumps(
            {
                "lane_count": len(lanes),
                "visible_candidate_count": len(bank.satellite_numbers),
                "output_json": str(args.output_json),
                "output_report": str(args.output_report),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
