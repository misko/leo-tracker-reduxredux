"""One-dimensional causal phase quadrature with a nearest-alias proposal per phase.

This is a bounded nomination score, not a normalized satellite-identity
posterior. Orbital-shape modes and the original final likelihood are restored
when refining nominees and fitting positions.
"""

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import gammaln

PERIOD=1/4.4e-6


def integrate(values,radio_mean,covariance,phases,phase_means,phase_sds,nu,frequency_at_phase):
    y,r,c,grid,mean,sd=map(np.asarray,(values,radio_mean,covariance,phases,phase_means,phase_sds))
    if y.ndim!=1 or r.shape!=y.shape or c.shape!=(len(y),len(y)) or grid.ndim!=1 or len(grid)<2 or np.any(np.diff(grid)<=0):raise ValueError('matching observations and increasing phase grid required')
    if mean.ndim!=1 or sd.shape!=mean.shape or np.any(sd<=0) or not np.isfinite(sd).all():raise ValueError('finite positive phase prior scales required')
    if nu is not None and nu<=2:raise ValueError('finite-variance Student phase prior required')
    root=np.linalg.cholesky(c);constant=float(2*np.log(np.diag(root)).sum()+len(y)*np.log(2*np.pi))
    weights=np.empty(len(grid));weights[0]=(grid[1]-grid[0])/2;weights[-1]=(grid[-1]-grid[-2])/2;weights[1:-1]=(grid[2:]-grid[:-2])/2
    logmass=np.full(len(mean),-np.inf);peak=np.full(len(mean),-np.inf);peak_phase=np.zeros(len(mean));peak_alias=np.zeros(len(mean),int)
    for phase,weight in zip(grid,weights,strict=True):
        frequency,visible=frequency_at_phase(float(phase));frequency=np.asarray(frequency);visible=np.asarray(visible,bool)
        if frequency.shape!=(len(mean),len(y)) or visible.shape!=(len(mean),):raise ValueError('candidate geometry dimensions differ')
        raw=(y-r)[None,:]-frequency;alias=np.rint(-raw.mean(axis=1)/PERIOD).astype(int);raw+=alias[:,None]*PERIOD
        white=solve_triangular(root,raw.T,lower=True);cost=np.sum(white*white,axis=0)+constant;z=(phase-mean)/sd
        if nu is None:prior=-.5*z*z-np.log(sd)-.5*np.log(2*np.pi)
        else:prior=gammaln((nu+1)/2)-gammaln(nu/2)-.5*np.log(np.pi*(nu-2))-np.log(sd)-.5*(nu+1)*np.log1p(z*z/(nu-2))
        density=np.where(visible,-.5*cost+prior,-np.inf);logmass=np.logaddexp(logmass,density+np.log(weight));improved=density>peak
        peak_phase[improved]=phase;peak_alias[improved]=alias[improved];peak[improved]=density[improved]
    return dict(score=-2*logmass,peak_phase_s=peak_phase,aliases=peak_alias,
        phase_grid_points=len(grid),nearest_alias_is_a_proposal_not_a_full_wrapped_probability=True)
