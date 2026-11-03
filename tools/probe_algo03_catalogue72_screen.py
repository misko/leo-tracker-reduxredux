"""Screen added causal candidates on unchanged GLRT curves and calibration.

This proposal diagnostic omits calibration covariance and physical orbit modes.
It is not an association or position result. Both c arms must independently
favor the same added candidate before a full physical refit is justified.
"""

import argparse
from pathlib import Path
import numpy as np
from algo02_scan import bind_run_directory,load_scan
from ds23_family_screen import screen_family
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from prepare_algo03_catalogue72 import OUT,SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD


def competitive(left,right,old_count,total):
    if not left["candidates"] or not right["candidates"]:return False
    a,b=left["candidates"][0],right["candidates"][0]
    return bool(a["candidate_index"]>=old_count and a["candidate_index"]==b["candidate_index"] and
        a["alias"]==b["alias"] and all(v["noise_screen_pass"] and v["RMS_hz"]<=450 and
        abs(v["bias_hz"])<=3000 and abs(v["phase_s"])<=15 for v in (a,b)) and
        all(r["gap_to_second"] is not None and r["gap_to_second"]>2*np.log(total) for r in (left,right)))


def link_inputs(case):
    directory=OUT/case
    for name in ("tracks.json","observations.json","tracking.json","radio_noise.json","result.json","algo02_result.json"):
        path=directory/name
        if not path.exists():path.symlink_to(SOURCE/case/name)
    prior=OUT/"causal_prior"/case;prior.mkdir(parents=True,exist_ok=True)
    for name in ("previous.tle","previous_receipt.json","receipt.json"):
        path=prior/name
        if not path.exists():path.symlink_to(directory/name)


def run(case):
    directory=OUT/case;output=directory/"screen.json"
    if output.exists():raise FileExistsError("preserve scientific screen")
    extension=read(directory/"extension_receipt.json");old_count=extension["original_candidates"]
    old=read(SOURCE/case/"algo02_result.json")
    if not extension["added_candidates"]:
        write(output,dict(case=case,added_candidates=[],rows=[],no_catalogue_change=True,
            no_GPS_or_position_inference_performed=True,extension_sha256=sha(directory/"extension_receipt.json")))
        return
    link_inputs(case);bind_run_directory(OUT);scan=load_scan(OUT,case)
    initial=read(SOURCE/case/"result.json");node=initial["final_node"];keep=np.asarray(old["mask"],bool)
    p=problem(scan,node,"c0",keep);model=old["hyperparameters_from_pre_RF_TLE_only"]
    widths,receipt=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipt,model["shrinkage"]);widths=widths*model["multiplier"]
    active={r["component"]:np.flatnonzero(keep[sl]) for r,sl in zip(p.rows,p.slices,strict=True)}
    occupied_linear={o for e in old["linear_entries"] for o in e["observation_ids"]} if old["linear_paired_valid"] else set()
    rows=[]
    for i in scan.curved:
        t=scan.tracks[i];use=active.get(t["key"],np.array([],dtype=int));was_active=len(use)>0
        if not was_active:
            if occupied_linear.intersection(t["observation_ids"]):continue
            use=np.arange(len(t["times"]))
        if len(use)<6:continue
        rows.append(dict(track_index=i,component=t["key"],points=len(use),active_incumbent_curve=was_active,
            observation_indices=use,arms={}))
    for arm in ("c0","fitted_c"):
        saved=old["policy_arms"][arm];x=np.asarray(saved["endpoint_east_north_km"]);state=saved["state"]
        f,e,d=phase_linear_frequency(scan.geometry,*latlon(x))
        for row in rows:
            i=row["track_index"];t=scan.tracks[i];use=row["observation_indices"];ix=scan.index[i][use];q=t["rf_hz"]/11.5e9
            y=t["values"]-scan.hardware(t,np.asarray(state["beta"]))
            y-=q*scan.rx_basis[i]@np.asarray(state["smooth"])[t["receiver"]-1];y=y[use]
            meta=scan.fixed_window_noise
            noise=np.array([meta["per_observation_noise_sigma_hz"][t["observation_ids"][k]]
                if meta["extra_parameter_BIC_gain"]>0 else scan.radio_sigma_hz for k in use])
            predicted=q*(f[:,ix]+d[:,ix]*means[:,None]);derivative=q*d[:,ix]
            screen=screen_family([dict(observed=y,predicted=predicted,derivative=derivative,
                sigma=noise,power=1.,visible=e[:,ix].min(axis=1)>=0.)],widths,bias_sigma_hz=300.)
            ordered=[int(j) for j in np.argsort(screen["cost"]) if np.isfinite(screen["cost"][j])][:3]
            candidates=[]
            for j in ordered:
                phase=float(screen["phase_correction_s"][j]);bias=float(screen["bias_hz"][0][j]);alias=int(screen["aliases"][0][j])
                residual=y+alias*PERIOD-predicted[j]-derivative[j]*phase-bias
                diagnostics=batch_noise_screen(residual[None],t["times"][use])
                candidates.append(dict(candidate_index=j,norad=int(scan.norads[j]),added_candidate=j>=old_count,
                    cost=float(screen["cost"][j]),phase_s=float(phase+means[j]),bias_hz=bias,alias=alias,
                    RMS_hz=float(np.sqrt(np.mean(residual**2))),noise_screen_pass=bool(diagnostics["noise_screen_pass"][0])))
            finite_new=[float(v) for v in screen["cost"][old_count:] if np.isfinite(v)]
            finite_old=[float(v) for v in screen["cost"][:old_count] if np.isfinite(v)]
            row["arms"][arm]=dict(candidates=candidates,
                gap_to_second=candidates[1]["cost"]-candidates[0]["cost"] if len(candidates)>1 else None,
                best_added_cost=min(finite_new) if finite_new else None,best_original_cost=min(finite_old) if finite_old else None)
    for row in rows:
        row["competitive_added_candidate_in_both_c_arms"]=competitive(row["arms"]["c0"],row["arms"]["fitted_c"],old_count,len(scan.norads))
    write(output,dict(case=case,added_candidates=extension["added_candidates"],rows=rows,
        no_GPS_or_post_scan_TLE_used=True,no_points_associated_and_no_position_updated=True,
        original_calibration_and_position_are_RF_only=True,screen_is_approximate_proposal_only=True,
        phase_prior_hyperparameters_from_original_causal_history_preserved=True,
        source_sha256=sha(Path(__file__)),extension_sha256=sha(directory/"extension_receipt.json"),
        incumbent_sha256=sha(SOURCE/case/"algo02_result.json")))
    print(case,"added",len(extension["added_candidates"]),"curves",len(rows),"competitive",sum(r["competitive_added_candidate_in_both_c_arms"] for r in rows),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
