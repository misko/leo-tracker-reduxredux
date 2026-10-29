"""Random grouped validation and Gaussian prediction for track annotation."""
import numpy as np
from scipy.linalg import cho_solve, solve_triangular


def family_folds(labels,eligible,*,seed,folds=3):
    """Random whole-family folds, retaining every receiver/channel together."""
    j=np.asarray(labels);use=np.asarray(eligible,bool)
    if j.ndim!=1 or use.shape!=j.shape or not np.issubdtype(j.dtype,np.integer) or folds<2:
        raise ValueError('integer family labels, matching mask and at least two folds required')
    families=np.unique(j[use])
    if len(families)<folds:raise ValueError('not enough independently grouped families')
    shuffled=np.random.default_rng(seed).permutation(families);result=[]
    for k in range(folds):
        withheld=np.sort(shuffled[k::folds]);held=use&np.isin(j,withheld);train=use&~held
        result.append((train,held,dict(seed=int(seed),fold=k,held_families=withheld.tolist(),
            training_families=np.unique(j[train]).tolist(),held_points=int(held.sum()),training_points=int(train.sum()))))
    return result


def grouped_split(times, focus_times, *, seed, block_s=12., guard_s=2.):
    """One scan-wide partition; target groups guarantee a useful validation set.

    All simultaneous receiver/channel observations share a block assignment.
    A guard removes training observations near held-block boundaries.
    """
    t=np.asarray(times,float);focus=np.asarray(focus_times,float)
    if t.ndim!=1 or focus.ndim!=1 or not len(t) or not len(focus) or not np.isfinite(t).all() or not np.isfinite(focus).all():
        raise ValueError('finite nonempty time vectors required')
    if not np.isfinite([block_s,guard_s]).all() or block_s<=0 or not 0<=guard_s<block_s/2:
        raise ValueError('positive blocks and smaller nonnegative guard required')
    groups=np.floor(t/block_s).astype(int);fg=np.unique(np.floor(focus/block_s).astype(int))
    available=np.unique(groups)
    if len(fg)<3 or not set(fg)<=set(available):raise ValueError('focus needs at least three observed blocks')
    rng=np.random.default_rng(seed)
    chosen=set(rng.choice(fg,max(1,int(np.ceil(len(fg)*.25))),replace=False).tolist())
    rest=np.array(sorted(set(available)-set(fg)),int)
    if len(rest):chosen.update(rng.choice(rest,int(np.ceil(len(rest)*.25)),replace=False).tolist())
    held=np.isin(groups,list(chosen));train=~held
    for g in chosen:train&=~((t>=g*block_s-guard_s)&(t<=(g+1)*block_s+guard_s))
    return train,held,dict(seed=int(seed),block_s=block_s,guard_s=guard_s,
        held_blocks=sorted(chosen),training_points=int(train.sum()),held_points=int(held.sum()),purged_points=int((~train&~held).sum()))


def predictive_score(raw, design, coefficient_precision, sigma):
    """Gaussian held density integrating training coefficient uncertainty.

    Position and learned noise precision are plug-in estimates, not integrated.
    """
    y=np.asarray(raw,float);u=np.asarray(design,float);g=np.asarray(coefficient_precision,float)
    s=np.broadcast_to(np.asarray(sigma,float),y.shape)
    if y.ndim!=1 or not len(y) or u.ndim!=2 or u.shape[0]!=len(y) or g.shape!=(u.shape[1],u.shape[1]):
        raise ValueError('matching nonempty response, design and precision required')
    if not all(np.isfinite(x).all() for x in (y,u,g,s)) or np.any(s<=0) or not np.allclose(g,g.T):
        raise ValueError('finite inputs, positive noise and symmetric precision required')
    root=np.linalg.cholesky(g)
    covariance=np.diag(s*s)+u@cho_solve((root,True),u.T)
    covariance=(covariance+covariance.T)/2
    chol=np.linalg.cholesky(covariance);z=solve_triangular(chol,y,lower=True)
    objective=float(z@z+2*np.log(np.diag(chol)).sum()+len(y)*np.log(2*np.pi))
    return dict(negative_twice_log_density=objective,points=len(y),rms_hz=float(np.sqrt(np.mean(y*y))),
                normalized_quadratic=float(z@z/len(y)),prediction_sigma_hz=np.sqrt(np.diag(covariance)))


