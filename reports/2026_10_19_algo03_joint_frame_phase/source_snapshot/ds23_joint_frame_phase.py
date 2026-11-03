"""Qualify shared frame-phase structure independently of orbit and position.

Carrier corrections inferred only from frame phases are ambiguous by 750 Hz.
This helper returns that ambiguity explicitly; it does not calibrate hardware
or claim a calibrated carrier covariance.
"""

import numpy as np


def phase_line(times, values, weights):
    t,z,w=np.asarray(times,float),np.asarray(values,complex),np.asarray(weights,float)
    if (t.ndim!=1 or t.shape!=z.shape or t.shape!=w.shape or len(t)<4 or
            not all(np.isfinite(a).all() for a in (t,z,w)) or np.any(w<=0)
            or np.any(abs(z)==0) or np.any(np.diff(t)<=0)):
        raise ValueError('four ordered finite nonzero frame gains and positive weights required')
    z=z/abs(z);w=w/w.sum();center=float(w@t);x=t-center
    frequencies=np.linspace(-375.,375.,1501)
    rotation=np.exp(-2j*np.pi*frequencies[:,None]*x)
    score=abs(rotation@(w*z))**2;k=int(np.argmax(score));delta=float(frequencies[k])
    if 0<k<len(frequencies)-1:
        curve=score[k-1]-2*score[k]+score[k+1]
        if curve<0:
            delta+=float(np.clip(.5*(score[k-1]-score[k+1])/curve,-.5,.5))*.5
    corrected=z*np.exp(-2j*np.pi*delta*x)
    mean_phase=float(np.angle(w@corrected))
    residual=np.angle(corrected*np.exp(-1j*mean_phase))
    rms=float(np.sqrt(w@(residual**2)))
    # A repeatability diagnostic only. Correlated phase noise and local maxima
    # are not represented by this conditional local slope standard deviation.
    effective=float(1/np.sum(w*w))
    slope_sigma=float(rms/np.sqrt(max(effective-2,1)*max(w@(x*x),1e-20))/(2*np.pi))
    return dict(coherence=float(abs(w@corrected)**2),frequency_correction_mod750_hz=delta,
        residual_phase_rad=residual,phase_RMS_rad=rms,effective_frames=effective,
        conditional_slope_sigma_hz=slope_sigma,frame_phase_rad=np.angle(z),frame_time_s=t,
        normalized_weights=w,frequency_search_boundary=k in (0,len(frequencies)-1),
        ambiguity_period_hz=750.,covariance_not_calibrated=True)


def paired_phase(times, gains0, gains1, snr0, snr1, *, permutations=499, seed=51432):
    a,b=np.asarray(gains0,complex),np.asarray(gains1,complex)
    s0,s1=np.asarray(snr0,float),np.asarray(snr1,float)
    if len(a)!=len(b) or a.shape!=s0.shape or b.shape!=s1.shape:
        raise ValueError('paired receiver gains and SNRs required')
    weights=s0*s1/(s0+s1)
    result=phase_line(times,b*a.conj(),weights)
    result['individual']=[phase_line(times,a,s0),phase_line(times,b,s1)]
    rng=np.random.default_rng(seed)
    orders=np.array([rng.permutation(len(a)) for _ in range(permutations)])
    phase0=a/abs(a);phase1=b/abs(b)
    surrogate=(phase1[orders]*phase0.conj()[None]).T
    w=result['normalized_weights'];t=np.asarray(times);x=t-w@t
    rotation=np.exp(-2j*np.pi*np.linspace(-375.,375.,1501)[:,None]*x)
    fractions=np.max(abs(rotation@(w[:,None]*surrogate))**2,axis=0)
    pvalue=float((1+np.sum(fractions>=result['coherence']))/(permutations+1))
    result.update(permutation_max_coherence=fractions,permutation_tail_fraction=pvalue,
        null_preserves_frame_amplitudes_but_is_not_an_independent_measurement=True,
        shared_nonlinear_phase_candidate=bool(result['coherence']>=.9 and
            max(d['coherence'] for d in result['individual'])<.8 and
            result['effective_frames']>=8 and pvalue<=.01 and not result['frequency_search_boundary']))
    return result
