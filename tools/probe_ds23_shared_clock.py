"""Same-variance shared satellite clock covariance on selected DS23 cases.

This is a covariance hypothesis, not a GPS-tuned clock or a new TLE mean.
"""

import argparse
from pathlib import Path

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_satellite_prior_controls import clock_design
from investigate_algo01_ds23_0217 import diagnostics, problem
from investigate_dsx01_localization_failures import fit
from run_algo01_ds23_sample import OUT as SOURCE, ROOT, final_scan, read, sha, write

OUT=ROOT/"reports/2026_10_18_ds23_shared_clock"
ARMS=("c0","fitted_c")


def clock_problem(scan,node,keep,arm,reference):
    p=problem(scan,node,arm,keep,reference)
    clock,independent=clock_design(p.flat_labels,p.q*11.5e9,p.supported_local,
        shared_sigma=np.sqrt(.9)*1000,reference_hz=12.5e9,preserve_variance=True)

    def calculate(x):
        result=JointMarginal.calculate(p,x)
        original=result["features"]
        stop=original.shape[1]-len(p.members)
        constants=original[:,stop:]*independent[:,None]/1000
        features=np.column_stack((original[:,:stop],clock,constants))
        raw=p.values-p.q*result["intercept"]
        bound=hierarchical_bound(raw[keep],features[keep],p.point_noise[keep],p.noise_groups[keep])
        present=np.unique(p.noise_groups[keep])
        noise_precision=np.zeros(len(p.members));noise_precision[present]=bound["noise_precision"]
        bound["noise_precision"]=noise_precision
        bound["conditional_residual_hz"]=raw-features@bound["coefficient"]
        bound["residual"]=np.r_[bound["residual"],np.sqrt(p.noise_volume)]
        result.update(bound,features=features)
        return result

    def conditional_frequency(x):
        result=calculate(x)
        start=p.hardware.shape[1]+p.smooth.shape[1]
        stop=result["features"].shape[1]-len(p.members)
        return (result["intercept"]+result["features"][:,start:stop]@
                result["coefficient"][start:stop]/p.q,result["elevation"])

    p.calculate=calculate;p.conditional_frequency=conditional_frequency
    return p


def refit(scan,node,keep,arm):
    labels=sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    reference=np.zeros(len(labels));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=clock_problem(scan,node,keep,arm,reference)
        fitted=fit(p,anchor,iterations=48)
        anchor=np.array(fitted["parameters"])
        phase=p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch,fit=fitted,max_phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    result=diagnostics(p,anchor)
    result.update(gates=retained_metrics(p,anchor),history=history,
                  covariance="same marginal 1000 Hz variance; 90% RF-scaled shared component at 12.5 GHz")
    return result


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/"result.json")
    node,keep=original["final_node"],np.array(original["final_mask"],bool)
    base=problem(scan,node,"c0",keep)
    history=[]
    for epoch in range(4):
        pair={arm:refit(scan,node,keep,arm) for arm in ARMS}
        failed={r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"] if not r["compatible"]}
        history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
        if not failed or epoch==3:
            break
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row["component"] in failed:keep[sl]=False
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+".json"),dict(case=case,arms=pair,mask=keep,history=history,valid=not failed,
          GPS_used=False,latest_TLE_mean_and_physical_orbit_priors_unchanged=True,
          same_marginal_fragment_variance=True,matched_c_masks_and_budget=True,
          source_sha256=sha(Path(__file__)),baseline_sha256=sha(SOURCE/case/"result.json")))
    print(case,{a:pair[a]["endpoint_east_north_km"].tolist() for a in ARMS},flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
