#!/usr/bin/env python3
"""Local blind position refinement with identity and circular-offset marginalization.

This research tool keeps nominal orbit states and full-catalogue identity priors
from a sealed five-block refinement.  At every trial position it recomputes all
candidate shape likelihoods.  A receiver/pilot-edge nuisance intercept is then
integrated on a uniform circle; no identity or intercept is fixed from truth.

The resulting scores are composite evidence, not calibrated probabilities.
"""

# ruff: noqa: E402 -- numerical thread limits must precede NumPy/SciPy imports.

from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import importlib.util
import json
import resource
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    ObservationArc,
    Region,
    ScoreConfig,
    logsumexp,
)
from leo.sky.propagation import parse_element_sets

PILOT_ALIAS_HZ = 1.0 / 4.4e-6
CANONICAL_RF_HZ = 11_200_000_000.0
FIVE_BLOCK_PARTITION = "five-chronological-blocks-train-0-2-4-heldout-1-3-v1"
SIGMA_ARMS_HZ = (3_000.0, 10_000.0, 30_000.0)
OUTLIER_ARMS = (0.05, 0.2)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(value: object) -> str:
    body = dict(value) if isinstance(value, dict) else value
    if isinstance(body, dict):
        body.pop("content_digest", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wrap_alias_hz(value):
    values = np.asarray(value, dtype=float)
    wrapped = (values + PILOT_ALIAS_HZ / 2) % PILOT_ALIAS_HZ - PILOT_ALIAS_HZ / 2
    return float(wrapped) if wrapped.ndim == 0 else wrapped


def circular_factor(offset_hz, grid_hz, sigma_hz, outlier_probability):
    """Return dimensionless P*((1-epsilon)*WN(offset-grid)+epsilon/P)."""
    if (
        not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or not np.isfinite(outlier_probability)
        or not 0 < outlier_probability < 1
    ):
        raise ValueError("positive sigma and an open-interval outlier probability required")
    residual = wrap_alias_hz(np.asarray(offset_hz)[..., None] - np.asarray(grid_hz))
    image_count = int(np.ceil(8 * sigma_hz / PILOT_ALIAS_HZ)) + 1
    kernel = np.zeros_like(residual, dtype=float)
    for image in range(-image_count, image_count + 1):
        kernel += np.exp(-0.5 * ((residual + image * PILOT_ALIAS_HZ) / sigma_hz) ** 2)
    wrapped_normal_times_period = (
        PILOT_ALIAS_HZ / (np.sqrt(2 * np.pi) * sigma_hz) * kernel
    )
    return (1 - outlier_probability) * wrapped_normal_times_period + outlier_probability


def maximum_factor(sigma_hz: float, outlier_probability: float) -> float:
    """Exact finite-stencil maximum used by ``circular_factor``."""
    return float(circular_factor(0.0, 0.0, sigma_hz, outlier_probability).item())


@dataclass(frozen=True)
class CircularArm:
    sigma_hz: float | None = None
    outlier_probability: float | None = None
    grid_size: int = 1024
    pruning_log_error: float = 1e-8

    def __post_init__(self):
        uniform = self.sigma_hz is None and self.outlier_probability is None
        if not uniform and (self.sigma_hz is None or self.outlier_probability is None):
            raise ValueError("uniform control or both circular controls required")
        if self.grid_size < 32 or self.pruning_log_error <= 0:
            raise ValueError("invalid quadrature or pruning bound")
        if not uniform:
            maximum_factor(float(self.sigma_hz), float(self.outlier_probability))

    @property
    def uniform(self) -> bool:
        return self.sigma_hz is None

    @property
    def name(self) -> str:
        if self.uniform:
            return "uniform-factor-control"
        return f"sigma-{self.sigma_hz:g}-outlier-{self.outlier_probability:g}"

    def grid_hz(self) -> np.ndarray:
        return np.linspace(
            -PILOT_ALIAS_HZ / 2, PILOT_ALIAS_HZ / 2, self.grid_size, endpoint=False
        )


@dataclass(frozen=True)
class CachedTrack:
    session_id: str
    episode_id: str
    tracklet_id: str
    receiver_id: int
    pilot_edge: str
    channel: int
    actual_rf_hz: float
    arc: ObservationArc
    positions_km: np.ndarray
    velocities_km_s: np.ndarray
    norads: np.ndarray
    catalogue_size: int
    support_digest: str = "synthetic"

    def __post_init__(self):
        count = len(self.arc.time_s)
        if (
            self.positions_km.shape != self.velocities_km_s.shape
            or self.positions_km.shape != (len(self.norads), count, 3)
            or self.catalogue_size < len(self.norads)
            or self.actual_rf_hz <= 0
            or len(np.unique(self.arc.segment)) != 1
            or not np.all(np.isfinite(self.positions_km))
            or not np.all(np.isfinite(self.velocities_km_s))
        ):
            raise ValueError("invalid individual-track state cache")

    @property
    def group(self) -> tuple[int, str]:
        return self.receiver_id, self.pilot_edge


@dataclass(frozen=True)
class StateCache:
    region: Region
    config: ScoreConfig
    tracks: tuple[CachedTrack, ...]
    provenance: dict[str, object]

    def __post_init__(self):
        if not self.tracks:
            raise ValueError("state cache cannot be empty")
        identities = [(row.session_id, row.episode_id) for row in self.tracks]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate cached episode")


@dataclass(frozen=True)
class TrackShape:
    candidate_train_log: np.ndarray
    candidate_joint_log: np.ndarray
    candidate_native_mean_hz: np.ndarray
    null_train_log: float
    null_joint_log: float
    visible: np.ndarray


def track_shape(track: CachedTrack, receiver, config: ScoreConfig) -> TrackShape:
    """Compute full-support train and train+heldout shapes at one position."""
    arc = track.arc
    delta = track.positions_km - receiver.ecef_km[0]
    distance = np.linalg.norm(delta, axis=-1)
    prediction = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * track.velocities_km_s, axis=-1)
        / distance
    )
    elevation = np.sum(delta * receiver.up[0], axis=-1) / distance
    visible = np.min(elevation[:, arc.training], axis=-1) >= np.sin(
        np.deg2rad(config.minimum_elevation_deg)
    )
    residual = arc.frequency_hz[None, :] - prediction
    mean = np.mean(residual[:, arc.training], axis=1)
    train_mse = np.mean((residual[:, arc.training] - mean[:, None]) ** 2, axis=1)
    test_mse = np.mean((residual[:, ~arc.training] - mean[:, None]) ** 2, axis=1)
    null_mean = float(np.mean(arc.frequency_hz[arc.training]))
    null_train_mse = float(np.mean((arc.frequency_hz[arc.training] - null_mean) ** 2))
    null_test_mse = float(np.mean((arc.frequency_hz[~arc.training] - null_mean) ** 2))
    n = config.effective_count
    candidate_train = (
        -0.5 * n * train_mse / config.signal_sigma_hz**2
        - n * np.log(config.signal_sigma_hz)
        + np.log(config.signal_prior / track.catalogue_size)
    )
    candidate_train = np.where(visible, candidate_train, -np.inf)
    candidate_test = (
        -0.5 * n * test_mse / config.signal_sigma_hz**2
        - n * np.log(config.signal_sigma_hz)
    )
    null_train = (
        -0.5 * n * null_train_mse / config.null_sigma_hz**2
        - n * np.log(config.null_sigma_hz)
        + np.log1p(-config.signal_prior)
    )
    null_test = (
        -0.5 * n * null_test_mse / config.null_sigma_hz**2
        - n * np.log(config.null_sigma_hz)
    )
    return TrackShape(
        candidate_train,
        candidate_train + candidate_test,
        wrap_alias_hz(mean * track.actual_rf_hz / CANONICAL_RF_HZ),
        float(null_train),
        float(null_train + null_test),
        visible,
    )


