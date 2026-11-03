"""Keep causal physical orbit uncertainty for singly observed families too.

Replication changes how well uncertainty can be constrained; it does not make
an unreplicated satellite's non-phase orbit exact. Engineering scales and the
causal history are unchanged. Original ALGO02 sources stay frozen.
"""

import numpy as np
from build_dsx01_orbit_modes import build_modes
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from investigate_algo01_ds23_0217 import problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def include_unreplicated(p, builder=build_modes):
    previous=list(p.supported)
    p.supported=list(p.labels)
    p.supported_local=list(range(len(p.labels)))
    p.mode_bank,p.mode_metadata=builder(p.scan,p.labels,p.supported,"physical")
    p.new_uncertain_families=[j for j in p.labels if j not in previous]
    return p


def make_problem(scan,node,keep,arm,reference,powers,means,model,enabled=True):
    p=problem(scan,node,arm,keep,reference)
    if enabled:
        include_unreplicated(p)
    p.phase_sigma*=model["multiplier"]
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model["nu"] is not None:
        groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    def calculate(position):
        geometry=JointMarginal.calculate(p,position)
        features=geometry["features"]
        scale=np.ones(width);scale[-len(p.members):]=.3
        raw=p.values-p.q*geometry["intercept"]-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],
            p.noise_groups[keep],powers=powers[present],prior_groups=None if model["nu"] is None else groups,
            prior_nu=model["nu"] or 4.)
        bound=scale_posterior(bound,scale)
        latent=bound["coefficient"].copy()
        bound["coefficient"]=latent+mean;bound["latent_coefficient"]=latent
        precision=np.zeros(len(p.members));precision[present]=bound["noise_precision"]
        bound["noise_precision"]=precision
        bound["conditional_residual_hz"]=p.values-p.q*geometry["intercept"]-features@bound["coefficient"]
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound["residual"]=np.r_[bound["residual"],np.sqrt(volume)]
        geometry.update(bound)
        return geometry
    p.calculate=calculate
    return p
