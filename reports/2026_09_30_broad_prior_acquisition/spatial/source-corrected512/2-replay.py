"""Conditional broad-prior spatial-map replay; outputs are diagnostics, not fitted posteriors."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from math import log
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = REPORT.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPORT))
from leo.analysis.adaptive_location_map import (  # noqa: E402
    MapState, RefinementConfig, TrackFactor, uniform_disk_state, update_map,
)
from common import CACHE, load_scan, seal, source_bindings  # noqa: E402
from physics import build_physics_factor, gaussian_logpdf  # noqa: E402
from rf import VectorizedTrackLikelihood  # noqa: E402

FIXED_CONFIG = RefinementConfig(
    max_cells=128,
    quadrature_order=2,
    min_cell_mass=1e-6,
    min_log_likelihood_range=1.0,
    max_refinements_per_round=32,
    max_points_per_call=64,
)
DEVELOPMENT_CONFIG_512 = RefinementConfig(
    max_cells=512,
    quadrature_order=2,
    min_cell_mass=1e-6,
    min_log_likelihood_range=1.0,
    max_refinements_per_round=128,
    max_points_per_call=64,
)
QUADRATURE_LOG_EVIDENCE_TOLERANCE = 0.5


def nuisance_bank(name):
    if name == "fixed_zero":
        return np.zeros((1, 1)), ("tau_s",), np.ones(1)
    if name == "tau_gh3":
        return np.array([[-np.sqrt(3.)], [0.], [np.sqrt(3.)]]), ("tau_s",), np.array([1/6,2/3,1/6])
    raise ValueError(name)


def validate_against_frozen(scan, track_count=3):
    rng=np.random.default_rng(20260930)
    radius=250*np.sqrt(rng.random(5)); angle=2*np.pi*rng.random(5)
    points=np.column_stack((radius*np.sin(angle),radius*np.cos(angle)))
    maximum=0.0
    checked=[]
    for track_id,track in scan.tracks[:track_count]:
        port=VectorizedTrackLikelihood(track,scan.bank,scan.config)
        actual=port(points,np.zeros((1,1)))[:,0,:]
        frozen=build_physics_factor(track,scan.bank,scan.layout,scan.config).factor
        expected=np.empty_like(actual)
        for point_index,(east,north) in enumerate(points):
            state=np.zeros(scan.layout.dimension); state[:2]=east,north
            for branch,candidate in enumerate(frozen.candidates):
                prediction=candidate.predict(state)
                prior=candidate.prior(state) if callable(candidate.prior) else candidate.prior
                expected[point_index,branch]=(log(prior)+gaussian_logpdf(
                    frozen.observation-prediction.mean,prediction.covariance
                ) if prior else -np.inf)
            background=(frozen.background_prior(state) if callable(frozen.background_prior)
                        else frozen.background_prior)
            expected[point_index,-1]=log(background)+frozen.background_log_likelihood
        finite=np.isfinite(actual)&np.isfinite(expected)
        difference=float(np.max(np.abs(actual[finite]-expected[finite]))) if np.any(finite) else 0.
        if not np.array_equal(np.isfinite(actual),np.isfinite(expected)) or difference > 1e-6:
            raise ValueError(f"vectorized likelihood mismatch for {track_id}: {difference}")
        maximum=max(maximum,difference); checked.append(track_id)
    return {"tracks":checked,"points_per_track":5,"maximum_absolute_log_likelihood_difference":maximum,
            "tolerance":1e-6}


def run(unit, bank_name, track_limit, validate, profile="fixed128"):
    started=time.monotonic(); scan=load_scan(unit)
    map_config = FIXED_CONFIG if profile == "fixed128" else DEVELOPMENT_CONFIG_512
    hypotheses,labels,prior=nuisance_bank(bank_name)
    state=uniform_disk_state(scan.config.prior_center_lat_deg,scan.config.prior_center_lon_deg,250.,
                             hypotheses,labels,prior,radial_rings=4,angular_sectors=8)
    receipt={"schema":"adaptive-spatial-map-conditional/v1","unit_id":unit,
             "session_id":scan.session_id,"status":"running","nuisance_model":bank_name,
             "qualification":"conditional diagnostic; height, receiver drifts, and satellite epochs fixed zero",
             "profile":profile,"config":map_config.__dict__,
             "quadrature_log_evidence_tolerance":QUADRATURE_LOG_EVIDENCE_TOLERANCE,
             "inputs":scan.inputs,"source_sha256":source_bindings((HERE/"rf.py",HERE/"replay.py",
                 ROOT/"src/leo/analysis/adaptive_location_map.py")),"tracks":[]}
    if validate: receipt["vectorized_validation"]=validate_against_frozen(scan)
    unresolved=False
    for track_id,track in scan.tracks[:track_limit]:
        port=VectorizedTrackLikelihood(track,scan.bank,scan.config)
        port.deadline=started+85.
        factor=TrackFactor(port.observation_ids,port.branch_ids,port)
        before=state
        try:
            result=update_map(before,factor,map_config)
            audit_base=MapState(before.center_latitude_deg,before.center_longitude_deg,
                before.radius_km,before.nuisance_hypotheses,before.nuisance_labels,
                result.state.cells,before.consumed_observation_ids,before.factors)
            audit=update_map(audit_base,factor,RefinementConfig(max_cells=len(result.state.cells),quadrature_order=3,
                min_cell_mass=map_config.min_cell_mass,min_log_likelihood_range=map_config.min_log_likelihood_range,
                max_points_per_call=map_config.max_points_per_call))
        except TimeoutError:
            receipt["status"]="budget_reached"
            break
        quadrature_error=abs(result.log_evidence-audit.log_evidence)
        hit_bound=len(result.state.cells)==map_config.max_cells and (
            result.maximum_cell_log_likelihood_range >= map_config.min_log_likelihood_range)
        unresolved |= hit_bound or quadrature_error > QUADRATURE_LOG_EVIDENCE_TOLERANCE
        state=result.state
        receipt["tracks"].append({"track_id":track_id,"log_evidence":result.log_evidence,
            "quadrature_log_evidence_error":quadrature_error,"cells":len(state.cells),
            "refined_parents":result.refined_parent_count,"max_log_likelihood_range":result.maximum_cell_log_likelihood_range,
            "spatial_convergence_unresolved":hit_bound or quadrature_error>QUADRATURE_LOG_EVIDENCE_TOLERANCE,
            "top_branches":sorted(result.branch_probabilities.items(),key=lambda item:-item[1])[:10]})
        if time.monotonic()-started > 85: receipt["status"]="budget_reached"; break
    else:
        receipt["status"]="spatial_convergence_unresolved" if unresolved else "diagnostic_complete"
    receipt["cells"]=[{"radius_squared_min":c.radius_squared_min,"radius_squared_max":c.radius_squared_max,
        "angle_min_rad":c.angle_min_rad,"angle_max_rad":c.angle_max_rad,"joint_mass":c.joint_mass.tolist(),
        "depth":c.depth} for c in state.cells]
    receipt["consumed_tracks"]=len(receipt["tracks"]); receipt["wall_seconds"]=time.monotonic()-started
    output=CACHE/"spatial"/f"{unit}-{bank_name}-{profile}-tracks{track_limit}.json"
    seal(output,receipt); return output,receipt


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("unit")
    parser.add_argument("--nuisance",choices=("fixed_zero","tau_gh3"),default="fixed_zero")
    parser.add_argument("--tracks",type=int,default=8); parser.add_argument("--validate",action="store_true")
    parser.add_argument("--profile",choices=("fixed128","development512"),default="fixed128")
    args=parser.parse_args()
    path,document=run(args.unit,args.nuisance,args.tracks,args.validate,args.profile)
    print(json.dumps({"path":str(path),"status":document["status"],"tracks":document["consumed_tracks"],
                      "seconds":document["wall_seconds"]}))
