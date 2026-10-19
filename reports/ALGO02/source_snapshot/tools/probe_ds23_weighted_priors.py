"""Preset prior-factor controls on the frozen cross-receiver family rule."""

import argparse
from pathlib import Path

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import diagnostics, problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_receiver_smooth_prior import scale_posterior
from run_algo01_ds23_sample import OUT as SOURCE, ROOT, final_scan, read, sha, write

OUT=ROOT/"reports/2026_10_18_ds23_weighted_prior_controls"
ARMS=("c0","fitted_c")
CONTROLS=("phase_floor3","fragment300","receiver50","combined")


def controlled_problem(scan,node,keep,arm,reference,weights,control):
    p=problem(scan,node,arm,keep,reference,"phase_floor3" if control in ("phase_floor3","combined") else "baseline")
    def calculate(x):
        result=JointMarginal.calculate(p,x)
        features=result["features"]
        scale=np.ones(features.shape[1])
        if control in ("fragment300","combined"):
            scale[-len(p.members):]=.3
        if control in ("receiver50","combined"):
            start=p.hardware.shape[1]
            scale[start:start+p.smooth.shape[1]]=.25
        raw=p.values-p.q*result["intercept"]
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],
                                 p.noise_groups[keep],powers=weights[present])
        bound=scale_posterior(bound,scale)
        precision=np.zeros(len(p.members));precision[present]=bound["noise_precision"]
        bound["noise_precision"]=precision
        bound["conditional_residual_hz"]=raw-features@bound["coefficient"]
        volume=float(2*np.sum(weights[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound["residual"]=np.r_[bound["residual"],np.sqrt(volume)]
        result.update(bound)
        return result
    p.calculate=calculate
    return p


def refit(scan,node,keep,arm,weights,control):
    reference=np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
    anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=controlled_problem(scan,node,keep,arm,reference,weights,control)
        fitted=fit(p,anchor,iterations=48)
        anchor=np.asarray(fitted["parameters"])
        phase=p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch,fit=fitted,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    d=diagnostics(p,anchor)
    d.update(history=history,gates=retained_metrics(p,anchor))
    return d


def run(case):
    OUT.mkdir(parents=True,exist_ok=True)
    output=OUT/(case+".json")
    if output.exists():return
    scan=final_scan(case);baseline=read(SOURCE/case/"result.json")
    node,original_keep=baseline["final_node"],np.array(baseline["final_mask"],bool)
    weights=np.array(read(WEIGHTS/case/"result.json")["results"]["cross_rx_support"]["weights"])
    base=problem(scan,node,"c0",original_keep)
    results={}
    for control in CONTROLS:
        keep=original_keep.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights,control) for arm in ARMS}
            failed={r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"] if not r["compatible"]}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed),
                endpoints={arm:pair[arm]["endpoint_east_north_km"] for arm in ARMS},
                RMS_hz={arm:pair[arm]["RMS_hz"] for arm in ARMS}))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row["component"] in failed:keep[sl]=False
        results[control]=dict(arms=pair,mask=keep,history=history,valid=not failed)
        print(case,control,"retained",int(keep.sum()),"valid",not failed,flush=True)
    write(output,dict(case=case,results=results,source_sha256=sha(Path(__file__)),
          baseline_sha256=sha(SOURCE/case/"result.json"),
          weight_input_sha256=sha(WEIGHTS/case/"result.json"),GPS_used=False,
          discrete_identities_causal_inputs_and_weights_frozen=True,matched_c_pair_masks_and_budget=True,
          priors=dict(phase_floor_s=3,fragment_sigma_hz=300,receiver_smooth_sigma_hz=50),
          controls_prespecified_without_GPS_model_selection=True))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
