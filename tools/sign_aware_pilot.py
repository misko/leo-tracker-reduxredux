"""Carrier fit with an unknown real signed amplitude in each pilot frame.

One common complex phase replaces independent complex frame phases. Exact
within-frame RF likelihood resolves the extra frame-rate frequency aliases.
Timing and code rate are conditioned on a prior RF fit. No orbit input exists.
"""

import numpy as np


def sign_spectrum(workspace, frequencies, offset, ppm, subset='all',control=False):
    d=workspace.evaluate(frequencies,offset,ppm,subset,control=control,details=True)
    gain,energy=d['coefficients'],d['energies']
    cross=np.sum(energy*gain*gain,axis=0)
    total=np.sum(energy*abs(gain)**2,axis=0)
    explained=(total+abs(cross))/2
    return dict(score=explained/max(d['raw_energy'],1e-20),
        phase_rad=.5*np.angle(cross),coherence_squared=abs(cross)**2/np.maximum(total**2,1e-30),
        details=d)


def phase_proposals(workspace,base,subset,radius):
    d=workspace.evaluate([base['CFO_hz']],base['offset_samples'],base['modulation_ppm'],subset,details=True)
    times=np.array([workspace.t[workspace.frames[k]].mean() for k in d['frames']])
    g=d['coefficients'][:,0];e=d['energies'][:,0]
    grid=np.arange(-radius,radius+.1,2.5)
    rotation=np.exp(-4j*np.pi*grid[:,None]*(times-workspace.mid)[None])
    score=abs(rotation@(e*g*g))
    peaks=[k for k in range(1,len(grid)-1) if score[k]>=score[k-1] and score[k]>=score[k+1]]
    peaks=sorted(peaks,key=lambda k:score[k],reverse=True)[:8]
    if not peaks:raise ValueError('no sign-aware phase-frequency proposal')
    return grid[peaks]


def fit_sign_carrier(workspace,base,subset='all',radius=400.):
    center=float(base['CFO_hz']);offset,ppm=base['offset_samples'],base['modulation_ppm']
    deltas=phase_proposals(workspace,base,subset,radius)
    grids=[np.clip(center+delta+np.arange(-8,8.1,1.),center-radius,center+radius) for delta in deltas]
    frequencies=np.unique(np.concatenate(grids))
    result=sign_spectrum(workspace,frequencies,offset,ppm,subset)
    scores=result['score'];j=int(np.argmax(scores));f=float(frequencies[j])
    if 0<j<len(frequencies)-1 and np.allclose(np.diff(frequencies[j-1:j+2]),1.):
        curve=scores[j-1]-2*scores[j]+scores[j+1]
        if curve<0:f+=float(np.clip(.5*(scores[j-1]-scores[j+1])/curve,-.5,.5))
    final=sign_spectrum(workspace,[f-1.,f,f+1.],offset,ppm,subset)
    d=final['details'];frames=d['frames']
    samples=sum(len(workspace.frames[k]) for k in frames)
    # Complex Gaussian profile -2 log likelihood, up to a constant common to
    # all tested carriers. The noise proxy is not a calibrated RF error bar.
    objective=2*samples*np.log(np.maximum(1-final['score'],1e-15))
    curvature=float(objective[0]-2*objective[1]+objective[2])
    g=d['coefficients'][:,1];e=d['energies'][:,1];weights=e*abs(g)**2
    effective=float(weights.sum()**2/max(weights@weights,1e-30))
    times=np.array([workspace.t[workspace.frames[k]].mean() for k in frames])
    dt=times-workspace.mid;mu=float(weights@dt/max(weights.sum(),1e-30))
    information=float(weights@((dt-mu)**2))
    time=workspace.mid+float(weights@((dt-mu)*.5*dt*dt))/information if information>0 else workspace.mid
    alternatives=[]
    for grid in grids:
        indices=np.searchsorted(frequencies,grid);k=indices[int(np.argmax(scores[indices]))]
        if abs(frequencies[k]-f)>=60:
            alternatives.append(float(2*samples*np.log(max(1-scores[k],1e-15))-objective[1]))
    return dict(CFO_hz=f,score=float(final['score'][1]),coherence_squared=float(final['coherence_squared'][1]),
        common_phase_rad=float(final['phase_rad'][1]),effective_frames=effective,frames=len(frames),
        frequency_sigma_proxy_hz=float(np.sqrt(2/curvature)) if curvature>0 else None,
        nearest_other_mode_objective_gap=min(alternatives) if alternatives else None,
        frequency_search_boundary=abs(f-center)>=radius-5,offset_samples=offset,modulation_ppm=ppm,
        subset=subset,effective_time_from_probe_start_s=time,
        aliases_resolved_by_exact_within_frame_RF_likelihood=True)


def predict_frame_phase(workspace,trained,heldout):
    d=workspace.evaluate([trained['CFO_hz']],trained['offset_samples'],trained['modulation_ppm'],heldout,details=True)
    g=d['coefficients'][:,0];e=d['energies'][:,0]
    real=np.real(g*np.exp(-1j*trained['common_phase_rad']))
    total=float(np.sum(e*abs(g)**2))
    return float(np.sum(e*real*real)/max(total,1e-30))


def surrogate_rank(workspace,fit,seed,controls=199):
    d=workspace.evaluate([fit['CFO_hz']],fit['offset_samples'],fit['modulation_ppm'],details=True)
    g=d['coefficients'][:,0];e=d['energies'][:,0];weights=e*abs(g)**2
    t=np.array([workspace.t[workspace.frames[k]].mean() for k in d['frames']])
    rotation=np.exp(-4j*np.pi*np.arange(-400,400.1,5.)[:,None]*(t-workspace.mid)[None])
    phases=np.random.default_rng(seed).uniform(-np.pi,np.pi,size=(len(t),controls))
    null=(abs(rotation@(weights[:,None]*np.exp(2j*phases)))**2/max(weights.sum()**2,1e-30)).max(axis=0)
    return dict(rank=float((1+np.sum(null>=fit['coherence_squared']))/(controls+1)),
        maximum_null_coherence=float(null.max()),controls=controls)


def sign_aware_fit(workspace,base,seed=20261021):
    fits={subset:fit_sign_carrier(workspace,base,subset) for subset in ('all','even','odd')}
    predictions={'even_to_odd':predict_frame_phase(workspace,fits['even'],'odd'),
        'odd_to_even':predict_frame_phase(workspace,fits['odd'],'even')}
    split=abs(fits['even']['CFO_hz']-fits['odd']['CFO_hz'])
    pooled=abs(fits['all']['CFO_hz']-(fits['even']['CFO_hz']+fits['odd']['CFO_hz'])/2)
    null=surrogate_rank(workspace,fits['all'],seed)
    checks=dict(coherence=fits['all']['coherence_squared']>=.8,
        frame_support=fits['all']['effective_frames']>=8,
        heldout_phase=min(predictions.values())>=.9,
        fold_frequency_agreement=split<=10 and pooled<=5,
        frequency_interior=not any(r['frequency_search_boundary'] for r in fits.values()),
        alias_separation=all(r['nearest_other_mode_objective_gap'] is not None and r['nearest_other_mode_objective_gap']>10 for r in fits.values()),
        random_phase_control=null['rank']<=.01)
    return dict(fits=fits,heldout_phase_fraction=predictions,fold_CFO_difference_hz=split,
        full_vs_fold_average_difference_hz=pooled,surrogate=null,checks=checks,
        accepted=all(checks.values()),
        timing_and_rate_conditioned_on_previous_all_frame_RF_fit=True,
        uncertainty_proxy_not_calibrated_absolute_CFO_error=True)
