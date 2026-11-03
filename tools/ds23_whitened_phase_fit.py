"""Local curvature scaling for the expensive, correlated RF phase fit."""

import numpy as np
from scipy.optimize import minimize,LinearConstraint


def curvature_whitener(statistics,parameters,scale,step=1e-3):
    p=np.asarray(parameters,float);scale=np.asarray(scale,float);hessian=np.zeros((len(p),len(p)))
    for k in range(len(p)):
        delta=np.zeros_like(p);delta[k]=step*scale[k]
        hessian[:,k]=(statistics(p+delta)['gradient_scaled']-statistics(p-delta)['gradient_scaled'])/(2*step)
    hessian=(hessian+hessian.T)/2
    eigen,vectors=np.linalg.eigh(hessian)
    clipped=np.maximum(eigen,max(1e-5,float(max(eigen))*1e-7))
    whitener=vectors@np.diag(1/np.sqrt(clipped))@vectors.T
    return whitener,dict(observed_scaled_hessian_eigenvalues=eigen,
        clipped_eigenvalues=clipped,clipped_directions=int(np.sum(eigen<clipped)),
        curvature_step_scaled=step,not_absolute_covariance_coverage=True)


def minimize_whitened(statistics,start,scale,lower,upper,whitener,*,maxiter=40):
    start,scale,lower,upper,whitener=map(lambda x:np.asarray(x,float),(start,scale,lower,upper,whitener))
    if np.any(start<lower) or np.any(start>upper):raise ValueError('warm RF start outside original bounds')
    initial=statistics(start)['NLL']
    def objective(z):
        result=statistics(start+scale*(whitener@z))
        return result['NLL']-initial,whitener.T@result['gradient_scaled']
    bounds=LinearConstraint(whitener,(lower-start)/scale,(upper-start)/scale)
    fitted=minimize(objective,np.zeros(len(start)),jac=True,method='SLSQP',constraints=[bounds],
        options=dict(maxiter=maxiter,ftol=1e-8))
    parameters=start+scale*(whitener@fitted.x);final=statistics(parameters)
    return dict(parameters=parameters,NLL=float(final['NLL']),converged=bool(fitted.success),
        message=str(fitted.message),calls=int(fitted.nfev),iterations=int(fitted.nit),
        maximum_whitened_gradient=float(max(abs(whitener.T@final['gradient_scaled']))),
        maximum_scaled_gradient=float(max(abs(final['gradient_scaled']))),
        boundary=bool(np.any(abs(parameters-lower)<1e-4) or np.any(abs(parameters-upper)<1e-4)))


def fit_phase_whitened(problem,start,*,bounds_center,whitener=None,maxiter=40):
    p=np.asarray(start,float);center=np.asarray(bounds_center,float)
    if p.shape!=(problem.width+1,) or center.shape!=(problem.width,):
        raise ValueError('full phase/RF start and original RF bound center required')
    lower=np.r_[center[:problem.count]-800,center[problem.count:problem.code_start]-375,
        np.tile([-.75,-40.],2*problem.count),np.full(2*problem.count,-5.),-6.]
    upper=np.r_[center[:problem.count]+800,center[problem.count:problem.code_start]+375,
        np.tile([.75,40.],2*problem.count),np.full(2*problem.count,5.),np.log(np.pi)]
    scale=np.r_[problem.scale,1.];curvature=None
    if whitener is None:whitener,curvature=curvature_whitener(problem.statistics,p,scale)
    result=minimize_whitened(problem.statistics,p,scale,lower,upper,whitener,maxiter=maxiter)
    final=result['parameters'];sigma=float(np.exp(final[-1]))
    return dict(parameters=final[:problem.width],full_parameters=final,sigma_rad=sigma,fit_phase_variance=True,
        training_NLL=result['NLL'],converged=result['converged'],message=result['message'],
        calls=result['calls'],iterations=result['iterations'],maximum_scaled_gradient=result['maximum_scaled_gradient'],
        maximum_whitened_gradient=result['maximum_whitened_gradient'],
        boundary=bool(np.any(abs(final[:-1]-lower[:-1])<1e-4) or np.any(abs(final[:-1]-upper[:-1])<1e-4)),
        phase_variance_boundary=bool(abs(final[-1]-lower[-1])<1e-3 or abs(final[-1]-upper[-1])<1e-3),
        source_carrier_hz=final[:problem.count],receiver_clock_hz=final[problem.count:problem.code_start],
        curvature=curvature,whitener=whitener,original_RF_bounds_center=center,
        absolute_CFO_covariance_not_calibrated=True)
