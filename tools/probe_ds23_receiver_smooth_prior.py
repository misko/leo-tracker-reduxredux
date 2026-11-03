"""Controlled zero/quarter smooth-receiver prior, preserving linear drift."""

import argparse
from pathlib import Path

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from investigate_algo01_ds23_0217 import diagnostics, problem
from investigate_dsx01_localization_failures import fit
from run_algo01_ds23_sample import OUT as SOURCE, ROOT, final_scan, read, sha, write

OUT=ROOT/"reports/2026_10_18_ds23_receiver_smooth_prior"
ARMS=("c0","fitted_c")


def scale_posterior(bound, scales):
    """Return means/precisions in the original design coordinates, including zero modes."""
    s=np.asarray(scales)
    bound["coefficient"]*=s
    nonzero=s!=0
    bound["coefficient_prior_precision"][nonzero]/=s[nonzero]**2
    return bound


def smooth_problem(scan,node,keep,arm,reference,sigma_hz):
    p=problem(scan,node,arm,keep,reference)
    def calculate(x):
        result=JointMarginal.calculate(p,x)
        features=result["features"]
        scale=np.ones(features.shape[1])
        start=p.hardware.shape[1]
        scale[start:start+p.smooth.shape[1]]=sigma_hz/200
        raw=p.values-p.q*result["intercept"]
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep])
        bound=scale_posterior(bound,scale)
        precision=np.zeros(len(p.members));precision[np.unique(p.noise_groups[keep])]=bound["noise_precision"]
        bound["noise_precision"]=precision
        bound["conditional_residual_hz"]=raw-features@bound["coefficient"]
        bound["residual"]=np.r_[bound["residual"],np.sqrt(p.noise_volume)]
        result.update(bound)
        return result
    p.calculate=calculate
    return p


def refit(scan,node,keep,arm,sigma):
    reference=np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
    anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=smooth_problem(scan,node,keep,arm,reference,sigma)
        result=fit(p,anchor,iterations=48)
        anchor=np.asarray(result["parameters"])
        phase=p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    output=diagnostics(p,anchor)
    output.update(gates=retained_metrics(p,anchor),history=history)
    return output


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/"result.json")
    node=original["final_node"];original_keep=np.asarray(original["final_mask"],bool)
    base=problem(scan,node,"c0",original_keep)
    outputs={}
    for sigma in (0.,50.):
        keep=original_keep.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,sigma) for arm in ARMS}
            failed={r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"] if not r["compatible"]}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row["component"] in failed:keep[sl]=False
        outputs[str(sigma)]=dict(arms=pair,mask=keep,history=history,valid=not failed)
        print(case,"smooth sigma",sigma,"points",int(keep.sum()),"valid",not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+".json"),dict(case=case,results=outputs,source_sha256=sha(Path(__file__)),
        original_sigma_hz=200,GPS_used=False,linear_receiver_drift_and_causal_orbit_priors_unchanged=True,
        c_pair_observations_masks_aliases_and_priors_matched=True))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
