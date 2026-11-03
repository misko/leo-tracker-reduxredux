"""Change cross-band linear-drift correlation at fixed marginal variance.

Original native coordinates encode mean drift SD10Hz/s and a signed contrast
SD0.5Hz/s. Both bands therefore have SDsqrt(100.25), but correlation99.75/100.25.
The alternative changes only that correlation, using the same two coordinates,
all original phase/orbit priors and the same pointwise band-drift variance.
"""

import numpy as np
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior

ORIGINAL_CORRELATION=99.75/100.25


def drift_coordinate_scales(correlation):
    rho=float(correlation)
    if not np.isfinite(rho) or not -1<rho<1:raise ValueError('finite cross-band drift correlation strictly between -1 and1 required')
    if rho==ORIGINAL_CORRELATION:return np.ones(2)
    variance=100.25
    return np.array([np.sqrt(variance*(1+rho)/2)/10,np.sqrt(variance*(1-rho)/2)/.5])


def make_band_drift_problem(scan,node,mask,arm,reference,powers,means,hyper,correlation):
    factors=drift_coordinate_scales(correlation)
    p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
    if correlation==ORIGINAL_CORRELATION:return p
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    prior_groups=np.full(width,-1,int)
    if hyper['nu'] is not None:prior_groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[[4,6]]=factors[0];scale[[5,7]]=factors[1];scale[-len(p.members):]=.3
    present=np.unique(p.noise_groups[mask])
    volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[mask]]*np.log(p.point_noise[mask]/40)))
    def calculate(position):
        geometry=geometry_features(p,position,0.);features=geometry['features']
        raw=p.values-p.q*geometry['intercept']-features@mean
        bound=hierarchical_bound(raw[mask],(features*scale)[mask],p.point_noise[mask],p.noise_groups[mask],
            powers=np.asarray(powers)[present],prior_groups=None if hyper['nu'] is None else prior_groups,
            prior_nu=4 if hyper['nu'] is None else hyper['nu'])
        bound=scale_posterior(bound,scale);bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)];geometry.update(bound)
        return geometry
    p.calculate=calculate;p.band_drift_correlation=correlation;p.band_drift_coordinate_scales=factors
    return p
