"""Full-catalogue log-sum-exp scoring with compact batched gradients."""
import numpy as np
from window_inputs import prepare_scan as _establish_research_imports
from shared_visibility_port import SharedVisibilityPort


def normalized_mass(scores):
    scores=np.asarray(scores,dtype=float);maximum=float(np.max(scores))
    if scores.ndim!=1 or not np.isfinite(maximum) or np.any(np.isnan(scores)):
        raise ValueError('finite branch mass required')
    weights=np.exp(scores-maximum);total=float(np.sum(weights))
    return maximum+np.log(total),weights/total


def visibility_mixture_gradient(probabilities,components):
    logs,reduced,epochs=components;count=len(epochs)
    p=np.asarray(probabilities,dtype=float)
    if p.shape!=(count+1,):raise ValueError('branch mass shape mismatch')
    result=np.zeros(5+count);result[:3]=p@reduced
    result[5:]=p[:-1]*reduced[:-1,2]+p[-1]*epochs
    return result


def residual_mixture_gradient(probabilities,residual,precision,jacobians):
    residual=np.asarray(residual);jacobians=np.asarray(jacobians)
    solved=residual@precision.T
    weight=(4+residual.shape[1])/(4+np.einsum('ni,ni->n',residual,solved))
    compact=np.einsum('nmc,nm->nc',jacobians,solved)*(probabilities*weight)[:,None]
    result=np.zeros(5+len(residual));result[:5]=np.sum(compact[:,:5],axis=0)
    result[5:]=compact[:,5]
    return result


class MarginalVisibilityPort(SharedVisibilityPort):
    def marginal_score(self,state):
        self._evaluate(state)
        return float(normalized_mass(self._scores)[0])

    def marginal_score_gradient(self,state):
        self._evaluate(state);value,probabilities=normalized_mass(self._scores)
        batch=self.original.linearize_candidates(state,np.arange(self.candidate_count))
        np.testing.assert_allclose(batch['means'],self._means,rtol=1e-9,atol=1e-7)
        residual=self.observation[None,:]-batch['means']
        gradient=visibility_mixture_gradient(probabilities,self._components)
        gradient+=residual_mixture_gradient(probabilities[:-1],residual,self.likelihood.precision,batch['jacobians'])
        if not np.all(np.isfinite(gradient)):raise ValueError('nonfinite marginal gradient')
        return float(value),gradient
