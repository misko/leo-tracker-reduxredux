"""Condition existing radio priors on independent differential-RX measurements.

No new drift coordinate is added. Gaussian calibration data first condition
the existing Gaussian radio block exactly. Curved RF observations then update
that correlated prior through the existing Gaussian/Gamma bound. Predictive
linear observations retain the complete posterior covariance and never update
the returned radio/phase/orbit calibration.
"""

import numpy as np

from ds23_frequency_events import make_event_problem, event_design
from ds23_predictive_linear import linear_geometry, predictive_residual
from ds23_height_problem import geometry_features
from dsx01_joint_marginal import JointMarginal
from dsx01_hierarchical_bound import hierarchical_bound
from leo.analysis.research.retained_track_likelihood import PERIOD


def principal_radio_contrast(values):
    """Choose the zero-centred radio gauge for a pilot-alias contrast.

    This is a coordinate convention, not independent evidence for an absolute
    alias. A calibration using this value remains conditional on that branch.
    """
    values=np.asarray(values,float)
    if not np.isfinite(values).all():
        raise ValueError('finite relative carriers required')
    return (values+PERIOD/2)%PERIOD-PERIOD/2


def condition_unit_gaussian(design, values, sigma):
    d,z,s=np.asarray(design,float),np.asarray(values,float),np.asarray(sigma,float)
    if (d.ndim!=2 or z.shape!=(len(d),) or s.shape!=z.shape or not len(z) or
            np.any(s<=0) or not all(np.isfinite(x).all() for x in (d,z,s))):
        raise ValueError('finite matching Gaussian calibration arrays required')
    a=d/s[:,None]
    precision=np.eye(d.shape[1])+a.T@a
    root=np.linalg.cholesky(precision)
    mean=np.linalg.solve(root.T,np.linalg.solve(root,a.T@(z/s)))
    transform=np.linalg.solve(root.T,np.eye(len(precision)))
    covariance=transform@transform.T
    marginal=np.diag(s*s)+d@d.T
    mroot=np.linalg.cholesky(marginal)
    white=np.linalg.solve(mroot,z)
    cost=float(white@white+2*np.log(np.diag(mroot)).sum()+len(z)*np.log(2*np.pi))
    return dict(mean=mean,transform=transform,inverse_transform=root.T,
                covariance=covariance,precision=precision,negative_twice_log_density=cost)