def _retained_indices(
    candidate_weights: np.ndarray,
    *,
    sigma_hz: float,
    outlier_probability: float,
    log_error_budget: float,
) -> tuple[np.ndarray, float, float]:
    """Retain enough mass for a rigorous factor-mixture log-error bound."""
    weights = np.asarray(candidate_weights, dtype=float)
    if np.any(weights < 0) or np.sum(weights) > 1 + 1e-12:
        raise ValueError("candidate weights must be unnormalized mixture probabilities")
    max_abs = max(
        1 - outlier_probability,
        maximum_factor(sigma_hz, outlier_probability) - 1,
    )
    allowed_relative = -np.expm1(-log_error_budget)
    allowed_mass = allowed_relative * outlier_probability / max_abs
    order = np.argsort(-weights, kind="stable")
    cumulative = np.cumsum(weights[order])
    total = float(np.sum(weights))
    keep = int(np.searchsorted(cumulative, total - allowed_mass, side="left") + 1)
    keep = min(keep, len(order))
    retained = order[:keep]
    omitted = max(0.0, total - float(np.sum(weights[retained])))
    relative_bound = omitted * max_abs / outlier_probability
    log_bound = -np.log1p(-relative_bound) if relative_bound < 1 else np.inf
    return retained, omitted, float(log_bound)


