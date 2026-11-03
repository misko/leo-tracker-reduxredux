"""Independent Gaussian information alongside existing robust RF factors.

Research-only extension. The original Student phase and Gamma noise priors are
retained; Gaussian measurements have fixed precision and no likelihood power.
An empty measurement set delegates to the frozen original implementation.
"""

import numpy as np
from scipy.special import gammaln
from dsx01_hierarchical_bound import hierarchical_bound


def gaussian_factor_bound(raw,features,sigma,groups,factor_values,factor_design,factor_sigma,
                          *,prior_groups=None,powers=1.,noise_nu=4.,prior_nu=4.,iterations=256):
    y,u,g=np.asarray(raw,float),np.asarray(features,float),np.asarray(groups)
    z,d,sf=np.asarray(factor_values,float),np.asarray(factor_design,float),np.asarray(factor_sigma,float)
    if (y.ndim!=1 or not len(y) or u.ndim!=2 or len(u)!=len(y) or g.shape!=y.shape
            or not np.issubdtype(g.dtype,np.integer) or np.any(g<0)
            or z.ndim!=1 or d.shape!=(len(z),u.shape[1]) or sf.shape!=z.shape
            or any(not np.isfinite(v).all() for v in (y,u,z,d,sf)) or np.any(sf<=0)):
        raise ValueError('finite matching observations and independent Gaussian factors required')
    if not len(z):
        return hierarchical_bound(y,u,sigma,g,prior_groups=prior_groups,powers=powers,
            noise_nu=noise_nu,prior_nu=prior_nu,iterations=iterations)
    s=np.broadcast_to(np.asarray(sigma,float),y.shape)
    if (np.any(s<=0) or not np.isfinite(s).all() or noise_nu<=0 or prior_nu<=2 or iterations<1
            or not np.isfinite(noise_nu+prior_nu)):
        raise ValueError('positive finite noise, degrees and iteration budget required')
    _,g=np.unique(g,return_inverse=True);counts=np.bincount(g);width=u.shape[1]
    power=np.broadcast_to(np.asarray(powers,float),counts.shape)
    if np.any(power<=0) or np.any(power>1) or not np.isfinite(power).all():
        raise ValueError('fixed positive RF likelihood powers at most one required')
    prior=np.full(width,-1,int) if prior_groups is None else np.asarray(prior_groups)
    if prior.shape!=(width,) or not np.issubdtype(prior.dtype,np.integer) or np.any(prior< -1):
        raise ValueError('one Student prior group or minus one per coefficient required')
    selected=prior>=0;prior=prior.copy();_,prior[selected]=np.unique(prior[selected],return_inverse=True)
    dimensions=np.bincount(prior[selected]);a0=b0=noise_nu/2;alpha=a0+power*counts/2
    pa0,pb0=prior_nu/2,(prior_nu-2)/2;pa=pa0+dimensions/2;v0=pa0/pb0
    rate=alpha.copy();prate=pa/v0
    a,r=u/s[:,None],y/s;af,rf=d/sf[:,None],z/sf
    fixed_gram=af.T@af;fixed_rhs=af.T@rf;blocks=[]
    for k in range(len(counts)):
        use=g==k;cols=np.flatnonzero(np.any(a[use]!=0,axis=0));local=a[use][:,cols]
        blocks.append((cols,local.T@local,local.T@r[use]))

    def posterior(weight,precision):
        gram=np.diag(precision)+fixed_gram;rhs=fixed_rhs.copy()
        for w,(cols,matrix,b) in zip(power*weight,blocks,strict=True):
            gram[np.ix_(cols,cols)]+=w*matrix;rhs[cols]+=w*b
        root=np.linalg.cholesky(gram);mean=np.linalg.solve(root.T,np.linalg.solve(root,rhs))
        inverse=np.linalg.solve(root,np.eye(width));covariance=inverse.T@inverse
        volume=max(0.,float(2*np.log(np.diag(root)).sum()-np.log(precision).sum()))
        return mean,covariance,volume,gram

    history=[]
    for _ in range(iterations):
        weight,v=alpha/rate,pa/prate;precision=np.ones(width);precision[selected]=v[prior[selected]]
        coefficient,covariance,_,_=posterior(weight,precision)
        native=(y-u@coefficient)/s
        variance=np.array([np.sum(covariance[np.ix_(cols,cols)]*matrix.T) for cols,matrix,_ in blocks])
        energy=np.bincount(g,weights=native**2)+np.maximum(0,variance)
        next_rate=b0+power*energy/2
        pe=np.bincount(prior[selected],weights=(coefficient**2+np.diag(covariance))[selected],minlength=len(dimensions))
        next_prate=pb0+pe/2
        change=max(float(np.max(abs(np.log(next_rate/rate)))),float(np.max(abs(np.log(next_prate/prate)),initial=0)))
        rate,prate=next_rate,next_prate;history.append(change)
        if change<1e-5:break
    weight,v=alpha/rate,pa/prate;precision=np.ones(width);precision[selected]=v[prior[selected]]
    coefficient,covariance,volume,gram=posterior(weight,precision)
    native=y-u@coefficient;innovation=native/s*np.sqrt((power*weight)[g])
    fixed_innovation=(z-d@coefficient)/sf
    ratio=rate/b0
    ng=np.maximum(0,2*alpha*(np.log(ratio)+1/ratio-1))
    pg=np.maximum(0,2*pa0*(np.log(v0/v)+v/v0-1))
    nc=2*gammaln(a0)-2*gammaln(alpha)+power*counts*np.log(b0)
    pc=2*gammaln(pa0)-2*gammaln(pa)+dimensions*np.log(pa0)+2*pa*np.log(pa/pa0)-dimensions
    normalization=float(np.sum(power[g]*(np.log(2*np.pi)+2*np.log(s)))+nc.sum()+pc.sum()
                        +len(z)*np.log(2*np.pi)+2*np.log(sf).sum())
    residual=np.r_[innovation,coefficient*np.sqrt(precision),np.sqrt(volume),np.sqrt(ng),np.sqrt(pg),fixed_innovation]
    return dict(residual=residual,coefficient=coefficient,coefficient_covariance=covariance,
        coefficient_posterior_precision=gram,coefficient_prior_precision=precision,
        quadratic=float(innovation@innovation+np.sum(precision*coefficient**2)+fixed_innovation@fixed_innovation),
        logvolume=volume,conditional_residual_hz=native,noise_precision=weight,prior_group_precision=v,
        noise_gamma_cost=float(ng.sum()),prior_gamma_cost=float(pg.sum()),gamma_cost=float(ng.sum()+pg.sum()),
        normalization_constant=normalization,negative_twice_elbo=float(residual@residual+normalization),
        effective_observations=float(power@counts),independent_Gaussian_observations=len(z),
        precision_iterations=len(history),final_log_precision_change=history[-1],
        noise_shape=alpha,noise_rate=rate,prior_shape=pa,prior_rate=prate)


