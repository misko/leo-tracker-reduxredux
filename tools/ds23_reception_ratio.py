"""RF reception-ratio diagnostic, with a nominal Gaussian-beam contrast.

The installed pattern/pose are unmeasured. A signed slope permits provisional
receiver mapping to be contradicted. Predictive qualification must precede use
as an association prior. No geographic coordinate is an input to this module.
"""

import numpy as np


def beam_contrast(azimuth_deg,elevation_deg):
    a,e=np.deg2rad(np.broadcast_arrays(np.asarray(azimuth_deg,float),np.asarray(elevation_deg,float)))
    if not np.isfinite(a).all() or not np.isfinite(e).all():raise ValueError('finite horizon directions required')
    elevation=np.deg2rad(70.)
    angles=[]
    for axis in [270.,90.]:
        cosine=np.sin(e)*np.sin(elevation)+np.cos(e)*np.cos(elevation)*np.cos(a-np.deg2rad(axis))
        angles.append(np.arccos(np.clip(cosine,-1,1)))
    return angles[1]**2-angles[0]**2


def logit_ratio(first,second):
    a,b=np.broadcast_arrays(np.asarray(first,float),np.asarray(second,float))
    if not np.isfinite(a).all() or not np.isfinite(b).all() or np.any((a<=0)|(a>=1)|(b<=0)|(b>=1)):
        raise ValueError('native margins strictly between zero and one required')
    return np.log(a/(1-a))-np.log(b/(1-b))


def fit_ratio(rows,with_direction=True):
    if not rows:raise ValueError('nonempty family reception evidence required')
    band=np.array([r['band'] for r in rows],int);x=np.array([r['feature'] for r in rows]);y=np.array([r['log_ratio'] for r in rows])
    if not set(band).issubset({0,1}) or not np.isfinite(np.r_[x,y]).all():raise ValueError('finite two-band family evidence required')
    design=np.eye(2)[band]
    if with_direction:design=np.column_stack((design,x))
    # Broad fixed priors, independent of position errors and held-out family.
    prior=np.full(design.shape[1],1/10.**2)
    coefficient=np.linalg.solve(design.T@design+np.diag(prior),design.T@y)
    return coefficient


def cross_validate(rows):
    families=sorted({r['norad'] for r in rows});folds=[]
    if len(families)<4:return dict(qualified=False,reason='fewer_than_four_curved_families',folds=[])
    for family in families:
        train=[r for r in rows if r['norad']!=family];test=[r for r in rows if r['norad']==family]
        if any(sum(r['band']==band for r in train)<2 for band in {r['band'] for r in test}):
            continue
        a,b=fit_ratio(train,False),fit_ratio(train,True);records=[]
        for row in test:
            records.append(dict(observed=row['log_ratio'],baseline_prediction=float(a[row['band']]),
                direction_prediction=float(b[row['band']]+b[-1]*row['feature']),feature=row['feature'],band=row['band']))
        folds.append(dict(norad=family,training_families=sorted({r['norad'] for r in train}),slope=float(b[-1]),predictions=records))
    if len(folds)<4:return dict(qualified=False,reason='fewer_than_four_supported_held_family_folds',folds=folds)
    baseline=sum((r['observed']-r['baseline_prediction'])**2 for f in folds for r in f['predictions'])
    alternative=sum((r['observed']-r['direction_prediction'])**2 for f in folds for r in f['predictions'])
    slopes=np.array([f['slope'] for f in folds]);sign_consistent=bool(np.all(slopes>0) or np.all(slopes<0))
    gain=1-alternative/max(baseline,1e-30)
    return dict(qualified=bool(gain>.2 and sign_consistent),folds=folds,baseline_squared_error=baseline,
        direction_squared_error=alternative,held_family_SSE_fractional_improvement=float(gain),
        slope_sign_consistent=sign_consistent,full_coefficients=fit_ratio(rows,True),
        nominal_pattern_not_independently_measured=True)
