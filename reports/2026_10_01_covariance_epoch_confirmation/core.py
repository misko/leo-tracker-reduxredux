"""Frozen-control confirmation of combined temporal covariance and epoch quadrature."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_DIR = ROOT / "reports/2026_09_30_sacramento_model_comparison"
if str(OLD_DIR) not in sys.path:
    sys.path.insert(0, str(OLD_DIR))

SPEC = importlib.util.spec_from_file_location("sacramento_frozen_core", OLD_DIR / "core.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen Sacramento core")
old = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = old
SPEC.loader.exec_module(old)


def load_methods():
    return json.loads((HERE / "method-configs.json").read_text())["arms"]


class DirectLikelihood(old.DirectLikelihood):
    """Add the M24 likelihood without altering any frozen control implementation."""

    epoch_nodes_s = (-0.5, 0.0, 0.5)

    def association_problem(self, theta, arm):
        if arm != "M24":
            return super().association_problem(theta, arm)
        theta = np.asarray(theta, dtype=float)
        problems = []
        for epoch_s in self.epoch_nodes_s:
            shifted = theta.copy()
            shifted[2] += epoch_s
            problems.append(super().association_problem(shifted, "M2"))
        backgrounds = np.stack([item.background_log_likelihood for item in problems])
        if not np.allclose(backgrounds, backgrounds[0], rtol=0.0, atol=1e-12):
            raise RuntimeError("M2 background changed under satellite-only epoch quadrature")
        signal = logsumexp(
            np.stack([item.signal_log_likelihood for item in problems]), axis=0
        ) - math.log(len(problems))
        return old.AssociationProblem(signal, backgrounds[0], problems[0].candidate_labels)


def run_model(unit, arm, evidence_root):
    """Run one arm with the frozen search, evidence, prior, and qualification rules."""
    begun = time.monotonic()
    methods = load_methods()
    if arm not in methods:
        raise ValueError(f"unknown confirmation arm {arm}")
    evidence_root = Path(evidence_root)
    evidence_path = evidence_root / f"{unit}.json"
    orbit_path = evidence_root / f"{unit}-orbits.json"
    evidence = json.loads(evidence_path.read_text())
    orbit_meta = json.loads(orbit_path.read_text())
    source_path = Path(evidence["source"]["path"])
    source = json.loads(source_path.read_text())
    bank_path = Path(orbit_meta["state_file"])
    if (
        not orbit_meta["tle"]["causal"]
        or orbit_meta["session_id"] != evidence["session_id"]
        or old.digest(source_path) != evidence["source"]["sha256"]
        or old.digest(bank_path) != orbit_meta["state_sha256"]
    ):
        raise ValueError("causal input binding failure")
    with np.load(bank_path, allow_pickle=False) as data:
        bank = old.OrbitBank(
            tuple(map(int, data["satellite_ids"])), data["knot_times_s"],
            data["positions_ecef_km"], data["velocities_ecef_km_s"],
        )
    config = old.PhysicsConfig(
        prior_center_lat_deg=old.CENTER_LAT,
        prior_center_lon_deg=old.CENTER_LON,
        support_radius_km=old.RADIUS_KM,
    )
    union = old.geometric_candidate_union(bank, config)
    wanted = set(union.norad_ids)
    indices = np.array([i for i, value in enumerate(bank.norad_ids) if value in wanted])
    bank = old.OrbitBank(
        tuple(bank.norad_ids[i] for i in indices), bank.times_s,
        bank.positions_ecef_km[indices], bank.velocities_ecef_km_s[indices],
    )
    tracks, exclusions = old.independent_tracks(evidence)
    likelihood = DirectLikelihood(
        evidence, source, bank, tracks, old.training_masks(source)
    )
    bounds = [(-250, 250), (-250, 250), (-5, 5)]
    seeded = []
    for start in old._starts():
        point = np.asarray(start, dtype=float)
        simplex = np.tile(point, (4, 1))
        for axis, step in enumerate((12.0, 12.0, 0.5)):
            simplex[axis + 1, axis] += step
        value = likelihood.score_position(point, arm)["negative_log_posterior"]
        seeded.append((value, point, simplex))
    results = [
        minimize(
            lambda point: likelihood.score_position(point, arm)["negative_log_posterior"],
            point,
            method="Nelder-Mead",
            bounds=bounds,
            options={
                "initial_simplex": simplex,
                "maxiter": 60,
                "xatol": 0.5,
                "fatol": 0.5,
            },
        )
        for _, point, simplex in sorted(seeded, key=lambda row: row[0])[:2]
    ]
    result = min(results, key=lambda item: item.fun)
    point = {
        "east_km": float(result.x[0]),
        "north_km": float(result.x[1]),
        "tau_s": float(result.x[2]),
    }
    qualified = bool(
        result.success
        and np.isfinite(result.fun)
        and np.all(np.isfinite(result.x))
        and math.hypot(result.x[0], result.x[1]) <= old.RADIUS_KM
    )
    receipt = {
        "schema": "covariance-epoch-confirmation-prediction/v1",
        "unit_id": unit,
        "arm": arm,
        "method": methods[arm],
        "status": "completed" if qualified else "optimizer_unqualified",
        "qualified": qualified,
        "reference_coordinate_accessed": False,
        "prior": {
            "center": [old.CENTER_LAT, old.CENTER_LON],
            "radius_km": old.RADIUS_KM,
            "density": "exact uniform disk",
        },
        "inputs": {
            str(path): old.digest(path)
            for path in (evidence_path, orbit_path, source_path, bank_path)
        },
        "objective": float(result.fun),
        "optimizer": {
            "diagnostic_converged": bool(result.success),
            "message": str(result.message),
            "nfev": int(result.nfev),
            "coarse_start_count": len(seeded),
            "refinement_count": 2,
        },
        "candidate_count": len(bank.norad_ids),
        "retained_tracks": len(likelihood.rows),
        "excluded_tracks": exclusions,
        "wall_seconds": time.monotonic() - begun,
    }
    if qualified:
        receipt["point_estimate"] = point
        receipt["point_latlon_deg"] = old.en_latlon(point["east_km"], point["north_km"])
    else:
        receipt["diagnostic_unqualified_point"] = point
    return receipt
