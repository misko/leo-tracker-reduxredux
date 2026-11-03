"""Reception-time geometry for fixed-evidence ALGO03 numerical experiments.

No new physical parameter or prior is introduced. The existing one-way kernel
is differentiated for the same absolute orbital phase and three state modes.
"""

import numpy as np

from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry,predictive_residual
from dsx01_reception_doppler import reception_frequency
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km


def physical_geometry(p,position,*,enabled=True,relativistic=True):
    original=geometry_features(p,position,0.)
    if not enabled:
        return original
    site=geodetic_to_ecef_km(*latlon(position),0.)
    def frequency(phase,mode=None,amplitude=0.):
        def states(t):
            r,v=paired_phase_states(p.sky,t,p.flat_labels,phase)
            if mode is not None:
                dr,dv=paired_phase_states(p.mode_bank,t,p.flat_labels*3+mode,np.repeat(phase,3))
                r=r+amplitude*dr;v=v+amplitude*dv
            return r,v
        return reception_frequency(states,p.flat_times,site,relativistic=relativistic)[0]
    f=frequency(p.reference)
    derivative=(frequency(p.reference+.01)-frequency(p.reference-.01))/.02
    intercept=f-derivative*p.reference[p.flat_labels]
    features=original['features'].copy();begin=p.hardware.shape[1]+p.smooth.shape[1]
    features[:,begin:begin+len(p.labels)]=0.
    features[np.arange(len(f)),begin+p.flat_labels]=p.q*derivative*p.phase_sigma[p.flat_labels]
    mode_begin=begin+len(p.labels)
    if p.supported_local:
        mode_derivatives=np.column_stack([(frequency(p.reference,k,.001)-frequency(p.reference,k,-.001))/.002
                                          for k in range(3)])
        for k,j in enumerate(p.supported_local):
            use=p.flat_labels==j
            features[use,mode_begin+3*k:mode_begin+3*k+3]=p.q[use,None]*mode_derivatives[use]
    return dict(original,features=features,frequency=f,intercept=intercept,derivative=derivative,
                reception_correction_hz=f-original['frequency'])


def reception_problem(scan,node,keep,arm,reference,powers,means,model,*,enabled=True):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:
        groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(x):
        geometry=physical_geometry(p,x,enabled=enabled)
        features=geometry['features'];raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        bound=scale_posterior(bound,scale)
        bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound)
        return geometry
    p.calculate=calculate
    return p


def attach_reception_predictions(p,entries,powers,*,enabled=True):
    if not entries:
        return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    curved_calculate=p.calculate
    def calculate(position):
        c=curved_calculate(position);g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=physical_geometry(view,position,enabled=enabled)
        mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction=predictive_residual(values-mean,geometry['features'],gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-mean
        c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.linear_entries=entries;p.linear_slices=slices
    p.curved_calculate=curved_calculate
    return p
