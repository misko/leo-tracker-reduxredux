"""Independent finite-window same-RX RF contrasts in the original hierarchy.

Contrasts retain fragment constants, orbital uncertainty and the small response
to frequency rate. This is not an orbital timing factor. Callers must quarantine
the original IQ support before constructing this research problem.
"""

import numpy as np

from ds23_differential_information import difference_query
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_gaussian_information import gaussian_factor_bound
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry,predictive_residual
from dsx01_joint_marginal import JointMarginal
from leo.analysis.research.retained_track_likelihood import PERIOD


def lift_measured_contrast(measured,native,lifted,aliases):
    a=np.asarray(aliases,int);native=np.asarray(native,float);lifted=np.asarray(lifted,float)
    if a.shape!=(2,) or native.shape!=(2,) or lifted.shape!=(2,) or not np.isfinite(np.r_[measured,native,lifted]).all():
        raise ValueError('two finite native/lifted carriers and two integer fragment aliases required')
    correction=lifted-native
    if not np.allclose(correction/PERIOD,np.rint(correction/PERIOD),rtol=0,atol=1e-8):
        raise ValueError('graph lifts must be exact integer carrier aliases')
    return float(measured+correction[0]-correction[1]+(a[0]-a[1])*PERIOD)


def windowed_geometry(p,measurement,position,*,time_step_s=.01):
    rows=measurement['curve_rows'];t=measurement.get('carrier_epoch_s',measurement['time_s']);rf=measurement['rf_hz']
    response=np.asarray(measurement['frequency_rate_response_s'],float)
    if response.shape!=(2,) or not np.isfinite(response).all() or time_step_s<=0:
        raise ValueError('two finite carrier-rate responses and positive time step required')
    values=[];features=[]
    for time in [t-time_step_s,t,t+time_step_s]:
        view=difference_query(p,rows,time,rf);g=geometry_features(view,position,0.)
        values.append(view.q*g['intercept']);features.append(g['features'])
    slope=(values[2]-values[0])/(2*time_step_s)
    derivative=(features[2]-features[0])/(2*time_step_s)
    return dict(intercept_hz=float(values[1][0]-values[1][1]+response@slope),
        features=features[1][0]-features[1][1]+response@derivative,
        component_rate_intercept_hz_s=slope,component_rate_features_hz_s=derivative)


def make_differential_problem(scan,node,keep,arm,reference,powers,means,model,measurements):
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,[])
    if not measurements:return p
    nb,ns=p.hardware.shape[1],p.smooth.shape[1];begin=nb+ns
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    scales=np.ones(width);scales[-len(p.members):]=.3
    prior=np.full(width,-1,int)
    if model['nu'] is not None:prior[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    observed=[]
    for r in measurements:
        rows=r['curve_rows']
        if [scan.tracks[p.members[k]]['key'] for k in rows]!=r['curve_components']:
            raise ValueError('RF ownership rows no longer match original curved components')
        if [int(scan.norads[p.rows[k]['candidate_index']]) for k in rows]!=r['proposed_norads']:
            raise ValueError('RF ownership hypothesis differs from original candidate identities')
        observed.append(lift_measured_contrast(r['difference_hz'],r['native_CFO_hz'],r['lifted_CFO_hz'],[p.alias[k] for k in rows]))
    observed=np.asarray(observed);sigma=np.array([r['sigma_hz'] for r in measurements]);present=np.unique(p.noise_groups[keep])
    def calculate(position):
        g=JointMarginal.calculate(p,position);features=g['features']
        query=[windowed_geometry(p,r,position) for r in measurements]
        d=np.array([r['features'] for r in query]);intercept=np.array([r['intercept_hz'] for r in query])
        raw=p.values-p.q*g['intercept']-features@mean
        bound=gaussian_factor_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            observed-intercept-d@mean,d*scales,sigma,powers=np.asarray(powers)[present],
            prior_groups=None if model['nu'] is None else prior,prior_nu=4 if model['nu'] is None else model['nu'])
        latent=bound['coefficient']*scales;bound['coefficient']=latent+mean;bound['latent_coefficient']=latent
        bound['coefficient_prior_precision']/=scales**2
        bound['coefficient_covariance']*=scales[:,None]*scales[None,:]
        bound['calibration_posterior_precision']=bound['coefficient_posterior_precision']/scales[:,None]/scales[None,:]
        bound['coefficient_posterior_precision']=bound['calibration_posterior_precision']
        noise=np.zeros(len(p.members));noise[present]=bound['noise_precision'];bound['noise_precision']=noise
        bound['conditional_residual_hz']=p.values-p.q*g['intercept']-features@bound['coefficient']
        bound['differential_residual_hz']=observed-intercept-d@bound['coefficient']
        bound['differential_sigma_hz']=sigma
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        g.update(bound);return g
    p.calculate=calculate;p.independent_differential_measurements=measurements
    return p


def attach_differential_predictive(p,entries,powers):
    if not getattr(p,'independent_differential_measurements',[]):return attach_event_predictive(p,entries,powers)
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.calculate
    def calculate(position):
        c=curved(position);g=geometry_features(view,position,0.)
        predicted=view.q*g['intercept']+g['features']@c['coefficient']
        bound=predictive_residual(values-predicted,g['features'],c['calibration_posterior_precision'],sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['negative_twice_elbo']+=bound['objective']
        c['normalization_constant']+=bound['normalization_constant'];c['residual']=np.r_[c['residual'],bound['residual']]
        c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=g['elevation'];return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries;p.linear_slices=slices
    return p
