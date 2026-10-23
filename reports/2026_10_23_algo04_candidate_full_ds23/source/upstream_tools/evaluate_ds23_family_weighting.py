"""Frozen, GPS-blind family-weighting rules on the original 20-scan DS23 sample."""

import argparse
import copy
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import candidate_profile, competitor_confidence, refit
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import OUT as SOURCE, ROOT, final_scan, read, sha, write

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

OUT=ROOT/"reports/2026_10_18_ds23_family_weighting_active_support"
METHODS=("cross_rx_support","family_cap50","cross_rx_cap100")
ARMS=("c0","fitted_c")


def family_weights(rows, members, tracks, confidence, method, active_counts=None):
    active_counts=(np.array([len(tracks[i]["times"]) for i in members]) if active_counts is None
                   else np.asarray(active_counts))
    if len(active_counts)!=len(rows) or np.any(active_counts<0):
        raise ValueError("one nonnegative retained count per original fragment required")
    owners={j:{(tracks[i]["receiver"],tracks[i]["channel"])
               for r,i,n in zip(rows,members,active_counts,strict=True) if r["candidate_index"]==j and n>0}
            for j in {r["candidate_index"] for r in rows}}
    counts={j:sum(n for r,n in zip(rows,active_counts,strict=True)
                  if r["candidate_index"]==j) for j in owners}
    values=[]
    for r,c in zip(rows,confidence,strict=True):
        j=r["candidate_index"]
        cross=len({rx for rx,ch in owners[j]})>=2
        replicated=len(owners[j])>=2 and c>=.95
        support=1. if cross else (.6 if replicated else .2)
        if method=="cross_rx_support":value=support
        elif method=="family_cap50":value=min(1.,50/max(counts[j],1))
        elif method=="cross_rx_cap100":value=support*min(1.,100/max(counts[j],1))
        else:raise ValueError("unknown frozen method")
        values.append(value)
    return np.array(values),owners,counts


def confidence_for(scan,node,keep,baseline):
    saved=baseline["arms"]["c0"]["record"]
    p=problem(scan,node,"c0",keep,np.asarray(saved["phase_reference"]))
    point=np.asarray(saved["endpoint_east_north_km"])
    state=p.state(point)
    widths,_=phase_widths(scan,list(range(len(scan.norads))))
    weights=[]
    anchors=[point]+[np.clip(point+d,-12.5,12.5) for d in
            (np.array([2,0]),np.array([-2,0]),np.array([0,2]),np.array([0,-2]))]
    for anchor in anchors:
        f,e,d=phase_linear_frequency(scan.geometry,*latlon(anchor))
        row_weights=[]
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            tr,ix=scan.tracks[i],scan.index[i]
            active=keep[sl]
            if not active.any():
                row_weights.append(0.)
                continue
            q=tr["rf_hz"]/11.5e9
            y=tr["values"]-scan.hardware(tr,state["beta"])-q*scan.rx_basis[i]@state["smooth"][tr["receiver"]-1]
            profile=candidate_profile(y[active],q*f[:,ix][:,active],q*d[:,ix][:,active],
                                      e[:,ix][:,active],scan.radio_sigma_hz,widths)
            row_weights.append(competitor_confidence(profile["cost"],row["candidate_index"])[0])
        weights.append(row_weights)
    return np.min(weights,axis=0)


def worker(case):
    path=OUT/case
    path.mkdir(parents=True,exist_ok=True)
    if (path/"result.json").exists():
        return read(path/"result.json")["receipt"]
    mark=time.monotonic()
    scan=final_scan(case)
    baseline=read(SOURCE/case/"result.json")
    node,original_keep=baseline["final_node"],np.asarray(baseline["final_mask"],bool)
    p=problem(scan,node,"c0",original_keep)
    confidence=confidence_for(scan,node,original_keep,baseline)
    results={}
    for method in METHODS:
        weights,owners,counts=family_weights(p.rows,p.members,scan.tracks,confidence,method,
                                             [original_keep[sl].sum() for sl in p.slices])
        keep=original_keep.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights) for arm in ARMS}
            failed={r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"] if not r["compatible"]}
            history.append(dict(epoch=epoch,input_points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:
                break
            for r,sl in zip(p.rows,p.slices,strict=True):
                if r["component"] in failed:
                    keep[sl]=False
            if not keep.any():
                break
        results[method]=dict(arms=pair,weights=weights,mask=keep,history=history,
            valid=not failed,owners={str(int(scan.norads[j])):sorted(v) for j,v in owners.items()},
            family_points={str(int(scan.norads[j])):v for j,v in counts.items()})
        print(case,method,int(keep.sum()),"valid",not failed,flush=True)
    receipt=dict(case=case,seconds=time.monotonic()-mark,source_sha256=sha(Path(__file__)),
                 baseline_sha256=sha(SOURCE/case/"result.json"),GPS_used=False)
    write(path/"result.json",dict(receipt=receipt,confidence=confidence,results=results,
        identities_aliases_noise_and_other_priors_preserved=True,matched_c_masks=True))
    return receipt


def run(workers):
    OUT.mkdir(parents=True,exist_ok=True)
    sample=read(SOURCE/"sample.json")
    cases=[r["dataset_label"] for r in sample["selected"]]
    write(OUT/"protocol.json",dict(cases=cases,methods=METHODS,workers=workers,
        selected_before_new_results=True,original_sample_sha256=sha(SOURCE/"sample.json"),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/probe_algo01_0217_improvements.py"),
        GPS_used_for_inference_or_rule_selection=False,development_scan="DS23-0217",
        target_mean_and_median_km=.5,causal_inputs_unchanged=True,baseline_results_unchanged=True,
        same_budget_per_c_arm=dict(phase_rounds=5,steps_per_round=48,max_gate_rounds=4),
        support_powers=[1.,.6,.2],family_caps=[50,100],hard_confidence_threshold=.95,
        excluded_points_do_not_create_confidence_or_independent_owner_votes=True,
        warning="20-scan benchmark includes development scan; not all 413 DS23 recordings"))
    receipts=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(worker,case):case for case in cases}
        for future in as_completed(futures):
            try:receipts.append(future.result())
            except Exception as error:
                receipts.append(dict(case=futures[future],status="failed",reason=repr(error)))
            write(OUT/"execution.json",receipts)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,default=2)
    args=parser.parse_args();run(args.workers)