def mixture_curve(
    candidate_log: np.ndarray,
    null_log: float,
    native_mean_hz: np.ndarray,
    arm: CircularArm,
    *,
    track_log_error_budget: float,
) -> tuple[np.ndarray, dict[str, object]]:
    """Approximate only bounded low-mass factor terms; retain baseline mass exactly."""
    candidate_log = np.asarray(candidate_log, dtype=float)
    baseline = float(np.logaddexp(logsumexp(candidate_log), null_log))
    if arm.uniform:
        return np.asarray([baseline]), {
            "candidate_count": len(candidate_log),
            "retained_candidate_count": 0,
            "omitted_candidate_weight": 0.0,
            "log_error_bound": 0.0,
        }
    weights = np.exp(candidate_log - baseline)
    retained, omitted, bound = _retained_indices(
        weights,
        sigma_hz=float(arm.sigma_hz),
        outlier_probability=float(arm.outlier_probability),
        log_error_budget=track_log_error_budget,
    )
    factor = circular_factor(
        np.asarray(native_mean_hz)[retained],
        arm.grid_hz(),
        float(arm.sigma_hz),
        float(arm.outlier_probability),
    )
    normalized = 1 + np.sum(weights[retained, None] * (factor - 1), axis=0)
    if np.any(normalized <= 0) or bound > track_log_error_budget * (1 + 1e-8):
        raise RuntimeError("candidate pruning failed its declared likelihood bound")
    return baseline + np.log(normalized), {
        "candidate_count": len(candidate_log),
        "retained_candidate_count": len(retained),
        "retained_indices": retained,
        "omitted_candidate_weight": omitted,
        "log_error_bound": bound,
        "baseline_candidate_weights": weights,
    }


def _logmeanexp(values: np.ndarray) -> float:
    return float(logsumexp(values) - np.log(len(values)))


