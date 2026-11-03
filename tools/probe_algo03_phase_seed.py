"""Fixed-observation phase refits from independent RF-derived stage seeds.

This is a local mechanism experiment, not a change to frozen ALGO02. The
ALGO01 position is an inference result, never a GPS or stationary-site prior.
All branches see the identical original curved observations and causal priors.
"""

import argparse
from pathlib import Path

import numpy as np

from algo02_scan import bind_run_directory, load_scan
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_learned_prior_restarts import refit_start
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ROOT / "reports/2026_10_19_algo03_phase_seed"


def rf_seeds(initial_position):
    point = np.asarray(initial_position, float)
    if point.shape != (2,) or not np.isfinite(point).all() or np.any(abs(point)>12.5):
        raise ValueError("a finite regional RF-derived position is required")
    seeds = [np.zeros(2)]
    if np.linalg.norm(point)>1e-8:
        seeds.append(point.copy())
    return seeds


def run(run_dir, case):
    output=OUT/(case+".json")
    if output.exists():
        raise FileExistsError("preserve scientific results")
    OUT.mkdir(exist_ok=True)
    bind_run_directory(run_dir)
    scan=load_scan(run_dir,case)
    initial=read(run_dir/case/"result.json")
    incumbent=read(run_dir/case/"algo02_result.json")
    node=initial["final_node"]
    keep=np.asarray(incumbent["original_mask"],bool)
    powers=np.asarray(incumbent["weights"])
    model=incumbent["hyperparameters_from_pre_RF_TLE_only"]
    labels=sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    _,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,model["shrinkage"])
    initial_x=initial["arms"]["c0"]["record"]["endpoint_east_north_km"]
    seeds=rf_seeds(initial_x)
    protocol=dict(case=case,seeds=seeds,seed_source="regional origin and independent ALGO01 c0 RF endpoint",
        fixed_original_mask=keep,mask_sha256=sha(run_dir/case/"algo02_result.json"),
        no_GPS_or_future_RF_or_post_scan_TLE_used=True,
        paired_c_observations_masks_aliases_identities_priors_and_budgets=True,
        rounds_per_seed=5,steps_per_round=48,
        selection="lowest c0 normalized ELBO on identical original observations, before gate-based exclusion",
        no_gate_relaxation_or_point_removal_in_this_experiment=True,
        source_sha256=sha(Path(__file__)))
    write(OUT/(case+"_protocol.json"),protocol)
    trials=[]
    for seed in seeds:
        pair={a:refit_start(scan,node,keep,a,powers,means,model["multiplier"],model["nu"],seed)
              for a in ("c0","fitted_c")}
        trials.append(dict(seed=seed,arms=pair))
        write(OUT/(case+"_partial.json"),dict(protocol=protocol,trials=trials))
        print(case,"seed",seed.tolist(),"c0",pair["c0"]["negative_twice_elbo"],
              "failed",sum(not t["compatible"] for t in pair["c0"]["gates"]["tracks"]),flush=True)
    chosen=min(range(len(trials)),key=lambda k:trials[k]["arms"]["c0"]["negative_twice_elbo"])
    write(output,dict(protocol=protocol,trials=trials,chosen=chosen,
        incumbent_arms=incumbent["policy_arms"],
        not_a_qualified_position_policy=True))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--run-dir",type=Path,default=ROOT/"reports/2026_10_19_algo02_ds23_full")
    args=parser.parse_args()
    run(args.run_dir,args.case)
