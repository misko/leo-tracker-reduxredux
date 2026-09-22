#!/usr/bin/env python3
"""Locally refine blind position with one bounded receive-clock offset per scan."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.regional_doppler import Region, ScoreConfig, score_states
from leo.sky.propagation import parse_element_sets


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"{name} has no loader")
    spec.loader.exec_module(module)
    return module


def lagrange_weights(nodes: np.ndarray, value: float) -> np.ndarray:
    if value < nodes[0] or value > nodes[-1]:
        raise ValueError("clock escapes its hard bracket")
    exact = np.flatnonzero(np.isclose(nodes, value, atol=1e-14, rtol=0))
    if len(exact):
        output = np.zeros(len(nodes))
        output[exact[0]] = 1
        return output
    weights = np.ones(len(nodes))
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i != j:
                weights[i] *= (value - nodes[j]) / (nodes[i] - nodes[j])
    return weights


@dataclass(slots=True)
class StateCache:
    nodes_s: np.ndarray
    position0: np.ndarray
    velocity0: np.ndarray
    position_delta: np.ndarray
    velocity_delta: np.ndarray

    @classmethod
    def build(cls, nodes_s, states):
        nodes = np.asarray(nodes_s, dtype=float)
        zero = int(np.flatnonzero(nodes == 0)[0])
        p0, v0 = states[zero]
        pd = np.asarray([p - p0 for p, _v in states], dtype=np.float32)
        vd = np.asarray([v - v0 for _p, v in states], dtype=np.float32)
        return cls(nodes, p0, v0, pd, vd)

    def at(self, clock_s: float) -> tuple[np.ndarray, np.ndarray]:
        weights = lagrange_weights(self.nodes_s, clock_s)
        return (
            self.position0 + np.tensordot(weights, self.position_delta, axes=(0, 0)),
            self.velocity0 + np.tensordot(weights, self.velocity_delta, axes=(0, 0)),
        )


def clock_nodes(lower: float, upper: float) -> np.ndarray:
    if not lower < 0 < upper:
        raise ValueError("clock bracket must contain zero strictly")
    return np.unique(np.r_[np.linspace(lower, 0, 3), np.linspace(0, upper, 3)])


def doppler(receiver, position, velocity):
    from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ

    delta = position - receiver
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocity, axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def visibility_mask(position, receiver, up, training, minimum_elevation_deg):
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=-1)
    elevation = np.sum(delta * up, axis=-1) / distance
    return np.min(elevation[:, training], axis=-1) >= np.sin(
        np.deg2rad(minimum_elevation_deg)
    )


def qualifies(*, converged, maximum_error_hz, visibility_mismatches, score_delta):
    return bool(
        converged
        and np.isfinite(maximum_error_hz)
        and maximum_error_hz <= 0.2
        and visibility_mismatches == 0
        and np.isfinite(score_delta)
        and abs(score_delta) <= 1e-4
    )


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output directory required")
    if args.position_radius_km <= 0 or args.max_evaluations < 8:
        raise ValueError("positive position radius and at least eight evaluations required")
    started = time.monotonic()
    source_code_digest = digest(Path(__file__))

    def guard() -> None:
        if time.monotonic() - started > args.budget_seconds:
            raise TimeoutError("joint clock refinement time budget exhausted")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > args.max_rss_kib:
            raise MemoryError("joint clock refinement RSS budget exhausted")

    refinement = json.loads(args.refinement.read_text())
    checksum = args.refinement.with_name("result.sha256")
    if (
        not checksum.is_file()
        or checksum.read_text().strip() != hashlib.sha256(args.refinement.read_bytes()).hexdigest()
        or not refinement.get("complete")
        or refinement.get("position_truth_used") is not False
    ):
        raise ValueError("sealed truth-free completed refinement required")
    audit = json.loads(args.clock_audit.read_text())
    claimed = audit.pop("content_digest")
    if claimed != "sha256:" + hashlib.sha256(
        json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest():
        raise ValueError("clock audit content digest mismatch")
    if (
        not audit["summary"]["all_qualified"]
        or not audit["summary"]["all_causal_for_allowed_offsets"]
    ):
        raise ValueError("qualified causal clock brackets required")
    replay_path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    replay = load_module(replay_path, "joint_clock_replay")
    region = Region(**refinement["region"])
    acquisition_path = Path(refinement["run"]) / "result.json"
    expected_acquisition = refinement["acquisition_file_digests"]["result.json"]
    if digest(acquisition_path) != expected_acquisition or expected_acquisition != refinement[
        "source_result_digest"
    ]:
        raise ValueError("sealed acquisition result binding mismatch")
    acquisition = json.loads(acquisition_path.read_text())
    config = ScoreConfig(**acquisition["score"])
    if config.signal_sigma_hz != 250.0:
        raise ValueError("matched clock ablation requires the executed 250 Hz score")
    bounds_by_session = {
        row["session_id"]: tuple(row["allowed_clock_s_relative_to_reference"])
        for row in audit["sessions"]
    }
    cache = []
    session_sources = {}
    session_accounting = {}
    support_rows = []
    for session_id in refinement["sessions"]:
        evidence_path = args.evidence / "evidence" / f"{session_id}.json"
        document = json.loads(evidence_path.read_text())
        provenance = refinement["provenance"][session_id]
        if digest(evidence_path) != provenance["rf_digest"]:
            raise ValueError("RF evidence binding mismatch")
        metadata = document["inventory"]
        tle_name = metadata["tle_file"]
        if Path(tle_name).name != tle_name:
            raise ValueError("unsafe TLE basename")
        tle_path = evidence_path.parent / tle_name
        if (
            digest(tle_path) != metadata["tle_digest"]
            or digest(tle_path) != provenance["tle_digest"]
        ):
            raise ValueError("TLE binding mismatch")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, metadata["reference_utc_ns"], region
        )
        nodes = clock_nodes(*bounds_by_session[session_id])
        session_sources[session_id] = (catalogue, indices, metadata, population)
        session_accounting[session_id] = {
            "full_catalogue_count": population,
            "regional_candidate_count": len(indices),
            "regional_prefilter_exclusion_count": population - len(indices),
            "clock_nodes_s": nodes.tolist(),
        }
        for episode_id, arc in replay.load_observations(document, max_per_partition=0):
            guard()
            states = []
            retained0 = None
            for node in nodes:
                p, v, retained = replay.state_arrays(
                    catalogue,
                    indices,
                    metadata["reference_utc_ns"],
                    arc.time_s,
                    clock_s=float(node),
                )
                if retained0 is None:
                    retained0 = retained
                elif not np.array_equal(retained0, retained):
                    raise ValueError("clock nodes change evaluated candidate support")
                states.append((p, v))
            assert retained0 is not None
            norads = np.asarray(catalogue.satellite_numbers)[retained0]
            support_digest = "sha256:" + hashlib.sha256(
                np.sort(norads).astype("<i8").tobytes()
            ).hexdigest()
            baseline_support = next(
                row
                for row in provenance["evaluated_support"]
                if row["episode_id"] == episode_id
            )
            if (
                support_digest != baseline_support["evaluated_norad_digest"]
                or len(norads) != baseline_support["evaluated_candidate_count"]
            ):
                raise ValueError("clock cache support differs from sealed nominal refinement")
            cache.append(
                (session_id, episode_id, arc, StateCache.build(nodes, states), norads, population)
            )
            support_rows.append(
                {
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "candidate_count": len(norads),
                    "candidate_digest": support_digest,
                    "propagation_or_radius_exclusion_count": len(indices) - len(norads),
                }
            )
    session_order = list(refinement["sessions"])

    def score(values, *, heldout=False):
        guard()
        point = np.asarray(values[:2])
        grid = region.points([point[0]], [point[1]])
        clocks = dict(zip(session_order, values[2:], strict=True))
        total = 0.0
        for session_id, _episode, arc, state, _norads, population in cache:
            p, v = state.at(float(clocks[session_id]))
            result = score_states(arc, p, v, grid, population, config)
            total += float(result["heldout_logbf" if heldout else "train_logbf"][0])
        return total

    start = np.asarray(
        [refinement["selected"]["east_km"], refinement["selected"]["north_km"]]
        + [0.0] * len(session_order)
    )
    nominal_train = score(start)
    if not np.isclose(nominal_train, refinement["training_score"], atol=1e-5, rtol=0):
        raise ValueError("nominal matched score differs from sealed refinement")
    bounds = [
        (
            max(-region.width_km / 2, start[0] - args.position_radius_km),
            min(region.width_km / 2, start[0] + args.position_radius_km),
        ),
        (
            max(-region.height_km / 2, start[1] - args.position_radius_km),
            min(region.height_km / 2, start[1] + args.position_radius_km),
        ),
        *(bounds_by_session[session] for session in session_order),
    ]
    fit = minimize(
        lambda value: -score(value),
        start,
        method="Powell",
        bounds=bounds,
        options={"maxfev": args.max_evaluations, "xtol": 1e-5, "ftol": 1e-7},
    )
    fitted = np.asarray(fit.x)
    fitted_grid = region.points([fitted[0]], [fitted[1]])
    clocks = dict(zip(session_order, fitted[2:], strict=True))
    audit_max = 0.0
    visibility_mismatches = 0
    audit_by_clock = []
    exact_train = exact_heldout = 0.0
    top_support = []
    refiner = load_module(Path(__file__).with_name("refine_recent_joint_position.py"), "refiner")
    for session_id, episode_id, arc, state, norads, population in cache:
        p, v = state.at(float(clocks[session_id]))
        catalogue, indices, metadata, _ = session_sources[session_id]
        exact_p, exact_v, exact_retained = replay.state_arrays(
            catalogue,
            indices,
            metadata["reference_utc_ns"],
            arc.time_s,
            clock_s=float(clocks[session_id]),
        )
        exact_norads = np.asarray(catalogue.satellite_numbers)[exact_retained]
        if not np.array_equal(norads, exact_norads):
            raise ValueError("exact fitted replay changes candidate support")
        stencil = np.unique(
            np.r_[
                np.linspace(*bounds_by_session[session_id], 9),
                0.0,
                clocks[session_id],
            ]
        )
        for audit_clock in stencil:
            guard()
            approximate_p, approximate_v = state.at(float(audit_clock))
            replay_p, replay_v, replay_retained = replay.state_arrays(
                catalogue,
                indices,
                metadata["reference_utc_ns"],
                arc.time_s,
                clock_s=float(audit_clock),
            )
            if not np.array_equal(exact_retained, replay_retained):
                raise ValueError("dense exact clock audit changes candidate support")
            error = np.max(
                np.abs(
                    doppler(fitted_grid.ecef_km[0], approximate_p, approximate_v)
                    - doppler(fitted_grid.ecef_km[0], replay_p, replay_v)
                )
            )
            audit_max = max(audit_max, float(error))
            approximate_visible = visibility_mask(
                approximate_p,
                fitted_grid.ecef_km[0],
                fitted_grid.up[0],
                arc.training,
                config.minimum_elevation_deg,
            )
            exact_visible = visibility_mask(
                replay_p,
                fitted_grid.ecef_km[0],
                fitted_grid.up[0],
                arc.training,
                config.minimum_elevation_deg,
            )
            visibility_mismatches += int(np.sum(approximate_visible != exact_visible))
            audit_by_clock.append(
                {
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "clock_s": float(audit_clock),
                    "maximum_abs_error_hz": float(error),
                    "visibility_mismatch_count": int(
                        np.sum(approximate_visible != exact_visible)
                    ),
                }
            )
        exact_score = score_states(arc, exact_p, exact_v, fitted_grid, population, config)
        exact_train += float(exact_score["train_logbf"][0])
        exact_heldout += float(exact_score["heldout_logbf"][0])
        weights, null = refiner.posterior_at(
            arc, exact_p, exact_v, fitted_grid, population, config
        )
        order = np.argsort(-weights, kind="stable")[:8]
        top_support.append(
            {
                "session_id": session_id,
                "episode_id": episode_id,
                "null_weight": null,
                "candidates": [
                    {"norad": int(norads[i]), "weight": float(weights[i])}
                    for i in order
                    if weights[i] > 0
                ],
                "omitted_identity_weight": float(1 - null - np.sum(weights[order])),
            }
        )
    approximate_fitted_train = score(fitted)
    score_delta = approximate_fitted_train - exact_train
    qualified = bool(
        qualifies(
            converged=fit.success,
            maximum_error_hz=audit_max,
            visibility_mismatches=visibility_mismatches,
            score_delta=score_delta,
        )
        and np.isfinite(exact_train)
        and np.isfinite(exact_heldout)
    )
    latitude, longitude = region.coordinates(float(fitted[0]), float(fitted[1]))
    distance_to_clock_bound = {
        key: float(min(value - bounds_by_session[key][0], bounds_by_session[key][1] - value))
        for key, value in clocks.items()
    }
    output = {
        "schema": "joint-receive-clock-local-refinement/v1",
        "complete": True,
        "qualification": "diagnostic" if qualified else "insufficient",
        "truth_accessed": False,
        "known_position_used": False,
        "scope": "local ablation from one independently sealed nominal basin",
        "position_radius_km": args.position_radius_km,
        "unsearched_clock_induced_modes": True,
        "refinement_digest": digest(args.refinement),
        "clock_audit_digest": digest(args.clock_audit),
        "replay_source_digest": digest(replay_path),
        "source_code_digest": source_code_digest,
        "score": {**asdict(config), "full_catalogue_prior": True},
        "nominal": {
            "east_km": float(start[0]),
            "north_km": float(start[1]),
            "training_score": nominal_train,
            "heldout_score": score(start, heldout=True),
        },
        "fitted": {
            "east_km": float(fitted[0]),
            "north_km": float(fitted[1]),
            "latitude_deg": float(latitude),
            "longitude_deg": float(longitude),
            "clock_s": {key: float(value) for key, value in clocks.items()},
            "clock_at_bound": {
                key: distance_to_clock_bound[key] <= 1e-5 for key in clocks
            },
            "clock_distance_to_nearest_bound_s": distance_to_clock_bound,
            "approximate_training_score": approximate_fitted_train,
            "training_score": exact_train,
            "heldout_score": exact_heldout,
            "approximation_training_score_delta": score_delta,
        },
        "optimizer": {
            "converged": bool(fit.success),
            "message": str(fit.message),
            "evaluations": int(fit.nfev),
        },
        "exact_replay": {
            "complete": True,
            "maximum_abs_prediction_error_hz": audit_max,
            "tolerance_hz": 0.2,
            "dense_clock_points_per_scan_minimum": 9,
            "visibility_mismatch_count": visibility_mismatches,
            "per_episode_clock": audit_by_clock,
        },
        "session_accounting": session_accounting,
        "support": support_rows,
        "tracks": top_support,
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(output, indent=2, allow_nan=False) + "\n"
    (args.output / "result.json").write_text(payload)
    (args.output / "result.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--clock-audit", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-evaluations", type=int, default=180)
    parser.add_argument("--position-radius-km", type=float, default=100.0)
    parser.add_argument("--budget-seconds", type=float, default=900)
    parser.add_argument("--max-rss-kib", type=int, default=6_000_000)
    run(parser.parse_args())