def greedy_phase_design(covariance,phase_coordinates,measurement_sigma_s,budget):
    """A-optimal local design: reduce 2D position variance, without phase truth."""
    c=np.asarray(covariance,float).copy();coords=np.asarray(phase_coordinates)
    if (c.ndim!=2 or c.shape[0]!=c.shape[1] or len(c)<2 or not np.allclose(c,c.T)
            or not np.isfinite(c).all() or coords.ndim!=1 or not np.issubdtype(coords.dtype,np.integer)
            or len(set(coords))!=len(coords) or np.any(coords<2) or np.any(coords>=len(c))
            or not np.isfinite(measurement_sigma_s) or measurement_sigma_s<=0
            or not isinstance(budget,int) or budget<0):
        raise ValueError('joint position/physical-phase covariance and positive measurement SD required')
    np.linalg.cholesky(c)
    chosen=[];history=[]
    for _ in range(min(budget,len(coords))):
        remaining=[int(k) for k in coords if k not in chosen]
        gains=[float(c[:2,k]@c[:2,k]/(c[k,k]+measurement_sigma_s**2)) for k in remaining]
        best=remaining[int(np.argmax(gains))];before=float(np.trace(c[:2,:2]))
        c-=np.outer(c[:,best],c[best])/(c[best,best]+measurement_sigma_s**2)
        chosen.append(best);history.append(dict(coordinate=best,trace_before_km2=before,
            trace_after_km2=float(np.trace(c[:2,:2])),gain_km2=max(gains)))
    return dict(coordinates=chosen,history=history,covariance=c)
