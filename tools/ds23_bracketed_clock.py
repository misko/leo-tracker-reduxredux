"""One common UTC coordinate bounded by this recording's original host bracket.

This profiles a uniform interval timing prior, rather than claiming an exact
sample timestamp at its midpoint. It is distinct from sample-rate drift,
satellite transmitter CFO, and publication-event phase correlations.
"""

from types import SimpleNamespace
import numpy as np
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry,predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def clock_interval(document,origin_utc_ns):
    if 'source' in document:
        a=document['clock_anchor'];lo=a['before']['realtime_ns'];hi=a['after']['realtime_ns']
        offsets=[a[k]['realtime_ns']-a[k]['monotonic_ns'] for k in ('before','after')]
        lo=a['before']['monotonic_ns']+min(offsets)
        hi=a['after']['monotonic_ns']+max(offsets)
    else:
        timing=document['timing']
        if not timing['qualified']:raise ValueError('qualified UTC evidence required')
        lo=timing['first_sample_earliest_utc_ns'];hi=timing['first_sample_latest_utc_ns']
    if not lo<=origin_utc_ns<=hi or not 0<hi-lo<=2_000_000_000:
        raise ValueError('original time origin must lie inside the recorded UTC bracket')
    return dict(lower_s=(lo-origin_utc_ns)/1e9,upper_s=(hi-origin_utc_ns)/1e9,
                width_s=(hi-lo)/1e9,origin_utc_ns=origin_utc_ns,
                no_GPS_or_TLE_used=True)


def clock_geometry(p,position,shift_s):
    view=SimpleNamespace(**vars(p));view.reference=p.reference+shift_s
    c=geometry_features(view,np.asarray(position)[:2],0.)
    # The phase prior refers to independent TLE error. The common clock has
    # already shifted the orbit evaluation and is not subtracted as TLE phase.
    c['intercept']=c['intercept']+c['derivative']*shift_s
    return c


def clock_problem(scan,node,keep,arm,reference,powers,means,model,interval,*,fixed_shift_s=None):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.events=[];p.fixed_shift_s=fixed_shift_s
    p.clock_shift=lambda x:float(np.asarray(x)[2]*.1) if fixed_shift_s is None else float(fixed_shift_s)
    if fixed_shift_s is None:
        p.initial=np.r_[p.initial,0.];p.lower=np.r_[p.lower,interval['lower_s']/.1];p.upper=np.r_[p.upper,interval['upper_s']/.1]
    elif not interval['lower_s']<=fixed_shift_s<=interval['upper_s']:
        raise ValueError('fixed clock estimate lies outside recorded interval')
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(x):
        c=clock_geometry(p,x,p.clock_shift(x));u=c['features']
        raw=p.values-p.q*c['intercept']-u@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(u*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=None if model['nu'] is None else groups,prior_nu=model['nu'] or 4.)
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-u@b['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)]
        c.update(b,common_UTC_shift_s=p.clock_shift(x));return c
    p.calculate=calculate
    original_state=p.state
    def state(x):
        s=original_state(x);s['common_UTC_shift_s']=p.clock_shift(x)
        return s
    p.state=state
    return p


def attach_clock_prediction(p,entries,powers):
    if not entries:return p
    if p.fixed_shift_s is None:
        raise ValueError('linear evidence cannot estimate the common UTC correction')
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.calculate
    def calculate(x):
        c=curved(x);g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=clock_geometry(view,x,p.fixed_shift_s)
        expected=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction=predictive_residual(values-expected,geometry['features'],gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['objective'];c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant'];c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-expected;c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries;p.linear_slices=slices
    return p