def polynomial_reference(times, values, training, held, *, max_order=4, noise_floor_hz=40.):
    """Training-selected polynomial reference: a model-gap diagnostic, not ID.

    Only training values select order, coefficients and residual noise. Geometry
    may use all timestamps. Parameter covariance is propagated to held points.
    """
    t,y=np.asarray(times,float),np.asarray(values,float)
    train,test=np.asarray(training,bool),np.asarray(held,bool)
    if t.shape!=y.shape or t.ndim!=1 or train.shape!=t.shape or test.shape!=t.shape or np.any(train&test):
        raise ValueError('matching disjoint masks and time/value vectors required')
    if train.sum()<max_order+3 or not test.any() or np.ptp(t)<=0 or not np.isfinite(t).all() or not np.isfinite(y).all() or noise_floor_hz<=0:
        raise ValueError('finite samples with sufficient training/held support required')
    z=2*(t-t.min())/np.ptp(t)-1;offers=[]
    for order in range(1,max_order+1):
        u=np.polynomial.legendre.legvander(z,order);a=u[train];coef=np.linalg.lstsq(a,y[train],rcond=None)[0]
        r=y[train]-a@coef;n=int(train.sum());sigma2=max(float(r@r/n),noise_floor_hz**2)
        offers.append(dict(order=order,training_bic=float(n*np.log(sigma2)+(order+1)*np.log(n)),
            coefficient=coef,design=u,sigma2=sigma2))
    best=min(offers,key=lambda q:q['training_bic']);u=best['design'];sigma=np.sqrt(best['sigma2'])
    score=predictive_score(y[test]-u[test]@best['coefficient'],u[test],u[train].T@u[train]/best['sigma2'],sigma)
    return dict(order=best['order'],training_bic=best['training_bic'],training_noise_hz=float(sigma),held=score,
                coefficient=best['coefficient'],prediction_hz=u@best['coefficient'])


def replay_split(times, receipt):
    """Apply a recorded scan-wide assignment to a subset of original points."""
    t=np.asarray(times,float);block=receipt['block_s'];guard=receipt['guard_s'];chosen=receipt['held_blocks']
    held=np.isin(np.floor(t/block).astype(int),chosen);train=~held
    for g in chosen:train&=~((t>=g*block-guard)&(t<=(g+1)*block+guard))
    return train,held


def identity_consensus(folds, *, minimum_folds=3, minimum_margin=10., score_name='joint'):
    """Conservative identity annotation; never authorizes a position update.

    Margins compare the same held observations under competing joint models.
    This is conditional predictive evidence, not a calibrated identity posterior.
    """
    votes=[]
    if len(folds)<minimum_folds:return dict(status='insufficient_partitions',norad=None,votes=[])
    for fold in folds:
        proposals=fold.get('proposals',[])
        if len({p['norad'] for p in proposals})<2:return dict(status='insufficient_competitors',norad=None,votes=votes)
        for arm in ('c0','fitted_c'):
            ordered=sorted(proposals,key=lambda q:q['arms'][arm]['scores'][score_name]['negative_twice_log_density'])
            best,second=ordered[:2];v=best['arms'][arm]
            score=v['scores'][score_name]['negative_twice_log_density']
            margin=second['arms'][arm]['scores'][score_name]['negative_twice_log_density']-score
            finite=np.isfinite([score,margin,v['scores']['target']['rms_hz'],v['final_phase_change_s'],v['minimum_target_elevation_deg']]).all()
            adequate=bool(finite and v['scores']['target']['rms_hz']<=450 and v['final_phase_change_s']<=.01 and v['minimum_target_elevation_deg']>=0)
            votes.append(dict(seed=fold['seed'],arm=arm,norad=best['norad'],runner_up=second['norad'],margin=float(margin),adequate=adequate))
    common={v['norad'] for v in votes};norad=next(iter(common)) if len(common)==1 else None
    status=('unstable_identity' if norad is None else 'prediction_mismatch' if not all(v['adequate'] for v in votes)
            else 'ambiguous_identity' if min(v['margin'] for v in votes)<minimum_margin else 'conditionally_supported_identity')
    return dict(status=status,norad=norad,votes=votes,minimum_margin=min(v['margin'] for v in votes),
                position_inclusion_authorized=False,conditional_on_graph_and_competitor_search=True)
