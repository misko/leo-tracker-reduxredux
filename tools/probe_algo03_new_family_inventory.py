"""All-causal-catalogue inventory of unused curved graph observations.

Proposal screening only: radio calibration is frozen and its uncertainty and
physical orbit modes are omitted. No screened row is claimed as an association
or used for localization. Unlike ALGO02 extensions, this permits new families.
"""

import argparse
from pathlib import Path

import numpy as np

from ds23_family_screen import screen_family
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_height import context
from probe_ds23_predictive_linear import OUT as INCUMBENT
from probe_ds23_statistical_curvature import curvature_evidence
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, sha, write
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/"reports/2026_10_19_algo03_new_family_inventory"


def unused_curves(tracks,occupied):
    return [i for i,t in enumerate(tracks) if len(t["observation_ids"])==len(set(t["observation_ids"]))
            and not set(t["observation_ids"]).intersection(occupied)]


def run(case):
    OUT.mkdir(exist_ok=True)
    output=OUT/(case+".json")
    if output.exists():
        raise FileExistsError("preserve scientific inventory")
    scan,node,keep,powers,means,model,_,baseline=context(case,"archived")
    old=read(INCUMBENT/(case+".json"))["results"]["all_linear"]
    occupied={o for a in baseline["c0"]["gates"]["tracks"] for o in a["observation_ids"]}
    if old["paired_valid"]:
        occupied.update(o for e in old["entries"] for o in e["observation_ids"])
    labels=list(range(len(scan.norads)))
    widths,receipts=phase_widths(scan,labels)
    widths=np.asarray(widths)*model["multiplier"]
    means=forecast_phase_mean(receipts,model["shrinkage"])
    existing={r["candidate_index"] for r in node["seed"]["rows"]}
    rows=[]
    for i in unused_curves(scan.tracks,occupied):
        t=scan.tracks[i]
        noise=np.array([scan.fixed_window_noise["per_observation_noise_sigma_hz"][o]
            if scan.fixed_window_noise["extra_parameter_BIC_gain"]>0 else scan.radio_sigma_hz
            for o in t["observation_ids"]])
        evidence=curvature_evidence(t["times"],t["values"],noise)
        if evidence["eligible"]:
            rows.append(dict(track_index=i,component=t["key"],points=len(t["times"]),radio=evidence,arms={}))
    for arm in ("c0","fitted_c"):
        record=old["policy_arms"][arm]
        x=np.array(record["endpoint_east_north_km"])
        state=record["state"]
        f,e,d=phase_linear_frequency(scan.geometry,*latlon(x))
        for row in rows:
            i=row["track_index"];t=scan.tracks[i];ix=scan.index[i];q=t["rf_hz"]/11.5e9
            noise=np.array([scan.fixed_window_noise["per_observation_noise_sigma_hz"][o]
                if scan.fixed_window_noise["extra_parameter_BIC_gain"]>0 else scan.radio_sigma_hz
                for o in t["observation_ids"]])
            y=t["values"]-scan.hardware(t,np.array(state["beta"]))
            y-=q*scan.rx_basis[i]@np.array(state["smooth"])[t["receiver"]-1]
            predicted=q*(f[:,ix]+d[:,ix]*means[:,None]);derivative=q*d[:,ix]
            screen=screen_family([dict(observed=y,predicted=predicted,derivative=derivative,
                sigma=noise,power=1.,visible=e[:,ix].min(axis=1)>=0)],widths,bias_sigma_hz=300.)
            ordered=[int(j) for j in np.argsort(screen["cost"]) if np.isfinite(screen["cost"][j])][:5]
            candidates=[]
            for j in ordered:
                phi=float(screen["phase_correction_s"][j]);bias=float(screen["bias_hz"][0][j])
                alias=int(screen["aliases"][0][j])
                residual=y+alias*PERIOD-predicted[j]-derivative[j]*phi-bias
                diagnostic=batch_noise_screen(residual[None],t["times"])
                candidates.append(dict(candidate_index=j,norad=int(scan.norads[j]),new_family=j not in existing,
                    cost=float(screen["cost"][j]),phase_s=float(means[j]+phi),alias=alias,bias_hz=bias,
                    RMS_hz=float(np.sqrt(np.mean(residual**2))),noise_screen_pass=bool(diagnostic["noise_screen_pass"][0])))
            gap=candidates[1]["cost"]-candidates[0]["cost"] if len(candidates)>1 else None
            row["arms"][arm]=dict(candidates=candidates,gap_to_second=gap)
    for row in rows:
        left,right=[row["arms"][a] for a in ("c0","fitted_c")]
        first=[a["candidates"][0] if a["candidates"] else None for a in (left,right)]
        row["strong_paired_new_family_proposal"]=bool(all(v is not None for v in first) and
            first[0]["candidate_index"]==first[1]["candidate_index"] and
            first[0]["alias"]==first[1]["alias"] and all(v["new_family"] and v["noise_screen_pass"] and
                v["RMS_hz"]<=450 and abs(v["bias_hz"])<=3000 and abs(v["phase_s"])<=15 for v in first) and
            all(a["gap_to_second"] is not None and a["gap_to_second"]>2*np.log(len(scan.norads)) for a in (left,right)))
    write(output,dict(case=case,rows=rows,candidate_count=len(scan.norads),
        only_disjoint_whole_curves_with_radio_curvature_evidence=True,
        no_GPS_post_scan_TLE_or_identity_whitelist_used=True,
        proposal_cost_is_approximate_Gaussian_no_calibration_covariance_or_physical_orbit_modes=True,
        strong_gap_rule="both c arms gap > 2 log(causal candidate count), not calibrated probability",
        no_points_associated_or_position_updated=True,source_sha256=sha(Path(__file__)),
        incumbent_sha256=sha(INCUMBENT/(case+".json"))))
    print(case,"eligible unused curved",len(rows),"strong new family",sum(r["strong_paired_new_family_proposal"] for r in rows),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
