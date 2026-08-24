#!/usr/bin/env python3
"""Calibrate the recent three-dwell orbital-shape search at matched wrong times.

This report-only tool repeats the entire visible-candidate, identity, epoch, and
bounded-nuisance search in every control sky.  It also collapses simultaneous
receiver replicas into TLE-blind physical-signal clusters before family-wise
calibration.  It does not change a persisted production contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.catalog.database import create_catalog_engine
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets
from leo.storage import BulkUriResolver

try:
    from tools import report_five_dwell_degree1_only as degree1
    from tools import report_five_dwell_tle_cone as base
    from tools import report_multi_dwell_starlink_association as association
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    import report_five_dwell_degree1_only as degree1
    import report_five_dwell_tle_cone as base
    import report_multi_dwell_starlink_association as association

SESSION_IDS = (
    "cap-20260824T192019-9023840c8e9f",
    "cap-20260824T192252-9981b9c27853",
    "cap-20260824T192531-491832825b97",
)
DEFAULT_FIGURE_ROOT = Path("reports/figures/2026_08_24_recent_three_continuity_tle")
DEFAULT_SOURCE_EVIDENCE = DEFAULT_FIGURE_ROOT / "recent-three-degree1-evidence.json"
DEFAULT_PUBLISHED_EVIDENCE = DEFAULT_FIGURE_ROOT / "recent-three-tle-null-evidence.json"
RF_REPLICA_TOLERANCE_HZ = 10.0
RATE_REPLICA_TOLERANCE_HZ_S = 100.0
OVERLAP_REPLICA_FRACTION = 0.80


@dataclass(frozen=True, slots=True)
class AuditTrack:
    selected: degree1.SelectedLinearTrack
    series: association.TrackSeries
    train: np.ndarray
    linear: dict[str, float]

    @property
    def label(self) -> str:
        return self.selected.label

    @property
    def path(self) -> str:
        return self.selected.path.label

    @property
    def rf_hz(self) -> float:
        return float(self.selected.path.rf_frequency_hz)

    @property
    def rate_hz_s(self) -> float:
        return float(self.selected.rate_hz_s)

    @property
    def train_count(self) -> int:
        return int(np.sum(self.train))

    @property
    def holdout_count(self) -> int:
        return int(np.sum(~self.train))


@dataclass(frozen=True, slots=True)
class AuditDwell:
    session_id: str
    start_ns: int
    duration_s: float
    catalogue: Any
    snapshot_digest: str
    tracks: tuple[AuditTrack, ...]
    clusters: tuple[tuple[int, ...], ...]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE_EVIDENCE)
    parser.add_argument(
        "--published-evidence",
        type=Path,
        default=DEFAULT_PUBLISHED_EVIDENCE,
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_DATABASE_URL", base.DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--bulk-root", type=Path, default=base.DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=base.DEFAULT_TLE_ROOT)
    parser.add_argument("--horizon-deg", type=float, default=base.DEFAULT_HORIZON_DEG)
    parser.add_argument("--maximum-selected-per-path", type=int, default=16)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision(ref: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd()}", "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def stream_name(path: str) -> str:
    return path.split("/", 1)[0]


def overlap_fraction(first: AuditTrack, second: AuditTrack) -> float:
    a = first.selected
    b = second.selected
    overlap = max(0.0, min(a.end_s, b.end_s) - max(a.start_s, b.start_s))
    return overlap / min(a.duration_s, b.duration_s)


def replica_clusters(tracks: tuple[AuditTrack, ...]) -> tuple[tuple[int, ...], ...]:
    """Pre-TLE graph components for simultaneous, same-RF receiver copies."""

    parent = list(range(len(tracks)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(tracks)):
        for right in range(left + 1, len(tracks)):
            a = tracks[left]
            b = tracks[right]
            is_replica = (
                stream_name(a.path) != stream_name(b.path)
                and abs(a.rf_hz - b.rf_hz) <= RF_REPLICA_TOLERANCE_HZ
                and abs(a.rate_hz_s - b.rate_hz_s) <= RATE_REPLICA_TOLERANCE_HZ_S
                and overlap_fraction(a, b) >= OVERLAP_REPLICA_FRACTION
            )
            if is_replica:
                union(left, right)
    groups: dict[int, list[int]] = {}
    for index in range(len(tracks)):
        groups.setdefault(find(index), []).append(index)
    return tuple(tuple(values) for values in sorted(groups.values(), key=lambda v: v[0]))


def load_dwells(args: argparse.Namespace) -> list[AuditDwell]:
    source = json.loads(args.source_evidence.read_text(encoding="utf-8"))
    association._validate_source_cohort(source, SESSION_IDS)
    engine = create_catalog_engine(args.database_url)
    resolver = BulkUriResolver(args.bulk_root, allowed_namespaces=("analysis",), create=False)
    archive = TleArchiveReader(args.tle_root)
    result: list[AuditDwell] = []
    with Session(engine) as database:
        cohort = base._cohort(database, SESSION_IDS)
        for run in cohort:
            paths = degree1._path_evidence(database, resolver, run)
            start_ns, duration_s = base._nominal_capture(paths)
            selected, _, _, _ = degree1._selected_tracks(
                paths,
                start_ns,
                maximum_selected=args.maximum_selected_per_path,
            )
            preselected = selected[:3]
            eligible = tuple(
                track
                for track in preselected
                if track.duration_s >= association.MINIMUM_TRACK_DURATION_S
                and track.trajectory.point_count >= association.MINIMUM_TRACK_OBSERVATIONS
            )
            if len(eligible) != 3:
                raise ValueError(f"{run.session_id}: expected three eligible tracks")
            snapshot = base._select_causal_space_track_snapshot(
                archive,
                anchor_utc_ns=start_ns,
                provider=base.REQUIRED_TLE_PROVIDER,
            )
            catalogue = parse_element_sets(archive.read(snapshot))
            tracks = []
            for selected_track in eligible:
                series = association._track_series(selected_track, start_ns)
                train = association._temporal_split(series.time_s)
                tracks.append(
                    AuditTrack(
                        selected_track,
                        series,
                        train,
                        association._linear_null(series, train),
                    )
                )
            track_tuple = tuple(tracks)
            result.append(
                AuditDwell(
                    run.session_id,
                    start_ns,
                    duration_s,
                    catalogue,
                    snapshot.digest,
                    track_tuple,
                    replica_clusters(track_tuple),
                )
            )
    return result


def aggregate_rms(pairs: list[tuple[float, int]]) -> float:
    return float(
        math.sqrt(
            sum(value * value * count for value, count in pairs) / sum(count for _, count in pairs)
        )
    )


def prediction_at_shift(
    track: AuditTrack,
    prediction_times_s: np.ndarray,
    prediction_hz: np.ndarray,
    epoch_shift_s: float,
) -> dict[str, Any]:
    shifted = track.series.time_s + epoch_shift_s
    predicted = np.interp(shifted, prediction_times_s, prediction_hz)
    residual, reference_s, offset_hz, drift_hz_s = association._fit_affine_nuisance(
        track.series.time_s,
        track.series.cfo_hz - predicted,
        track.train,
        association.MODEL_DRIFT_BOUNDS_HZ_S["bounded_200"],
    )
    return {
        "epoch_adjustment_s": float(epoch_shift_s),
        "nuisance_reference_s": reference_s,
        "fitted_frequency_offset_hz": offset_hz,
        "nuisance_drift_hz_s": drift_hz_s,
        "train_residual_rms_hz": association._rms(residual[track.train]),
        "holdout_residual_rms_hz": association._rms(residual[~track.train]),
    }


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: (item["train_residual_rms_hz"], item["catalog_number"]))


def finish_selection(
    ranked: list[dict[str, Any]],
    linear_holdout_rms_hz: float,
    member_linear_holdout_rms_hz: list[float] | None = None,
) -> dict[str, Any]:
    if len(ranked) < 2:
        raise ValueError("candidate search produced fewer than two candidates")
    best = ranked[0]
    margin = float(ranked[1]["train_residual_rms_hz"] - best["train_residual_rms_hz"])
    orbit = float(best["holdout_residual_rms_hz"])
    alternative_holdout = min(
        float(row["holdout_residual_rms_hz"])
        for row in ranked[1:]
        if int(row["catalog_number"]) != int(best["catalog_number"])
    )
    advantage = float(linear_holdout_rms_hz - orbit)
    skill = float(1.0 - (orbit / linear_holdout_rms_hz) ** 2)
    log_line_gain = float(2.0 * math.log(linear_holdout_rms_hz / orbit))
    log_train_separation = float(
        2.0
        * math.log(float(ranked[1]["train_residual_rms_hz"]) / float(best["train_residual_rms_hz"]))
    )
    log_holdout_separation = float(2.0 * math.log(alternative_holdout / orbit))
    member_orbit = [float(value) for value in best.get("member_holdout_residual_rms_hz", [orbit])]
    member_line = member_linear_holdout_rms_hz or [float(linear_holdout_rms_hz)]
    if len(member_orbit) != len(member_line):
        raise ValueError("member holdout arrays differ")
    all_receiver_log_line_gain = float(
        min(
            2.0 * math.log(line / orbital)
            for line, orbital in zip(member_line, member_orbit, strict=True)
        )
    )
    interior = bool(
        abs(best["epoch_adjustment_s"])
        < association.PRIMARY_EPOCH_BOUND_S - association.EPOCH_STEP_S / 2.0
    )
    gate_score = min(
        advantage / association.SECURE_HOLDOUT_ADVANTAGE_HZ,
        margin / association.SECURE_RUNNER_UP_MARGIN_HZ,
        association.SECURE_HOLDOUT_RMS_HZ / orbit,
    )
    if not interior:
        gate_score = min(gate_score, -1.0)
    named_statistic = min(
        all_receiver_log_line_gain,
        log_train_separation,
        log_holdout_separation,
    )
    return {
        "candidate_count": len(ranked),
        "candidate_name": best["object_name"],
        "catalog_number": int(best["catalog_number"]),
        "epoch_adjustment_s": float(best["epoch_adjustment_s"]),
        "nuisance_drift_hz_s": best.get("nuisance_drift_hz_s"),
        "train_rms_hz": float(best["train_residual_rms_hz"]),
        "holdout_rms_hz": orbit,
        "linear_holdout_rms_hz": float(linear_holdout_rms_hz),
        "holdout_advantage_hz": advantage,
        "predictive_skill_fraction": skill,
        "log_line_mse_gain": log_line_gain,
        "all_receiver_log_line_mse_gain": all_receiver_log_line_gain,
        "runner_margin_hz": margin,
        "best_alternative_holdout_rms_hz": alternative_holdout,
        "heldout_alternative_margin_hz": alternative_holdout - orbit,
        "log_training_runner_separation": log_train_separation,
        "log_heldout_alternative_separation": log_holdout_separation,
        "named_association_statistic": float(named_statistic),
        "epoch_interior": interior,
        "joint_gate_score": float(gate_score),
        "passes_numerical_shape_gate": bool(gate_score >= 1.0),
        "runner_catalog_number": int(ranked[1]["catalog_number"]),
    }


def evaluate_dwell_block(
    dwell: AuditDwell,
    observer: ObserverSiteV1,
    horizon_deg: float,
    time_shift_s: float,
) -> dict[str, Any]:
    shifted_start_ns = dwell.start_ns + round(time_shift_s * base._NS_PER_S)
    satellites, _, _ = association._candidate_catalogue(
        dwell.catalogue,
        observer,
        shifted_start_ns,
        dwell.duration_s,
        horizon_deg,
    )
    _, prediction_times_s, _, observed = association._prediction_bank(
        dwell.catalogue,
        satellites,
        observer,
        shifted_start_ns,
        dwell.duration_s,
    )
    doppler_by_rf = {
        track.rf_hz: doppler_shift_hz(track.rf_hz, observed.range_rate_km_s)
        for track in dwell.tracks
    }
    visibility = {
        (track_index, satellite_index): association._visible_fraction(
            observed.elevation_deg[satellite_index],
            track.series,
            prediction_times_s,
            horizon_deg,
        )
        for track_index, track in enumerate(dwell.tracks)
        for satellite_index in range(len(satellites))
    }

    track_rows: list[dict[str, Any]] = []
    for track_index, track in enumerate(dwell.tracks):
        candidates = []
        for satellite_index, satellite in enumerate(satellites):
            if visibility[(track_index, satellite_index)] < association.MINIMUM_VISIBILITY_FRACTION:
                continue
            evaluated = association._evaluate_prediction(
                track.series,
                prediction_times_s,
                doppler_by_rf[track.rf_hz][satellite_index],
                train=track.train,
                maximum_drift_hz_s=association.MODEL_DRIFT_BOUNDS_HZ_S["bounded_200"],
            )
            candidates.append(
                {
                    **association._candidate_metadata(satellite),
                    **evaluated,
                }
            )
        selected = finish_selection(
            rank_rows(candidates),
            float(track.linear["holdout_residual_rms_hz"]),
        )
        selected.update({"track": track.label, "path": track.path})
        track_rows.append(selected)

    cluster_rows: list[dict[str, Any]] = []
    epoch_shifts = np.arange(
        -association.PRIMARY_EPOCH_BOUND_S,
        association.PRIMARY_EPOCH_BOUND_S + association.EPOCH_STEP_S / 2.0,
        association.EPOCH_STEP_S,
    )
    for cluster_index, member_indices in enumerate(dwell.clusters, start=1):
        member_tracks = [dwell.tracks[index] for index in member_indices]
        candidate_rows = []
        for satellite_index, satellite in enumerate(satellites):
            if any(
                visibility[(member_index, satellite_index)]
                < association.MINIMUM_VISIBILITY_FRACTION
                for member_index in member_indices
            ):
                continue
            epoch_rows = []
            for epoch_shift_s in epoch_shifts:
                members = [
                    prediction_at_shift(
                        track,
                        prediction_times_s,
                        doppler_by_rf[track.rf_hz][satellite_index],
                        float(epoch_shift_s),
                    )
                    for track in member_tracks
                ]
                epoch_rows.append(
                    {
                        "epoch_adjustment_s": float(epoch_shift_s),
                        "train_residual_rms_hz": aggregate_rms(
                            [
                                (row["train_residual_rms_hz"], track.train_count)
                                for row, track in zip(members, member_tracks, strict=True)
                            ]
                        ),
                        "holdout_residual_rms_hz": aggregate_rms(
                            [
                                (row["holdout_residual_rms_hz"], track.holdout_count)
                                for row, track in zip(members, member_tracks, strict=True)
                            ]
                        ),
                        "member_holdout_residual_rms_hz": [
                            row["holdout_residual_rms_hz"] for row in members
                        ],
                        "member_nuisance_drift_hz_s": [
                            row["nuisance_drift_hz_s"] for row in members
                        ],
                    }
                )
            best_epoch = min(
                epoch_rows,
                key=lambda item: (
                    item["train_residual_rms_hz"],
                    abs(item["epoch_adjustment_s"]),
                    item["epoch_adjustment_s"],
                ),
            )
            candidate_rows.append(
                {
                    **association._candidate_metadata(satellite),
                    **best_epoch,
                    "nuisance_drift_hz_s": best_epoch["member_nuisance_drift_hz_s"],
                }
            )
        linear_holdout = aggregate_rms(
            [
                (float(track.linear["holdout_residual_rms_hz"]), track.holdout_count)
                for track in member_tracks
            ]
        )
        member_linear_holdout = [
            float(track.linear["holdout_residual_rms_hz"]) for track in member_tracks
        ]
        selected = finish_selection(
            rank_rows(candidate_rows),
            linear_holdout,
            member_linear_holdout,
        )
        selected.update(
            {
                "cluster": f"C{cluster_index}",
                "members": [track.label for track in member_tracks],
                "paths": [track.path for track in member_tracks],
                "replicated": len(member_tracks) > 1,
            }
        )
        cluster_rows.append(selected)
    return {
        "session_id": dwell.session_id,
        "visible_satellite_count": len(satellites),
        "tracks": track_rows,
        "clusters": cluster_rows,
    }


def empirical_p(values: list[float], true_index: int = 0) -> float:
    true = values[true_index]
    controls = values[:true_index] + values[true_index + 1 :]
    return float((1 + sum(value >= true for value in controls)) / (len(controls) + 1))


def pseudo_p_matrix(matrix: np.ndarray) -> np.ndarray:
    """Inclusive rank p for every hypothesis/block; larger statistic is stronger."""

    hypotheses, blocks = matrix.shape
    result = np.empty_like(matrix, dtype=float)
    for hypothesis in range(hypotheses):
        for block in range(blocks):
            result[hypothesis, block] = np.mean(matrix[hypothesis] >= matrix[hypothesis, block])
    return result


def westfall_young_minp(matrix: np.ndarray) -> dict[str, Any]:
    p_matrix = pseudo_p_matrix(matrix)
    true_raw = p_matrix[:, 0]
    min_p_by_block = np.min(p_matrix, axis=0)
    single = np.asarray(
        [np.mean(min_p_by_block <= value) for value in true_raw],
        dtype=float,
    )
    order = np.argsort(true_raw, kind="stable")
    step = np.empty(matrix.shape[0], dtype=float)
    previous = 0.0
    for rank, index in enumerate(order):
        remaining = order[rank:]
        permutation_min = np.min(p_matrix[remaining], axis=0)
        adjusted = float(np.mean(permutation_min <= true_raw[index]))
        previous = max(previous, adjusted)
        step[index] = previous
    return {
        "raw_empirical_p": true_raw.tolist(),
        "single_step_minp_fwer_p": single.tolist(),
        "step_down_minp_fwer_p": step.tolist(),
        "minimum_p_by_block": min_p_by_block.tolist(),
        "warning": (
            "Approximate randomization calibration: common 30-second sky shifts are correlated "
            "and are not literal exchangeable permutations. Forty controls limit p resolution "
            "to 1/41."
        ),
    }


def family_summary(
    blocks: list[dict[str, Any]],
    key: str,
    statistic: str,
) -> dict[str, Any]:
    labels = []
    rows_by_block = []
    for block_index, block in enumerate(blocks):
        rows = []
        for dwell_index, dwell in enumerate(block["dwells"], start=1):
            for row in dwell[key]:
                label = f"D{dwell_index} " + (row["track"] if key == "tracks" else row["cluster"])
                rows.append((label, row))
        if block_index == 0:
            labels = [label for label, _ in rows]
        elif labels != [label for label, _ in rows]:
            raise ValueError("hypothesis ordering changed across blocks")
        rows_by_block.append([float(row[statistic]) for _, row in rows])
    matrix = np.asarray(rows_by_block, dtype=float).T
    wy = westfall_young_minp(matrix)
    return {
        "labels": labels,
        "true_values": matrix[:, 0].tolist(),
        "wrong_time_median": np.median(matrix[:, 1:], axis=1).tolist(),
        "wrong_time_best": np.max(matrix[:, 1:], axis=1).tolist(),
        **wy,
    }


def population_summary(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    statistics: dict[str, list[float]] = {
        "equal_dwell_mean_all_receiver_log_line_mse_gain": [],
        "equal_dwell_median_all_receiver_log_line_mse_gain": [],
        "cluster_win_count": [],
        "dwell_win_count": [],
        "runner_100_cluster_count": [],
        "numerical_gate_cluster_count": [],
    }
    for block in blocks:
        dwell_means = []
        dwell_medians = []
        clusters = []
        for dwell in block["dwells"]:
            dwell_clusters = dwell["clusters"]
            clusters.extend(dwell_clusters)
            gains = [row["all_receiver_log_line_mse_gain"] for row in dwell_clusters]
            dwell_means.append(float(np.mean(gains)))
            dwell_medians.append(float(np.median(gains)))
        statistics["equal_dwell_mean_all_receiver_log_line_mse_gain"].append(
            float(np.mean(dwell_means))
        )
        statistics["equal_dwell_median_all_receiver_log_line_mse_gain"].append(
            float(np.mean(dwell_medians))
        )
        statistics["cluster_win_count"].append(
            float(sum(row["all_receiver_log_line_mse_gain"] > 0.0 for row in clusters))
        )
        statistics["dwell_win_count"].append(float(sum(value > 0.0 for value in dwell_means)))
        statistics["runner_100_cluster_count"].append(
            float(
                sum(
                    row["runner_margin_hz"] >= association.SECURE_RUNNER_UP_MARGIN_HZ
                    for row in clusters
                )
            )
        )
        statistics["numerical_gate_cluster_count"].append(
            float(sum(row["passes_numerical_shape_gate"] for row in clusters))
        )
    result = {
        name: {
            "true_value": values[0],
            "wrong_time_median": float(np.median(values[1:])),
            "wrong_time_best": float(max(values[1:])),
            "empirical_p": empirical_p(values),
            "all_block_values": values,
        }
        for name, values in statistics.items()
    }
    shifts = [float(block["time_shift_s"]) for block in blocks]
    population_values = statistics["equal_dwell_mean_all_receiver_log_line_mse_gain"]
    result["post_hoc_time_guard_sensitivity"] = {
        str(guard_s): {
            "control_count": sum(abs(value) >= guard_s for value in shifts[1:]),
            "empirical_p": empirical_p(
                [
                    population_values[0],
                    *[
                        value
                        for value, shift in zip(population_values[1:], shifts[1:], strict=True)
                        if abs(shift) >= guard_s
                    ],
                ]
            ),
        }
        for guard_s in (30, 60, 90, 120, 180, 300)
    }
    return result


def audit_true_against_published(
    true_block: dict[str, Any],
    published_path: Path,
) -> dict[str, Any]:
    published = json.loads(published_path.read_text(encoding="utf-8"))
    expected = {
        (dwell["session_id"], track["label"]): track
        for dwell in published["dwells"]
        for track in dwell["tracks"]
    }
    checks = []
    for dwell in true_block["dwells"]:
        for track in dwell["tracks"]:
            reference = expected[(dwell["session_id"], track["track"])]
            best = reference["models"]["bounded_200"]["best"]
            checks.append(
                {
                    "session_id": dwell["session_id"],
                    "track": track["track"],
                    "catalog_number_equal": track["catalog_number"] == best["catalog_number"],
                    "train_rms_difference_hz": track["train_rms_hz"]
                    - best["train_residual_rms_hz"],
                    "holdout_rms_difference_hz": track["holdout_rms_hz"]
                    - best["holdout_residual_rms_hz"],
                    "runner_margin_difference_hz": track["runner_margin_hz"]
                    - reference["models"]["bounded_200"]["runner_up_training_margin_hz"],
                }
            )
    return {
        "published_evidence_sha256": sha256(published_path),
        "checks": checks,
        "all_candidate_ids_equal": all(item["catalog_number_equal"] for item in checks),
        "maximum_absolute_numeric_difference_hz": max(
            abs(item[key])
            for item in checks
            for key in (
                "train_rms_difference_hz",
                "holdout_rms_difference_hz",
                "runner_margin_difference_hz",
            )
        ),
    }


def _cluster_matrix(blocks: list[dict[str, Any]], statistic: str) -> np.ndarray:
    return np.asarray(
        [
            [float(row[statistic]) for dwell in block["dwells"] for row in dwell["clusters"]]
            for block in blocks
        ],
        dtype=float,
    ).T


def plot_calibration(
    path: Path,
    blocks: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> None:
    labels = evidence["cluster_all_receiver_line_gain_family"]["labels"]
    gain = _cluster_matrix(blocks, "all_receiver_log_line_mse_gain")
    runner = _cluster_matrix(blocks, "runner_margin_hz")
    population = evidence["population"]["equal_dwell_mean_all_receiver_log_line_mse_gain"]
    population_by_shift = {
        float(block["time_shift_s"]): float(value)
        for block, value in zip(
            blocks,
            population["all_block_values"],
            strict=True,
        )
    }
    ordered_shifts = sorted(population_by_shift)
    figure, axes = plt.subplots(1, 3, figsize=(17, 6.4))
    y = np.arange(len(labels))

    low, median, high = np.quantile(gain[:, 1:], (0.1, 0.5, 0.9), axis=1)
    axes[0].hlines(y, low, high, color="#9aa6b2", linewidth=4, alpha=0.65)
    axes[0].scatter(median, y, color="#687381", marker="|", s=85, label="wrong-time median")
    axes[0].scatter(gain[:, 0], y, color="#d1495b", s=44, label="true time")
    axes[0].axvline(0.0, color="#1d3557", linewidth=0.9)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("all-receiver log MSE gain over line")
    axes[0].set_title("A · True curve gains are common in control skies", loc="left")
    axes[0].grid(axis="x", alpha=0.18)
    axes[0].legend(fontsize=8)

    runner_median = np.median(runner[:, 1:], axis=1)
    axes[1].scatter(runner_median, y, color="#687381", marker="|", s=85)
    axes[1].scatter(runner[:, 0], y, color="#d1495b", s=44)
    axes[1].axvline(
        association.SECURE_RUNNER_UP_MARGIN_HZ,
        color="#1d3557",
        linestyle="--",
        linewidth=1,
        label="100 Hz gate",
    )
    axes[1].set_xscale("log")
    axes[1].set_yticks(y, labels)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("training runner margin (Hz, log scale)")
    axes[1].set_title("B · True identities are less separated than controls", loc="left")
    axes[1].grid(axis="x", alpha=0.18)
    axes[1].legend(fontsize=8)

    control_x = [value for value in ordered_shifts if value != 0.0]
    control_y = [population_by_shift[value] for value in control_x]
    axes[2].plot(control_x, control_y, color="#277da1", marker="o", markersize=3)
    axes[2].scatter(
        [0.0],
        [population_by_shift[0.0]],
        color="#d1495b",
        s=70,
        zorder=3,
        label=f"true time · p={population['empirical_p']:.4f}",
    )
    axes[2].axhline(0.0, color="#1d3557", linewidth=0.9)
    axes[2].set_xlabel("common campaign time shift (s)")
    axes[2].set_ylabel("equal-dwell mean cluster log-MSE gain")
    axes[2].set_title("C · Population advantage is a post-hoc near miss", loc="left")
    axes[2].grid(alpha=0.18)
    axes[2].legend(fontsize=8)

    figure.suptitle(
        "Matched full-search null: orbital shape is promising, named identity is not secure",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    figure.savefig(path, dpi=170)
    plt.close(figure)


def main() -> None:
    args = arguments()
    started = time.monotonic()
    args.output_root.mkdir(parents=True, exist_ok=True)
    dwells = load_dwells(args)
    observer = ObserverSiteV1(
        latitude_deg=base.DEFAULT_LATITUDE_DEG,
        longitude_deg=base.DEFAULT_LONGITUDE_DEG,
        altitude_m=base.DEFAULT_ALTITUDE_M,
        label="reviewed-spinnaker-sausalito-not-capture-bound",
    )
    shifts = [0.0, *[float(value) for value in base._null_shifts_s() if float(value) != 0.0]]
    blocks = []
    for block_index, shift_s in enumerate(shifts):
        block_started = time.monotonic()
        dwell_rows = [
            evaluate_dwell_block(dwell, observer, args.horizon_deg, shift_s) for dwell in dwells
        ]
        blocks.append(
            {
                "block_index": block_index,
                "time_shift_s": shift_s,
                "dwells": dwell_rows,
            }
        )
        print(
            json.dumps(
                {
                    "completed_block": block_index,
                    "time_shift_s": shift_s,
                    "runtime_s": time.monotonic() - block_started,
                }
            ),
            flush=True,
        )
    evidence = {
        "schema_version": 1,
        "analysis_kind": "recent_three_matched_full_shape_time_null",
        "analysis_commit": git_revision("HEAD"),
        "origin_main_commit": git_revision("origin/main"),
        "tool_sha256": sha256(Path(__file__)),
        "source_evidence_sha256": sha256(args.source_evidence),
        "published_evidence_sha256": sha256(args.published_evidence),
        "exploratory_post_hoc": True,
        "association_status": "unknown",
        "method": {
            "time_shifts_s": shifts,
            "candidate_search": (
                "Every block re-propagates the same causal TLE snapshot, screens the shifted "
                "visible sky, selects identity and a ±0.30 s/0.05 s epoch on the first 60%, "
                "fits per-receiver offset and ±200 Hz/s drift on training only, and scores "
                "the final 40%."
            ),
            "predictive_skill_fraction": "1 - orbit_holdout_MSE / linear_holdout_MSE",
            "cluster_selection": (
                "Replica clusters select one shared identity and one shared epoch; receiver offset "
                "and bounded drift remain separate. Singleton clusters reduce to the track search."
            ),
            "cluster_definition": {
                "different_receiver_stream": True,
                "rf_tolerance_hz": RF_REPLICA_TOLERANCE_HZ,
                "rate_tolerance_hz_s": RATE_REPLICA_TOLERANCE_HZ_S,
                "minimum_overlap_fraction_of_shorter": OVERLAP_REPLICA_FRACTION,
                "tle_blind": True,
            },
            "joint_gate_score": (
                "min(holdout_advantage/100 Hz, runner_margin/100 Hz, 500 Hz/holdout_RMS), "
                "with boundary epoch forced below zero; >=1 passes all numerical shape gates"
            ),
            "named_association_statistic": (
                "min(all-receiver heldout log-MSE gain over line, training runner log-MSE "
                "separation, heldout best-alternative log-MSE separation); the epoch-interior "
                "requirement remains a separate hard gate"
            ),
            "westfall_young": (
                "inclusive rank min-P using the same 41 common true/wrong-time blocks; both "
                "single-step and step-down values reported"
            ),
        },
        "dwell_cluster_membership": {
            dwell.session_id: [
                [dwell.tracks[index].label for index in cluster] for cluster in dwell.clusters
            ]
            for dwell in dwells
        },
        "track_skill_family": family_summary(blocks, "tracks", "predictive_skill_fraction"),
        "track_joint_gate_family": family_summary(blocks, "tracks", "joint_gate_score"),
        "cluster_skill_family": family_summary(blocks, "clusters", "predictive_skill_fraction"),
        "cluster_all_receiver_line_gain_family": family_summary(
            blocks, "clusters", "all_receiver_log_line_mse_gain"
        ),
        "cluster_joint_gate_family": family_summary(blocks, "clusters", "joint_gate_score"),
        "cluster_runner_family": family_summary(blocks, "clusters", "runner_margin_hz"),
        "cluster_heldout_alternative_family": family_summary(
            blocks, "clusters", "log_heldout_alternative_separation"
        ),
        "track_named_association_family": family_summary(
            blocks, "tracks", "named_association_statistic"
        ),
        "cluster_named_association_family": family_summary(
            blocks, "clusters", "named_association_statistic"
        ),
        "population": population_summary(blocks),
        "true_reproduction_audit": audit_true_against_published(
            blocks[0],
            args.published_evidence,
        ),
        "blocks": blocks,
        "limitations": [
            "This audit was designed after inspecting the cohort and is exploratory, not "
            "preregistered.",
            "The 40 common 30-second shifts are serially correlated and not literal permutations.",
            "The three dwells span about five minutes, so population prevalence is not "
            "established.",
            "A matched-field p tests whether some visible catalogue curve predicts better at "
            "true time; runner separation and independent replication remain necessary for "
            "named identity.",
            "The current production secure gate can combine a scalar identity and a different "
            "shape identity; this audit does not treat that mixed-identity gate as named-object "
            "evidence.",
        ],
    }
    reproduction = evidence["true_reproduction_audit"]
    if not reproduction["all_candidate_ids_equal"]:
        raise AssertionError("true-time candidate identities do not reproduce")
    if reproduction["maximum_absolute_numeric_difference_hz"] != 0.0:
        raise AssertionError("true-time numerical results do not reproduce exactly")
    evidence_path = args.output_root / "matched-shape-null-evidence.json"
    figure_path = args.output_root / "matched-shape-null-calibration.png"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    plot_calibration(figure_path, blocks, evidence)
    print(
        json.dumps(
            {
                "evidence_path": str(evidence_path),
                "figure_path": str(figure_path),
                "runtime_s": time.monotonic() - started,
                "population_mean_p": evidence["population"][
                    "equal_dwell_mean_all_receiver_log_line_mse_gain"
                ]["empirical_p"],
                "minimum_cluster_line_gain_fwer_p": min(
                    evidence["cluster_all_receiver_line_gain_family"]["single_step_minp_fwer_p"]
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
