"""Gaussian/Gamma variational inference for normalized two-piece phase priors.

Gaussian phase moments are integrated analytically on each side of the mode.
The reported ELBO includes the asymmetric normalization and all entropies.
"""

import numpy as np
from scipy.special import ndtr,digamma,gammaln

from ds23_skew_phase_prior import side_scales
from dsx01_hierarchical_bound import hierarchical_bound


def positive_second_moment(mean,variance):
    mean,variance=np.broadcast_arrays(np.asarray(mean,float),np.asarray(variance,float))
    if np.any(variance<=0) or not np.isfinite(mean).all() or not np.isfinite(variance).all():
        raise ValueError('finite Gaussian means and positive variances required')
    sd=np.sqrt(variance);z=mean/sd;pdf=np.exp(-z*z/2)/np.sqrt(2*np.pi)
    return (mean*mean+variance)*ndtr(z)+mean*sd*pdf


def gamma_kl(shape,rate,prior_shape,prior_rate):
    return ((shape-prior_shape)*digamma(shape)-gammaln(shape)+gammaln(prior_shape)
            +prior_shape*(np.log(rate)-np.log(prior_rate))+shape*(prior_rate/rate-1))


def skew_bound(raw,features,sigma,groups,phase_indices,nu,kappa,*,powers=1.,iterations=256):
    y,u,g=np.asarray(raw,float),np.asarray(features,float),np.asarray(groups)
    index=np.asarray(phase_indices,int)
    if y.ndim!=1 or not len(y) or u.ndim!=2 or u.shape[0]!=len(y) or g.shape!=y.shape or not np.issubdtype(g.dtype,np.integer):
        raise ValueError('matching observations, features and integer noise groups required')
    width=u.shape[1]
    if index.ndim!=1 or len(np.unique(index))!=len(index) or np.any(index<0) or np.any(index>=width):
        raise ValueError('distinct valid phase-coordinate indices required')
    if kappa==0:
        prior=np.full(width,-1,int);prior[index]=np.arange(len(index))
        return hierarchical_bound(y,u,sigma,g,powers=powers,prior_groups=prior if nu is not None else None,
                                  prior_nu=4 if nu is None else nu,iterations=iterations)
    left,right,_=side_scales(kappa,nu)
    s=np.broadcast_to(np.asarray(sigma,float),y.shape)
    if not all(np.isfinite(a).all() for a in (y,u,s)) or np.any(s<=0) or np.any(g<0) or iterations<1:
        raise ValueError('finite observations/features and positive noise/budgets required')
    _,g=np.unique(g,return_inverse=True);counts=np.bincount(g)
    power=np.broadcast_to(np.asarray(powers,float),counts.shape)
    if np.any(power<=0) or np.any(power>1) or not np.isfinite(power).all():
        raise ValueError('fixed likelihood powers in (0,1] required')
    alpha0=beta0=2.;alpha=alpha0+power*counts/2;rate=alpha.copy()
    pa0=(nu/2 if nu is not None else 1.);pb0=((nu-2)/2 if nu is not None else 1.)
    pa=pa0+.5;prior_rate=np.full(len(index),pa/(pa0/pb0))
    blocks=[];a=u/s[:,None];z=y/s
    for k in range(len(counts)):
        use=g==k;cols=np.flatnonzero(np.any(a[use]!=0,axis=0));local=a[use][:,cols]
        blocks.append((cols,local.T@local,local.T@z[use]))
    mean=np.zeros(width);covariance=np.eye(width);history=[]
    c_left,c_right=1/left**2,1/right**2
    old_precision=np.ones(width)
    for _ in range(iterations):
        weight=alpha/rate
        eta=pa/prior_rate if nu is not None else np.ones(len(index))
        variance=np.diag(covariance)[index];sd=np.sqrt(variance);zz=mean[index]/sd
        pdf=np.exp(-zz*zz/2)/np.sqrt(2*np.pi);positive=ndtr(zz)
        precision=np.ones(width);precision[index]=eta*(c_left*(1-positive)+c_right*positive)
        rhs=np.zeros(width);rhs[index]=-eta*sd*pdf*(c_right-c_left)
        gram=np.diag(precision)
        for w,(cols,matrix,b) in zip(power*weight,blocks,strict=True):
            gram[np.ix_(cols,cols)]+=w*matrix;rhs[cols]+=w*b
        root=np.linalg.cholesky(gram);inverse=np.linalg.solve(root,np.eye(width))
        next_covariance=inverse.T@inverse
        next_mean=np.linalg.solve(root.T,np.linalg.solve(root,rhs))
        native=(y-u@next_mean)/s
        variances=np.array([np.sum(next_covariance[np.ix_(cols,cols)]*matrix.T) for cols,matrix,b in blocks])
        energy=np.bincount(g,weights=native*native)+np.maximum(0,variances)
        next_rate=beta0+power*energy/2
        v=np.diag(next_covariance)[index];m=next_mean[index]
        positive_moment=positive_second_moment(m,v)
        prior_energy=c_left*(m*m+v)+(c_right-c_left)*positive_moment
        next_prior_rate=pb0+prior_energy/2 if nu is not None else prior_rate
        mean_change=np.max(abs(next_mean-mean)/np.maximum(1,np.sqrt(np.diag(next_covariance))))
        change=max(float(np.max(abs(np.log(next_rate/rate)))),
            float(np.max(abs(np.log(next_prior_rate/prior_rate)),initial=0)),
            float(np.max(abs(np.log(precision/old_precision)))),
            float(mean_change))
        mean,covariance=next_mean,next_covariance
        rate,prior_rate=next_rate,next_prior_rate;old_precision=precision
        history.append(change)
        if change<1e-5:break
    # q(Gamma) is optimal conditional on the final q(Gaussian). Its covariance
    # remains gram^-1; callers must use gaussian_precision for prediction.
    weight=alpha/rate;eta=pa/prior_rate if nu is not None else np.ones(len(index))
    elog_eta=digamma(pa)-np.log(prior_rate) if nu is not None else np.zeros(len(index))
    v=np.diag(covariance);m=mean[index]
    pm=positive_second_moment(m,v[index]);prior_energy=c_left*(m*m+v[index])+(c_right-c_left)*pm
    gaussian=np.ones(width,bool);gaussian[index]=False
    prior_kl=(np.sum((mean*mean+v)[gaussian])+np.sum(eta*prior_energy-elog_eta+2*np.log((left+right)/2))
              -width+2*np.log(np.diag(root)).sum())
    phase_gamma_kl=2*np.sum(gamma_kl(pa,prior_rate,pa0,pb0)) if nu is not None else 0.
    prior_kl+=phase_gamma_kl
    if prior_kl < -1e-7:raise ArithmeticError('negative joint prior KL')
    prior_kl=max(0.,float(prior_kl))
    native=y-u@mean;innovation=native/s*np.sqrt((power*weight)[g])
    variance_cost=float(np.sum(power*weight*np.maximum(0,variances)))
    ratio=rate/beta0;noise_gamma=np.maximum(0,2*alpha*(np.log(ratio)+1/ratio-1))
    normalization=float(np.sum(power[g]*(np.log(2*np.pi)+2*np.log(s)))
        +np.sum(2*gammaln(alpha0)-2*gammaln(alpha)+power*counts*np.log(beta0)))
    residual=np.r_[innovation,np.sqrt(variance_cost),np.sqrt(prior_kl),np.sqrt(noise_gamma)]
    return dict(residual=residual,coefficient=mean,conditional_residual_hz=native,
        gaussian_precision=gram,gaussian_covariance=covariance,
        noise_precision=weight,coefficient_prior_precision=precision,
        prior_group_precision=eta,normalization_constant=normalization,
        negative_twice_elbo=float(residual@residual+normalization),
        quadratic=float(innovation@innovation+np.sum(precision*mean*mean)),
        logvolume=float(max(0,2*np.log(np.diag(root)).sum()-np.log(precision).sum())),
        noise_gamma_cost=float(noise_gamma.sum()),prior_gamma_cost=float(phase_gamma_kl),
        gamma_cost=float(noise_gamma.sum()+phase_gamma_kl),prior_KL_cost=prior_kl,
        effective_observations=float(power@counts),precision_iterations=len(history),
        final_log_precision_change=history[-1],phase_side_scales=[left,right],
        noise_shape=alpha,noise_rate=rate,phase_shape=pa,phase_rate=prior_rate)
