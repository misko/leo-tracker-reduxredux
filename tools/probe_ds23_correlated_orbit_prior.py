"""Matched position evaluation of externally qualified phase/shape coupling."""

import argparse
import time
from pathlib import Path
import numpy as np
from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_correlated_orbit_problem import make_correlated_problem, attach_correlated_prediction
from investigate_dsx01_localization_failures import fit
from learn_ds23_joint_orbit_prior import OUT
from probe_ds23_height import context
from probe_ds23_predictive_linear import OUT as INCUMBENT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile


def refit(scan, node, keep, arm, powers, means, model, correlation, entries):
    reference=np.zeros(len(means))
    x=np.zeros(2)
    history=[]
    for _ in range(5):
        p=make_correlated_problem(scan,node,keep,arm,reference,powers,means,model,correlation)
        attach_correlated_prediction(p,entries,powers)
        result=fit(p,x,iterations=48)
        x=np.array(result["parameters"])
        phase=np.clip(p.state(x)["phases"][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=phase
    c=p.calculate(x)
    curved=p.curved_calculate(x) if entries else c
    linear_gates=[]
    for entry,sl in zip(entries,getattr(p,"linear_slices",[]),strict=True):
        track=scan.tracks[entry["track_index"]]
        residual=c["linear_raw_prediction_residual_hz"][sl]
        terms=profile(residual,np.zeros(len(residual)),*scan.white[entry["track_index"]],bias_sigma=300.)
        noise=batch_noise_screen(terms["innovations"],track["times"])
        valid=bool(terms["rms"][0]<=450 and abs(terms["bias"][0])<=3000 and
            int(terms["alias"][0])==0 and noise["noise_screen_pass"][0] and min(c["linear_elevation"][sl])>=0)
        linear_gates.append(dict(component=entry["component"],compatible=valid,points=entry["points"],
            rms_hz=float(terms["rms"][0]),bias_hz=float(terms["bias"][0]),observation_ids=entry["observation_ids"]))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,phase_reference=p.reference,
        state=p.state(x),gates=retained_metrics(p,x),linear_gates=linear_gates,active_points=int(keep.sum()),
        additional_predictive_points=sum(e["points"] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep]**2))),
        negative_twice_elbo=c["negative_twice_elbo"],curved_negative_twice_elbo=curved["negative_twice_elbo"],
        linear_predictive_objective=c.get("linear_predictive_objective",0.),
        calibration_replay_max_coefficient_difference=float(max(abs(c["coefficient"]-curved["coefficient"]))),
        final_phase_change_s=history[-1]["phase_change_s"],
        native_prior_is_diagonal=c["native_prior_is_diagonal"],prior_penalty=c["latent_prior_penalty"])


def run(case,null=False):
    OUT.mkdir(exist_ok=True)
    path=OUT/(case+("_null" if null else "")+"_position.json")
    if path.exists():
        raise FileExistsError("preserve scientific outputs")
    began=time.monotonic()
    scan,node,keep,powers,means,model,_,baseline=context(case,"archived")
    source=read(INCUMBENT/(case+".json"))
    original=source["results"]["all_linear"]["policy_arms"]
    entries=source["results"]["all_linear"]["entries"]
    learned=read(OUT/(case+"_prior.json")) if not null else None
    correlation=np.eye(4) if null else np.asarray(learned["selection"]["correlation"])
    if not null and not learned["selection"]["qualified"]:
        write(path,dict(case=case,prior_qualified=False,policy_arms=original,no_inference_needed=True))
        return
    curved={arm:refit(scan,node,keep,arm,powers,means,model,correlation,[]) for arm in ("c0","fitted_c")}
    linear={arm:refit(scan,node,keep,arm,powers,means,model,correlation,entries) for arm in ("c0","fitted_c")}
    cv=pair_passes(curved)
    lv=pair_passes(linear,include_linear=True)
    policy=linear if cv and lv else (curved if cv else original)
    write(path,dict(case=case,null_control=null,prior_qualified=True,correlation=correlation,
        curved_arms=curved,linear_arms=linear,curved_paired_valid=cv,linear_paired_valid=lv,
        policy_arms=policy,incumbent_arms=original,mask=keep,powers=powers,entries=entries,
        no_GPS_used=True,no_original_points_removed=True,no_satellite_or_alias_changes=True,
        no_linear_calibration_feedback=True,full_native_correlated_prior_used_for_predictive_covariance=True,
        same_observations_masks_c_priors_and_5x48_budgets=True,
        learned_prior_sha256=sha(OUT/(case+"_prior.json")) if not null else None,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_correlated_orbit_problem.py"),
        seconds=time.monotonic()-began))
    print(case,"correlated prior","null" if null else "learned","C",cv,"L",lv,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--null-control",action="store_true")
    args=parser.parse_args()
    run(args.case,args.null_control)
