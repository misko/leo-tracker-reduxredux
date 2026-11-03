"""Screen saved complex-gain phases for discrete frame rotations.

This concerns RF carrier phase in radians, not orbital phase in seconds.
Searching 2nd/4th/8th harmonics tests finite-alphabet phase ambiguities without
assuming continuity. Random-phase controls share the complete harmonic search.
"""

import numpy as np


def phase_harmonics(times,phases,*,controls=199,seed=20261020):
    t,p=np.asarray(times,float),np.asarray(phases,float)
    if t.ndim!=1 or p.shape!=t.shape or len(t)<4 or not np.isfinite(t).all() or not np.isfinite(p).all() or np.any(np.diff(t)<=0):
        raise ValueError('finite matching ordered frame times and phases required')
    if controls<1:raise ValueError('positive surrogate count required')
    frequencies=np.linspace(-375.,375.,151)
    rotation=np.exp(-2j*np.pi*frequencies[:,None]*(t-t.mean()))
    surrogate=np.random.default_rng(seed).uniform(-np.pi,np.pi,size=(len(t),controls))
    result={};null=np.zeros(controls)
    for harmonic in (1,2,4,8):
        values=abs(rotation@np.exp(1j*harmonic*p))**2/len(t)**2
        j=int(np.argmax(values))
        random=abs(rotation@np.exp(1j*harmonic*surrogate))**2/len(t)**2
        random=random.max(axis=0);null=np.maximum(null,random)
        result[str(harmonic)]=dict(coherence=float(values[j]),powered_frequency_hz=float(frequencies[j]),
            frequency_correction_modulo_alias_hz=float(frequencies[j]/harmonic),
            physical_frequency_alias_period_hz=750./harmonic)
    maximum=max(r['coherence'] for r in result.values())
    pvalue=(1+int(np.sum(null>=maximum)))/(1+controls)
    fourth=result['4']['coherence'];first=result['1']['coherence']
    return dict(harmonics=result,maximum_search_corrected_surrogate_rank=float(pvalue),
        random_phase_maximum_search_scores=null,
        fourth_harmonic_rotation_candidate=bool(fourth>=.8 and first<.6 and pvalue<=.01),
        strict_unit_weights=True,surrogates_are_not_independent_measurements=True)
