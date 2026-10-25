"""One-family conditional Gaussian phase integral; no selection or optimization."""
import numpy as np
from scipy.integrate import quad
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, ndtr, ndtri
from scipy.special import roots_legendre

DOMAIN=(-15.,15.)


def solve(root,value):
    return solve_triangular(root.T,solve_triangular(root,value,lower=True),lower=False)


def gaussian_score(raw,design,precision,variance):
    """Normalized Gaussian with diagonal noise and integrated prior coordinates."""
    y,h,p,v=map(np.asarray,(raw,design,precision,variance))
    a=h/np.sqrt(v[:,None]*p[None,:]);w=y/np.sqrt(v)
    root=np.linalg.cholesky(np.eye(h.shape[1])+a.T@a)
    coefficient=solve(root,a.T@w)
    residual=w-a@coefficient
    return float(residual@residual+coefficient@coefficient+
                 2*np.log(np.diag(root)).sum()+np.log(v).sum()+len(y)*np.log(2*np.pi))


def reduce_family(values,intercept,design,precision,variance,prior_mean,
                  selected,phase_slot,mode_slots,phase_sigma,phase_mean):
    """Condition family rows on all other rows after removing its four columns."""
    y,b,h,p,v,m=map(np.asarray,(values,intercept,design,precision,variance,prior_mean))
    chosen=np.asarray(selected,bool);other=~chosen
    removed=np.r_[phase_slot,mode_slots]
    keep=np.ones(h.shape[1],bool);keep[removed]=False
    if not chosen.any() or not other.any():raise ValueError('both family and other data required')
    if np.max(abs(h[other][:,removed]),initial=0)>1e-12:
        raise ValueError('tested family columns leak into other-family rows')
    if np.max(abs(m[mode_slots]),initial=0)>1e-12:
        raise ValueError('physical modes must retain their zero prior mean')
    centered=y-b-h@m
    ho,ht=h[other][:,keep],h[chosen][:,keep]
    gram=np.diag(p[keep])+ho.T@(ho/v[other,None])
    root=np.linalg.cholesky(gram)
    posterior=solve(root,ho.T@(centered[other]/v[other]))
    uncertainty=solve_triangular(root,ht.T,lower=True).T
    covariance=np.diag(v[chosen])+uncertainty@uncertainty.T
    covariance=(covariance+covariance.T)/2
    raw=centered[chosen]+b[chosen]+h[chosen,phase_slot]*m[phase_slot]-ht@posterior
    derivative=h[chosen,phase_slot]/phase_sigma
    modes=h[chosen][:,mode_slots]/np.sqrt(p[mode_slots])[None,:]
    sd=phase_sigma/np.sqrt(p[phase_slot])
    shape_cov=covariance+modes@modes.T
    rs=np.linalg.cholesky(shape_cov)
    posterior_variance=1/(1/sd**2+derivative@solve(rs,derivative))
    posterior_mean=posterior_variance*(phase_mean/sd**2+
        derivative@solve(rs,raw-b[chosen]))
    affine_cov=shape_cov+sd**2*np.outer(derivative,derivative)
    affine_residual=raw-b[chosen]-derivative*phase_mean
    ra=np.linalg.cholesky(affine_cov);wa=solve_triangular(ra,affine_residual,lower=True)
    conditional=float(wa@wa+2*np.log(np.diag(ra)).sum()+chosen.sum()*np.log(2*np.pi))
    full=gaussian_score(centered,h,p,v)
    other_score=gaussian_score(centered[other],ho,p[keep],v[other])
    error=full-other_score-conditional
    if abs(error)>1e-5:raise ValueError('original Gaussian full/conditional closure failed: '+str(error))
    return dict(raw=raw,covariance=covariance,frozen_modes=modes,derivative=derivative,
                affine_intercept=b[chosen],prior_mean=float(phase_mean),prior_sd=float(sd),
                proposal_mean=float(posterior_mean),proposal_sd=float(np.sqrt(posterior_variance)),
                affine_conditional_objective=conditional,full_gaussian_objective=full,
                other_gaussian_objective=other_score,Gaussian_closure_error=float(error),
                removed_columns=removed,retained_columns=np.flatnonzero(keep))


def node_costs(raw,covariance,frequency,modes,*,root=None):
    """Positive-quadratic rank3 integration; batch axes node, observation, mode."""
    f,b=np.asarray(frequency),np.asarray(modes)
    root=np.linalg.cholesky(covariance) if root is None else root
    white=solve_triangular(root,(np.asarray(raw)[None]-f).T,lower=True).T
    wb=solve_triangular(root,b.transpose(1,0,2).reshape(len(raw),-1),lower=True)
    wb=wb.reshape(len(raw),len(f),b.shape[2]).transpose(1,0,2)
    gram=np.eye(b.shape[2])[None]+np.einsum('nki,nkj->nij',wb,wb)
    rhs=np.einsum('nki,nk->ni',wb,white)
    coefficient=np.linalg.solve(gram,rhs[...,None])[...,0]
    residual=white-np.einsum('nki,ni->nk',wb,coefficient)
    quadratic=np.sum(residual**2,axis=1)+np.sum(coefficient**2,axis=1)
    return quadratic+np.linalg.slogdet(gram)[1]+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi)


