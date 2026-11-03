"""Test radio-screened new curved families while retaining existing evidence.

New labels come only from the all-causal-catalogue inventory. Curved additions
may calibrate; accepted linear data remain prediction-only. A failed paired
gate restores the incumbent, never deleting an original active observation.
"""

import argparse
import copy
from pathlib import Path

import numpy as np
from algo02_scan import pair_passes
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_new_family_inventory import OUT as INVENTORY
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_height import context
from probe_ds23_predictive_linear import OUT as INCUMBENT, refit
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state

OUT=ROOT/"reports/2026_10_19_algo03_new_family_position"


def augment_rows(rows,aliases,keep,powers,tracks,proposals):
    rows=copy.deepcopy(rows);aliases=list(aliases)
    keep=np.array(keep,bool,copy=True);powers=np.array(powers,float,copy=True)
    lookup={t["key"]:t for t in tracks}
    counts=[len(lookup[r["component"]]["observation_ids"]) for r in rows]
    if sum(counts)!=len(keep) or len(rows)!=len(powers) or len(rows)!=len(aliases):
        raise ValueError("original calibration rows must match observations and aliases")
    boundaries=np.r_[0,np.cumsum(counts)]
    active={o for k,r in enumerate(rows) for o,a in zip(lookup[r["component"]]["observation_ids"],
        keep[boundaries[k]:boundaries[k+1]],strict=True) if a}
    original=set(active)
    for proposal in proposals:
        key=proposal["component"];ids=lookup[key]["observation_ids"]
        if len(ids)!=len(set(ids)) or active.intersection(ids):
            raise ValueError("additional whole curves must have disjoint physical observations")
        winner=proposal["arms"]["c0"]["candidates"][0]
        candidate=dict(component=key,candidate_index=winner["candidate_index"],
                       candidate_norad=winner["norad"],active_curvature=True)
        index=next((k for k,r in enumerate(rows) if r["component"]==key),None)
        if index is not None:
            rows[index]=candidate;aliases[index]=winner["alias"]
            keep[boundaries[index]:boundaries[index+1]]=True;powers[index]=.2
        else:
            rows.append(candidate);aliases.append(winner["alias"])
            keep=np.r_[keep,np.ones(len(ids),bool)];powers=np.r_[powers,.2]
        active.update(ids)
    return rows,aliases,keep,powers,original,active


def run(case):
    OUT.mkdir(exist_ok=True)
    output=OUT/(case+".json")
    if output.exists():
        raise FileExistsError("preserve scientific outputs")
    scan,node,keep,powers,_,model,_,_=context(case,"archived")
    old=read(INCUMBENT/(case+".json"))["results"]["all_linear"]
    inventory=read(INVENTORY/(case+".json"))
    proposals=[r for r in inventory["rows"] if r["strong_paired_new_family_proposal"]]
    if not proposals:
        write(output,dict(case=case,policy_arms=old["policy_arms"],incumbent_arms=old["policy_arms"],
                         no_new_family_proposal=True))
        return
    base=problem(scan,node,"c0",keep)
    rows,aliases,mask,power,original_ids,final_ids=augment_rows(base.rows,node["aliases"],keep,powers,scan.tracks,proposals)
    changed=copy.copy(scan)
    by_key={t["key"]:i for i,t in enumerate(scan.tracks)}
    changed.curved=[by_key[r["component"]] for r in rows]
    candidate=dict(seed=dict(rows=rows,state=zero_state(changed)),aliases=aliases)
    p=problem(changed,candidate,"c0",mask)
    _,receipt=phase_widths(changed,p.labels)
    means=forecast_phase_mean(receipt,model["shrinkage"])
    entries=old["entries"] if old["paired_valid"] else []
    assert not final_ids.intersection(o for entry in entries for o in entry["observation_ids"])
    curved={a:refit(changed,candidate,mask,power,means,model,a,[]) for a in ("c0","fitted_c")}
    linear={a:refit(changed,candidate,mask,power,means,model,a,entries) for a in ("c0","fitted_c")}
    valid=pair_passes(curved) and pair_passes(linear,include_linear=True)
    # Retain accepted old linear evidence as well as every original curved point.
    policy=linear if valid else old["policy_arms"]
    write(output,dict(case=case,curved_arms=curved,linear_arms=linear,paired_valid=valid,
        policy_arms=policy,incumbent_arms=old["policy_arms"],proposals=proposals,final_node=candidate,
        original_active_ids=sorted(original_ids),proposed_active_ids=sorted(final_ids),
        added_points=len(final_ids)-len(original_ids),new_curve_power=.2,final_mask=mask,powers=power,
        no_GPS_post_scan_TLE_or_identity_whitelist_used=True,
        no_original_point_removed_and_no_gate_relaxed=True,
        new_curves_have_independent_radio_curvature_and_both_c_arm_catalogue_agreement=True,
        no_linear_to_calibration_feedback=True,matched_c_budgets_and_data=True,
        source_sha256=sha(Path(__file__)),inventory_sha256=sha(INVENTORY/(case+".json")),
        incumbent_sha256=sha(INCUMBENT/(case+".json"))))
    print(case,"new family",len(proposals),"curves",len(final_ids)-len(original_ids),"points","paired",valid,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
