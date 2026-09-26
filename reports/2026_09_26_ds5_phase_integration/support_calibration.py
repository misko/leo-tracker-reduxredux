"""Cross-scan calibration of internal phase agreement, not geometric truth."""
import numpy as np
from scipy.optimize import minimize,minimize_scalar
from scipy.special import expit
from phase_factor import log_i0

def predict(parameters,x):
    a,b=np.asarray(parameters,float)
    return 8*expit(a+b*np.asarray(x,float))

def fit(rows,excluded_scan):
    development=[r for r in rows if r['session_id']!=excluded_scan]
    if not development:raise ValueError('independent development scans required')
    scans=sorted({r['session_id'] for r in development})
    x=np.array([r['feature'] for r in development]);error=np.array([r['error_rad'] for r in development])
    # Equal total weight per scan, scaled to the number of development dwells.
    w=np.array([1/sum(v['session_id']==r['session_id'] for v in development) for r in development]);w*=len(w)/w.sum()
    def objective(p):
        k=predict(p,x)
        return float(np.sum(w*(log_i0(k)-k*np.cos(error)))+.02*(p[0]**2+(p[1]/10)**2))
    result=minimize(objective,[-1.,10.],method='L-BFGS-B',bounds=[(-8,8),(0,40)])
    if not result.success:raise RuntimeError(result.message)
    baseline=minimize_scalar(lambda k:float(np.sum(w*(log_i0(k)-k*np.cos(error)))),bounds=(0,8),method='bounded')
    return dict(parameters=result.x.tolist(),constant_kappa=float(baseline.x),development_scans=scans,development_dwells=len(development),objective=float(result.fun))

def log_score(error,kappa):
    return np.asarray(kappa)*np.cos(error)-log_i0(kappa)
