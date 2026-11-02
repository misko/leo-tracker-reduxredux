"""Exact regional-box integration within the frozen local Gaussian model."""
import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import log_ndtr
from scipy.stats import multivariate_normal


def log_difference(a,b):
    if b>=a:return -np.inf
    return float(a+np.log(-np.expm1(b-a)))


def log_normal_interval(lo,hi):
    if not hi>lo:return -np.inf
    if lo>0:return log_difference(log_ndtr(-lo),log_ndtr(-hi))
    return log_difference(log_ndtr(hi),log_ndtr(lo))


def box_log_probability(mean,covariance,lower=(-12.5,-12.5),upper=(12.5,12.5)):
    """Deterministic scaled 1-D conditional-normal quadrature, in log units.

    The integrand is strongly log-concave. Integrating within 14 standard
    deviations of its constrained mode discards only negligible Gaussian tails.
    Scaling at that mode avoids underflow for very small rectangle masses.
    """
    mean=np.asarray(mean,float);cov=np.asarray(covariance,float)
    low=np.asarray(lower,float);high=np.asarray(upper,float)
    if mean.shape!=(2,)or cov.shape!=(2,2)or np.any(high<=low):raise ValueError('2-D Gaussian and positive box required')
    np.linalg.cholesky(cov)
    sd=np.sqrt(np.diag(cov));rho=cov[0,1]/np.prod(sd)
    conditional_sd=sd[1]*np.sqrt(1-rho*rho)
    a,b=(low[0]-mean[0])/sd[0],(high[0]-mean[0])/sd[0]
    def logf(z):
        center=mean[1]+rho*sd[1]*z
        return -.5*z*z-.5*np.log(2*np.pi)+log_normal_interval((low[1]-center)/conditional_sd,(high[1]-center)/conditional_sd)
    # The maximization is solely numerical quadrature scaling, never an RF or
    # nuisance fit. Strong log-concavity gives a unique constrained mode.
    search_low=max(a,-1e4);search_high=min(b,1e4)
    if search_low>=search_high:search_low,search_high=a,b
    optimum=minimize_scalar(lambda z:-logf(z),bounds=(search_low,search_high),method='bounded',options={'xatol':1e-10})
    mode=max([float(optimum.x),a,b,np.clip(0,a,b)],key=logf);peak=logf(mode)
    left=max(a,mode-14.);right=min(b,mode+14.)
    integrand=lambda z:float(np.exp(logf(z)-peak))
    integral,error=quad(integrand,left,right,epsabs=1e-12,epsrel=1e-11,limit=200,points=[mode]if left<mode<right else None)
    if integral<=0 or not np.isfinite(peak):raise FloatingPointError('Gaussian box quadrature failed')
    return dict(log_probability=float(min(0.,peak+np.log(integral))),relative_quadrature_error=float(error/integral),
        method='deterministic scaled conditional-normal quadrature')


def scipy_box_probability(mean,covariance,lower=(-12.5,-12.5),upper=(12.5,12.5)):
    return float(multivariate_normal.cdf(upper,mean=mean,cov=covariance,lower_limit=lower,
        maxpts=1000000,abseps=1e-10,releps=1e-10,rng=np.random.default_rng(2026110208)))


def condition_position(raw,sigma,nuisance,jacobian,mean,covariance):
    """Gaussian integration identity; held data update integration coordinates.

    No fitted RF parameter or held-data nuisance estimate is installed anywhere.
    C=diag(sigma²)+nuisance nuisance'; Jacobian differentiates TOTAL posterior
    predictive mean, retaining position/nuisance cross-covariance consistently.
    """
    s=np.asarray(sigma);u=np.asarray(nuisance);j=np.asarray(jacobian);r=np.asarray(raw)
    a=u/s[:,None];v=np.column_stack((r,j))/s[:,None]
    gram=np.eye(a.shape[1])+a.T@a
    inverse_v=(v-a@np.linalg.solve(gram,a.T@v))/s[:,None]
    precision=np.linalg.inv(covariance)+j.T@inverse_v[:,1:]
    updated_covariance=np.linalg.inv(precision)
    updated_mean=np.asarray(mean)+updated_covariance@j.T@inverse_v[:,0]
    return updated_mean,updated_covariance


def correct_score(unbounded_negative_twice_log_density,raw,sigma,nuisance,jacobian,mean,covariance,
                  lower=(-12.5,-12.5),upper=(12.5,12.5)):
    prior=box_log_probability(mean,covariance,lower,upper)
    updated_mean,updated_covariance=condition_position(raw,sigma,nuisance,jacobian,mean,covariance)
    posterior=box_log_probability(updated_mean,updated_covariance,lower,upper)
    correction=-2*(posterior['log_probability']-prior['log_probability'])
    return dict(negative_twice_log_density=float(unbounded_negative_twice_log_density+correction),
        correction_negative_twice_log_density=float(correction),prior_box=prior,posterior_box=posterior,
        integration_posterior_position_mean_km=updated_mean,integration_posterior_position_covariance_km2=updated_covariance,
        prior_scipy_box_probability=scipy_box_probability(mean,covariance,lower,upper),
        posterior_scipy_box_probability=scipy_box_probability(updated_mean,updated_covariance,lower,upper))
