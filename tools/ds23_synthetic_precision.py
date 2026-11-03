"""Synthetic measurement-precision controls without altering frozen contracts.

The original >=40Hz persisted noise contract is preserved. The existing
research precision builder permits >=1Hz overrides in a fresh problem. Its
1Hz residual reference changes only a position-independent score constant.
"""

import copy
import numpy as np

from probe_ds23_refined_precision import precision_problem
from ds23_frequency_events import attach_event_predictive


def measurement_noise(scan, members, fraction, seed):
    """Same standard-normal draw per physical ID at a declared precision."""
    if not np.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('finite measurement noise fraction in (0,1] required')
    ids=sorted({o for i in members for o in scan.tracks[i]['observation_ids']})
    meta=scan.fixed_window_noise
    nominal={o:(meta['per_observation_noise_sigma_hz'][o] if meta['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz) for o in ids}
    if not all(np.isfinite(v) and v>0 for v in nominal.values()):
        raise ValueError('positive declared observation uncertainties required')
    sigma={o:max(1., v*fraction) for o,v in nominal.items()}
    z=np.random.default_rng(seed).normal(size=len(ids))
    noise={o:float(value*sigma[o]) for o,value in zip(ids,z,strict=True)}
    return sigma,noise


def add_noise(scan, members, noise):
    for i in sorted(set(members)):
        track=scan.tracks[i]
        track['values']=np.asarray(track['values'])+np.asarray([noise[o] for o in track['observation_ids']])


def make_precision_control(scan,node,mask,arm,reference,powers,means,hyper,entries,sigma):
    p=precision_problem(scan,node,mask,arm,reference,powers,means,hyper,sigma)
    p.events=[]
    # Only the predictive adapter reads this ephemeral metadata. Construction
    # above still validates the unchanged original persisted >=40Hz contract.
    p.scan=copy.copy(scan)
    p.scan.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise)
    p.scan.fixed_window_noise['extra_parameter_BIC_gain']=1.
    p.scan.fixed_window_noise['per_observation_noise_sigma_hz'].update(sigma)
    attach_event_predictive(p,entries,powers)
    return p
