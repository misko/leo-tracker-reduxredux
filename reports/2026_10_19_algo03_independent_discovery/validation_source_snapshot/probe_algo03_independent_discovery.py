"""Independent regional RF discovery on a fixed original observation population.

The current observation weights are frozen to isolate nomination changes. This
is a mechanism experiment, not a new qualified weighting/association policy.
No branch wins by discarding measurements. GPS is absent from this module.
"""

import argparse
from pathlib import Path

import numpy as np
from algo02_scan import bind_run_directory, load_scan
from dsx01_radial_restarts import discover_at_start
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_joint_family_search import proposal_refit
from probe_ds23_learned_prior_restarts import STARTS, refit_start
from run_algo01_ds23_sample import ROOT, read, sha, write
from run_dsx01_clean_region import zero_state

OUT=ROOT/"reports/2026_10_19_algo03_independent_discovery"


def align_population(old_rows,new_rows,tracks,mask,powers):
    by_key={t["key"]:t for t in tracks}
    if {r["component"] for r in old_rows}!={r["component"] for r in new_rows}:
        raise ValueError("independent nomination must retain exactly the same curves")
    if len({r["component"] for r in new_rows})!=len(new_rows):
        raise ValueError("duplicate curve owner")
    counts=[len(by_key[r["component"]]["observation_ids"]) for r in old_rows]
    if sum(counts)!=len(mask) or len(old_rows)!=len(powers):
        raise ValueError("one original mask and power per physical curve required")
    boundaries=np.r_[0,np.cumsum(counts)]
    masks={r["component"]:np.asarray(mask[boundaries[k]:boundaries[k+1]],bool)
           for k,r in enumerate(old_rows)}
    weights={r["component"]:float(powers[k]) for k,r in enumerate(old_rows)}
    return (np.concatenate([masks[r["component"]] for r in new_rows]),
            np.array([weights[r["component"]] for r in new_rows]))


def run(run_dir,case,index,stage):
    OUT.mkdir(exist_ok=True)
    directory=OUT/case;directory.mkdir(exist_ok=True)
    output=directory/f"start_{index:02d}_{stage}.json"
    if output.exists():
        raise FileExistsError("preserve scientific outputs")
    bind_run_directory(run_dir)
    scan=load_scan(run_dir,case)
    initial=read(run_dir/case/"result.json")
    old=read(run_dir/case/"algo02_result.json")
    base=problem(scan,initial["final_node"],"c0",np.asarray(old["original_mask"],bool))
    if stage=="screen":
        discovery=discover_at_start(scan,scan.radio_sigma_hz,STARTS[index],budget=4)
        node=dict(seed=dict(rows=discovery["seed"]["rows"],state=zero_state(scan)),aliases=discovery["aliases"])
        keep,powers=align_population(base.rows,node["seed"]["rows"],scan.tracks,old["original_mask"],old["weights"])
    elif stage=="incumbent":
        node=initial["final_node"]
        keep=np.asarray(old["original_mask"],bool);powers=np.asarray(old["weights"])
        discovery=dict(original_nomination_control=True)
    else:
        saved=read(directory/f"start_{index:02d}_screen.json")
        node=saved["node"];discovery=saved["discovery"]
        keep=np.asarray(saved["mask"],bool);powers=np.asarray(saved["powers"])
    p=problem(scan,node,"c0",keep)
    _,receipts=phase_widths(scan,p.labels)
    model=old["hyperparameters_from_pre_RF_TLE_only"]
    means=forecast_phase_mean(receipts,model["shrinkage"])
    if stage=="screen":
        arms={"c0":proposal_refit(scan,node,keep,powers,means,model,2,12)}
    else:
        arms={a:refit_start(scan,node,keep,a,powers,means,model["multiplier"],model["nu"],[0.,0.])
              for a in ("c0","fitted_c")}
    write(output,dict(case=case,start_index=index,start=STARTS[index],stage=stage,node=node,
        discovery={k:v for k,v in discovery.items() if k not in ("seed","aliases")},mask=keep,powers=powers,
        arms=arms,active_points=int(keep.sum()),
        original_physical_observation_population_and_weights_preserved=True,
        original_causal_catalogue_and_physical_prior_scales_preserved=True,
        no_GPS_post_scan_TLE_or_stationary_history_position_used=True,
        no_gate_relaxation_or_original_point_removal=True,
        screen_budget=dict(rounds=2,steps=12,c_arm="c0"),full_budget=dict(rounds=5,steps=48,c_arms=2),
        not_a_qualified_new_position_policy=True,source_sha256=sha(Path(__file__)),
        incumbent_sha256=sha(run_dir/case/"algo02_result.json")))
    print(case,index,stage,"c0 ELBO",arms["c0"]["negative_twice_elbo"],
          "failed",sum(not t["compatible"] for t in arms["c0"]["gates"]["tracks"]),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--start-index",type=int,choices=range(len(STARTS)),required=True)
    parser.add_argument("--stage",choices=("screen","fit","incumbent"),default="screen")
    parser.add_argument("--run-dir",type=Path,default=ROOT/"reports/2026_10_19_algo02_ds23_full")
    args=parser.parse_args();run(args.run_dir,args.case,args.start_index,args.stage)
