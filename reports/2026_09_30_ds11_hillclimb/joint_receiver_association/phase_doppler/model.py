"""Robust slope and independent-recording transfer diagnostics."""
import numpy as np
from scipy.optimize import least_squares


def slope(times,residual,mask):
    times=np.asarray(times);residual=np.asarray(residual);mask=np.asarray(mask,bool)
    t=times[mask];y=residual[mask]
    if len(t)<3 or np.ptp(t)<=0:return dict(qualified=False,reason='insufficient_support')
    scale=np.ptp(t);design=np.column_stack((np.ones(len(t)),(t-t.mean())/scale))
    initial=np.linalg.lstsq(design,y,rcond=None)[0]
    fit=least_squares(lambda p:design@p-y,initial,jac=lambda p:design,loss='soft_l1',f_scale=100.,ftol=1e-12,xtol=1e-12,gtol=1e-10,max_nfev=300)
    return dict(qualified=bool(fit.success and fit.optimality<.001),slope_hz_per_s=float(fit.x[1]/scale),optimality=float(fit.optimality),support=len(t),span_s=float(scale))


def transfer(train,validation):
    if min(len(train),len(validation))<5:return dict(passed=False,qualified=False,reason='insufficient_groups')
    x=np.array([r['phase_residual'] for r in train])/.01;y=np.array([r['training_slope'] for r in train])
    design=np.column_stack((np.ones(len(x)),x))
    if np.linalg.matrix_rank(design)<2:return dict(passed=False,qualified=False,reason='rank_deficient')
    initial=np.linalg.lstsq(design,y,rcond=None)[0]
    fit=least_squares(lambda p:design@p-y,initial,jac=lambda p:design,loss='soft_l1',f_scale=10.,ftol=1e-12,xtol=1e-12,gtol=1e-10,max_nfev=300)
    vx=np.array([r['phase_residual'] for r in validation])/.01;vy=np.array([r['held_slope'] for r in validation])
    predicted=fit.x[0]+fit.x[1]*vx
    errors=abs(vy-predicted);zero=abs(vy);constant=abs(vy-np.median(y))
    shifts=[float(np.median(abs(vy-(fit.x[0]+fit.x[1]*np.roll(vx,k))))) for k in range(1,len(vx))]
    median=float(np.median(errors));control=[float(np.median(zero)),float(np.median(constant)),float(np.median(shifts))]
    qualified=bool(fit.success and fit.optimality<.001)
    return dict(qualified=qualified,parameters=fit.x.tolist(),optimality=float(fit.optimality),training_groups=len(train),validation_groups=len(validation),median_error_hz_per_s=median,zero_error_hz_per_s=control[0],constant_error_hz_per_s=control[1],cyclic_shift_median_error_hz_per_s=control[2],wins=int(np.sum(errors<zero)),predicted_validation_slope=predicted.tolist(),cyclic_shift_errors=shifts,passed=bool(qualified and np.sum(errors<zero)>len(vx)/2 and all(median<=.95*c for c in control)))
