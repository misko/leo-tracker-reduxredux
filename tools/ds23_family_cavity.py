"""Numerical Gaussian predictive screens for a held complete satellite family."""

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import gammaln
from leo.analysis.research.retained_track_likelihood import PERIOD


def coarse_phase_scores(values,radio_mean,frequency,derivative,phase_sigma,covariance,groups):
    """Integrate one phase per candidate against the same correlated base noise.

    Integer aliases are discrete proposals selected per complete fragment.
    The phase prior is moment-matched Gaussian for nomination only.
    """
    y,r,f,d,sd,c,g=map(np.asarray,(values,radio_mean,frequency,derivative,phase_sigma,covariance,groups))
    if f.shape!=d.shape or f.ndim!=2 or f.shape[1]!=len(y) or r.shape!=y.shape or c.shape!=(len(y),len(y)) or sd.shape!=(len(f),):
        raise ValueError('matching family data, candidate derivatives and covariance required')
    root=np.linalg.cholesky(c);aliases=np.zeros((len(f),int(g.max())+1),int)
    raw=y[None,:]-r[None,:]-f
    for k in range(aliases.shape[1]):
        use=g==k;aliases[:,k]=np.rint(-raw[:,use].mean(axis=1)/PERIOD).astype(int)
    raw=raw+aliases[:,g]*PERIOD
    b=solve_triangular(root,raw.T,lower=True);a=solve_triangular(root,(d*sd[:,None]).T,lower=True)
    norm=np.sum(a*a,axis=0);projection=np.sum(a*b,axis=0)
    scores=np.sum(b*b,axis=0)-projection**2/(1+norm)+np.log1p(norm)
    scores+=2*np.log(np.diag(root)).sum()+len(y)*np.log(2*np.pi)
    return dict(score=scores,aliases=aliases,phase_z=projection/(1+norm))


def unused_student_gap(nu):
    """Exact -2 variational gap of an entirely unused unit-variance phase prior."""
    if nu is None:return 0.
    a=float(nu)/2;b=a+.5
    return float(2*gammaln(a)-2*gammaln(b)+np.log(a)+2*b*np.log(b/a)-1)


def predictive_density_reference(raw,design,covariance,sigma):
    """Independent covariance-density calculation, dense or economy SVD."""
    y,u,c,s=map(np.asarray,(raw,design,covariance,sigma))
    if len(y)<=250:
        matrix=np.diag(s**2)+u@c@u.T
        return float(y@np.linalg.solve(matrix,y)+np.linalg.slogdet(matrix)[1]+len(y)*np.log(2*np.pi)),'dense'
    a=(u@np.linalg.cholesky(c))/s[:,None];b=y/s
    left,value,_=np.linalg.svd(a,full_matrices=False);projection=left.T@b
    objective=b@b-np.sum(projection**2*value**2/(1+value**2))+np.log1p(value**2).sum()
    objective+=2*np.log(s).sum()+len(y)*np.log(2*np.pi)
    return float(objective),'economy_SVD'


def legacy_phase_reference(history,initial,posterior):
    """Recover the reference used by the final fit, excluding its posterior update."""
    if len(history)<2 or any('fit' not in h or 'parameters' not in h['fit'] for h in history):
        raise ValueError('recorded phase-round fit endpoints required for reference replay')
    reference=np.asarray(initial,float).copy()
    for step in history[:-1]:reference=np.clip(posterior(reference,np.asarray(step['fit']['parameters'])), -15,15)
    return reference


def directional_orbit_frequency_reference(bank,modes,coefficient,times,phase,latitude,longitude):
    """Independent finite derivative along the fitted physical orbit direction.

    Richardson extrapolation removes the central difference's quadratic bias.
    Checking two extrapolations detects an unsuitable numerical step without
    changing the residual tolerance or the inference's linear orbital model.
    """
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    coefficient=np.asarray(coefficient,float);times=np.asarray(times,float)
    if np.asarray(bank['position_km']).shape[0]!=1:raise ValueError('one nominated satellite required')
    direction={field:np.einsum('k,ktd->td',coefficient,np.asarray(modes[field]))[None,:,:]
               for field in ['position_km','velocity_km_s']}
    size=float(np.max(np.linalg.norm(direction['position_km'],axis=-1)))
    step=.002/max(1.,size/1000.)
    def central(h):
        values=[]
        for sign in [-1,1]:
            changed=dict(time_s=bank['time_s'],**{field:np.asarray(bank[field])+sign*h*direction[field] for field in direction})
            values.append(paired_phase_frequency(changed,times,np.zeros(len(times),int),np.array([phase]),latitude,longitude)[0])
        return (values[1]-values[0])/(2*h)
    a,b,c=[central(step/k) for k in [1,2,4]]
    coarse=(4*b-a)/3;fine=(4*c-b)/3
    return fine,float(np.max(abs(fine-coarse)))
