"""Matched fixed-data position trial of uncertainty for every satellite family."""

import argparse
from pathlib import Path

import numpy as np
from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_all_family_uncertainty import make_problem, replication_gate_view
from ds23_predictive_linear import attach_predictive_linear
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from probe_ds23_predictive_linear import OUT as INCUMBENT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/"reports/2026_10_19_algo03_all_family_uncertainty_v2"


def refit(scan,node,keep,arm,powers,means,model,entries,enabled):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model,enabled)
        attach_predictive_linear(p,entries,powers)
        fitted=fit(p,x,iterations=48);x=np.array(fitted["parameters"])
        phase=np.clip(p.state(x)["phases"][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(max(abs(phase-reference)))))
        reference=phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;gates=[]
    for entry,sl in zip(entries,getattr(p,"linear_slices",[]),strict=True):
        track=scan.tracks[entry["track_index"]]
        raw=c["linear_raw_prediction_residual_hz"][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[entry["track_index"]],bias_sigma=300.)
        noise=batch_noise_screen(terms["innovations"],track["times"])
        valid=bool(terms["rms"][0]<=450 and abs(terms["bias"][0])<=3000 and int(terms["alias"][0])==0 and
                   noise["noise_screen_pass"][0] and min(c["linear_elevation"][sl])>=0)
        gates.append(dict(component=entry["component"],compatible=valid,points=entry["points"],
            observation_ids=entry["observation_ids"],rms_hz=float(terms["rms"][0]),bias_hz=float(terms["bias"][0])))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,
        phase_reference=p.reference,state=p.state(x),gates=retained_metrics(replication_gate_view(p),x),linear_gates=gates,
        active_points=int(keep.sum()),RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep]**2))),
        negative_twice_elbo=c["negative_twice_elbo"],curved_negative_twice_elbo=curved["negative_twice_elbo"],
        final_phase_change_s=history[-1]["phase_change_s"],
        calibration_replay_max_coefficient_difference=float(max(abs(c["coefficient"]-curved["coefficient"]))),
        added_uncertain_families=[int(scan.norads[j]) for j in getattr(p,"new_uncertain_families",[])],
        physical_orbit_mode_families=[int(scan.norads[j]) for j in p.supported])


def run(case,null=False):
    OUT.mkdir(exist_ok=True)
    output=OUT/(case+("_null" if null else "")+".json")
    if output.exists():
        raise FileExistsError("preserve scientific outputs")
    scan,node,keep,powers,means,model,_,_=context(case,"archived")
    old=read(INCUMBENT/(case+".json"))["results"]["all_linear"]
    entries=old["entries"]
    curved={a:refit(scan,node,keep,a,powers,means,model,[],not null) for a in ("c0","fitted_c")}
    linear={a:refit(scan,node,keep,a,powers,means,model,entries,not null) for a in ("c0","fitted_c")}
    cv=pair_passes(curved);lv=pair_passes(linear,include_linear=True)
    policy=linear if cv and lv else (curved if cv else old["policy_arms"])
    write(output,dict(case=case,null_control=null,curved_arms=curved,linear_arms=linear,
        curved_paired_valid=cv,linear_paired_valid=lv,policy_arms=policy,incumbent_arms=old["policy_arms"],
        original_observations_masks_aliases_identities_weights_and_5x48_budgets_preserved=True,
        original_physical_orbit_prior_scales_and_causal_history_preserved=True,
        no_original_point_removal_or_gate_relaxation=True,no_GPS_used=True,
        original_replication_gate_requirements_preserved_separately_from_orbit_uncertainty=True,
        no_linear_to_curved_calibration_feedback=True,source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/"tools/ds23_all_family_uncertainty.py"),
        incumbent_sha256=sha(INCUMBENT/(case+".json"))))
    print(case,"all-family uncertainty","null" if null else "full","C",cv,"L",lv,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--null-control",action="store_true")
    args=parser.parse_args()
    run(args.case,args.null_control)
