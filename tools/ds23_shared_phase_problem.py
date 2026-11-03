"""Full-covariance shared phase priors for independently qualified events."""

import numpy as np
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem


def phase_transform(begin,labels,supported,members,events,rho):
    if not 0<=rho<1 or len(events)!=len(labels):raise ValueError("aligned phase events and valid correlation required")
    width=begin+len(labels)+3*len(supported)+members;transform=np.eye(width)
    for event in set(e for e in events if e is not None):
        indices=[begin+k for k,e in enumerate(events) if e==event];n=len(indices)
        root=np.sqrt(1-rho)*np.eye(n)+(np.sqrt(1+(n-1)*rho)-np.sqrt(1-rho))/n*np.ones((n,n))
        transform[np.ix_(indices,indices)]=root
    if members:transform[:,-members:]*=.3
    return transform


def current_events(scan,labels,raw):
    result=[]
    for j in labels:
        number=str(int(scan.norads[j]));lines=scan.elements[number]["lines"]
        matches=[v["collected_utc_ns"] for v in raw["past_versions"].get(number,[]) if v["lines"]==lines]
        if len(matches)>1:raise ValueError("ambiguous current element publication event")
        result.append(matches[0] if matches else None)
    return result


def make_shared_problem(scan,node,keep,arm,reference,powers,means,model,events,rho):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model["multiplier"],model["nu"])
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    transform=phase_transform(begin,p.labels,p.supported,len(p.members),events,rho)
    inverse=np.linalg.solve(transform,np.eye(len(transform)));width=len(transform)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model["nu"] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    def calculate(position):
        geometry=geometry_features(p,position,0.);features=geometry["features"]
        raw=p.values-p.q*geometry["intercept"]-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features@transform)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=groups,prior_nu=model["nu"] or 4.)
        latent=bound["coefficient"].copy();latent_precision=bound["coefficient_prior_precision"].copy()
        native_precision=inverse.T@(latent_precision[:,None]*inverse)
        bound["coefficient"]=mean+transform@latent;bound["latent_coefficient"]=transform@latent
        bound["coefficient_prior_matrix"]=native_precision
        bound["coefficient_prior_precision"]=np.diag(native_precision).copy()
        bound["latent_prior_penalty"]=float(np.sum(latent**2*latent_precision))
        precision=np.zeros(len(p.members));precision[present]=bound["noise_precision"];bound["noise_precision"]=precision
        bound["conditional_residual_hz"]=p.values-p.q*geometry["intercept"]-features@bound["coefficient"]
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound["residual"]=np.r_[bound["residual"],np.sqrt(volume)]
        geometry.update(bound);return geometry
    p.calculate=calculate
    return p
