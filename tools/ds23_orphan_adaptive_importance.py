"""EM-guided importance integration of the unchanged orphan prediction model.

EM supplies numerical proposals only. Every proposal is corrected by its full
mixture density; no EM coefficient replaces the curved calibration estimate.
"""

import numpy as np
from scipy.special import logsumexp,ndtri
from scipy.stats import qmc

from ds23_orphan_predictive_mixture import PERIOD,wrapped_pdf
from ds23_height_problem import geometry_features


def gaussian_importance(proposals,power,seed):
    """Draw from a deterministic Gaussian mixture and evaluate exact p/q."""
    n=2**power;dimension=len(proposals[0]['mean'])
    fractions=np.array([p['weight'] for p in proposals]);fractions/=fractions.sum()
    counts=np.floor(n*fractions).astype(int);counts[0]+=n-int(counts.sum());weights=counts/n
    draws=[]
    for k,(p,count) in enumerate(zip(proposals,counts,strict=True)):
        if not count:raise ValueError('every importance component needs samples')
        exponent=int(np.ceil(np.log2(count)))
        uniform=qmc.Sobol(dimension,scramble=True,seed=seed+101*k).random_base2(exponent)[:count]
        normal=ndtri(np.clip(uniform,1e-12,1-1e-12))
        draws.append(p['mean']+normal@p['root'].T)
    z=np.concatenate(draws);density=[]
    for p,w in zip(proposals,weights,strict=True):
        centered=np.linalg.solve(p['root'],(z-p['mean']).T).T
        density.append(np.log(w)-.5*np.sum(centered**2,axis=1)-np.log(np.diag(p['root'])).sum()-.5*dimension*np.log(2*np.pi))
    prior=-.5*np.sum(z*z,axis=1)-.5*dimension*np.log(2*np.pi)
    return z,prior-logsumexp(density,axis=0)


class AdaptiveOrphans:
    def __init__(self,prediction,x):
        self.prediction=prediction;self.x=np.asarray(x);p=prediction.p
        c=p.curved_calculate(x) if hasattr(p,'curved_calculate') else p.calculate(x)
        u=c['features'][p.keep];g=p.noise_groups[p.keep]
        w=prediction.powers[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None]);cov=np.linalg.inv(gram)
        root=np.linalg.cholesky((cov+cov.T)/2);geometry=geometry_features(prediction.view,x,0.)
        self.base=prediction.view.q*geometry['intercept']+geometry['features']@c['coefficient']
        bias=np.zeros((len(self.base),prediction.bias_count))
        bias[np.arange(len(bias)),prediction.bias_index]=prediction.bias_sigma_hz
        self.design=np.column_stack((geometry['features']@root,bias));self.dimension=self.design.shape[1]
        self.families=len(prediction.active);self.n=len(prediction.observations)
        self.sigma=np.tile(prediction.noise,self.families)
        self.values=np.tile([o['measured_cfo_hz'] for o in prediction.observations],self.families)
        self.visible=geometry['elevation'].reshape(self.families,self.n)>=0
        self.visible_count=self.visible.sum(axis=0)

    def components(self,z):
        mean=self.base+self.design@z
        residual=(self.values-mean+PERIOD/2)%PERIOD-PERIOD/2
        density=wrapped_pdf(residual,self.sigma).reshape(self.families,self.n)
        normalized=density*self.visible/np.maximum(self.visible_count,1)
        return residual,normalized

    def em(self,initial_fraction,iterations=48):
        z=np.zeros(self.dimension);fraction=initial_fraction;history=[];normal=np.eye(self.dimension)
        for _ in range(iterations):
            residual,component=self.components(z);signal=component.sum(axis=0)*PERIOD
            signal[self.visible_count==0]=1.
            denominator=1-fraction+fraction*signal
            responsibility=fraction*PERIOD*component/denominator
            objective=float(.5*(z@z)-np.log(denominator).sum());history.append(objective)
            if len(history)>1 and history[-1]>history[-2]+1e-7:raise ValueError('EM proposal objective increased')
            precision=responsibility.ravel()/self.sigma**2
            normal=np.eye(self.dimension)+self.design.T@(self.design*precision[:,None])
            rhs=self.design.T@(precision*(residual+self.design@z))
            new=np.linalg.solve(normal,rhs)
            new_fraction=float(np.clip(responsibility.sum()/max(1,int(sum(self.visible_count>0))),1e-6,1-1e-6))
            change=np.linalg.norm(new-z)+abs(new_fraction-fraction)
            z,fraction=new,new_fraction
            if change<1e-6:break
        eigen,vectors=np.linalg.eigh((normal+normal.T)/2)
        # Inflate informative directions while preserving unit prior variance in
        # unused coordinates; doubling every unused variance ruins importance ESS.
        covariance=(vectors*np.minimum(1.,2/eigen))@vectors.T
        return dict(mean=z,root=np.linalg.cholesky((covariance+covariance.T)/2),weight=.3,
                    history=history,signal_fraction=fraction,coefficient_norm=float(np.linalg.norm(z)))

    def proposals(self):
        return [dict(mean=np.zeros(self.dimension),root=np.eye(self.dimension),weight=.1)]+[
            self.em(f) for f in [.05,.3,.7]]

    def ratios(self,z,shift_hz=0.):
        mean=self.base[:,None]+self.design@z.T
        density=wrapped_pdf(self.values[:,None]+shift_hz-mean,self.sigma[:,None]).reshape(self.families,self.n,-1)
        ratio=(density*self.visible[:,:,None]).sum(axis=0)*PERIOD/np.maximum(self.visible_count,1)[:,None]
        ratio[self.visible_count==0]=1.
        return ratio.T

    def integrate(self,proposals,power=10,seed=2026102204,nodes=64,details=False,shift_hz=0.):
        z,log_weight=gaussian_importance(proposals,power,seed);ratios=self.ratios(z,shift_hz)
        x,w=np.polynomial.legendre.leggauss(nodes);fraction=(x+1)/2;w=w/2
        log_likelihood=np.array([np.log1p(f*(ratios-1)).sum(axis=1) for f in fraction])
        log_joint=log_likelihood+np.log(w)[:,None]+log_weight[None,:]-np.log(len(z))
        normalization=logsumexp(log_joint);probability=np.exp(log_joint-normalization);draw_weight=probability.sum(axis=0)
        result=dict(relative_negative_twice_log_likelihood=float(-2*normalization),
            effective_nuisance_draws=float(1/np.sum(draw_weight**2)),
            posterior_signal_fraction=float(fraction@probability.sum(axis=1)),
            importance_prior_mass_estimate=float(np.exp(logsumexp(log_weight)-np.log(len(z)))))
        if details:
            result['point_signal_probabilities']=sum((probability[k,:,None]*(f*ratios)/(1-f+f*ratios)).sum(axis=0)
                                                     for k,f in enumerate(fraction))
        return result
