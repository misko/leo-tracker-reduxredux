"""Bounded blind replay with a larger temporary bank and moment-matched reduction."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import time

import numpy as np

from common import CACHE, HERE, ROOT, load_scan, seal, source_bindings, digest
from physics import build_physics_factor
from prior import build_uniform_prior, prior_description
from run import support_failures, location_components, initial_state_summary
from leo.analysis.gaussian_sum_location import FilterConfig, FilterState, update_filter
from leo.analysis.gaussian_mixture_reduction import (
    reduce_gaussian_mixture, projected_density_distortion,
)

POLICY = {"materialized_cap": 128, "retained_cap": 32, "max_child_work": 65536,
          "max_pair_evaluations": 40000, "distance_indices": list(range(6)),
          "maximum_discarded_mass": .01, "maximum_projected_merge_score": .1,
          "min_weight": 1e-12, "internal_wall_seconds": 85.}


def merge_update(state, factor, materialized_cap=128, retained_cap=32):
    updated = update_filter(state, factor, FilterConfig(
        max_components=materialized_cap, min_weight=POLICY["min_weight"],
        max_child_work=POLICY["max_child_work"]))
    reduced = reduce_gaussian_mixture(updated.state.components, retained_cap,
        distance_indices=POLICY["distance_indices"],
        max_pair_evaluations=POLICY["max_pair_evaluations"])
    distortion = projected_density_distortion(
        updated.state.components, reduced.components, POLICY["distance_indices"])
    state = FilterState(reduced.components, updated.state.consumed_observation_ids)
    return state, updated, reduced, distortion


def replay(unit, output, max_tracks=None):
    started = time.monotonic()
    output = Path(output)
    if output.exists() or output.with_suffix(".seal.json").exists():
        raise FileExistsError("preserve existing prediction")
    scan = load_scan(unit)
    state = build_uniform_prior(scan.layout)
    selected = scan.tracks if max_tracks is None else scan.tracks[:max_tracks]
    receipt = {"schema":"broad-prior-acquisition-prediction/v1", "unit_id":unit,
        "session_id":scan.session_id, "dataset":unit.split("-")[0],
        "arm":"merge128_to32", "status":"running", "inputs":scan.inputs,
        "source_sha256":source_bindings([Path(__file__),
            ROOT / "src/leo/analysis/gaussian_mixture_reduction.py"]),
        "config":{"physics":asdict(scan.config), "spatial_prior":prior_description(), "reduction":POLICY},
        "initial_state_summary":initial_state_summary(state),
        "planned_factors":len(scan.tracks), "requested_factors":len(selected),
        "exclusions":scan.exclusions, "candidate_count":len(scan.bank.norad_ids),
        "catalogue_gap":scan.catalogue_gap, "checkpoints":[], "gate_failures":[],
        "qualification":"same likelihood and shared nuisance priors as baseline; projected merge heuristic",
        "initial_components":location_components(state)}
    cumulative_score = 0.
    try:
        for index, (track_id, obs) in enumerate(selected):
            if time.monotonic() - started > POLICY["internal_wall_seconds"]:
                receipt["gate_failures"].append("internal_wall_budget")
                receipt["status"] = "budget_reached"
                break
            physics = build_physics_factor(obs, scan.bank, scan.layout, scan.config)
            state, update, reduction, distortion = merge_update(state, physics.factor)
            score = sum(r.score for r in reduction.merge_records)
            cumulative_score += score
            failures = support_failures(state, scan.config)
            if update.discarded_pre_normalization_mass > POLICY["maximum_discarded_mass"]:
                failures.append("posterior_mass_pruned_above_1_percent")
            if score > POLICY["maximum_projected_merge_score"]:
                failures.append("projected_merge_score_above_0_1_nat")
            checkpoint = {"index":index, "track_id":track_id,
                "observation_ids":list(physics.factor.observation_ids),
                "retained_mass_before_merging":update.retained_pre_normalization_mass,
                "discarded_mass_before_merging":update.discarded_pre_normalization_mass,
                "predictive_log_density":update.predictive_log_density,
                "background_probability":update.background_probability,
                "materialized_components":reduction.input_count,
                "retained_components":reduction.output_count,
                "pair_evaluations":reduction.pair_evaluations,
                "scoring_mode":reduction.scoring_mode,
                "full_joint_kl_bound":reduction.total_runnalls_upper_bound,
                "projected_merge_score":score, "cumulative_projected_score":cumulative_score,
                "projected_density_distortion":asdict(distortion),
                "gate_failures":failures, "seconds":time.monotonic()-started}
            receipt["checkpoints"].append(checkpoint)
            receipt["gate_failures"].extend(failures)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix(".progress.json").write_text(json.dumps(receipt, allow_nan=False))
            del update, reduction, distortion
            if failures:
                receipt["status"] = "gate_failed"
                break
        else:
            receipt["status"] = "complete" if len(selected) == len(scan.tracks) else "prefix_only"
    except Exception as error:
        receipt["status"] = "error"
        receipt["exception"] = {"type":type(error).__name__, "message":str(error)}
    receipt["components"] = location_components(state)
    receipt["consumed_observation_ids"] = list(state.consumed_observation_ids)
    receipt["gate_failures"] = sorted(set(receipt["gate_failures"]))
    receipt["native_pre_artifact_seconds"] = time.monotonic()-started
    state_path = CACHE / "states" / output.parent.name / (output.stem + ".npz")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        raise FileExistsError("preserve existing state artifact")
    np.savez_compressed(state_path, weights=np.array([c.weight for c in state.components]),
        means=np.stack([c.mean for c in state.components]),
        covariances=np.stack([c.covariance for c in state.components]),
        satellite_ids=np.array(scan.layout.norad_ids))
    receipt["state_artifact"] = {"path":str(state_path), "sha256":digest(state_path)}
    receipt["wall_seconds"] = time.monotonic()-started
    receipt["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    seal(output, receipt)
    print(json.dumps({"unit_id":unit,"status":receipt["status"],
        "factors":len(receipt["checkpoints"]),"gate_failures":receipt["gate_failures"],
        "seconds":receipt["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tracks", type=int)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (6*1024**3,6*1024**3))
    replay(args.unit, args.output, args.max_tracks)
