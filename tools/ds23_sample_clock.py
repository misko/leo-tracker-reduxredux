"""A coupled sample-clock frequency scale and elapsed-time geometry control.

epsilon means actual sample rate / nominal sample rate - 1. It divides both
reported carrier Hz and true elapsed time by 1+epsilon. Radio offset/drift
coefficients are reparameterized in the observed time coordinates as before.
Engineering ppm priors here are not measured hardware specifications.
"""

from types import SimpleNamespace
import numpy as np
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def clock_geometry(p,position,epsilon):
    e=np.asarray(epsilon,float)
    if e.shape!=(2,) or not np.isfinite(e).all() or np.any(abs(e)>.01):
        raise ValueError('two finite sample-clock fractional errors within one percent required')
    rate=1+e[p.flat_rx-1]
    view=SimpleNamespace(**vars(p));view.flat_times=p.flat_times/rate
    g=geometry_features(view,position,0.)
    for name in ('frequency','intercept','derivative'):g[name]/=rate
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    end=begin+len(p.labels)+3*len(p.supported)
    g['features'][:,begin:end]/=rate[:,None]
    return g


def clock_columns(p,position,orbital_coefficient,step=1e-5):
    start=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels);end=start+3*len(p.supported)
    coefficient=np.asarray(orbital_coefficient,float)
    if coefficient.shape!=(end-start,) or not np.isfinite(step) or not 0<step<.001:
        raise ValueError('matching original orbit coefficients and positive small differentiation step required')
    columns=[]
    for rx in (0,1):
        d=np.zeros(2);d[rx]=step;values=[]
        for e in (d,-d):
            g=clock_geometry(p,position,e)
            values.append(p.q*g['frequency']+g['features'][:,start:end]@coefficient)
        columns.append((values[0]-values[1])/(2*step))
    return np.column_stack(columns)


def make_clock_problem(scan,node,keep,arm,reference,powers,means,model,sigma_ppm,orbital_coefficient=None):
    if not np.isfinite(sigma_ppm) or sigma_ppm<0:raise ValueError('finite nonnegative clock-prior SD required')
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.flat_rx=np.concatenate([np.full(len(scan.tracks[i]['times']),scan.tracks[i]['receiver'],int) for i in p.members])
    start=p.hardware.shape[1]+p.smooth.shape[1]
    stop=start+len(p.labels)+3*len(p.supported);width=stop+2+len(p.members)
    orbit=np.zeros(3*len(p.supported)) if orbital_coefficient is None else np.asarray(orbital_coefficient)
    mean=np.zeros(width);mean[start:start+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[start:start+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(position):
        g=geometry_features(p,position,0.)
        columns=np.zeros((len(p.values),2)) if sigma_ppm==0 else clock_columns(p,position,orbit)*(sigma_ppm*1e-6)
        features=np.column_stack((g['features'][:,:stop],columns,g['features'][:,stop:]))
        raw=p.values-p.q*g['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=groups,prior_nu=4 if model['nu'] is None else model['nu'])
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*g['intercept']-features@b['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)]
        g.update(b,features=features,sample_clock_ppm=b['coefficient'][stop:stop+2]*sigma_ppm)
        return g
    p.calculate=calculate;p.clock_start=stop;p.clock_sigma_ppm=sigma_ppm
    p.clock_orbit_start=start+len(p.labels)
    return p


def exact_clock_replay(p,position):
    c=p.calculate(position);e=c['sample_clock_ppm']*1e-6
    actual=clock_geometry(p,position,e);coefficient=np.delete(c['coefficient'],[p.clock_start,p.clock_start+1])
    exact=p.q*actual['intercept']+actual['features']@coefficient
    approximate=p.q*c['intercept']+c['features']@c['coefficient'];error=exact-approximate
    return dict(maximum_prediction_difference_hz=float(max(abs(error[p.keep]))),
        maximum_prediction_difference_in_noise_units=float(max(abs(error[p.keep])/p.point_noise[p.keep])),
        RMS_prediction_difference_hz=float(np.sqrt(np.mean(error[p.keep]**2))))