def score_shape_groups(
    shapes: list[TrackShape],
    group_keys: list[tuple[int, str] | int | str],
    arm: CircularArm,
) -> dict[str, object]:
    """Score precomputed shapes; this is the dense-oracle parity boundary."""
    if not shapes or len(shapes) != len(group_keys):
        raise ValueError("one nonempty group key per shape required")
    per_curve_budget = arm.pruning_log_error / (2 * len(shapes))
    curves = []
    total_bound = 0.0
    for shape in shapes:
        train, train_info = mixture_curve(
            shape.candidate_train_log,
            shape.null_train_log,
            shape.candidate_native_mean_hz,
            arm,
            track_log_error_budget=per_curve_budget,
        )
        joint, joint_info = mixture_curve(
            shape.candidate_joint_log,
            shape.null_joint_log,
            shape.candidate_native_mean_hz,
            arm,
            track_log_error_budget=per_curve_budget,
        )
        total_bound += float(train_info["log_error_bound"]) + float(
            joint_info["log_error_bound"]
        )
        curves.append((train, joint, train_info, joint_info))
    groups: dict[object, list[int]] = defaultdict(list)
    for index, group in enumerate(group_keys):
        groups[group].append(index)
    training_score = 0.0
    heldout_score = 0.0
    group_values = []
    for group, indexes in sorted(groups.items(), key=lambda item: str(item[0])):
        train_sum = np.sum([curves[index][0] for index in indexes], axis=0)
        joint_sum = np.sum([curves[index][1] for index in indexes], axis=0)
        train_evidence = _logmeanexp(train_sum)
        joint_evidence = _logmeanexp(joint_sum)
        null_train = sum(shapes[index].null_train_log for index in indexes)
        null_test = sum(
            shapes[index].null_joint_log - shapes[index].null_train_log for index in indexes
        )
        training_score += train_evidence - null_train
        heldout_score += joint_evidence - train_evidence - null_test
        group_values.append(
            {
                "group": group,
                "indexes": indexes,
                "train_sum": train_sum,
                "joint_sum": joint_sum,
                "train_evidence": train_evidence,
            }
        )
    if total_bound > arm.pruning_log_error * (1 + 1e-8):
        raise RuntimeError("aggregate pruning error exceeds declared objective bound")
    return {
        "training_score": float(training_score),
        "heldout_score": float(heldout_score),
        "pruning_log_error_bound": float(total_bound),
        "curves": curves,
        "group_values": group_values,
    }


def evaluate_position(
    cache: StateCache,
    point_east_north_km,
    arm: CircularArm,
    *,
    details: bool = False,
) -> dict[str, object]:
    """Evaluate training objective and training-conditioned heldout score."""
    point = np.asarray(point_east_north_km, dtype=float)
    if point.shape != (2,):
        raise ValueError("one east/north point required")
    receiver = cache.region.points([point[0]], [point[1]])
    shapes = [track_shape(track, receiver, cache.config) for track in cache.tracks]
    scored = score_shape_groups(shapes, [track.group for track in cache.tracks], arm)
    curves = scored.pop("curves")
    group_values = scored.pop("group_values")
    group_rows = []
    track_rows: list[dict[str, object]] = [{} for _ in cache.tracks]
    for group_value in group_values:
        group = group_value["group"]
        indexes = group_value["indexes"]
        train_sum = group_value["train_sum"]
        train_evidence = group_value["train_evidence"]
        if details:
            posterior = np.exp(train_sum - logsumexp(train_sum))
            angles = (
                2 * np.pi * arm.grid_hz() / PILOT_ALIAS_HZ
                if not arm.uniform
                else np.zeros(1)
            )
            vector = np.sum(posterior * np.exp(1j * angles))
            mode_index = int(np.argmax(posterior))
            group_rows.append(
                {
                    "receiver_id": group[0],
                    "pilot_edge": group[1],
                    "track_count": len(indexes),
                    "posterior_mode_hz": (
                        None if arm.uniform else float(arm.grid_hz()[mode_index])
                    ),
                    "posterior_resultant": 0.0 if arm.uniform else float(abs(vector)),
                    "nuisance_interpretation": (
                        "circular model coordinate; not physical calibration"
                    ),
                }
            )
            for index in indexes:
                track_train, track_joint, train_info, joint_info = curves[index]
                predictive = (
                    _logmeanexp(train_sum + track_joint - track_train)
                    - train_evidence
                    - (shapes[index].null_joint_log - shapes[index].null_train_log)
                )
                track_rows[index] = _track_details(
                    cache.tracks[index],
                    shapes[index],
                    train_info,
                    posterior,
                    arm,
                    predictive,
                    joint_info,
                )
    result: dict[str, object] = scored
    if details:
        result.update(groups=group_rows, tracks=track_rows)
    return result


