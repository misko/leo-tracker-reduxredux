"""Bounded completed-track replay; no evaluator or reference-coordinate input."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np

from leo.analysis.gaussian_sum_location import FilterConfig, update_filter
from physics import (
    OrbitBank, StateLayout, TrackObservations,
    build_physics_factor, geometric_candidate_union,
)
from prior import build_uniform_prior, make_config, prior_description

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE_ROOT = Path("/home/mouse9911/.cache/leo/research/gaussian_sum_64_scan/states/v3")


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, document):
    with Path(path).open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")


def location_components(state):
    return [{"weight": c.weight, "mean": c.mean[:6].tolist(),
             "covariance": c.covariance[:6, :6].tolist(),
             "identity_history": list(c.identity_history)} for c in state.components]


def independent_tracks(evidence):
    """Fixed conservative exclusion, independent of measured values or location."""
    retained, excluded, consumed = [], [], set()
    for row in sorted(evidence["tracks"], key=lambda r: (
        r["support_end_utc_ns"], r["support_start_utc_ns"], r["track_id"]
    )):
        ids = set(row["physical_observation_ids"])
        conflicts = sorted(ids & consumed)
        if len(row["measured_hz"]) < 3 or conflicts:
            excluded.append({"track_id": row["track_id"],
                             "reason": "same_receiver_source_overlap" if conflicts else "too_short",
                             "conflicting_ids": conflicts})
        else:
            retained.append(row)
            consumed.update(ids)
    return retained, excluded


def support_failures(state, config):
    """Check declared five-sigma regional support, not just component centers."""
    failures = set()
    for component in state.components:
        horizontal_radius = 5 * np.sqrt(np.linalg.eigvalsh(component.covariance[:2, :2])[-1])
        if np.linalg.norm(component.mean[:2]) + horizontal_radius > config.support_radius_km:
            failures.add("position_support_boundary")
        if abs(component.mean[2]) + 5 * np.sqrt(component.covariance[2, 2]) > config.height_support_km:
            failures.add("height_support_boundary")
        if np.linalg.norm(component.mean[:2]) > 250.0:
            failures.add("uniform_region_center_boundary")
    return sorted(failures)


def initial_state_summary(state):
    means = np.stack([component.mean for component in state.components])
    return {
        "component_count": len(state.components),
        "weight_sum": sum(component.weight for component in state.components),
        "histories_empty": all(not component.identity_history for component in state.components),
        "consumed_observations": len(state.consumed_observation_ids),
        "state_dimension": means.shape[1],
        "max_abs_tau_s": float(np.max(np.abs(means[:, 3]))),
        "max_abs_rx_drift_hz_s": float(np.max(np.abs(means[:, 4:6]))),
        "max_abs_satellite_epoch_s": float(np.max(np.abs(means[:, 6:]), initial=0.0)),
    }


def run(unit, arm, prior_name, folder):
    started = time.monotonic()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{unit}-{prior_name}-{arm}.json"
    state_path = STATE_ROOT / folder.name / output.with_suffix(".state.npz").name
    if output.exists() or output.with_suffix(".seal.json").exists() or state_path.exists():
        raise FileExistsError("preserve previous prediction and seal")
    evidence_path = HERE / "evidence" / f"{unit}.json"
    orbit_meta_path = HERE / "evidence" / f"{unit}-orbits.json"
    evidence = json.loads(evidence_path.read_text())
    orbit_meta = json.loads(orbit_meta_path.read_text())
    source_path = Path(evidence["source"]["path"])
    if digest(source_path) != evidence["source"]["sha256"]:
        raise ValueError("source observation digest mismatch")
    if orbit_meta["observation_sha256"] != evidence["source"]["sha256"]:
        raise ValueError("orbit bank is not bound to these observations")
    if orbit_meta["session_id"] != evidence["session_id"] or not orbit_meta["tle"]["causal"]:
        raise ValueError("orbit identity or causality failure")
    source = json.loads(source_path.read_text())
    bank_path = Path(orbit_meta["state_file"])
    if digest(bank_path) != orbit_meta["state_sha256"]:
        raise ValueError("orbit state digest mismatch")
    if prior_name != "sacramento_uniform":
        raise ValueError("this panel requires the frozen Sacramento uniform-disk approximation")
    config = make_config()
    spatial_prior = prior_description()
    filter_config = FilterConfig(max_components=32, min_weight=1e-12,
                                 greedy=arm == "greedy", max_child_work=65536)
    with np.load(bank_path, allow_pickle=False) as data:
        bank = OrbitBank(tuple(map(int, data["satellite_ids"])), data["knot_times_s"],
                         data["positions_ecef_km"], data["velocities_ecef_km_s"])
    union = geometric_candidate_union(bank, config)
    selected_ids = set(union.norad_ids)
    indices = np.array([i for i, identifier in enumerate(bank.norad_ids) if identifier in selected_ids])
    if not indices.size:
        raise ValueError("empty response-free geometric union")
    bank = OrbitBank(tuple(bank.norad_ids[i] for i in indices), bank.times_s,
                     bank.positions_ecef_km[indices], bank.velocities_ecef_km_s[indices])
    layout = StateLayout(bank.norad_ids)
    state = build_uniform_prior(layout)
    tracks, exclusions = independent_tracks(evidence)
    config_doc = {"physics": asdict(config), "filter": asdict(filter_config), "prior": prior_name,
                  "spatial_prior": spatial_prior}
    code_paths = [Path(__file__), HERE / "physics.py", HERE / "PROTOCOL.md", HERE / "AMENDMENTS.md",
                  HERE / "prior.py", HERE / "prior-audit.json", HERE / "pipeline-prior-audit.json",
                  HERE / "ENGINEERING.md",
                  ROOT / "src/leo/analysis/gaussian_sum_location.py"]
    receipt = {
        "schema": "gaussian-sum-single-scan-prediction/v1", "dataset": unit.split("-")[0],
        "unit_id": unit, "session_id": evidence["session_id"], "arm": arm,
        "prior_name": prior_name, "status": "running",
        "flags": list(union.flags) + ["gaussian_approximation_to_uniform_disk", "unbounded_gaussian_tail_leakage"],
        "config": config_doc,
        "runtime": {"python": sys.version, "numpy": np.__version__},
        "config_sha256": "sha256:" + hashlib.sha256(json.dumps(config_doc, sort_keys=True).encode()).hexdigest(),
        "source_sha256": {str(p): digest(p) for p in code_paths},
        "inputs": {str(p): digest(p) for p in [evidence_path, orbit_meta_path, bank_path]},
        "candidate_count": len(bank.norad_ids), "state_dimension": layout.dimension,
        "candidate_union": asdict(union), "catalogue_gap": orbit_meta.get("catalogue_gap", orbit_meta["propagation_rejected_count"] > 0),
        "selection": {"all_tracks": len(evidence["tracks"]), "retained_tracks": len(tracks), "exclusions": exclusions},
        "initial_components": location_components(state), "checkpoints": [],
        "initial_state_summary": initial_state_summary(state),
        "prior_point_estimate": {"latitude_deg": config.prior_center_lat_deg,
                                 "longitude_deg": config.prior_center_lon_deg,
                                 "rule": "center_of_intended_uniform_disk"},
        "replay_semantics": evidence["replay_semantics"], "gate_failures": [],
    }
    try:
        if arm != "prior_only":
            for index, track in enumerate(tracks):
                if time.monotonic() - started > 85:
                    receipt["gate_failures"].append("internal_wall_budget")
                    receipt["status"] = "budget_reached"
                    break
                times = (np.asarray(track["times_utc_ns"], dtype=np.int64) - source["start_utc_ns"]) / 1e9
                track_obs = TrackObservations(tuple(track["physical_observation_ids"]), times,
                    np.asarray(track["measured_hz"]), np.full(len(times), track["receiver_id"], dtype=int),
                    rf_hz=track["rf_hz"])
                physics = build_physics_factor(track_obs, bank, layout, config)
                result = update_filter(state, physics.factor, filter_config)
                state = result.state
                if arm == "gaussian_sum" and result.discarded_pre_normalization_mass > .01:
                    receipt["gate_failures"].append("posterior_mass_pruned_above_1_percent")
                receipt["gate_failures"].extend(support_failures(state, config))
                if "ineligible_positive_prior_mass" in result.flags:
                    receipt["gate_failures"].append("source_prior_mass_missing")
                receipt["checkpoints"].append({
                    "factor": index, "track_id": track["track_id"],
                    "consumed_samples": len(state.consumed_observation_ids),
                    "elapsed_support_s": float(times[-1]),
                    "predictive_log_density": result.predictive_log_density,
                    "background_probability": result.background_probability,
                    "retained_mass": result.retained_pre_normalization_mass,
                    "top_associations": sorted(result.association_probabilities.items(), key=lambda p: -p[1])[:10],
                    "flags": list(result.flags) + list(physics.flags),
                    "components": location_components(state),
                    "wall_seconds": time.monotonic() - started,
                })
                # Save completed-prefix evidence even if an external wall limit fires later.
                (output.with_suffix(".progress.json")).write_text(json.dumps(receipt, allow_nan=False))
                if receipt["gate_failures"]:
                    receipt["status"] = "gate_failed"
                    break
            else:
                receipt["status"] = "complete"
        else:
            receipt["status"] = "complete"
    except Exception as error:
        receipt["status"] = "error"
        receipt["exception"] = {"type": type(error).__name__, "message": str(error)}
    receipt["components"] = location_components(state)
    receipt["gate_failures"] = sorted(set(receipt["gate_failures"]))
    receipt["wall_seconds"] = time.monotonic() - started
    receipt["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    state_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(state_path, weights=np.array([c.weight for c in state.components]),
             means=np.stack([c.mean for c in state.components]),
             covariances=np.stack([c.covariance for c in state.components]),
             satellite_ids=np.array(layout.norad_ids))
    receipt["state_artifact"] = {"path": str(state_path), "sha256": digest(state_path)}
    write_new(output, receipt)
    write_new(output.with_suffix(".seal.json"), {"prediction_sha256": digest(output)})
    print(json.dumps({"path": str(output), "status": receipt["status"],
                      "candidates": len(bank.norad_ids), "factors": len(receipt["checkpoints"]),
                      "seconds": receipt["wall_seconds"], "gate_failures": receipt["gate_failures"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unit")
    parser.add_argument("arm", choices=("gaussian_sum", "greedy", "prior_only"))
    parser.add_argument("--prior", choices=("sacramento_uniform",), default="sacramento_uniform")
    parser.add_argument("--output", type=Path, default=HERE / "runs")
    args = parser.parse_args()
    # Numerical libraries are imported before the cap; RLIMIT_AS includes their maps.
    resource.setrlimit(resource.RLIMIT_AS, (6 * 1024**3, 6 * 1024**3))
    run(args.unit, args.arm, args.prior, args.output)
