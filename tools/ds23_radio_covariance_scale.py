"""Estimate the marginal variance hidden by polynomial detrending.

A correlated process loses more variance during polynomial fitting than white
noise. Profile the same radio-only contrasts under both covariance shapes;
use their geometric mean variance ratio, weighted by residual dimensions.
"""

import numpy as np
from ds23_radio_correlation import contrasts,correlation


def variance_ratio(tracks,alpha,tau):
    weighted=0.;dimensions=0;pieces=0;seen=set();ratios=[]
    for track in tracks:
        times=np.asarray(track["times"]);values=np.asarray(track["values"])
        for piece in track["pieces"]:
            indices=[k for k,(t,oid) in enumerate(zip(times,track["observation_ids"],strict=True))
                     if piece["start_s"]<=t<=piece["end_s"] and oid not in seen]
            degree=piece["degree"]
            if len(indices)<2*(degree+1)+3:continue
            t=times[indices];b,z=contrasts(t,values[indices],degree);energy=float(z@z)
            if energy<=1e-12:continue
            seen.update(track["observation_ids"][k] for k in indices)
            root=np.linalg.cholesky(b.T@correlation(t,alpha,tau)@b)
            white=np.linalg.solve(root,z);ratio=float(white@white/energy)
            weighted+=len(z)*np.log(ratio);dimensions+=len(z);pieces+=1;ratios.append(ratio)
    return dict(marginal_variance_ratio=float(np.exp(weighted/dimensions)) if dimensions else 1.,
        pieces=pieces,residual_contrasts=dimensions,piece_variance_ratios=ratios,
        no_GPS_TLE_or_satellite_residuals_used=True,
        radio_covariance_amplitude_is_estimated_not_assumed_unchanged=True)
