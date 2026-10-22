"""A bounded duration ablation with distributed, measurable curvature support.

The published raw-curvature classifier keeps its original20-second cutoff.
This research alternative permits10seconds only when250Hz of nonlinear
amplitude and a >10 BIC quadratic gain survive every single-point deletion.
"""

import numpy as np


def curvature_evidence(track):
    t=np.asarray(track['times']);y=np.asarray(track['values']);rows=[]
    if len(t)<12 or np.ptp(t)<10:return dict(qualified=False,reason='minimum12points and10seconds')
    for omitted in [None]+list(range(len(t))):
        use=np.ones(len(t),bool)
        if omitted is not None:use[omitted]=False
        tt=t[use];yy=y[use];z=(tt-tt.mean())/np.ptp(tt);scores=[];rms=[]
        for degree in [1,2]:
            u=np.polynomial.legendre.legvander(z,degree);residual=yy-u@np.linalg.lstsq(u,yy,rcond=None)[0]
            variance=max(float(np.mean(residual**2)),1e-12)
            scores.append(len(tt)*np.log(variance)+(degree+1)*np.log(len(tt)));rms.append(float(np.sqrt(variance)))
        rows.append(dict(omitted=omitted,linear_RMS_hz=rms[0],quadratic_RMS_hz=rms[1],quadratic_BIC_gain=scores[0]-scores[1]))
    return dict(qualified=all(r['linear_RMS_hz']>=250 and r['quadratic_BIC_gain']>10 for r in rows),
        minimum_linear_RMS_hz=min(r['linear_RMS_hz'] for r in rows),minimum_quadratic_BIC_gain=min(r['quadratic_BIC_gain'] for r in rows),rows=rows,
        all_single_point_deletions_are_diagnostic_no_point_removed=True)


def supported_curvature(track):
    return curvature_evidence(track)['qualified']
