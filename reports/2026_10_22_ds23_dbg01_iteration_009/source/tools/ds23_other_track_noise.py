"""Heteroscedastic RF-only REML shape learned from other graph components.

No satellite prediction or geographic residual enters covariance learning.
Each polynomial piece profiles its own scale; only correlation shape is pooled.
"""

import numpy as np

ALPHAS=(.1,.3,.6,.9)
TAUS=(1.,3.,10.,30.,100.)


def blocks(tracks,sigma_by_id,fallback_sigma):
    result=[];seen=set()
    for track in tracks:
        t=np.asarray(track['times']);y=np.asarray(track['values'])
        for piece in track['pieces']:
            ix=np.array([i for i,(time,oid) in enumerate(zip(t,track['observation_ids'],strict=True))
                if piece['start_s']<=time<=piece['end_s'] and oid not in seen],int)
            degree=piece['degree']
            if len(ix)<2*(degree+1)+3:continue
            sigma=np.array([sigma_by_id.get(track['observation_ids'][i],fallback_sigma) for i in ix])
            if np.any(sigma<=0):raise ValueError('positive native RF noise required')
            z=(t[ix]-t[ix].mean())/max(1.,np.ptp(t[ix]));design=np.polynomial.legendre.legvander(z,degree)/sigma[:,None]
            q,_=np.linalg.qr(design,mode='complete');basis=q[:,degree+1:];contrast=basis.T@(y[ix]/sigma)
            if contrast@contrast<=1e-12:continue
            ids=[track['observation_ids'][i] for i in ix];seen.update(ids)
            result.append(dict(component=track['key'],times=t[ix],basis=basis,contrast=contrast,observation_ids=ids))
    return result


def shape_score(piece,alpha,tau):
    b=piece['basis'];z=piece['contrast'];n=len(z)
    kernel=(1-alpha)*np.eye(len(b))+alpha*np.exp(-abs(piece['times'][:,None]-piece['times'])/tau)
    covariance=b.T@kernel@b;root=np.linalg.cholesky(covariance);white=np.linalg.solve(root,z)
    scale=float(white@white/n)
    return float(n*np.log(max(scale,1e-15))+2*np.log(np.diag(root)).sum()),scale


def fit_shape(pieces):
    dimensions=sum(len(p['contrast']) for p in pieces)
    if not dimensions:return dict(qualified=False,alpha=0.,tau_s=10.,pieces=0,dimensions=0)
    scores={(a,t):0. for a in ALPHAS for t in TAUS};baseline=0.
    for p in pieces:
        b=p['basis'];z=p['contrast'];m=len(z);baseline+=m*np.log(float(z@z/m))
        for tau in TAUS:
            eigen,axes=np.linalg.eigh(b.T@np.exp(-abs(p['times'][:,None]-p['times'])/tau)@b)
            eigen=np.maximum(eigen,0.);power=(axes.T@z)**2
            for alpha in ALPHAS:
                variance=1-alpha+alpha*eigen;scores[alpha,tau]+=m*np.log(float(np.sum(power/variance)/m))+np.log(variance).sum()
    a,t=min(scores,key=scores.get);gain=baseline-scores[a,t];penalty=2*np.log(dimensions)
    qualified=len(pieces)>=10 and gain>penalty
    return dict(qualified=bool(qualified),alpha=a if qualified else 0.,tau_s=t if qualified else 10.,pieces=len(pieces),dimensions=dimensions,
        radio_REML_gain=float(gain),complexity_penalty=float(penalty),baseline_cost=float(baseline),
        candidates=[dict(alpha=a,tau_s=t,cost=float(s)) for (a,t),s in scores.items()],
        no_GPS_TLE_or_position_residuals_used=True)


def validation(pieces,model):
    baseline=0.;correlated=0.;scale_log=0.;n=0
    for p in pieces:
        white,ws=shape_score(p,0.,10.);colored,cs=shape_score(p,model['alpha'],model['tau_s'])
        baseline+=white;correlated+=colored;n+=len(p['contrast']);scale_log+=len(p['contrast'])*np.log(cs/ws)
    return dict(pieces=len(pieces),dimensions=n,radio_REML_gain=float(baseline-correlated),
        profiled_variance_ratio=float(np.exp(scale_log/n)) if n else 1.,
        positive_target_gain=bool(n and baseline>correlated),
        diagnostic_REML_contrast_score_not_identity_probability=True)
