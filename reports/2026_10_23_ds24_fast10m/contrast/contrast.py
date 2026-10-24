"""Native temporal contrasts with exact shared covariance, no position truth."""
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize


def contrast_score(y, features, variance, groups):
    """Gaussian marginal on orthonormal within-group contrasts, via REML identity.

    K=diag(variance)+features@features.T. Constant group uncertainties cancel.
    No independence approximation or slope removal is made.
    """
    y=np.asarray(y,float); f=np.asarray(features,float); v=np.asarray(variance,float)
    groups=np.asarray(groups)
    if y.ndim!=1 or v.shape!=y.shape or groups.shape!=y.shape or f.shape[0]!=len(y):
        raise ValueError('matching observation dimensions required')
    if not np.isfinite(v).all() or np.any(v<=0):
        raise ValueError('positive finite variances required')
    if not len(y): return 0.
    _,g=np.unique(groups,return_inverse=True)
    counts=np.bincount(g); ng=len(counts)
    if ng==len(y): return 0.
    x=np.eye(ng)[g]/np.sqrt(counts[g,None])
    dinv=1/v; df=f*dinv[:,None]
    small=cho_factor(np.eye(f.shape[1])+f.T@df,lower=True)
    def inv(z):
        z=np.asarray(z); dz=z*dinv if z.ndim==1 else z*dinv[:,None]
        return dz-df@cho_solve(small,f.T@dz)
    iy=inv(y); ix=inv(x); gram=cho_factor(x.T@ix,lower=True)
    b=x.T@iy
    q=float(y@iy-b@cho_solve(gram,b))
    logdet=float(np.log(v).sum()+2*np.log(np.diag(small[0])).sum()
                 +2*np.log(np.diag(gram[0])).sum())
    return q+logdet+(len(y)-ng)*np.log(2*np.pi)


def objective(p, position, powers):
    from ds23_predictive_linear import linear_geometry
    from ds23_height_problem import geometry_features
    c=p.curved_calculate(position) if hasattr(p,'curved_calculate') else p.calculate(position)
    entries=getattr(p,'linear_entries',[])
    if not entries: return float(c['negative_twice_elbo'])
    view,values,sigma,groups,_=linear_geometry(p,entries)
    geometry=geometry_features(view,position,0.)
    u=geometry['features']
    if getattr(p,'events',[]):
        raise ValueError('event nuisance not supported by this frozen variant')
    g=p.noise_groups[p.keep]
    weights=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    train=c['features'][p.keep]
    gram=np.diag(c['coefficient_prior_precision'])+train.T@(train*weights[:,None])
    root=np.linalg.cholesky(gram)
    features=np.linalg.solve(root,u.T).T
    raw=values-view.q*geometry['intercept']-u@c['coefficient']
    return float(c['negative_twice_elbo'])+contrast_score(raw,features,2*sigma**2,groups)


def fit(d,kind,arm,paths,frozen=False,full=False):
    """Five phase refreshes, 48 scalar iterations; original gates applied outside.

    Both native variants start at the same graph parent. Frozen only updates
    curved phase linearization at that fixed position. Calibration remains curved.
    """
    from probe_ds23_frequency_events import summary
    parent=d['arms'][arm]
    x=np.asarray(parent['endpoint_east_north_km'],float)
    reference=np.asarray(parent['phase_reference'],float)
    history=[]
    for _ in range(5):
        p=paths.build(d,kind,arm,reference)
        scalar=(lambda z:float(p.calculate(z)['negative_twice_elbo'])) if full else (lambda z:objective(p,z,d['powers']))
        if not frozen:
            origin=scalar(x)
            result=minimize(lambda z:scalar(z)-origin,x,
                method='SLSQP',bounds=list(zip(p.lower,p.upper)),
                options=dict(maxiter=48,ftol=1e-7,eps=1e-3))
            x=np.asarray(result.x)
            solver=dict(success=bool(result.success),iterations=int(result.nit),message=str(result.message))
        else: solver=dict(success=True,iterations=0,message='position fixed at graph parent')
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(solver=solver,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    saved=summary(p,x,d['entries'])
    saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
                 temporal_contrast_objective=objective(p,x,d['powers']),
                 position_frozen=frozen,objective_used_for_optimization='fixed_parent' if frozen else ('full_native' if full else 'curved_plus_temporal_contrasts'))
    return saved
