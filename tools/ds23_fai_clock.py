"""Research covariance for channel-dependent transmitter CFO steps.

Fifty-hertz zero-mean Gaussian offsets are constant inside a 15-second slot.
This tests an engineering clock hypothesis, not an ephemeris correction. The
same-satellite/same-RF key approximates a common beam and needs validation.
"""

import numpy as np

from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def slot_keys(labels, rf_hz, times, origin_utc_ns, utc_boundary_phase_s):
    phase=(int(origin_utc_ns)%15_000_000_000)/1e9
    return [(int(j),round(float(rf)),int(np.floor((phase+float(t)-utc_boundary_phase_s)/15)))
            for j,rf,t in zip(labels,rf_hz,times,strict=True)]


def clock_design(p, *, sigma_hz, utc_boundary_phase_s):
    if sigma_hz<0 or not np.isfinite(sigma_hz) or not 0<=utc_boundary_phase_s<15:
        raise ValueError('nonnegative finite clock SD and phase within 15-second period required')
    keys=slot_keys(np.asarray(p.labels)[p.flat_labels],p.q*11.5e9,p.flat_times,
                   p.scan.receipt['origin_utc_ns'],utc_boundary_phase_s)
    unique=sorted({key for key,active in zip(keys,p.keep,strict=True) if active})
    lookup={key:k for k,key in enumerate(unique)}
    design=np.zeros((len(keys),len(unique)))
    for k,key in enumerate(keys):
        if key in lookup:
            design[k,lookup[key]]=sigma_hz
    return design,unique


def clock_problem(scan,node,keep,arm,reference,powers,means,model,*,sigma_hz,utc_boundary_phase_s):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    clock,keys=clock_design(p,sigma_hz=sigma_hz,utc_boundary_phase_s=utc_boundary_phase_s)
    original_width=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    width=original_width+clock.shape[1];stop=original_width-len(p.members)
    start=p.hardware.shape[1]+p.smooth.shape[1]
    mean=np.zeros(width);mean[start:start+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:
        groups[start:start+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(position):
        geometry=geometry_features(p,position,0.)
        features=np.column_stack((geometry['features'][:,:stop],clock,geometry['features'][:,stop:]))
        raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        result=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        result=scale_posterior(result,scale)
        result['latent_coefficient']=result['coefficient'].copy();result['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=result['noise_precision'];result['noise_precision']=precision
        result['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@result['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        result['residual']=np.r_[result['residual'],np.sqrt(volume)]
        geometry.update(result,features=features,clock_keys=keys,
            clock_offset_posterior_hz=sigma_hz*result['coefficient'][stop:stop+len(keys)])
        return geometry
    p.calculate=calculate
    return p
