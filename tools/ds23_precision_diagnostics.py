"""Expose the legacy residual screen's sensitivity at actual RF uncertainty."""

import numpy as np
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def compare_screens(residual,times,sigma):
    r,t,s=map(lambda v:np.asarray(v,float),(residual,times,sigma))
    if r.ndim!=1 or s.shape!=r.shape or t.shape!=r.shape or not np.isfinite(s).all() or np.any(s<=0):
        raise ValueError('matching finite residual/time/noise vectors and positive scales required')
    legacy=batch_noise_screen(r[None],t)
    # Convert to dimensionless residuals; the owned screen has a 75 Hz floor.
    scaled=batch_noise_screen((75*r/s)[None],t)
    def scalar(d):return {k:v[0].item() for k,v in d.items()}
    return dict(legacy=scalar(legacy),RF_scaled=scalar(scaled),
        standardized_RMS=float(np.sqrt(np.mean((r/s)**2))),
        conditional_diagnostic_not_calibrated_predictive_test=True)
