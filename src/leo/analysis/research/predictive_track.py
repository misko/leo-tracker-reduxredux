"""Prediction-only evidence, conditional on a separately fitted calibration."""
import numpy as np
from scipy.linalg import cho_solve
from scipy.special import logsumexp
from leo.analysis.research.retained_track_likelihood import PERIOD


def receiver_design(times,rf_hz,receiver,channel,rx_basis,*,fitted_c=False):
    """Existing receiver coordinates in physical-prior units; no fitting."""
    t=np.asarray(times,float);basis=np.asarray(rx_basis,float)
    if t.ndim!=1 or not len(t) or basis.ndim!=2 or len(basis)!=len(t):raise ValueError('matching time and basis rows required')
    if receiver not in (1,2) or channel not in range(1,9) or not np.isfinite(rf_hz) or rf_hz<=0:
        raise ValueError('valid receiver, channel and RF required')
    if not np.isfinite(t).all() or not np.isfinite(basis).all():raise ValueError('finite receiver geometry required')
    nb=8+int(fitted_c);width=basis.shape[1];u=np.zeros((len(t),nb+2*width));rx=receiver-1;high=int(channel>4)
    u[:,2*rx+high]=PERIOD/np.sqrt(12)
    u[:,4+2*rx]=(t-150)*10
    u[:,5+2*rx]=(t-150)*(-1 if high==0 else 1)*.5
    if fitted_c:u[:,8]=(rf_hz/1e9-11.5)*200000
    u[:,nb+rx*width:nb+(rx+1)*width]=rf_hz/11.5e9*basis*200
    return u


def gaussian_log_density(residual,covariance):
    r=np.asarray(residual,float);cov=np.asarray(covariance,float)
    if r.ndim!=1 or not len(r) or cov.shape!=(len(r),len(r)) or not np.isfinite(r).all() or not np.isfinite(cov).all():
        raise ValueError('matching finite response and covariance required')
    if not np.allclose(cov,cov.T,rtol=1e-10,atol=1e-8):raise ValueError('symmetric covariance required')
    root=np.linalg.cholesky((cov+cov.T)/2)
    return float(-.5*(r@cho_solve((root,True),r)+2*np.log(np.diag(root)).sum()+len(r)*np.log(2*np.pi)))


def condition_coefficients(mean,covariance,design,residual,noise_covariance):
    """Conditional predictive moments; never mutate calibration inputs."""
    a,c,h,r,n=(np.asarray(v,float) for v in (mean,covariance,design,residual,noise_covariance))
    if a.ndim!=1 or c.shape!=(len(a),len(a)) or r.ndim!=1 or h.shape!=(len(r),len(a)) or n.shape!=(len(r),len(r)):
        raise ValueError('matching coefficient and observation geometry required')
    if not len(r):return a.copy(),c.copy()
    total=n+h@c@h.T;cross=c@h.T
    root=np.linalg.cholesky((total+total.T)/2)
    posterior=c-cross@cho_solve((root,True),cross.T)
    return a+cross@cho_solve((root,True),r),(posterior+posterior.T)/2


def phase_mixture_evidence(observed,means,base_covariance,orbital_modes,log_prior,visible):
    """Normalized exact phase-grid evidence with Gaussian orbital integration.

    Woodbury solves only a small orbital matrix per phase. Invisible components
    have zero likelihood without renormalizing their prior mass away.
    """
    y,m,b,u,lp=(np.asarray(v,float) for v in (observed,means,base_covariance,orbital_modes,log_prior))
    visible=np.asarray(visible,bool)
    if y.ndim!=1 or not len(y) or m.ndim!=2 or m.shape[1:]!=y.shape or b.shape!=(len(y),len(y)) or u.ndim!=3 or u.shape[:2]!=m.shape or lp.shape!=(len(m),) or visible.shape!=lp.shape:
        raise ValueError('matching phase mixture geometry required')
    if not all(np.isfinite(v).all() for v in (y,m,b,u)) or not np.isfinite(lp).any() or np.isnan(lp).any() or np.isposinf(lp).any():
        raise ValueError('finite geometry and a finite phase prior required')
    if not np.allclose(b,b.T,rtol=1e-10,atol=1e-8):raise ValueError('symmetric covariance required')
    root=np.linalg.cholesky((b+b.T)/2);count,n,width=u.shape
    raw=np.linalg.solve(root,(y-m).T).T
    whitened=np.linalg.solve(root,u.transpose(1,0,2).reshape(n,-1)).reshape(n,count,width).transpose(1,0,2)
    gram=np.eye(width)+np.einsum('mni,mnj->mij',whitened,whitened)
    rhs=np.einsum('mni,mn->mi',whitened,raw)
    coefficients=np.linalg.solve(gram,rhs[...,None])[...,0]
    quadratic=np.sum(raw*raw,axis=1)-np.sum(rhs*coefficients,axis=1)
    logdet=2*np.log(np.diag(root)).sum()+np.linalg.slogdet(gram)[1]
    component=-.5*(quadratic+logdet+n*np.log(2*np.pi));prior=lp-logsumexp(lp)
    joint=np.where(visible,prior+component,-np.inf);evidence=float(logsumexp(joint))
    weights=np.exp(joint-evidence) if np.isfinite(evidence) else np.zeros(count)
    return dict(negative_twice_log_density=-2*evidence,phase_weights=weights,
        orbital_posterior_mean=coefficients,component_log_density=component,
        visible_prior_mass=float(np.exp(prior[visible]).sum()))


