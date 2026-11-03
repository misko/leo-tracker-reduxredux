"""Matched position test of history-only, age-covered phase scales."""

import argparse
import time
from pathlib import Path
import numpy as np
from algo02_scan import pair_passes
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from learn_algo03_age_covered_phase_prior import OUT as PRIOR
from learn_ds23_phase_variance_law import phase_sigma
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import refit as curved_refit
from probe_ds23_predictive_linear import OUT as INCUMBENT,refit as linear_refit
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_age_covered_position"


def scale_multiplier(receipts,old_sigma,scale):
    sigma=np.array([phase_sigma(scale["floor_s"],scale["gain"],r["old_new_alignment_s"] or 0.,
        r["age_s"]+150.,r["previous_epoch_gap_s"] or 1.) for r in receipts])
    return sigma/old_sigma


def run(case,null=False):
    OUT.mkdir(exist_ok=True);path=OUT/(case+("_null" if null else "")+".json")
    if path.exists():raise FileExistsError("preserve scientific outputs")
    began=time.monotonic();prior=read(PRIOR/(case+".json"))
    source=read(INCUMBENT/(case+".json"));old=source["results"]["all_linear"]["policy_arms"]
    if not null and not prior["selection"]["qualified"]:
        write(path,dict(case=case,prior_qualified=False,policy_arms=old,no_inference_needed=True))
        return
    scan,node,keep,powers,means,model,_,_=context(case,"archived")
    base=problem(scan,node,"c0",keep);widths,receipts=phase_widths(scan,base.labels)
    model=dict(model)
    if not null:model["multiplier"]=scale_multiplier(receipts,widths,prior["selection"]["all_past_scale"])
    entries=source["results"]["all_linear"]["entries"]
    curved={a:curved_refit(scan,node,keep,a,powers,means,model["multiplier"],model["nu"])
            for a in ("c0","fitted_c")}
    linear={a:linear_refit(scan,node,keep,powers,means,model,a,entries) for a in ("c0","fitted_c")}
    cv=pair_passes(curved);lv=pair_passes(linear,include_linear=True)
    policy=linear if cv and lv else (curved if cv else old)
    write(path,dict(case=case,null_control=null,prior_qualified=True,
        curved_arms=curved,linear_arms=linear,curved_paired_valid=cv,linear_paired_valid=lv,
        policy_arms=policy,incumbent_arms=old,mask=keep,powers=powers,entries=entries,
        multiplier=model["multiplier"],phase_width_receipts=receipts,
        original_points_labels_aliases_and_other_priors_preserved=True,
        no_GPS_or_post_scan_TLE_used=True,no_linear_to_calibration_feedback=True,
        same_observations_c_priors_and_5x48_budgets=True,
        prior_sha256=sha(PRIOR/(case+".json")),incumbent_sha256=sha(INCUMBENT/(case+".json")),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_age_covered_phase_prior.py"),
        seconds=time.monotonic()-began))
    print(case,"age-covered scale","C",cv,"L",lv,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    parser.add_argument("--null-control",action="store_true");args=parser.parse_args()
    run(args.case,args.null_control)
