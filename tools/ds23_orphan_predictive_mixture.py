"""Normalized wrapped-CFO/clutter prediction, conditional on curved evidence.

This research extension reads no position truth or catalogue whitelist. Shared
Gaussian calibration draws are integrated jointly across all orphan points;
independent per-point marginal densities are not multiplied in their place.
"""

from types import SimpleNamespace

import numpy as np
from scipy.special import logsumexp, ndtri
from scipy.stats import qmc

from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis


def wrapped_pdf(residual,sigma):
    r=(np.asarray(residual)+PERIOD/2)%PERIOD-PERIOD/2
    s=np.asarray(sigma)
    if not np.isfinite(s).all() or np.any(s<=0) or np.any(s>PERIOD/20):
        raise ValueError('positive noise smaller than one twentieth of alias period required')
    return sum(np.exp(-.5*((r+k*PERIOD)/s)**2) for k in [-1,0,1])/(np.sqrt(2*np.pi)*s)


def integrated_clutter(signal_ratios,nodes=32,details=False):
    """Integrate one uniform signal-fraction prior and joint nuisance draws.

    Input rows are complete shared-nuisance realizations, columns observations;
    ratios are normalized signal density divided by uniform alias-period clutter.
    Output is negative twice log likelihood relative to the all-clutter density.
    """
    r=np.asarray(signal_ratios,float)
    if r.ndim!=2 or not r.size or np.any(r<0) or not np.isfinite(r).all():
        raise ValueError('finite nonnegative draw-by-observation ratios required')
    x,w=np.polynomial.legendre.leggauss(nodes);fraction=(x+1)/2;w=w/2
    conditional=np.array([np.log1p(f*(r-1)).sum(axis=1) for f in fraction])
    log_joint=conditional+np.log(w)[:,None]-np.log(len(r))
    normalizer=logsumexp(log_joint);posterior=np.exp(log_joint-normalizer)
    draw_weight=posterior.sum(axis=0)
    result=dict(relative_negative_twice_log_likelihood=float(-2*normalizer),
        effective_nuisance_draws=float(1/np.sum(draw_weight**2)),
        posterior_signal_fraction=float(fraction@posterior.sum(axis=1)))
    if details:
        result['point_signal_probabilities']=sum((posterior[k,:,None]*(f*r)/(1-f+f*r)).sum(axis=0)
                                                 for k,f in enumerate(fraction))
    return result


def orphan_rows(data):
    graph={oid for t in data['scan'].tracks for oid in t['observation_ids']}
    return sorted([o for o in data['observations'] if o['observation_id'] not in graph],
                  key=lambda o:(o['receiver'],o['channel'],o['actual_rf_hz'],o['time_s'],o['observation_id']))


def geometry_view(p,observations):
    active=sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
    if not active or not observations:raise ValueError('active curved families and orphan observations required')
    times=np.array([o['time_s'] for o in observations]);rf=np.array([o['actual_rf_hz'] for o in observations])
    receivers=np.array([o['receiver'] for o in observations]);channels=np.array([o['channel'] for o in observations])
    n=len(times);hardware=np.zeros((n,p.hardware.shape[1]));smooth=np.zeros((n,p.smooth.shape[1]));width=smooth.shape[1]//2
    for i,(t,f,rx,ch) in enumerate(zip(times,rf,receivers,channels,strict=True)):
        band=int(ch>4);hardware[i,2*(rx-1)+band]=PERIOD/np.sqrt(12)
        hardware[i,4+2*(rx-1)]=t-150;hardware[i,5+2*(rx-1)]=(t-150)*(-1 if band==0 else 1)*.5
        if p.fitted_c:hardware[i,8]=(f/1e9-11.5)*200000
        smooth[i,(rx-1)*width:rx*width]=(f/11.5e9)*projected_receiver_basis(np.array([t]))[0]
    count=len(active);lanes=sorted({(o['receiver'],o['channel'],o['actual_rf_hz']) for o in observations})
    lane_index=np.array([lanes.index((o['receiver'],o['channel'],o['actual_rf_hz'])) for o in observations])
    fields=dict(vars(p));fields.update(flat_times=np.tile(times,count),
        flat_labels=np.repeat([p.labels.index(j) for j in active],n),q=np.tile(rf/11.5e9,count),
        hardware=np.tile(hardware,(count,1)),smooth=np.tile(smooth,(count,1)),
        constants=np.zeros((n*count,p.constants.shape[1])))
    # One constant per inferred family and physical RX/channel/RF lane, shared
    # across that scan; its existing300Hz scale is integrated, never fitted freely.
    bias_index=np.concatenate([lane_index+k*len(lanes) for k in range(count)])
    metadata=p.scan.fixed_window_noise;lookup=metadata['per_observation_noise_sigma_hz']
    noise=np.array([lookup[o['observation_id']] if metadata['extra_parameter_BIC_gain']>0 else p.scan.radio_sigma_hz for o in observations])*np.sqrt(2)
    return SimpleNamespace(**fields),active,bias_index,len(lanes)*count,noise


class OrphanPrediction:
    def __init__(self,p,observations,powers,*,seed=2026102204,draw_power=8,nodes=32,bias_sigma_hz=300.):
        self.p=p;self.observations=observations;self.powers=np.asarray(powers)
        self.view,self.active,self.bias_index,self.bias_count,self.noise=geometry_view(p,observations)
        self.nodes=nodes;self.bias_sigma_hz=bias_sigma_hz;self.width=p.event_start
        # Events are excluded in this prototype. Coordinate order is inherited
        # from the frozen curved model, including every original fragment slot.
        if p.events:raise ValueError('orphan prototype uses the unchanged event-free incumbent')
        uniform=qmc.Sobol(self.width+self.bias_count,scramble=True,seed=seed).random_base2(draw_power)
        self.normal=ndtri(np.clip(uniform,1e-12,1-1e-12))

    def ratios(self,x,shift_hz=0.):
        p=self.p;c=p.curved_calculate(x) if hasattr(p,'curved_calculate') else p.calculate(x)
        features=c['features'][p.keep];groups=p.noise_groups[p.keep]
        weights=self.powers[groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+features.T@(features*weights[:,None])
        covariance=np.linalg.inv(gram);root=np.linalg.cholesky((covariance+covariance.T)/2)
        coefficients=c['coefficient'][:,None]+root@self.normal[:,:self.width].T
        geometry=geometry_features(self.view,np.asarray(x),0.)
        mean=self.view.q[:,None]*geometry['intercept'][:,None]+geometry['features']@coefficients
        mean+=self.bias_sigma_hz*self.normal[:,self.width+self.bias_index].T
        n=len(self.observations);count=len(self.active)
        y=np.tile([o['measured_cfo_hz']+shift_hz for o in self.observations],count)
        density=wrapped_pdf(y[:,None]-mean,np.tile(self.noise,count)[:,None]).reshape(count,n,-1)
        visible=(geometry['elevation'].reshape(count,n)>=0)
        # Every conditional signal density integrates to one when any active
        # family is visible. If none is visible, use the identical clutter density.
        numbers=visible.sum(axis=0)
        ratios=(density*visible[:,:,None]).sum(axis=0)*PERIOD/np.maximum(numbers,1)[:,None]
        ratios[numbers==0]=1.
        return ratios.T

    def calculate(self,x,*,shift_hz=0.,details=False):
        return integrated_clutter(self.ratios(x,shift_hz),self.nodes,details)