def radio_difference_design(width,hardware_width,smooth_width,event_start,events,
                            times,channels,rf_hz,basis):
    t,ch,rf=np.broadcast_arrays(np.asarray(times,float),np.asarray(channels),np.asarray(rf_hz,float))
    b=np.asarray(basis,float)
    if (t.ndim!=1 or hardware_width not in (8,9) or smooth_width%2 or
            b.shape!=(len(t),smooth_width//2) or event_start+len(events)!=width or
            not all(np.isfinite(v).all() for v in (t,ch,rf,b)) or np.any(rf<=0)):
        raise ValueError('matching radio coordinates and coefficient dimensions required')
    result=np.zeros((len(t),width))
    band=(ch>4).astype(int)
    q=rf/11.5e9
    for rx,sign in ((0,-1.),(1,1.)):
        result[np.arange(len(t)),2*rx+band]=sign*PERIOD/np.sqrt(12)
        result[:,4+2*rx]=sign*10*(t-150)
        result[:,5+2*rx]=sign*(t-150)*np.where(band==0,-.5,.5)
        start=hardware_width+rx*(smooth_width//2)
        result[:,start:start+smooth_width//2]=sign*200*q[:,None]*b
    if events:
        for rx,sign in ((1,-1.),(2,1.)):
            result[:,event_start:]+=sign*event_design(t,np.full(len(t),rx),ch,rf,
                                                     np.full(len(t),-1),events)
    return result


def make_calibrated_problem(scan,node,keep,arm,reference,powers,means,model,events,measurements,basis_function):
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,events)
    if not measurements:
        return p
    nb,ns=p.hardware.shape[1],p.smooth.shape[1]
    original_width=nb+ns+len(p.labels)+3*len(p.supported)+len(p.members)
    width=original_width+len(events)
    times=np.array([r['time_s'] for r in measurements])
    channels=np.array([r['channel'] for r in measurements])
    rf=np.array([r['rf_hz'] for r in measurements])
    design=radio_difference_design(width,nb,ns,original_width,events,times,channels,rf,basis_function(times))
    values=np.array([r['relative_CFO_hz'] for r in measurements])
    sigma=np.array([r['sigma_hz'] for r in measurements])
    radio=list(range(nb+ns))+[original_width+k for k,e in enumerate(events) if e['kind']!='family']
    conditioned=condition_unit_gaussian(design[:,radio],values,sigma)
    transform=np.eye(width)
    inverse=np.eye(width)
    transform[np.ix_(radio,radio)]=conditioned['transform']
    inverse[np.ix_(radio,radio)]=conditioned['inverse_transform']
    constants=np.arange(original_width-len(p.members),original_width)
    transform[constants,constants]=.3
    inverse[constants,constants]=1/.3
    mean=np.zeros(width)
    mean[radio]=conditioned['mean']
    mean[nb+ns:nb+ns+len(p.labels)]=means/p.phase_sigma
    prior_groups=np.full(width,-1,int)
    if model['nu'] is not None:
        prior_groups[nb+ns:nb+ns+len(p.labels)]=np.arange(len(p.labels))
    labels=np.asarray(p.labels)[p.flat_labels]
    receivers=np.concatenate([np.full(len(scan.tracks[i]['times']),scan.tracks[i]['receiver']) for i in p.members])
    channels_RF=np.concatenate([np.full(len(scan.tracks[i]['times']),scan.tracks[i]['channel']) for i in p.members])
    event_features=event_design(p.flat_times,receivers,channels_RF,p.q*11.5e9,labels,events)
    present=np.unique(p.noise_groups[keep])
    def calculate(position):
        geometry=JointMarginal.calculate(p,position)
        if not np.allclose(geometry['scales'],1.,atol=1e-12,rtol=0):
            raise ValueError('calibration prototype requires the fixed physical prior scales')
        features=np.column_stack((geometry['features'],event_features))
        transformed=features@transform
        raw=p.values-p.q*geometry['intercept']-features@mean
        bound=hierarchical_bound(raw[keep],transformed[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=None if model['nu'] is None else prior_groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        latent=bound['coefficient'].copy()
        precision_latent=bound['coefficient_prior_precision'].copy()
        full_precision=(inverse.T*precision_latent)@inverse
        coefficient=mean+transform@latent
        weights=np.zeros(len(p.members))
        weights[present]=bound['noise_precision']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound.update(coefficient=coefficient,latent_coefficient=latent,noise_precision=weights,
            coefficient_prior_precision=np.diag(full_precision).copy(),
            full_coefficient_prior_precision=full_precision,
            conditional_residual_hz=p.values-p.q*geometry['intercept']-features@coefficient,
            calibration_residual_hz=values-design@coefficient,
            calibration_sigma_hz=sigma,
            calibration_prior_log_density=conditioned['negative_twice_log_density'],
            physical_prior_is_correlated=True)
        bound['negative_twice_elbo']+=conditioned['negative_twice_log_density']
        bound['normalization_constant']+=conditioned['negative_twice_log_density']
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound,features=features,event_amplitudes_hz=
            np.array([e['sigma_hz'] for e in events])*coefficient[original_width:])
        return geometry
    p.calculate=calculate
    p.independent_radio_calibration=measurements
    return p


def attach_calibrated_predictive(p,entries,powers):
    if not getattr(p,'independent_radio_calibration',[]):
        from ds23_frequency_events import attach_event_predictive
        return attach_event_predictive(p,entries,powers)
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    rx=np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']),p.scan.tracks[e['track_index']]['receiver']) for e in entries])
    ch=np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']),p.scan.tracks[e['track_index']]['channel']) for e in entries])
    design=event_design(view.flat_times,rx,ch,view.q*11.5e9,np.asarray(p.labels)[view.flat_labels],p.events)
    curved=p.calculate
    def calculate(position):
        c=curved(position)
        g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        features=c['features'][p.keep]
        gram=c['full_coefficient_prior_precision']+features.T@(features*w[:,None])
        geometry=geometry_features(view,position,0.)
        full_features=np.column_stack((geometry['features'],design))
        prediction=view.q*geometry['intercept']+full_features@c['coefficient']
        bound=predictive_residual(values-prediction,full_features,gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['negative_twice_elbo']+=bound['objective']
        c['normalization_constant']+=bound['normalization_constant']
        c['residual']=np.r_[c['residual'],bound['residual']]
        c['linear_raw_prediction_residual_hz']=values-prediction
        c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate
    p.curved_calculate=curved
    p.linear_entries,p.linear_slices=entries,slices
    return p
