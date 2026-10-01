"""All-candidate residual curvature for the full marginal model, no truncation."""
import numpy as np
from marginal_visibility_port import normalized_mass
from epoch_block_curvature import solve_blocks


def candidate_blocks(port,state):
    _,probabilities=normalized_mass(port.score_all(state))
    batch=port.original.linearize_candidates(state,np.arange(port.candidate_count))
    residual=port.observation[None,:]-batch['means'];precision=port.likelihood.precision
    quadratic=np.einsum('ni,ij,nj->n',residual,precision,residual)
    weights=probabilities[:-1]*(4+residual.shape[1])/(4+quadratic)
    jac=batch['jacobians']
    return np.einsum('nmi,mk,nkj->nij',jac,precision,jac)*weights[:,None,None]


def curvature_direction(model,state,gradient):
    blocks=[candidate_blocks(port,state[columns]) for port,columns in zip(model.ports,model.columns,strict=True)]
    return -solve_blocks(model.precision,model.columns,blocks,gradient)
