"""Audit exact range normalization of fitted orbital state deviations.

The state perturbations themselves remain the existing three linear physical
modes. This is not exact propagation of a newly fitted TLE and is not orbit
truth. No observations or priors are changed and no GPS is read.
"""

import argparse
from pathlib import Path
import numpy as np
from ds23_height_problem import geometry_features
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as INCUMBENT
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

OUT=ROOT/"reports/2026_10_19_algo03_orbit_linearization"


def state_doppler(position,velocity,site):
    line=np.asarray(position)-np.asarray(site);distance=np.linalg.norm(line,axis=-1)
    if np.any(distance<=0):raise ValueError("positive receiver-satellite range required")
    return -11.5e9/299792.458*np.sum(line*np.asarray(velocity),axis=-1)/distance


def audit(scan,node,keep,powers,means,model,saved,arm):
    p=make_problem(scan,node,keep,arm,np.array(saved["phase_reference"]),powers,means,model["multiplier"],model["nu"])
    x=np.array(saved["endpoint_east_north_km"]);c=p.calculate(x);g=geometry_features(p,x,0.)
    start=p.hardware.shape[1]+p.smooth.shape[1];stop=start+len(p.labels)+3*len(p.supported)
    coefficients=c["coefficient"]
    phase=coefficients[start:start+len(p.labels)]*p.phase_sigma
    position,velocity=paired_phase_states(p.sky,p.flat_times,p.flat_labels,phase)
    modes=p.mode_bank["position_km"].shape[0]//len(p.labels)
    if modes!=3:raise ValueError("exactly three native physical orbit modes expected")
    expanded=(p.flat_labels[:,None]*modes+np.arange(modes)).ravel()
    dp,dv=paired_phase_states(p.mode_bank,np.repeat(p.flat_times,modes),expanded,np.repeat(phase,modes))
    dp,dv=dp.reshape(-1,modes,3),dv.reshape(-1,modes,3)
    weights=np.zeros((len(p.labels),3))
    weights[p.supported_local]=coefficients[start+len(p.labels):stop].reshape(-1,3)
    displacement=np.einsum("nkd,nk->nd",dp,weights[p.flat_labels])
    velocity_change=np.einsum("nkd,nk->nd",dv,weights[p.flat_labels])
    exact=p.q*state_doppler(position+displacement,velocity+velocity_change,geodetic_to_ecef_km(*latlon(x),0.))
    approximate=p.q*g["intercept"]+g["features"][:,start:stop]@coefficients[start:stop]
    difference=exact-approximate;active=difference[keep]
    return dict(maximum_CFO_difference_hz=float(max(abs(active))),RMS_CFO_difference_hz=float(np.sqrt(np.mean(active**2))),
        maximum_difference_in_noise_units=float(max(abs(active)/p.point_noise[keep])),
        maximum_orbital_displacement_km=float(max(np.linalg.norm(displacement[keep],axis=1))),
        maximum_phase_relinearization_error_s=float(max(abs(phase-p.reference))),
        orbit_coefficients=weights,points=int(keep.sum()))


def run(case):
    OUT.mkdir(exist_ok=True);path=OUT/(case+".json")
    if path.exists():raise FileExistsError("preserve numerical audit")
    scan,node,keep,powers,means,model,_,_=context(case,"archived")
    source=read(INCUMBENT/(case+".json"));old=source["results"]["all_linear"]["policy_arms"]
    result={arm:audit(scan,node,keep,powers,means,model,old[arm],arm) for arm in ("c0","fitted_c")}
    write(path,dict(case=case,arms=result,no_GPS_used=True,no_observations_or_inference_changed=True,
        not_exact_propagation_of_a_perturbed_TLE=True,source_sha256=sha(Path(__file__))))
    print(case,result,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
