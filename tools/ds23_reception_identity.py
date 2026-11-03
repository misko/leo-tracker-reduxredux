"""Family-held-out reception scores for causal identity proposals.

The fixed logit-ratio noise floors are engineering assumptions, not calibrated
identity probabilities. A shared family effect prevents two bands from being
treated as independent copies. The tested family cannot train coefficients.
"""

import numpy as np


def design(rows,direction=True):
    if not rows:raise ValueError('nonempty family reception rows required')
    band=np.asarray([r['band'] for r in rows],int)
    if not set(band).issubset({0,1}):raise ValueError('two native bands required')
    a=np.eye(2)[band]
    if direction:a=np.column_stack((a,[r['feature'] for r in rows]))
    y=np.asarray([r['log_ratio'] for r in rows],float)
    if not np.isfinite(a).all() or not np.isfinite(y).all():raise ValueError('finite reception evidence required')
    return a,y


def train(rows,held_family,*,direction=True):
    if any(r['norad']==held_family for r in rows):raise ValueError('held family leaked into reception calibration')
    a,y=design(rows,direction)
    families=np.asarray([r['norad'] for r in rows])
    # Independent measurement SD1, unseen shared family SD1, coefficient SD10.
    noise=np.eye(len(rows))+(families[:,None]==families[None,:])
    precision=np.eye(a.shape[1])*.01+a.T@np.linalg.solve(noise,a)
    covariance=np.linalg.inv(precision)
    coefficient=covariance@a.T@np.linalg.solve(noise,y)
    return dict(coefficient=coefficient,covariance=covariance,direction=direction,
        training_families=sorted(set(families.tolist())),held_family=int(held_family))


def scores(model,rows,candidate_features=None):
    if any(r['norad']!=model['held_family'] for r in rows):raise ValueError('test must be exactly the excluded family')
    a,y=design(rows,model['direction'])
    features=np.asarray([r['feature'] for r in rows])[None] if candidate_features is None else np.asarray(candidate_features,float)
    if features.ndim!=2 or features.shape[1]!=len(rows) or not np.isfinite(features).all():
        raise ValueError('finite candidate by held-band feature matrix required')
    designs=np.broadcast_to(a,(len(features),*a.shape)).copy()
    if model['direction']:designs[:,:,-1]=features
    raw=y[None]-designs@np.asarray(model['coefficient'])
    covariance=np.eye(len(rows))+np.ones((len(rows),len(rows)))
    covariance=covariance[None]+designs@np.asarray(model['covariance'])@designs.swapaxes(-1,-2)
    root=np.linalg.cholesky(covariance)
    residual=np.linalg.solve(root,raw[...,None])[...,0]
    return np.sum(residual**2,axis=1)+2*np.log(np.diagonal(root,axis1=-2,axis2=-1)).sum(axis=1)+len(rows)*np.log(2*np.pi)