def _track_details(
    track: CachedTrack,
    shape: TrackShape,
    train_info: dict[str, object],
    group_posterior: np.ndarray,
    arm: CircularArm,
    heldout_score: float,
    joint_info: dict[str, object],
) -> dict[str, object]:
    baseline, circular, null_weight = training_identity_posterior(
        shape, train_info, group_posterior, arm
    )
    order = np.argsort(-circular, kind="stable")[:8]
    return {
        "session_id": track.session_id,
        "episode_id": track.episode_id,
        "tracklet_id": track.tracklet_id,
        "receiver_id": track.receiver_id,
        "pilot_edge": track.pilot_edge,
        "channel": track.channel,
        "observations": len(track.arc.time_s),
        "heldout_score": float(heldout_score),
        "candidate_count": len(track.norads),
        "train_kernel_retained_candidate_count": train_info["retained_candidate_count"],
        "joint_kernel_retained_candidate_count": joint_info["retained_candidate_count"],
        "candidates": [
            {
                "norad": int(track.norads[index]),
                "shape_weight": float(baseline[index]),
                "circular_weight": float(circular[index]),
                "native_training_mean_hz": float(shape.candidate_native_mean_hz[index]),
            }
            for index in order
            if circular[index] > 0
        ],
        "null_weight": null_weight,
        "omitted_circular_identity_weight": float(np.sum(circular) - np.sum(circular[order])),
    }


