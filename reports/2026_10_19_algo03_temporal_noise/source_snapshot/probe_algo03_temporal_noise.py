"""Matched temporal GLRT covariance test on frozen ALGO02 observations."""

import argparse
import time
from pathlib import Path
import numpy as np
from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_temporal_noise_problem import make_temporal_problem,attach_temporal_prediction
from investigate_dsx01_localization_failures import fit
from learn_algo03_radio_correlation import OUT as PRIOR
from probe_ds23_height import context
from probe_ds23_predictive_linear import OUT as INCUMBENT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/"reports/2026_10_19_algo03_temporal_noise"


def refit(scan,node,keep,arm,powers,means,model,entries,alpha,tau):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_temporal_problem(scan,node,keep,arm,reference,powers,means,model,alpha,tau)
        attach_temporal_prediction(p,entries,powers,alpha,tau)
        result=fit(p,x,iterations=48);x=np.array(result["parameters"])
        phase=np.clip(p.state(x)["phases"][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(max(abs(phase-reference)))));reference=phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;linear_gates=[]
    for e,sl in zip(entries,getattr(p,"linear_slices",[]),strict=True):
        track=scan.tracks[e["track_index"]];residual=c["linear_raw_prediction_residual_hz"][sl]
        terms=profile(residual,np.zeros(len(residual)),*scan.white[e["track_index"]],bias_sigma=300.)
        noise=batch_noise_screen(terms["innovations"],track["times"])
        valid=bool(terms["rms"][0]<=450 and abs(terms["bias"][0])<=3000 and int(terms["alias"][0])==0
            and noise["noise_screen_pass"][0] and min(c["linear_elevation"][sl])>=0)
        linear_gates.append(dict(component=e["component"],compatible=valid,points=e["points"],
            rms_hz=float(terms["rms"][0]),bias_hz=float(terms["bias"][0]),observation_ids=e["observation_ids"]))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,phase_reference=p.reference,
        state=p.state(x),gates=retained_metrics(p,x),linear_gates=linear_gates,active_points=int(keep.sum()),
        additional_predictive_points=sum(e["points"] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep]**2))),
        negative_twice_elbo=c["negative_twice_elbo"],curved_negative_twice_elbo=curved["negative_twice_elbo"],
        linear_predictive_objective=c.get("linear_predictive_objective",0.),
        calibration_replay_max_coefficient_difference=float(max(abs(c["coefficient"]-curved["coefficient"]))),
        final_phase_change_s=history[-1]["phase_change_s"])


def run(case,null=False):
    OUT.mkdir(exist_ok=True);path=OUT/(case+("_null" if null else "")+".json")
    if path.exists():raise FileExistsError("preserve scientific outputs")
    began=time.monotonic();prior=read(PRIOR/(case+".json"))
    source=read(INCUMBENT/(case+".json"));old=source["results"]["all_linear"]["policy_arms"]
    if not null and not prior["selection"]["qualified"]:
        write(path,dict(case=case,prior_qualified=False,policy_arms=old,no_inference_needed=True));return
    scan,node,keep,powers,means,model,_,_=context(case,"archived")
    alpha=0. if null else prior["selection"]["alpha"];tau=prior["selection"]["tau_s"]
    entries=source["results"]["all_linear"]["entries"]
    curved={a:refit(scan,node,keep,a,powers,means,model,[],alpha,tau) for a in ("c0","fitted_c")}
    linear={a:refit(scan,node,keep,a,powers,means,model,entries,alpha,tau) for a in ("c0","fitted_c")}
    cv=pair_passes(curved);lv=pair_passes(linear,include_linear=True)
    policy=linear if cv and lv else (curved if cv else old)
    write(path,dict(case=case,null_control=null,prior_qualified=True,alpha=alpha,tau_s=tau,
        curved_arms=curved,linear_arms=linear,curved_paired_valid=cv,linear_paired_valid=lv,
        policy_arms=policy,incumbent_arms=old,mask=keep,powers=powers,entries=entries,
        original_points_labels_aliases_marginal_noise_scales_and_other_priors_preserved=True,
        no_GPS_or_post_scan_TLE_used=True,no_linear_to_calibration_feedback=True,
        original_unwhitened_residual_gates_unchanged=True,
        same_observations_c_priors_and_5x48_budgets=True,
        prior_sha256=sha(PRIOR/(case+".json")),incumbent_sha256=sha(INCUMBENT/(case+".json")),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_temporal_noise_problem.py"),
        seconds=time.monotonic()-began))
    print(case,"temporal noise",alpha,tau,"C",cv,"L",lv,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    parser.add_argument("--null-control",action="store_true");args=parser.parse_args()
    run(args.case,args.null_control)
