"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import time
import numpy as np
from scipy.optimize import minimize
from algo06_science.common import read, write, reconstruct, ARMS
from algo06_science.position import family_score
from phase_reference_checks import phase_refresh
from prototype_dsx01_continuous_position import latlon

def error(x):
    """Evaluation-only metadata is intentionally absent from the runtime."""
    return None

def build(*args, **kwargs):
    raise RuntimeError('ALGO07 engine must configure reconstruction')


def derivatives(fun,x,h=.05):
    eye=np.eye(2)*h;v=fun(x);g=np.zeros(2);H=np.zeros((2,2))
    for i in range(2):
        plus,minus=fun(x+eye[i]),fun(x-eye[i]);g[i]=(plus-minus)/(2*h);H[i,i]=(plus-2*v+minus)/h**2
    H[0,1]=H[1,0]=(fun(x+eye[0]+eye[1])-fun(x+eye[0]-eye[1])-fun(x-eye[0]+eye[1])+fun(x-eye[0]-eye[1]))/(4*h*h)
    return g,H

def objective(p,d,x):
    c=p.calculate(x)
    return float(c['negative_twice_elbo']+family_score(d['families'],d,p,x)+np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)

def refit(d,z,arm,start,omit=None,phase_scale=1.,rounds=5):
    old=d['problems'][arm][0];reference=old.reference.copy();x=np.array(start);history=[];began=time.monotonic()
    for epoch in range(rounds):
        p,dd=build(d,z,arm,reference,omit,phase_scale)
        opt=minimize(lambda v:objective(p,dd,v),x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
            options=dict(maxiter=35,maxfun=140,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
        x=opt.x;updated,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
        history.append(dict(success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,x=x.copy(),**check))
        if check['phase_change_s']<=.01:break
        if epoch<rounds-1:reference=updated
    c=p.calculate(x)
    return dict(x=x,latlon=latlon(x),error_m=error(x),objective=objective(p,dd,x),
        rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),history=history,
        reference=p.reference,active_points=int(p.keep.sum()),seconds=time.monotonic()-began,
        phase_closed=check['phase_change_s']<=.01,optimizer_success=bool(opt.success),
        boundary=bool(np.any(abs(x)>12.49)),diagnostic_only=True,omitted_norad=omit,phase_scale=phase_scale)
