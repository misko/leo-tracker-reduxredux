"""Independent expected-log-density audit for shared Gaussian/Gamma fits."""

import numpy as np
from scipy.special import digamma,gammaln


def position_information(derivative,features,weight,prior_precision):
    """Schur information after Gaussian nuisance elimination, at fixed weights.

    This local diagnostic conditions on identities, Gamma variables and the
    adopted physical model. It is not a calibrated confidence interval.
    """
    j,u,w,v=map(np.asarray,(derivative,features,weight,prior_precision))
    if j.shape!=(len(w),2) or u.shape[0]!=len(w) or v.shape!=(u.shape[1],) or np.any(w<=0) or np.any(v<=0):
        raise ValueError('two position derivatives, matching nuisances and positive weights/priors required')
    gram=np.diag(v)+u.T@(w[:,None]*u);cross=j.T@(w[:,None]*u)
    raw=j.T@(w[:,None]*j);projected=raw-cross@np.linalg.solve(gram,cross.T);projected=(projected+projected.T)/2
    covariance=np.linalg.inv(projected);eig,axes=np.linalg.eigh(covariance)
    if np.any(eig<=0):raise ValueError('positive local position information required')
    return dict(local_position_covariance_km2=covariance,local_position_axis_SD_km=np.sqrt(eig),
        position_information_before_nuisance=raw,position_information_after_nuisance=projected,
        fraction_trace_information_retained=float(np.trace(projected)/np.trace(raw)),
        position_axes_east_north=axes,conditional_on_Gamma_and_identities_not_accuracy=True)


def expected_log_density(raw,features,sigma,groups,powers,mean,scales,coefficient,
                         noise_precision,coefficient_precision,phase_slots,nu):
    """Compute -2 ELBO from distribution expectations and entropies.

    Unlike the inference residual construction, explicitly retain posterior
    coefficient covariance and Gamma entropy terms. Coordinates here are the
    original unit-prior latent variables before physical scaling.
    """
    y,u,s,g=np.asarray(raw),np.asarray(features),np.asarray(sigma),np.asarray(groups)
    _,g=np.unique(g,return_inverse=True);power=np.asarray(powers);count=np.bincount(g)
    a=u*np.asarray(scales)/s[:,None];z=(y-u@mean)/s
    value=(np.asarray(coefficient)-mean)/scales
    precision=np.asarray(coefficient_precision)*scales**2
    tau=np.asarray(noise_precision);alpha=2+power*count/2;rate=alpha/tau
    gram=np.diag(precision)+a.T@((power[g]*tau[g])[:,None]*a)
    cov=np.linalg.inv(gram);posterior=np.linalg.solve(gram,a.T@(power[g]*tau[g]*z))
    residual=z-a@value;variance=np.einsum('ij,jk,ik->i',a,cov,a)
    elogtau=digamma(alpha)-np.log(rate)
    likelihood=float(np.sum(power[g]*(-.5*np.log(2*np.pi)-np.log(s)+.5*elogtau[g]-.5*tau[g]*(residual**2+variance))))
    elogv=np.zeros(len(value));prior_gamma=entropy_gamma=0.
    if nu is not None:
        slots=np.asarray(phase_slots,int);pa0,pb0=nu/2,(nu-2)/2;pa=pa0+.5;v=precision[slots];prate=pa/v
        elog=digamma(pa)-np.log(prate);elogv[slots]=elog
        prior_gamma=float(np.sum(pa0*np.log(pb0)-gammaln(pa0)+(pa0-1)*elog-pb0*v))
        entropy_gamma=float(np.sum(pa-np.log(prate)+gammaln(pa)+(1-pa)*digamma(pa)))
    prior_theta=float(-.5*np.sum(np.log(2*np.pi)-elogv+precision*(value**2+np.diag(cov))))
    prior_tau=float(np.sum(2*np.log(2)-gammaln(2)+elogtau-2*tau))
    entropy_tau=float(np.sum(alpha-np.log(rate)+gammaln(alpha)+(1-alpha)*digamma(alpha)))
    entropy_theta=float(.5*(len(value)*(1+np.log(2*np.pi))-np.linalg.slogdet(gram)[1]))
    return dict(negative_twice_elbo=-2*(likelihood+prior_theta+prior_tau+prior_gamma+entropy_theta+entropy_tau+entropy_gamma),
        maximum_coefficient_normal_equation_error=float(np.max(abs(value-posterior))),
        covariance_physical=cov*scales[:,None]*scales[None,:],
        prior_precision_physical=precision/scales**2)