def training_identity_posterior(
    shape: TrackShape,
    train_info: dict[str, object],
    group_posterior: np.ndarray,
    arm: CircularArm,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Marginalize one track identity under the all-training group posterior."""
    baseline = np.asarray(train_info.get("baseline_candidate_weights", []), dtype=float)
    if arm.uniform:
        evidence = float(
            np.logaddexp(logsumexp(shape.candidate_train_log), shape.null_train_log)
        )
        baseline = np.exp(shape.candidate_train_log - evidence)
        circular = baseline.copy()
        null_weight = float(np.exp(shape.null_train_log - evidence))
    else:
        grid = arm.grid_hz()
        retained = np.asarray(train_info["retained_indices"], dtype=int)
        evidence = float(
            np.logaddexp(logsumexp(shape.candidate_train_log), shape.null_train_log)
        )
        null_weight = float(np.exp(shape.null_train_log - evidence))
        factor = np.ones((len(baseline), len(grid)))
        if len(retained):
            factor[retained] = circular_factor(
                shape.candidate_native_mean_hz[retained],
                grid,
                float(arm.sigma_hz),
                float(arm.outlier_probability),
            )
        normalization = null_weight + np.sum(baseline[:, None] * factor, axis=0)
        circular = baseline * ((factor / normalization) @ group_posterior)
        null_weight = float(null_weight * np.sum(group_posterior / normalization))
    return baseline, circular, null_weight


def refine_local_mode(
    objective,
    seed_east_north_km,
    region: Region,
    *,
    radius_km: float = 100.0,
    max_evaluations: int = 140,
) -> dict[str, object]:
    """Refine one training-selected basin within a clipped local square."""
    seed = np.asarray(seed_east_north_km, dtype=float)
    if seed.shape != (2,) or radius_km <= 0 or max_evaluations < 4:
        raise ValueError("valid seed, positive radius, and at least four evaluations required")
    lower = np.maximum(seed - radius_km, [-region.width_km / 2, -region.height_km / 2])
    upper = np.minimum(seed + radius_km, [region.width_km / 2, region.height_km / 2])
    simplex = np.tile(seed, (3, 1))
    for axis in range(2):
        step = min(10.0, upper[axis] - seed[axis])
        if step <= 0:
            step = -min(10.0, seed[axis] - lower[axis])
        simplex[axis + 1, axis] += step
    fit = minimize(
        lambda value: -float(objective(value)),
        seed,
        method="Nelder-Mead",
        bounds=list(zip(lower, upper, strict=True)),
        options={
            "maxfev": max_evaluations,
            "xatol": 0.02,
            "fatol": 1e-5,
            "initial_simplex": simplex,
        },
    )
    tolerance = 0.021
    return {
        "east_km": float(fit.x[0]),
        "north_km": float(fit.x[1]),
        "training_score": -float(fit.fun),
        "converged": bool(fit.success),
        "evaluations": int(fit.nfev),
        "message": str(fit.message),
        "seed_east_north_km": seed.tolist(),
        "local_lower_east_north_km": lower.tolist(),
        "local_upper_east_north_km": upper.tolist(),
        "bound_hit": bool(np.any(fit.x <= lower + tolerance) or np.any(fit.x >= upper - tolerance)),
    }


def verify_refinement(path: Path) -> tuple[dict, dict]:
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.with_name("result.sha256").read_text().strip() != checksum:
        raise ValueError("refinement result checksum mismatch")
    result = json.loads(path.read_text())
    seal_path = path.with_name("refinement-seal.json")
    seal = json.loads(seal_path.read_text())
    if (
        seal.get("result_digest") != "sha256:" + checksum
        or seal.get("position_truth_used") is not False
        or seal.get("all_fits_converged") is not True
        or result.get("complete") is not True
        or result.get("position_truth_used") is not False
        or result.get("partition") != FIVE_BLOCK_PARTITION
        or result.get("geometry_pair_factor_used") is not False
        or not result.get("fits")
        or not all(row.get("converged") is True for row in result["fits"])
    ):
        raise ValueError("complete sealed converged five-block refinement required")
    run = Path(result["run"])
    acquisition_seal = json.loads((run / "acquisition-seal.json").read_text())
    for name, expected in acquisition_seal.get("files", {}).items():
        if Path(name).name != name or digest(run / name) != expected:
            raise ValueError("acquisition seal mismatch")
    if seal.get("acquisition_seal_digest") != digest(run / "acquisition-seal.json"):
        raise ValueError("refinement does not bind acquisition seal")
    return result, acquisition_seal


def _rf_lanes(directory: Path, manifest_path: Path) -> tuple[dict, dict]:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("content_digest") != content_digest(manifest):
        raise ValueError("RF shard manifest content digest mismatch")
    expected = manifest.get("files", manifest.get("provenance", {}).get("rf_shard_digests", {}))
    expected = {
        path: value.get("sha256", value) if isinstance(value, dict) else value
        for path, value in expected.items()
    }
    expected_by_name = {Path(path).name: value for path, value in expected.items()}
    paths = sorted(directory.glob("scan-*.json"))
    if not expected_by_name or {path.name for path in paths} != set(expected_by_name):
        raise ValueError("RF shard inventory differs from manifest")
    lanes = {}
    for path in paths:
        if digest(path) != expected_by_name[path.name]:
            raise ValueError("RF shard digest mismatch")
        shard = json.loads(path.read_text())
        for track in shard["tracks"]:
            key = shard["session"]["session_id"], track["tracklet_id"]
            if key in lanes:
                raise ValueError("duplicate RF lane authority")
            lanes[key] = track["lane"]
    return lanes, {str(path): digest(path) for path in paths}


def build_state_cache(
    refinement_path: Path,
    evidence_directory: Path,
    rf_shards: Path,
    rf_shard_manifest: Path,
    *,
    single_session: str | None = None,
) -> StateCache:
    """Build one reusable exact-state cache without accessing position truth."""
    refinement, acquisition_seal = verify_refinement(refinement_path)
    lanes, shard_digests = _rf_lanes(rf_shards, rf_shard_manifest)
    replay_path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    adapter_path = Path(__file__).with_name("replay_five_block_regional.py")
    replay = load_module(replay_path, "joint_circular_replay")
    adapter = load_module(adapter_path, "joint_circular_five_block")
    loader = adapter.FiveBlockLoader()
    replay.load_observations = loader
    acquisition = json.loads((Path(refinement["run"]) / "result.json").read_text())
    inventory_path = evidence_directory / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if (
        inventory.get("known_position_used") is not False
        or inventory.get("prior_matched_norads_used", False)
        or digest(inventory_path) != acquisition["inventory_digest"]
    ):
        raise ValueError("truth-free sealed evidence inventory required")
    region = Region(**refinement["region"])
    config = ScoreConfig(**acquisition["score"])
    sessions = list(refinement["sessions"])
    if single_session is not None:
        if single_session not in sessions:
            raise ValueError("single session absent from refinement")
        sessions = [single_session]
    tracks = []
    provenance = {}
    for session in sessions:
        evidence_path = evidence_directory / "evidence" / f"{session}.json"
        document = json.loads(evidence_path.read_text())
        source = refinement["provenance"][session]
        if digest(evidence_path) != source["rf_digest"]:
            raise ValueError("RF evidence binding mismatch")
        metadata = document["inventory"]
        tle_name = metadata["tle_file"]
        if Path(tle_name).name != tle_name:
            raise ValueError("unsafe TLE basename")
        tle_path = evidence_path.parent / tle_name
        if (
            metadata["tle_collected_ns"] >= metadata["reference_utc_ns"] - 5_000_000_000
            or digest(tle_path) != metadata["tle_digest"]
            or digest(tle_path) != source["tle_digest"]
        ):
            raise ValueError("noncausal or unbound TLE")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, metadata["reference_utc_ns"], region
        )
        series = {row["tracklet_id"]: row for row in document["series"]}
        episodes = {row["episode_id"]: row for row in document["episodes"]}
        support = {row["episode_id"]: row for row in source["evaluated_support"]}
        loaded = replay.load_observations(document, max_per_partition=0)
        for episode_id, arc in loaded:
            episode = episodes.get(episode_id)
            if episode is None or len(episode["members"]) != 1:
                raise ValueError("joint circular fitter requires individual RF tracks")
            tracklet_id = episode["members"][0]
            row = series[tracklet_id]
            lane = lanes[(session, tracklet_id)]
            if (
                int(lane["receiver_id"]) != int(row["receiver_id"])
                or int(lane["channel"]) != int(row["channel"])
                or float(lane["actual_rf_hz"]) != float(row["actual_rf_hz"])
                or float(lane["canonical_rf_hz"]) != CANONICAL_RF_HZ
            ):
                raise ValueError("RF lane metadata differs from evidence")
            p, v, retained = replay.state_arrays(
                catalogue, indices, metadata["reference_utc_ns"], arc.time_s
            )
            norads = np.asarray(catalogue.satellite_numbers)[retained]
            support_digest = "sha256:" + hashlib.sha256(
                np.sort(norads).astype("<i8").tobytes()
            ).hexdigest()
            baseline = support.get(episode_id)
            if baseline is None or baseline["evaluated_norad_digest"] != support_digest:
                raise ValueError("full candidate support differs from sealed refinement")
            tracks.append(
                CachedTrack(
                    session,
                    episode_id,
                    tracklet_id,
                    int(lane["receiver_id"]),
                    str(lane["edge"]),
                    int(lane["channel"]),
                    float(lane["actual_rf_hz"]),
                    arc,
                    p,
                    v,
                    norads,
                    population,
                    support_digest,
                )
            )
        provenance[session] = {
            "evidence_digest": digest(evidence_path),
            "tle_digest": digest(tle_path),
            "track_count": len(loaded),
        }
    return StateCache(
        region,
        config,
        tuple(tracks),
        {
            "position_truth_accessed": False,
            "refinement_digest": digest(refinement_path),
            "refinement_seal_digest": digest(refinement_path.with_name("refinement-seal.json")),
            "acquisition_seal_digest": digest(Path(refinement["run"]) / "acquisition-seal.json"),
            "acquisition_file_digests": acquisition_seal["files"],
            "evidence_inventory_digest": digest(inventory_path),
            "rf_shard_manifest_digest": digest(rf_shard_manifest),
            "rf_shard_digests": shard_digests,
            "replay_source_digest": digest(replay_path),
            "partition_adapter_digest": digest(adapter_path),
            "sessions": provenance,
            "seed_fits": refinement["fits"],
        },
    )


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output directory required")
    if not np.isfinite(args.budget_seconds) or args.budget_seconds <= 0:
        raise ValueError("positive finite time budget required")
    started = time.monotonic()
    cache = build_state_cache(
        args.refinement,
        args.evidence,
        args.rf_shards,
        args.rf_shard_manifest,
        single_session=args.single_session,
    )
    arms = [CircularArm()]
    if args.all_arms:
        arms += [
            CircularArm(sigma, outlier, args.grid_size)
            for sigma in SIGMA_ARMS_HZ
            for outlier in OUTLIER_ARMS
        ]
    elif args.sigma_hz is not None or args.outlier_probability is not None:
        arms = [CircularArm(args.sigma_hz, args.outlier_probability, args.grid_size)]
    seeds = list(cache.provenance["seed_fits"])
    if args.seed_index is not None:
        if not 0 <= args.seed_index < len(seeds):
            raise ValueError("seed index outside sealed refinement fits")
        seeds = [seeds[args.seed_index]]
    args.output.mkdir(parents=True)
    outputs = []
    evaluations = 0

    def guard() -> None:
        if time.monotonic() - started > args.budget_seconds:
            raise TimeoutError("bounded joint refinement budget exhausted")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 1_800_000:
            raise MemoryError("joint refinement RSS exceeds 1.8GB")

    for arm in arms:
        fits = []
        for seed in seeds:
            def objective(point, selected_arm=arm):
                nonlocal evaluations
                guard()
                result = evaluate_position(cache, point, selected_arm)
                evaluations += 1
                with (args.output / "checkpoint.jsonl").open("a") as stream:
                    stream.write(json.dumps({
                        "arm": selected_arm.name,
                        "evaluation": evaluations,
                        "east_km": float(point[0]),
                        "north_km": float(point[1]),
                        "training_score": result["training_score"],
                        "elapsed_s": time.monotonic() - started,
                    }) + "\n")
                return result["training_score"]

            fits.append(
                refine_local_mode(
                    objective,
                    [seed["east_km"], seed["north_km"]],
                    cache.region,
                    radius_km=args.radius_km,
                    max_evaluations=args.max_evaluations,
                )
            )
        selected = max(fits, key=lambda row: row["training_score"])
        detail = evaluate_position(
            cache, [selected["east_km"], selected["north_km"]], arm, details=True
        )
        latitude, longitude = cache.region.coordinates(
            selected["east_km"], selected["north_km"]
        )
        outputs.append(
            {
                "arm": arm.name,
                "sigma_hz": arm.sigma_hz,
                "outlier_probability": arm.outlier_probability,
                "grid_size": arm.grid_size,
                "fits": fits,
                "selected": selected,
                "latitude_deg": float(latitude),
                "longitude_deg": float(longitude),
                **detail,
            }
        )
    result = {
        "schema": "blind-joint-circular-position-refinement/v1",
        "complete": True,
        "scientific_status": "local composite-likelihood diagnostic",
        "position_truth_used": False,
        "identity_refreshed_at_every_position": True,
        "heldout_selected_position_or_identity": False,
        "nominal_exact_orbits": True,
        "partition": FIVE_BLOCK_PARTITION,
        "track_count": len(cache.tracks),
        "observation_count": sum(len(track.arc.time_s) for track in cache.tracks),
        "arms": outputs,
        "provenance": {
            **cache.provenance,
            "source_code_digest": digest(Path(__file__)),
        },
        "limitations": [
            "shape energies are a composite likelihood, not a calibrated posterior",
            "the circular intercept is a nuisance coordinate with no asserted physical meaning",
            "tracks and receivers can remain statistically dependent",
            "five-block heldout scores interpolate within the captured time span",
            "local fits condition on training-selected basins and do not replace wide searches",
            "nominal causal TLE states are used without orbit correction",
        ],
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    result["content_digest"] = content_digest(result)
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    (args.output / "result.json").write_text(payload)
    (args.output / "result.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rf-shards", type=Path, required=True)
    parser.add_argument("--rf-shard-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single-session")
    parser.add_argument("--seed-index", type=int)
    parser.add_argument("--radius-km", type=float, default=100.0)
    parser.add_argument("--max-evaluations", type=int, default=140)
    parser.add_argument("--budget-seconds", type=float, default=600.0)
    parser.add_argument("--grid-size", type=int, default=1024)
    parser.add_argument("--all-arms", action="store_true")
    parser.add_argument("--sigma-hz", type=float)
    parser.add_argument("--outlier-probability", type=float)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
