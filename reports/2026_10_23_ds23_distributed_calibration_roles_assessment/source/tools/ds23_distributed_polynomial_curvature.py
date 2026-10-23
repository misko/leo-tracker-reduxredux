"""RF-only distributed nonlinear support through degree4, including inflections."""

import numpy as np


def evidence(track):
    t=np.asarray(track['times'],float);y=np.asarray(track['values'],float)
    if t.shape!=y.shape or t.ndim!=1 or not np.isfinite(t).all() or not np.isfinite(y).all():raise ValueError('matching finite source times and values required')
    if len(t)<12 or np.ptp(t)<10:return dict(qualified=False,reason='minimum12points and10seconds')
    rows=[]
    for omitted in [None]+list(range(len(t))):
        use=np.ones(len(t),bool)
        if omitted is not None:use[omitted]=False
        tt,yy=t[use],y[use];n=len(tt);z=(tt-tt.mean())/np.ptp(tt);fits=[]
        for degree in [1,2,3,4]:
            if degree>1 and n<4*(degree+1):continue
            u=np.polynomial.legendre.legvander(z,degree);pred=u@np.linalg.lstsq(u,yy,rcond=None)[0];res=yy-pred;variance=max(float(np.mean(res*res)),1e-12)
            fits.append(dict(degree=degree,BIC=n*np.log(variance)+(degree+1)*np.log(n),prediction=pred,residual_RMS_hz=np.sqrt(variance)))
        nonlinear=fits[1:]
        if not nonlinear:return dict(qualified=False,reason='every deletion needs at least4points per nonlinear coefficient')
        best=min(nonlinear,key=lambda r:r['BIC']);amplitude=float(np.sqrt(np.mean((best['prediction']-fits[0]['prediction'])**2)));gain=float(fits[0]['BIC']-best['BIC']);penalty=float(2*np.log(len(nonlinear)))
        rows.append(dict(omitted=omitted,best_degree=best['degree'],nonlinear_RMS_hz=amplitude,quadratic_or_higher_BIC_gain=gain,degree_search_penalty=penalty,
            residual_RMS_hz=float(best['residual_RMS_hz']),qualified=bool(amplitude>=250 and gain>10+penalty)))
    return dict(qualified=all(r['qualified'] for r in rows),minimum_nonlinear_RMS_hz=min(r['nonlinear_RMS_hz'] for r in rows),
        minimum_penalized_BIC_gain=min(r['quadratic_or_higher_BIC_gain']-r['degree_search_penalty'] for r in rows),
        degrees_selected=sorted({r['best_degree'] for r in rows}),rows=rows,all_deletions_diagnostic_no_point_removed=True)
