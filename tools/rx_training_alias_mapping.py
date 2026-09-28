#!/usr/bin/env python3
"""Export training-only raw/alias coordinates for a frozen candidate bank.

The raw cache is filtered by the frozen grouped partition before projection or
trajectory reconstruction.  This stage preserves the bank's track ordering and
never examines reception or held-frequency candidates.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.rx_training_candidate_bank import (
    atomic_json,
    canonical_digest,
    digest,
    partition_index,
    source_window_id,
    training_only_input,
)

CANONICAL_RF_HZ = 11_200_000_000.0
ALIAS_SPACING_HZ = 1.0 / 4.4e-6
PAIR_EPOCH_GATE_NS = 2_200
PAIR_EPOCH_PERIOD_NS = 1_000_000_000.0 / 750.0
CALIBRATION_BIN_HZ = 5_000.0
CALIBRATION_INLIER_HZ = 10_000.0
CALIBRATION_MIN_WINDOWS = 10
CALIBRATION_MAX_MAD_HZ = 2_500.0


def protocol_sha256(path: Path) -> str:
    return digest(path.read_bytes())


def _edge(value: Any) -> str:
    return str(getattr(value, "value", value))


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def unique_tracklets(trajectory: Any) -> dict[str, Any]:
    """Return unambiguous public tracklets, rejecting divergent duplicates."""
    result: dict[str, Any] = {}
    signatures: dict[str, tuple[tuple[Any, ...], ...]] = {}
    for tracklet in trajectory.tracklets:
        track_id = str(tracklet.tracklet_id)
        signature = tuple(
            (
                str(point.candidate_id),
                int(point.relative_alias_index),
                float(point.normalized_raw_cfo_hz),
                float(point.normalized_dealiased_cfo_hz),
            )
            for point in tracklet.points
        )
        if track_id in signatures and signatures[track_id] != signature:
            raise ValueError(f"trajectory has divergent duplicate tracklet: {track_id}")
        signatures[track_id] = signature
        result[track_id] = tracklet
    return result


def unique_track_graph_observations(trajectory: Any) -> dict[str, dict[str, Any]]:
    """Index each unambiguous public track graph by its source group."""
    result: dict[str, dict[str, Any]] = {}
    signatures: dict[str, tuple[tuple[str, str], ...]] = {}
    for hypothesis in trajectory.hypotheses:
        episode_by_id = {str(item.episode_id): item for item in hypothesis.graph.episodes}
        observation_by_id = {
            str(item.observation_id): item for item in hypothesis.graph.observations
        }
        for binding in hypothesis.tracklet_episode_bindings:
            track_id = str(binding.tracklet_id)
            episode = episode_by_id[str(binding.episode_id)]
            observations = [observation_by_id[str(value)] for value in episode.observation_ids]
            by_source = {str(item.source_group_id): item for item in observations}
            if len(by_source) != len(observations):
                raise ValueError(f"track graph repeats a source group: {track_id}")
            signature = tuple(
                sorted((source, str(item.observation_id)) for source, item in by_source.items())
            )
            if track_id in signatures and signatures[track_id] != signature:
                raise ValueError(f"trajectory has divergent public graphs: {track_id}")
            signatures[track_id] = signature
            result[track_id] = by_source
    return result


def candidate_window_index(raw: Any, filtered: Any, projected: tuple[Any, ...]) -> dict[str, str]:
    """Bind projected candidates to windows without overwriting probe locators."""
    probe_windows: dict[tuple[int, int, int], str] = {}
    for probe in filtered.probes:
        locator = (probe.visit_index, probe.receiver_id, probe.probe_index)
        if locator in probe_windows:
            raise ValueError(f"duplicate public probe locator: {locator}")
        probe_windows[locator] = source_window_id(raw, probe)
    return {
        str(point.candidate_id): probe_windows[
            (point.visit_index, point.receiver_id, point.probe_index)
        ]
        for point in projected
    }


def export_selected_tracks(
    session_id: str,
    frozen_tracks: list[dict[str, Any]],
    trajectory: Any,
    projected: tuple[Any, ...],
    candidate_windows: dict[str, str],
    *,
    canonical_rf_hz: float = CANONICAL_RF_HZ,
    alias_spacing_hz: float = ALIAS_SPACING_HZ,
) -> list[dict[str, Any]]:
    """Bind each frozen bank observation to its exact reconstructed point."""
    by_track = unique_tracklets(trajectory)
    graph_by_track = unique_track_graph_observations(trajectory)
    candidates = {str(item.candidate_id): item for item in projected}
    output = []
    for frozen in frozen_tracks:
        track_id = str(frozen["track_id"])
        tracklet = by_track.get(track_id)
        if tracklet is None:
            raise ValueError(f"frozen bank track absent from reconstruction: {track_id}")
        graph_observations = graph_by_track.get(track_id)
        if graph_observations is None:
            raise ValueError(f"frozen bank track lacks an unambiguous public graph: {track_id}")
        public_points: dict[str, tuple[Any, Any]] = {}
        for point in tracklet.points:
            candidate = candidates.get(str(point.candidate_id))
            if candidate is None:
                raise ValueError(f"track point lacks projected candidate: {point.candidate_id}")
            observation = graph_observations.get(str(candidate.source_group_id))
            if observation is None:
                raise ValueError(f"track point lacks graph provenance: {point.candidate_id}")
            observation_id = str(observation.observation_id)
            if observation_id in public_points:
                raise ValueError(
                    f"track points collapse to one graph observation: {observation_id}"
                )
            public_points[observation_id] = (point, candidate)
        if len(public_points) != len(tracklet.points):
            raise ValueError(f"track point/graph provenance is not one-to-one: {track_id}")
        observation_ids = [str(value) for value in frozen["training_observation_ids"]]
        if len(public_points) != len(observation_ids) or set(public_points) != set(observation_ids):
            raise ValueError(f"frozen observation IDs do not exactly reconstruct: {track_id}")
        channel, edge, receiver_id, actual_rf_hz = tracklet.lane_key
        edge = _edge(edge)
        scale = canonical_rf_hz / float(actual_rf_hz)
        rows = []
        for observation_id in observation_ids:
            point, candidate = public_points[observation_id]
            lane = (
                int(candidate.channel),
                _edge(candidate.edge),
                int(candidate.receiver_id),
                float(candidate.actual_rf_hz),
            )
            expected = (int(channel), edge, int(receiver_id), float(actual_rf_hz))
            if lane != expected:
                raise ValueError(f"candidate/track lane mismatch: {observation_id}")
            raw = float(candidate.measured_cfo_hz)
            normalized_raw = float(point.normalized_raw_cfo_hz)
            alias_index = int(point.relative_alias_index)
            normalized_dealiased = float(point.normalized_dealiased_cfo_hz)
            verification_error = normalized_raw - raw * scale
            dealias_error = normalized_dealiased - (
                normalized_raw - alias_index * alias_spacing_hz * scale
            )
            if abs(verification_error) > 1e-6 or abs(dealias_error) > 1e-6:
                raise ValueError(f"public coordinate reconstruction failed: {observation_id}")
            rows.append(
                {
                    "observation_id": observation_id,
                    "candidate_id": str(candidate.candidate_id),
                    "source_window_id": candidate_windows[str(candidate.candidate_id)],
                    "support_center_utc_ns": int(candidate.support_center_utc_ns),
                    "raw_cfo_hz": raw,
                    "relative_alias_index": alias_index,
                    "normalized_raw_cfo_hz": normalized_raw,
                    "normalized_dealiased_cfo_hz": normalized_dealiased,
                    "coordinate_verification_error_hz": verification_error,
                }
            )
        output.append(
            {
                "session_id": session_id,
                "track_id": track_id,
                "receiver_id": int(receiver_id),
                "channel": int(channel),
                "edge": edge,
                "actual_rf_hz": float(actual_rf_hz),
                "canonical_rf_hz": canonical_rf_hz,
                "canonical_scale": scale,
                "raw_alias_spacing_hz": alias_spacing_hz,
                "normalized_alias_spacing_hz": alias_spacing_hz * scale,
                "training_alias_points": rows,
                "maximum_coordinate_verification_error_hz": max(
                    abs(row["coordinate_verification_error_hz"]) for row in rows
                ),
            }
        )
    return output


def wrapped_difference(value: float, period: float = ALIAS_SPACING_HZ) -> float:
    """Map an ambiguity-periodic difference to the fixed half-open interval."""
    return (value + period / 2.0) % period - period / 2.0


def paired_epoch_distance_ns(left_utc_ns: int, right_utc_ns: int) -> float:
    """Return epoch separation modulo the known 750 Hz frame period."""
    delta = float(right_utc_ns - left_utc_ns)
    centered = (
        (delta + PAIR_EPOCH_PERIOD_NS / 2.0) % PAIR_EPOCH_PERIOD_NS
        - PAIR_EPOCH_PERIOD_NS / 2.0
    )
    return abs(centered)


def calibrate_receiver_biases(
    projected: tuple[Any, ...],
    candidate_windows: dict[str, str],
) -> list[dict[str, Any]]:
    """Estimate per-lane rx1-rx0 bias from epoch-compatible training pairs."""
    lanes: dict[
        tuple[str, int, str, float], dict[str, dict[int, list[Any]]]
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for point in projected:
        key = (
            str(point.session_id),
            int(point.channel),
            _edge(point.edge),
            float(point.actual_rf_hz),
        )
        if int(point.receiver_id) in (0, 1):
            window = candidate_windows[str(point.candidate_id)]
            lanes[key][window][int(point.receiver_id)].append(point)

    output = []
    for key in sorted(lanes):
        windows = lanes[key]
        differences_by_window: dict[str, list[float]] = defaultdict(list)
        for window in sorted(windows):
            receivers = windows[window]
            for left in receivers.get(0, ()):
                for right in receivers.get(1, ()):
                    epoch_difference = paired_epoch_distance_ns(
                        int(left.support_center_utc_ns), int(right.support_center_utc_ns)
                    )
                    if epoch_difference > PAIR_EPOCH_GATE_NS:
                        continue
                    differences_by_window[window].append(
                        wrapped_difference(
                            float(right.measured_cfo_hz) - float(left.measured_cfo_hz)
                        )
                    )

        all_differences = [value for values in differences_by_window.values() for value in values]
        votes: list[tuple[str, float]] = []
        if all_differences:
            bins = Counter(math.floor(value / CALIBRATION_BIN_HZ) for value in all_differences)
            modal_bin = min(bins, key=lambda index: (-bins[index], index))
            modal_values = [
                value
                for value in all_differences
                if math.floor(value / CALIBRATION_BIN_HZ) == modal_bin
            ]
            initial = _median(modal_values)
            for window in sorted(differences_by_window):
                nearest = min(
                    differences_by_window[window], key=lambda value: (abs(value - initial), value)
                )
                if abs(nearest - initial) <= CALIBRATION_INLIER_HZ:
                    votes.append((window, nearest))
        vote_values = [value for _, value in votes]
        bias = _median(vote_values) if vote_values else None
        mad = _median([abs(value - bias) for value in vote_values]) if vote_values else None
        qualified = (
            len(votes) >= CALIBRATION_MIN_WINDOWS
            and mad is not None
            and mad <= CALIBRATION_MAX_MAD_HZ
        )
        output.append(
            {
                "session_id": key[0],
                "channel": key[1],
                "edge": key[2],
                "actual_rf_hz": key[3],
                "bias_rx1_minus_rx0_hz": bias,
                "distinct_training_windows": len(votes),
                "training_window_votes": [
                    {"source_window_id": window, "wrapped_rx1_minus_rx0_hz": value}
                    for window, value in votes
                ],
                "candidate_pair_count": len(all_differences),
                "mad_hz": mad,
                "qualified": qualified,
                "unqualified_reason": (
                    None if qualified else "insufficient_or_unstable_training_support"
                ),
            }
        )
    return output


def _module_receipt(module: Any) -> dict[str, str]:
    path = Path(inspect.getsourcefile(module) or "")
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def main() -> None:  # noqa: PLR0915
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--candidate-bank", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")
    if protocol_sha256(args.protocol) != args.protocol_sha256:
        raise ValueError("protocol hash is not frozen")

    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates

    from leo.analysis import persistent_hop_trajectory as trajectory_module
    from leo.application import scanner_trajectory as projection_module

    inventory = {row["session_id"]: row for row in json.loads(args.inventory.read_text())}
    partition_document = json.loads(args.partitions.read_text())
    partitions = partition_index(partition_document)
    bank = json.loads(args.candidate_bank.read_text())
    if bank.get("schema") != "rx-training-candidate-bank/v1" or bank.get("status") != "complete":
        raise ValueError("candidate bank is not complete v1 evidence")
    if bank["source_digests"]["partitions"] != digest(args.partitions.read_bytes()):
        raise ValueError("candidate bank/partition binding mismatch")
    tracks_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bank["tracks"]:
        tracks_by_session[row["session_id"]].append(row)

    tracks, calibrations, accounting = [], [], {}
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    for session_id in sorted(tracks_by_session):
        entry = inventory[session_id]
        payload = Path(entry["cache_file"]).read_bytes()
        if not entry["ready"] or digest(payload) != entry["cache_sha256"]:
            raise ValueError(f"derived cache failed inventory binding: {session_id}")
        raw = pickle.loads(payload)
        filtered, counts = training_only_input(raw, partitions[session_id])
        projected = project_scanner_candidates(filtered)
        candidate_windows = candidate_window_index(raw, filtered, projected)
        trajectory = reconstruct_persistent_hop_trajectories(projected, config=config)
        session_tracks = export_selected_tracks(
            session_id,
            tracks_by_session[session_id],
            trajectory,
            projected,
            candidate_windows,
        )
        tracks.extend(session_tracks)
        session_calibrations = calibrate_receiver_biases(projected, candidate_windows)
        calibrations.extend(session_calibrations)
        accounting[session_id] = {
            **counts,
            "projected_training_candidates": len(projected),
            "exported_frozen_tracks": len(session_tracks),
            "qualified_calibration_lanes": sum(row["qualified"] for row in session_calibrations),
            "calibration_lanes": len(session_calibrations),
        }

    document = {
        "schema": "rx-training-alias-mapping/v1",
        "status": "complete",
        "protocol_sha256": args.protocol_sha256,
        "source_digests": {
            "inventory": digest(args.inventory.read_bytes()),
            "partitions": digest(args.partitions.read_bytes()),
            "candidate_bank": digest(args.candidate_bank.read_bytes()),
        },
        "constants": {
            "canonical_rf_hz": CANONICAL_RF_HZ,
            "raw_alias_spacing_hz": ALIAS_SPACING_HZ,
            "pair_epoch_gate_ns": PAIR_EPOCH_GATE_NS,
            "pair_epoch_period_ns": PAIR_EPOCH_PERIOD_NS,
            "calibration_bin_hz": CALIBRATION_BIN_HZ,
            "calibration_inlier_hz": CALIBRATION_INLIER_HZ,
            "calibration_min_windows": CALIBRATION_MIN_WINDOWS,
            "calibration_max_mad_hz": CALIBRATION_MAX_MAD_HZ,
        },
        "future_matching_contract": {
            "lane_identity": "exact session/channel/edge/actual_rf_hz; anchor receiver recorded",
            "alias_handling": (
                "wrapped equivalence class; integer alias unresolved; never fit alias on held data"
            ),
            "canonical_gate_hz": 2500.0,
        },
        "runtime_source_receipts": {
            "projection": _module_receipt(projection_module),
            "trajectory": _module_receipt(trajectory_module),
        },
        "accounting": accounting,
        "tracks": tracks,
        "receiver_calibrations": calibrations,
    }
    atomic_json(args.output, document)
    print(canonical_digest(document), flush=True)


if __name__ == "__main__":
    main()
