"""Apply unchanged ALGO02 gates after a fixed-population nomination contest.

The contest chooses by normalized c0 RF loss before exclusions. The candidate
must beat the incumbent on exactly the same observed population and weights.
No GPS enters the contest or the downstream paired policy.
"""

import argparse
from pathlib import Path

import numpy as np
from algo02_scan import bind_run_directory,history_fit,load_scan,pair_passes,paired_policy
from audit_ds23_algo01_coverage import retained_metrics
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import refit as linear_refit,select_entries
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_independent_discovery"


def nomination_wins(old_loss,new_loss,old_points,new_points,trials):
    if old_points!=new_points or old_points<=0 or trials<1:
        raise ValueError("a nomination contest requires the same nonempty observed population")
    if not np.isfinite([old_loss,new_loss]).all():
        return False
    return old_loss-new_loss>2*np.log(trials+1)


def owned(pair,entries):
    ids={o for t in pair["c0"]["gates"]["tracks"] if t["compatible"] for o in t["observation_ids"]}
    ids.update(o for e in entries for o in e["observation_ids"])
    return ids


def run(run_dir,case):
    directory=OUT/case;output=directory/"rescue.json"
    if output.exists():
        raise FileExistsError("preserve scientific rescue")
    bind_run_directory(run_dir);scan=load_scan(run_dir,case)
    old_path=run_dir/case/"algo02_result.json";old=read(old_path)
    screens=[read(p) for p in directory.glob("start_*_screen.json")]
    if len(screens)!=13:
        raise ValueError("all thirteen planned discovery starts must finish")
    finalists=sorted(screens,key=lambda r:r["arms"]["c0"]["negative_twice_elbo"])[:2]
    fits=[read(directory/f"start_{r['start_index']:02d}_fit.json") for r in finalists]
    chosen=min(fits,key=lambda r:r["arms"]["c0"]["negative_twice_elbo"])
    null_path=directory/"start_00_incumbent.json"
    if null_path.exists():
        null=read(null_path)
        if null["incumbent_sha256"]!=sha(old_path):
            raise ValueError("full-original-population incumbent replay belongs to another input")
        incumbent=null["arms"]["c0"]
    else:
        null_path=ROOT/"reports/2026_10_19_algo03_phase_seed"/(case+".json")
        null=read(null_path)
        if null["protocol"]["mask_sha256"]!=sha(old_path):
            raise ValueError("full-original-population incumbent replay belongs to another input")
        incumbent=null["trials"][0]["arms"]["c0"]
    candidate=chosen["arms"]["c0"]
    wins=nomination_wins(incumbent["negative_twice_elbo"],candidate["negative_twice_elbo"],
                         incumbent["active_points"],candidate["active_points"],len(screens))
    if not wins:
        write(output,dict(case=case,nomination_wins=False,policy_arms=old["policy_arms"],
            incumbent_arms=old["policy_arms"],
            full_original_population_c0_loss_before=incumbent["negative_twice_elbo"],
            full_original_population_c0_loss_after=candidate["negative_twice_elbo"],
            source_sha256=sha(Path(__file__)),incumbent_sha256=sha(old_path),
            full_incumbent_replay_sha256=sha(null_path)))
        return
    node=chosen["node"];keep0=np.array(chosen["mask"],bool);powers=np.array(chosen["powers"])
    model=old["hyperparameters_from_pre_RF_TLE_only"]
    p=problem(scan,node,"c0",keep0);_,receipt=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipt,model["shrinkage"])
    curved,keep,history=history_fit(scan,node,keep0,powers,means,model)
    cv=curved is not None and keep.any() and pair_passes(curved)
    entries=[];linear={};lv=False;policy=old["policy_arms"]
    if cv:
        saved=curved["c0"]
        p=make_problem(scan,node,keep,"c0",np.array(saved["phase_reference"]),powers,means,
                       model["multiplier"],model["nu"])
        x=np.array(saved["endpoint_east_north_km"])
        entries=select_entries(p,x,retained_metrics(p,x))
        linear={a:linear_refit(scan,node,keep,powers,means,model,a,entries) for a in ("c0","fitted_c")}
        policy,lv=paired_policy(curved,linear)
    old_ids=owned(old["policy_arms"],old["linear_entries"] if old["linear_paired_valid"] else [])
    new_ids=owned(policy,entries if lv else []) if cv else old_ids
    write(output,dict(case=case,nomination_wins=True,chosen_start_index=chosen["start_index"],
        full_original_population_c0_loss_before=incumbent["negative_twice_elbo"],
        full_original_population_c0_loss_after=candidate["negative_twice_elbo"],
        same_original_observation_population_and_weights_in_contest=True,
        search_penalty=2*np.log(len(screens)+1),curved_paired_valid=bool(cv),linear_paired_valid=bool(lv),
        curved_arms=curved,linear_arms=linear,policy_arms=policy,incumbent_arms=old["policy_arms"],
        final_node=node,original_mask=keep0,mask=keep,powers=powers,gate_history=history,entries=entries,
        incumbent_associated_points=len(old_ids),rescue_associated_points=len(new_ids),
        common_associated_points=len(old_ids&new_ids),new_associated_points=len(new_ids-old_ids),
        no_longer_associated_points=len(old_ids-new_ids),
        original_causal_priors_physical_model_and_gate_thresholds_preserved=True,
        no_GPS_or_post_scan_TLE_used=True,no_linear_to_calibration_feedback=True,
        new_nomination_qualification_is_a_heuristic_contest_not_calibrated_posterior_probability=True,
        fixed_original_weights_is_a_mechanism_control_not_a_new_support_weighting_policy=True,
        source_sha256=sha(Path(__file__)),incumbent_sha256=sha(old_path),
        finalist_input_sha256=[sha(directory/f"start_{r['start_index']:02d}_fit.json") for r in finalists],
        full_incumbent_replay_sha256=sha(null_path)))
    print(case,"discovery rescue","C",cv,"L",lv,"points",len(old_ids),"to",len(new_ids),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--run-dir",type=Path,default=ROOT/"reports/2026_10_19_algo02_ds23_full")
    args=parser.parse_args();run(args.run_dir,args.case)
