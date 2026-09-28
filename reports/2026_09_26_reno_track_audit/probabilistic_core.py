"""Offline pure numerical timing-prior experiment; no storage dependencies."""
import numpy as np
from scipy.special import gammaln, logsumexp
from scipy.stats import t as student_t


def student_logpdf(residual, scale, df=4.):
    if scale <= 0 or df <= 0:
        raise ValueError('positive scale and degrees of freedom required')
    return (gammaln((df+1)/2)-gammaln(df/2)-.5*np.log(df*np.pi)
            -np.log(scale)-(df+1)/2*np.log1p((np.asarray(residual)/scale)**2/df))


def prior_weights(grid, scale):
    lp=student_logpdf(grid,scale)
    return lp-logsumexp(lp)


def fit_profiles(measured, prediction, train, scale):
    """Training-only robust CFO profile; CFO is NOT marginalized in this prototype."""
    train=np.asarray(train,bool)
    if not train.any() or train.all():
        raise ValueError('both partitions required')
    raw=measured[None,:]-prediction
    x=raw[:,train]
    offset=np.median(x,axis=1)
    for _ in range(80):
        w=5/(4+(x-offset[:,None])**2/scale**2)
        updated=np.sum(w*x,axis=1)/np.sum(w,axis=1)
        if np.max(np.abs(updated-offset))<1e-7:
            offset=updated
            break
        offset=updated
    residual=raw-offset[:,None]
    ll=student_logpdf(residual,scale)
    return {'train':ll[:,train].sum(axis=1),'test':ll[:,~train].sum(axis=1),
            'test_mse':(residual[:,~train]**2).mean(axis=1),'offset':offset,
            'n_test':int((~train).sum())}


def summarize_grid(grid, logp):
    p=np.exp(logp-logsumexp(logp)); cdf=np.cumsum(p)
    return {'mean_s':float(p@grid),'map_s':float(grid[np.argmax(p)]),
            'central_90_s':[float(grid[min(np.searchsorted(cdf,q),len(grid)-1)]) for q in (.05,.95)],
            'edge_mass':float(p[0]+p[-1]) if len(p)>1 else 0.}


def evaluate(rows, total_grid, delta_grid, clock_grid, clock_sigma, scales, *, per_track=False, flat=False):
    """Exact discrete timing integration conditional on profiled per-track CFO.

    Shared satellite factors are applied once, not once per track. Observation
    likelihood assumes conditional independence; scores are diagnostic only.
    """
    step=total_grid[1]-total_grid[0]
    ix=np.rint((clock_grid[:,None]+delta_grid[None,:]-total_grid[0])/step).astype(int)
    if np.any(ix<0) or np.any(ix>=len(total_grid)):
        raise ValueError('prediction grid does not cover clock plus satellite support')
    groups={}
    for r in rows:
        key=r['track_id'] if per_track else r['satellite_id']
        groups.setdefault(key,[]).append(r)
    cp=np.zeros(len(clock_grid)) if clock_sigma is None else -.5*(clock_grid/clock_sigma)**2
    cp-=logsumexp(cp)
    train_clock=cp.copy(); joint_clock=cp.copy(); factors={}
    for key,rr in groups.items():
        lp=np.full(len(delta_grid),-np.log(len(delta_grid))) if flat else prior_weights(delta_grid,scales[rr[0]['satellite_id']])
        train=sum(r['train'][ix] for r in rr)+lp
        joint=train+sum(r['test'][ix] for r in rr)
        z=logsumexp(train,axis=1)
        train_clock+=z; joint_clock+=logsumexp(joint,axis=1)
        factors[key]=(train-z[:,None],rr)
    clock_post=train_clock-logsumexp(train_clock)
    track_out=[]; mse=0.; weight=0; boundary=[]
    for key,(conditional,rr) in factors.items():
        joint_p=np.exp(clock_post[:,None]+conditional)
        boundary.append(float(joint_p[:,0].sum()+joint_p[:,-1].sum()) if len(delta_grid)>1 else 0.)
        total_p=np.bincount(ix.ravel(),weights=joint_p.ravel(),minlength=len(total_grid))
        timing=summarize_grid(total_grid,np.log(np.maximum(total_p,1e-300)))
        for r in rr:
            expected_mse=float(total_p@r['test_mse'])
            mse+=r['weight_s']*expected_mse; weight+=r['weight_s']
            track_out.append({'track_id':r['track_id'],'satellite_id':r['satellite_id'],
                'timing':timing,'posterior_expected_test_rms_hz':float(np.sqrt(expected_mse))})
    n=sum(r['n_test'] for r in rows)
    score=float(logsumexp(joint_clock)-logsumexp(train_clock))
    return {'conditional_predictive_log_score':score,'negative_log_score_per_test_observation':-score/n,
            'training_log_integrated_profile_likelihood':float(logsumexp(train_clock)),
            'max_satellite_boundary_mass':max(boundary),
            'test_observations':n,'uncapped_posterior_expected_weighted_rms_hz':float(np.sqrt(mse/weight)),
            'clock':summarize_grid(clock_grid,clock_post),'tracks':track_out}


AGE_EDGES=np.array([0.,6.,12.,24.,48.,72.,120.,np.inf])


def calibrate_scales(rows):
    """Zero-centered robust t4 scales, with pooled fallback and 0.05 s floor.

    Age trend is not forced monotone; the archive must demonstrate its shape.
    """
    tau=np.array([r['equivalent_tau_s'] for r in rows]); age=np.array([r['age_hours'] for r in rows])
    if len(tau)<50:
        raise ValueError('insufficient historical pairs')
    divisor=student_t.ppf(.84,df=4)
    pooled=max(.05,float(np.quantile(np.abs(tau),.68)/divisor))
    out=[]
    for lo,hi in zip(AGE_EDGES[:-1],AGE_EDGES[1:]):
        x=tau[(age>=lo)&(age<hi)]
        scale=max(.05,float(np.quantile(np.abs(x),.68)/divisor)) if len(x)>=30 else pooled
        out.append({'lower_h':float(lo),'upper_h':None if np.isinf(hi) else float(hi),
            'n':len(x),'scale_s':scale,'pooled_fallback':len(x)<30,
            'median_s':float(np.median(x)) if len(x) else None})
    return out


def scale_at(age, bins):
    return next(b['scale_s'] for b in bins if age>=b['lower_h'] and (b['upper_h'] is None or age<b['upper_h']))
