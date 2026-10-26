"""Independent analytic noisy waveform controls for guarded clock prediction."""
import json
from pathlib import Path
import numpy as np
from dsx01_pilot_clock import FrameClock, synthetic_frame
from response import _fit_clock, _parity_frame, _clock_prediction, paired_interval


def control(mode='received_rate', seed=817):
    rng = np.random.default_rng(seed)
    frames = []
    ppm = 37. if mode == 'received_rate' else 0.
    for number in range(6):
        gains = rng.uniform(.3, 1.5, 8)*np.exp(1j*rng.uniform(-np.pi,np.pi,8))
        if mode == 'noise':
            gains[:] = 0
        iq = synthetic_frame(cfo=12023.4, ppm=ppm, gains=gains, roll=17 if mode=='wrong_sequence' else 0,
                             noise=.1 if mode!='noise' else 1., seed=seed+number)
        frames.append(FrameClock(iq, 2500000., 10.27, 12000., 'lower'))
    splits = [[_parity_frame(f, parity, 2500000., 10.27) for f in frames] for parity in (0,1)]
    results = {}
    for name, enabled in [('no_rate',False),('received_rate',True)]:
        fits = [_fit_clock(s, enabled) for s in splits]
        errors = [_clock_prediction(splits[k],splits[1-k],fits[k]) for k in (0,1)]
        results[name] = dict(fits=fits, frame_squared_errors=np.sum(errors,axis=0).tolist())
    first = np.asarray(results['no_rate']['frame_squared_errors'])
    second = np.asarray(results['received_rate']['frame_squared_errors'])
    return dict(mode=mode, injected_residual_cfo_hz=23.4, injected_received_rate_ppm=ppm,
                independent_channel_per_tone_and_frame=True, independent_noise=True,
                analytic_waveform_includes_scaled_symbol_boundaries=True,
                models=results, held_symbol_relative_SSE_improvement=1-second.sum()/first.sum(),
                descriptive_frame_bootstrap_95_interval=paired_interval(first-second,first))


if __name__ == '__main__':
    data = [control(mode) for mode in ('received_rate','zero_rate','wrong_sequence','noise')]
    print(json.dumps(dict(rows=data, separate_from_primary_response=True),indent=2))
