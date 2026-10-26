"""Necessary whole-owner gates; not identity calibration or position fitting."""
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp
from leo.analysis.research.retained_track_likelihood import PERIOD,profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

def source_gate(raw,times,white,elevation):
    raw=np.asarray(raw);terms=profile(raw,np.zeros(len(raw)),*white,bias_sigma=300.)
    noise=batch_noise_screen(terms['innovations'],times)
    primitive=dict(RMS=bool(terms['rms'][0]<=450),constant=bool(abs(terms['bias'][0])<=3000),
        alias=bool(int(terms['alias'][0])==0),noise=bool(noise['noise_screen_pass'][0]),visibility=bool(np.min(elevation)>=0))
    return dict(compatible=all(primitive.values()),primitive=primitive,rms_hz=float(terms['rms'][0]),
        bias_hz=float(terms['bias'][0]),residual_alias=int(terms['alias'][0]),
        raw_RMS_hz=float(np.sqrt(np.mean(raw**2))),minimum_elevation_deg=float(np.min(elevation)),
        noise={k:v[0] for k,v in noise.items()},profile_residual_hz=terms['residual'][0])

def mode_mean(raw,covariance,B):
    root=np.linalg.cholesky(covariance);u=np.linalg.solve(root,B);y=np.linalg.solve(root,raw)
    return np.linalg.solve(np.eye(B.shape[1])+u.T@u,u.T@y)

def phase_map(cd,comp,sr,coarse):
    prior=sr.law(cd)
    def terms(phases):
        phases=np.atleast_1d(phases);g=sr.k.m.q.phase_geometry(cd,comp['x'],phases)
        f=g['frequency_hz']*comp['q'][None];B=g['shape_columns_hz']*comp['q'][None,:,None]
        out=-.5*sr.sm.positive_costs(comp['raw'][None]-f,comp['covariance'],B,comp['shifts'])
        out+=prior['distribution'].logpdf(phases)[:,None]-np.log(prior['mass'])-np.log(len(comp['aliases']))
        out[np.min(g['elevation_deg'],axis=1)<0]=-np.inf
        return out
    extra=[prior['location']]+([float(coarse)] if np.isfinite(coarse) else [])
    grid=np.unique(np.r_[np.linspace(-15,15,641),[x for x in extra if -15<=x<=15]])
    scores=terms(grid);best=np.max(scores,axis=1)
    peaks=[i for i in range(len(grid)) if np.isfinite(best[i]) and (i==0 or best[i]>=best[i-1]) and (i==len(grid)-1 or best[i]>=best[i+1])]
    starts=sorted(peaks,key=lambda i:(-best[i],grid[i]))[:3]
    proposals=[(float(best[i]),float(grid[i]),int(np.argmax(scores[i]))) for i in starts]
    for i in starts:
        lo,hi=grid[max(0,i-1)],grid[min(len(grid)-1,i+1)]
        if hi<=lo:continue
        fit=minimize_scalar(lambda phi:-float(np.max(terms([phi])[0])),bounds=(lo,hi),method='bounded',options=dict(maxiter=50,xatol=1e-5))
        z=terms([fit.x])[0];proposals.append((float(np.max(z)),float(fit.x),int(np.argmax(z))))
    if not proposals:raise ValueError('no finite diagnostic phase/alias proposal')
    logdensity,phase,alias_index=max(proposals,key=lambda z:(z[0],-z[1],-z[2]))
    g=sr.k.m.q.phase_geometry(cd,comp['x'],np.asarray([phase]));B=g['shape_columns_hz'][0]*comp['q'][:,None]
    raw=comp['raw']+comp['shifts'][alias_index]-g['frequency_hz'][0]*comp['q']
    coefficient=mode_mean(raw,comp['covariance'],B)
    return dict(phase_s=phase,causal_location_s=prior['location'],causal_marginal_SD_s=prior['sd'],
        causal_z=(phase-prior['location'])/prior['sd'],alias=int(comp['aliases'][alias_index,0]),
        diagnostic_log_density=logdensity,grid_points=len(grid),peak_refinements=len(starts),global_MAP_certified=False,
        mode_coefficient=coefficient,conservative_raw_hz=raw,fullmode_raw_hz=raw-B@coefficient,
        nominal_elevation_deg=g['elevation_deg'][0],shape_means_calibrated=False,target_radio_mean_updated=False)
