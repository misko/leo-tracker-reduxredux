"""Bounded common-UTC integration with curved-only node calibration.

UTC advances observation time. An independent orbital phase still performs
the Earth-rotation undo inside the existing phase kernel. They are distinct.
Clock integration averages normalized generalized RF bounds; it is not an
exact likelihood for the existing Gamma variational approximation.
"""

from types import SimpleNamespace
import numpy as np

from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry,predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def uniform_quadrature(lower,upper,count):
    if not np.isfinite([lower,upper]).all() or lower>=upper or count<1:
        raise ValueError('ordered finite clock bounds and positive node count required')
    x,w=np.polynomial.legendre.leggauss(count)
    return (lower+upper)/2+(upper-lower)*x/2,w/2


def mixture(costs,prior_weights):
    cost,w=np.asarray(costs,float),np.asarray(prior_weights,float)
    if cost.ndim!=1 or w.shape!=cost.shape or not len(cost) or not np.isfinite(cost).all() or np.any(w<=0) or not np.isfinite(w).all():
        raise ValueError('finite node costs and positive aligned quadrature masses required')
    w=w/w.sum();logmass=np.log(w)-cost/2;peak=float(logmass.max())
    logz=peak+np.log(np.exp(logmass-peak).sum())
    return dict(objective=float(-2*logz),weights=np.exp(logmass-logz))


def mixture_residual(residuals,prior_weights):
    r=[np.asarray(v,float) for v in residuals]
    if not r or any(v.ndim!=1 or not np.isfinite(v).all() for v in r):
        raise ValueError('finite one-dimensional component residuals required')
    w=np.asarray(prior_weights,float);w=w/w.sum()
    m=mixture([float(v@v) for v in r],w);q=m['weights'];use=q>0
    kl=float(np.sum(q[use]*(np.log(q[use])-np.log(w[use]))))
    if kl< -1e-9:raise ValueError('negative discrete posterior KL')
    result=np.r_[np.concatenate([v*np.sqrt(p) for v,p in zip(r,q,strict=True)]),np.sqrt(2*max(0.,kl))]
    if not np.isclose(result@result,m['objective'],atol=1e-7,rtol=1e-10):
        raise ValueError('mixture residual does not represent integrated objective')
    return dict(m,residual=result,posterior_KL=max(0.,kl))


def utc_geometry(p,position,shift_s):
    if not np.isfinite(shift_s):raise ValueError('finite common UTC shift required')
    fields=dict(vars(p));fields['flat_times']=p.flat_times+shift_s
    # Hardware features/bases keep their original elapsed-time coordinates;
    # reference is independent TLE phase, not phase + UTC.
    return geometry_features(SimpleNamespace(**fields),np.asarray(position)[:2],0.)


def fixed_clock_node(scan,node,keep,arm,reference,powers,means,model,shift_s,interval=None):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.events=[];p.fixed_shift_s=None if shift_s is None else float(shift_s)
    if shift_s is None:
        if interval is None:raise ValueError('profiled UTC needs its recorded interval')
        p.initial=np.r_[p.initial,0.];p.lower=np.r_[p.lower,interval['lower_s']/.1];p.upper=np.r_[p.upper,interval['upper_s']/.1]
    clock=lambda position:.1*float(np.asarray(position)[2]) if shift_s is None else float(shift_s)
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(position):
        c=utc_geometry(p,position,clock(position));u=c['features']
        raw=p.values-p.q*c['intercept']-u@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(u*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=None if model['nu'] is None else groups,prior_nu=model['nu'] or 4.)
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-u@b['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)]
        c.update(b,common_UTC_shift_s=clock(position));return c
    p.calculate=calculate;original=p.state
    def state(position):
        s=original(position);s['common_UTC_shift_s']=clock(position);return s
    p.state=state
    return p


def attach_clock_prediction(p,entries,powers):
    if not entries:return p
    if p.fixed_shift_s is None:
        raise ValueError('linear measurements do not fit the profiled clock')
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.calculate
    def calculate(position):
        c=curved(position);g=p.noise_groups[p.keep]
        weight=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weight[:,None])
        geometry=utc_geometry(view,position,p.fixed_shift_s)
        expected=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction=predictive_residual(values-expected,geometry['features'],gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['objective'];c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant'];c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-expected;c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries;p.linear_slices=slices
    return p


class MarginalClock:
    def __init__(self,nodes,weights):
        if not nodes or len(nodes)!=len(weights):raise ValueError('one positive mass per clock node required')
        self.nodes=nodes;self.weights=np.asarray(weights,float)
        self.keep=nodes[0].keep;self.lower=nodes[0].lower;self.upper=nodes[0].upper
        self.initial=np.zeros(2)

    def calculate(self,position):
        components=[p.calculate(position) for p in self.nodes]
        residuals=[p.residual(position) for p in self.nodes]
        horizons=np.array([np.sum(np.maximum(0.,-c['elevation'][p.keep])**2)/4 for p,c in zip(self.nodes,components,strict=True)])
        offsets=np.array([c['negative_twice_elbo']+h-float(r@r) for c,h,r in zip(components,horizons,residuals,strict=True)])
        if np.ptp(offsets)>1e-5:raise ValueError('node residual normalization offsets differ')
        joint=mixture_residual(residuals,self.weights)
        curved=mixture([c.get('curved_negative_twice_elbo',c['negative_twice_elbo'])+h for c,h in zip(components,horizons,strict=True)],self.weights)
        mode=int(np.argmax(curved['weights']))
        return dict(components[mode],residual=joint['residual'],
            negative_twice_elbo=joint['objective']+float(offsets[0]),
            mixture_residual_energy=joint['objective'],mixture_normalization_offset=float(offsets[0]),
            joint_clock_weights=joint['weights'],curved_clock_weights=curved['weights'],
            curved_mixture_objective=curved['objective'],curved_clock_mode=mode,
            clock_KL_from_uniform=joint['posterior_KL'])

    def residual(self,position):return self.calculate(position)['residual']