def dense_node_cost(raw,covariance,frequency,modes):
    c=covariance+modes@modes.T;r=np.linalg.cholesky(c)
    w=solve_triangular(r,raw-frequency,lower=True)
    return float(w@w+2*np.log(np.diag(r)).sum()+len(raw)*np.log(2*np.pi))


def normal_logpdf(value,mean,sd):
    return -.5*((np.asarray(value)-mean)/sd)**2-np.log(sd)-.5*np.log(2*np.pi)


def domain_mass(mean,sd):
    a,b=ndtr((np.asarray(DOMAIN)-mean)/sd)
    mass=float(b-a)
    if not np.isfinite(mass) or mass<1e-12:raise ValueError('unresolved truncated Normal mass')
    return mass,float(a),float(b)


def proposal_rule(mean,sd,count):
    mass,a,b=domain_mass(mean,sd)
    nodes,weights=roots_legendre(count)
    u=(nodes+1)/2
    phases=mean+sd*ndtri(a+mass*u)
    return phases,np.log(weights/2),mass


def integrate(data,evaluate,branch,count):
    phases,weights,qmass=proposal_rule(data['proposal_mean'],data['proposal_sd'],count)
    f,b,e=evaluate(phases)
    if branch=='frozen':b=np.broadcast_to(data['frozen_modes'],b.shape)
    costs=node_costs(data['raw'],data['covariance'],f,b,root=data.get('covariance_root'))
    prior_mass=domain_mass(data['prior_mean'],data['prior_sd'])[0]
    logratio=(-costs/2+normal_logpdf(phases,data['prior_mean'],data['prior_sd'])-
        normal_logpdf(phases,data['proposal_mean'],data['proposal_sd']))
    terms=weights+logratio
    log_integral=float(logsumexp(terms)+np.log(qmass)-np.log(prior_mass))
    norm=np.exp(terms-logsumexp(terms))
    limits=phases[[0,-1]]
    prior_sampled=float(np.diff(ndtr((limits-data['prior_mean'])/data['prior_sd']))[0])
    q_sampled=float(np.diff(ndtr((limits-data['proposal_mean'])/data['proposal_sd']))[0])
    return dict(objective=-2*log_integral,log_evidence=log_integral,
        prior_domain_mass=prior_mass,proposal_domain_mass=qmass,
        sampled_phase_range_s=[float(phases.min()),float(phases.max())],
        maximum_normalized_weight=float(norm.max()),
        edge_node_weight=float(norm[0]+norm[-1]),minimum_sampled_elevation_deg=float(e.min()),
        prior_domain_mass_outside_sampled_range=max(0.,1-prior_sampled/prior_mass),
        proposal_domain_mass_outside_sampled_range=max(0.,1-q_sampled/qmass))


def adaptive_reference(data,evaluate,branch):
    """Direct phase-space adaptive reference; resolved modes, not global proof."""
    qmean,qsd=data['proposal_mean'],data['proposal_sd']
    points=np.unique(np.r_[np.linspace(*DOMAIN,31),qmean+qsd*np.array([-8,-4,-2,-1,-.5,0,.5,1,2,4,8])])
    points=points[(points>=DOMAIN[0])&(points<=DOMAIN[1])]
    prior_mass=domain_mass(data['prior_mean'],data['prior_sd'])[0]
    def logvalue(phases):
        f,b,e=evaluate(np.asarray(phases))
        if branch=='frozen':b=np.broadcast_to(data['frozen_modes'],b.shape)
        costs=node_costs(data['raw'],data['covariance'],f,b,root=data.get('covariance_root'))
        return -costs/2+normal_logpdf(phases,data['prior_mean'],data['prior_sd'])-np.log(prior_mass)
    peak=float(np.max(logvalue(points)))
    calls=0
    def density(phi):
        nonlocal calls
        calls+=1
        return float(np.exp(logvalue([phi])[0]-peak))
    result,error=quad(density,*DOMAIN,points=points[1:-1],epsabs=1e-10,epsrel=1e-8,limit=300)[:2]
    if result<=0 or not np.isfinite(result):raise ValueError('adaptive reference failed')
    return dict(objective=float(-2*(peak+np.log(result))),relative_error=float(error/result),
                evaluations=calls,phase_partition_s=points.tolist(),global_mode_certificate=False)