def selected_predictive_coordinates(mean,covariance,design,residual,noise_covariance,allowed):
    """Expose selected posterior moments without changing calibration outputs.

    The likelihood still marginalizes every uncertain coefficient. The caller
    may expose, for example, a satellite phase with no calibration observations,
    while preserving receiver means and their separately fitted covariance.
    """
    a=np.asarray(mean,float);cov=np.asarray(covariance,float);h=np.asarray(design,float);r=np.asarray(residual,float)
    noise=np.asarray(noise_covariance,float);indices=np.asarray(allowed,int)
    if a.ndim!=1 or cov.shape!=(len(a),len(a)) or h.shape!=(len(r),len(a)) or noise.shape!=(len(r),len(r)):
        raise ValueError('matching coefficient and predictive geometry required')
    if indices.ndim!=1 or len(set(indices))!=len(indices) or np.any(indices<0) or np.any(indices>=len(a)):
        raise ValueError('unique valid coordinate indices required')
    total=noise+h@cov@h.T
    shift=cov@h.T@cho_solve((np.linalg.cholesky((total+total.T)/2),True),r)
    result=a.copy();result[indices]+=shift[indices]
    return result


def mixture_prediction(observed,means,covariances,log_prior,training,held):
    """Exact Gaussian-mixture conditioning on target training observations.

    The separately supplied calibration posterior is not modified. All mixture
    weights and predictive moments use training observations only. Held values
    enter density and residual evaluation, never the predictive distribution.
    """
    y=np.asarray(observed,float);m=np.asarray(means,float);cov=np.asarray(covariances,float);lp=np.asarray(log_prior,float)
    train,test=np.asarray(training,bool),np.asarray(held,bool)
    if y.ndim!=1 or m.ndim!=2 or m.shape[1:]!=y.shape or cov.shape!=(len(m),len(y),len(y)) or lp.shape!=(len(m),):
        raise ValueError('matching mixture, observations and covariances required')
    if train.shape!=y.shape or test.shape!=y.shape or np.any(train&test) or not test.any():raise ValueError('disjoint training and nonempty held masks required')
    if not np.isfinite(y).all() or not np.isfinite(m).all() or not np.isfinite(cov).all() or not np.isfinite(lp).any() or np.isnan(lp).any() or np.isposinf(lp).any():
        raise ValueError('finite data and at least one finite mixture prior required')
    lp=lp-logsumexp(lp);train_log=[];predictions=[];conditional_cov=[];test_log=[]
    for mean,c in zip(m,cov,strict=True):
        mu=mean[test].copy();variance=c[np.ix_(test,test)].copy();lt=0.
        if train.any():
            tt=c[np.ix_(train,train)];cross=c[np.ix_(test,train)];r=y[train]-mean[train]
            root=np.linalg.cholesky(tt);mu+=cross@cho_solve((root,True),r)
            variance-=cross@cho_solve((root,True),cross.T);lt=gaussian_log_density(r,tt)
        variance=(variance+variance.T)/2
        predictions.append(mu);conditional_cov.append(variance);train_log.append(lt)
        test_log.append(gaussian_log_density(y[test]-mu,variance))
    log_weights=lp+train_log;training_evidence=float(logsumexp(log_weights));log_weights-=training_evidence;weights=np.exp(log_weights)
    predictions=np.asarray(predictions);mu=weights@predictions
    variance=sum(w*(c+np.outer(v-mu,v-mu)) for w,v,c in zip(weights,predictions,conditional_cov,strict=True))
    residual=y[test]-mu;score=float(-2*logsumexp(log_weights+test_log))
    return dict(negative_twice_log_density=score,training_negative_twice_log_density=-2*training_evidence,
        rms_hz=float(np.sqrt(np.mean(residual**2))),held_mean_hz=mu,held_residual_hz=residual,
        prediction_sigma_hz=np.sqrt(np.diag(variance)),held_covariance_hz2=variance,training_mixture_weights=weights,
        no_calibration_refit=True)
