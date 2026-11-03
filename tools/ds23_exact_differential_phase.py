"""Exact two-satellite phase refinement for a frozen relative-Doppler proposal.

The Gaussian phase and relative-constant priors match the earlier tangent
proposal. A local Laplace score is a nomination approximation, not identity
probability. Physical orbit modes are not introduced by this helper.
"""

import numpy as np
from scipy.optimize import minimize


def constant_profile(raw,sigma,prior_sigma):
    y=np.asarray(raw,float);bias=float(y.sum()/(len(y)+sigma**2/prior_sigma**2))
    residual=y-bias
    cost=float(residual@residual/sigma**2+(bias/prior_sigma)**2+np.log1p(len(y)*prior_sigma**2/sigma**2))
    return cost,bias,residual


def refine_pair(values,predict,mean,width,sigma,start,*,constant_sigma=1000.,iterations=80):
    y=np.asarray(values,float);mu=np.asarray(mean,float);sd=np.asarray(width,float);start=np.asarray(start,float)
    if (y.ndim!=1 or len(y)<4 or mu.shape!=(2,) or sd.shape!=(2,) or start.shape!=(2,)
            or not np.isfinite(np.r_[y,mu,sd,start,sigma,constant_sigma]).all() or np.any(sd<=0)
            or sigma<=0 or constant_sigma<=0):
        raise ValueError('finite relative data, two phase means/SDs/starts and positive frequency SDs required')
    lower=(-15-mu)/sd;upper=(15-mu)/sd;calls=0
    def objective(u,gradient=True):
        nonlocal calls
        phase=mu+sd*np.asarray(u);prediction=np.asarray(predict(phase),float);calls+=1
        if prediction.shape!=y.shape or not np.isfinite(prediction).all():raise ValueError('matching finite exact relative Doppler required')
        cost,bias,residual=constant_profile(y-prediction,sigma,constant_sigma);cost+=float(u@u)
        if not gradient:return cost,bias,residual
        derivatives=[]
        for k in range(2):
            delta=np.zeros(2);delta[k]=.01
            derivatives.append((np.asarray(predict(phase+delta))-np.asarray(predict(phase-delta)))/.02*sd[k]);calls+=2
        d=np.column_stack(derivatives)
        return cost,-2*d.T@residual/sigma**2+2*u
    fits=[]
    for seed in [start,mu]:
        initial=np.clip((seed-mu)/sd,lower,upper)
        fitted=minimize(objective,initial,jac=True,method='L-BFGS-B',bounds=list(zip(lower,upper,strict=True)),
            options=dict(maxiter=iterations,maxls=24,ftol=1e-12,gtol=1e-6))
        value,bias,residual=objective(fitted.x,False)
        fits.append((value,fitted,bias,residual))
    cost,fitted,bias,residual=min(fits,key=lambda r:r[0]);u=fitted.x;phase=mu+sd*u
    gradient=objective(u)[1];columns=[]
    for k in range(2):
        step=.01/sd[k];delta=np.zeros(2);delta[k]=step
        columns.append((objective(u+delta)[1]-objective(u-delta)[1])/(4*step))
    hessian=np.column_stack(columns);asymmetry=float(np.max(abs(hessian-hessian.T))/max(1.,np.max(abs(hessian))))
    hessian=(hessian+hessian.T)/2;eigenvalues=np.linalg.eigvalsh(hessian)
    boundary=bool(np.any(abs(phase)>=14.999))
    positive=bool(eigenvalues.min()>0)
    score=cost+np.linalg.slogdet(hessian)[1] if positive else None
    return dict(phase_s=phase,relative_bias_hz=bias,RMS_hz=float(np.sqrt(np.mean(residual**2))),
        residual_hz=residual,profile_cost=cost,local_Laplace_score=score,
        maximum_scaled_gradient=float(np.max(abs(gradient))),phase_boundary=boundary,
        observed_half_cost_hessian=hessian,hessian_eigenvalues=eigenvalues,hessian_asymmetry=asymmetry,
        valid_local_nomination=positive and not boundary and float(np.max(abs(gradient)))<.05 and asymmetry<.01,
        optimizer_success=bool(fitted.success),optimizer_message=str(fitted.message),calls=calls,
        start_scores=[r[0] for r in fits],physical_orbit_modes_omitted=True)
