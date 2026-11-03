#!/usr/bin/env python3
"""Independent closed-form forward oracle for the frozen likelihood callback."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "reports/2026_09_30_gaussian_sum_64_scan"))
import physics  # noqa: E402
from leo.analysis.gaussian_sum_location import gaussian_logpdf  # noqa: E402


def geodetic_ecef_km(lat_deg, lon_deg, height_km=0.0):
    lat, lon = np.radians([lat_deg, lon_deg]); a = 6378.137; e2 = 6.6943799901413165e-3
    n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return np.array([(n+height_km)*math.cos(lat)*math.cos(lon),
                     (n+height_km)*math.cos(lat)*math.sin(lon),
                     (n*(1-e2)+height_km)*math.sin(lat)])


def direct_doppler(position, velocity, receiver, reference_hz, sign):
    line = position-receiver; unit = line/np.linalg.norm(line, axis=1, keepdims=True)
    return sign*reference_hz/299_792.458*np.sum(velocity*unit, axis=1)


def make_case(outlier_hz=0.0):
    config = physics.PhysicsConfig(prior_center_lat_deg=38.5816,
        prior_center_lon_deg=-121.4944, support_radius_km=50.0)
    knots = np.arange(-20.0, 81.0, 5.0)
    receiver = geodetic_ecef_km(config.prior_center_lat_deg, config.prior_center_lon_deg)
    up=receiver/np.linalg.norm(receiver); east=np.cross(np.array([0.,0.,1.]),up); east/=np.linalg.norm(east)
    north=np.cross(up,east)
    origins=np.array([receiver+1000.*up+250.*east, receiver+1150.*up-300.*north])
    velocities=np.array([5.5*east+1.1*north, -4.8*east+2.0*north])
    positions = origins[:,None,:]+velocities[:,None,:]*knots[None,:,None]
    bank = physics.OrbitBank((70001,70002), knots, positions,
        np.broadcast_to(velocities[:,None,:], positions.shape).copy())
    layout = physics.StateLayout(bank.norad_ids); times = np.linspace(0.,55.,8); clock = .7
    queried = origins[0]+velocities[0]*(times+clock)[:,None]
    measured = direct_doppler(queried, np.broadcast_to(velocities[0], queried.shape), receiver,
        config.reference_frequency_hz, config.doppler_sign)
    drift=.35; measured += 18_000.+drift*(times-times.mean())
    measured += np.array([0.,2.,-1.,1.5,-2.,.5,-1.5,outlier_hz])
    track = physics.TrackObservations(tuple(f"synthetic:{i}" for i in range(8)), times,
        measured, np.zeros(8,dtype=int), config.reference_frequency_hz)
    state=np.zeros(layout.dimension); state[3]=clock; state[4]=drift
    return track,bank,layout,config,state


def evaluate(outlier_hz=0.0):
    track,bank,layout,config,state=make_case(outlier_hz)
    factor=physics.build_physics_factor(track,bank,layout,config).factor; rows=[]
    for candidate in factor.candidates:
        pred=candidate.predict(state); prior=candidate.prior(state) if callable(candidate.prior) else candidate.prior
        joint=-math.inf if prior <= 0 else math.log(prior)+gaussian_logpdf(factor.observation-pred.mean,pred.covariance)
        rows.append({"candidate":candidate.label,"log_joint":float(joint)})
    bp=factor.background_prior(state) if callable(factor.background_prior) else factor.background_prior
    bg=float(math.log(bp)+factor.background_log_likelihood)
    return {"schema":"independent-forward-synthetic/v1","generator":"closed_form_linear_ecef",
        "generator_uses_likelihood_prediction_callback":False,"known_candidate":"70001",
        "clock_offset_s":.7,"receiver_drift_hz_s":.35,"constant_cfo_hz":18000.,
        "outlier_hz":outlier_hz,"candidates":rows,"background_log_joint":bg,
        "best_label":max(rows+[{"candidate":"background","log_joint":bg}],key=lambda x:x["log_joint"])["candidate"]}


if __name__ == "__main__":
    result={"clean":evaluate(),"outlier":evaluate(20_000.),"scope":"synthetic contract oracle; no real-data accuracy claim"}
    output=HERE/"synthetic-results.json"; output.write_text(json.dumps(result,indent=2)+"\n"); print(output)
