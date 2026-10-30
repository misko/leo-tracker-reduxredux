"""An explicit existing phase coordinate in a conditional research likelihood.

Receivers, other satellites and orbit coefficients stay at the curved-data
posterior means at each position. Correlated old fragment constants reconcile
with the explicit phase. Their uncertainty has no design on predictive points.
The phase density normalization is retained when comparing positions.
"""
import numpy as np
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_height_problem import geometry_features

PHASE_UNIT_S=.1


def evidence_context(d,policy):
    """Isolate fixed measurement noise and unit curve powers in matched trials."""
    if policy=='original':return d
    if policy=='unit_weights_only':return dict(d,powers=np.ones(len(d['powers'])))
    if policy not in ('annotation_fixed','fixed_noise_only'):raise ValueError('unknown evidence weighting policy')
    from include_predictive_annotations import annotation_noise_context
    changed=annotation_noise_context(d)
    if policy=='fixed_noise_only':changed['powers']=np.asarray(d['powers']).copy()
    return changed


def conditional_phase(mean, precision, phase_index, bias_indices, value):
    """Marginal phase density after conditioning others and eliminating biases."""
    a,g=np.asarray(mean,float),np.asarray(precision,float);b=np.asarray(bias_indices,dtype=int)
    if a.ndim!=1 or g.shape!=(len(a),len(a)) or not np.isfinite(np.r_[a,g.ravel(),value]).all():
        raise ValueError('finite matching coefficient and precision geometry required')
    if not 0<=phase_index<len(a) or b.ndim!=1 or len(set(b))!=len(b) or np.any(b<0) or np.any(b>=len(a)) or phase_index in b:
        raise ValueError('distinct valid phase and bias coordinates required')
    if not np.allclose(g,g.T):raise ValueError('symmetric precision required')
    local=g[np.ix_(b,b)];cross=g[b,phase_index]
    np.linalg.cholesky(local)
    response=np.linalg.solve(local,cross)
    q=float(g[phase_index,phase_index]-cross@response)
    if q<=0:raise ValueError('positive conditional phase precision required')
    delta=np.zeros(len(a));delta[phase_index]=value-a[phase_index];delta[b]=-response*delta[phase_index]
    return dict(coefficient=a+delta,delta=delta,precision=q,
        negative_twice_phase_log_density=float(q*delta[phase_index]**2-np.log(q)+np.log(2*np.pi)))


def attach_explicit_phase(p,entries,powers,family):
    """Wrap a no-event problem; optimizer coordinates are east, north, phase/.1s."""
    if p.events or family not in p.labels or not entries:raise ValueError('existing family and predictive entries in a no-event model required')
    begin=p.hardware.shape[1]+p.smooth.shape[1];local=p.labels.index(family);phase_index=begin+local
    bias_start=begin+len(p.labels)+3*len(p.supported)
    biases=[bias_start+k for k,r in enumerate(p.rows) if r['candidate_index']==family]
    curved=p.curved_calculate
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    def calculate(z):
        z=np.asarray(z,float)
        if z.shape!=(3,) or not np.isfinite(z).all():raise ValueError('east, north and scaled shared phase required')
        x=z[:2];base=curved(x);c=dict(base)
        g=p.noise_groups[p.keep];w=np.asarray(powers)[g]*base['noise_precision'][g]/p.point_noise[p.keep]**2
        u=base['features'][p.keep];gram=np.diag(base['coefficient_prior_precision'])+u.T@(u*w[:,None])
        phase=conditional_phase(base['coefficient'],gram,phase_index,biases,z[2]*PHASE_UNIT_S/p.phase_sigma[local])
        geometry=geometry_features(view,x,0.);h=geometry['features']
        raw=values-view.q*geometry['intercept']-h@phase['coefficient']
        prediction=predictive_residual(raw,np.empty((len(raw),0)),np.empty((0,0)),sigma*np.sqrt(2),groups)
        density=phase['negative_twice_phase_log_density']
        c.update(coefficient=phase['coefficient'],latent_coefficient=base['latent_coefficient']+phase['delta'],
            conditional_residual_hz=base['conditional_residual_hz']-base['features']@phase['delta'],
            linear_raw_prediction_residual_hz=raw,linear_elevation=geometry['elevation'],
            negative_twice_elbo=base['negative_twice_elbo']+density+prediction['objective'],
            curved_negative_twice_elbo=base['negative_twice_elbo'],linear_predictive_objective=prediction['objective'],
            explicit_phase_density=density,explicit_phase_conditional_precision=phase['precision'],
            shared_satellite_receiver_change=float(np.max(abs(phase['delta'][:begin]))),
            shared_satellite_coefficient_change=phase['delta'],
            objective_kind='curved_ELBO_plus_conditional_phase_density_plus_predictive_density',
            residual=np.r_[base['residual'],prediction['residual']],
            residual_vector_not_an_objective_factorization=True)
        return c
    p.calculate=calculate;p.curved_calculate=lambda z:curved(np.asarray(z)[:2])
    p.lower=np.r_[p.lower[:2],-15/PHASE_UNIT_S];p.upper=np.r_[p.upper[:2],15/PHASE_UNIT_S]
    p.shared_satellite_families=[family];p.explicit_phase_family=family
    return p
