"""One joint phase/shape Student scale per satellite; no new physical mode.

The existing marginal standard deviations and phase Student degrees stay fixed.
The change is dependence of tail events: a large correction in one orbital
coordinate predicts less confidence in that satellite's other coordinates.
"""

from math import lgamma
import numpy as np

from ds23_height_problem import geometry_features
from ds23_joint_orbit_prior import standardized
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior
from learn_ds23_causal_phase_forecast import distribution_cost


def joint_student_cost(z,nu):
    z=np.asarray(z,float)
    if z.ndim!=2 or not np.isfinite(z).all() or nu<=2:
        raise ValueError('finite vectors and Student degrees >2 required')
    d=z.shape[1]
    return (d*np.log((nu-2)*np.pi)+2*lgamma(nu/2)-2*lgamma((nu+d)/2)+
            (nu+d)*np.log1p(np.sum(z*z,axis=1)/(nu-2)))


def density_gain(rows,model):
    if model['nu'] is None:
        raise ValueError('this control requires an existing Student phase marginal')
    z=standardized(rows,model)
    old=distribution_cost(z[:,0],np.ones(len(z)),1.,model['nu'])+np.sum(z[:,1:]**2,axis=1)+3*np.log(2*np.pi)
    return old-joint_student_cost(z,model['nu'])


def qualify(rows,boundary,prefix_model,full_model):
    if any(m['nu'] is None for m in (prefix_model,full_model)):
        return dict(qualified=False,reason='existing phase marginal is Gaussian')
    train=[r for r in rows if r['validation_time_ns']<=boundary and r['norad']%5!=0]
    future=[r for r in rows if r['validation_time_ns']>boundary]
    disjoint=[r for r in future if r['norad']%5==0]
    if min(map(len,(train,future,disjoint)))<30:
        return dict(qualified=False,reason='insufficient causal temporal/satellite support',
                    counts=[len(train),len(future),len(disjoint)])
    gains={name:float(density_gain(part,prefix_model).sum()) for name,part in
           (('training',train),('future',future),('disjoint_future',disjoint))}
    penalty=2*np.log(2.)
    return dict(qualified=bool(gains['training']>0 and gains['future']>penalty and gains['disjoint_future']>penalty),
        density_gains=gains,selection_penalty=penalty,counts=[len(train),len(future),len(disjoint)],
        all_past_gain=float(density_gain(rows,full_model).sum()),
        no_distribution_parameter_fitted=True,all_marginal_variances_and_phase_degrees_unchanged=True,
        causal_TLE_updates_are_correlated_prediction_proxies_not_orbit_truth=True)


def family_groups(begin,labels,supported,members):
    width=begin+len(labels)+3*len(supported)+members
    groups=np.full(width,-1,int)
    groups[begin:begin+len(labels)]=np.arange(len(labels))
    for k,j in enumerate(supported):
        groups[begin+len(labels)+3*k:begin+len(labels)+3*k+3]=labels.index(j)
    return groups


def make_joint_tail_problem(scan,node,keep,arm,reference,powers,means,model):
    if model['nu'] is None:
        raise ValueError('existing Student phase marginal required')
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.events=[]
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    groups=family_groups(begin,p.labels,p.supported,len(p.members));width=len(groups)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    scales=np.ones(width);scales[-len(p.members):]=.3
    def calculate(position):
        geometry=geometry_features(p,position,0.)
        features=geometry['features'];raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=groups,prior_nu=model['nu'])
        bound=scale_posterior(bound,scales)
        bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound);return geometry
    p.calculate=calculate
    return p
