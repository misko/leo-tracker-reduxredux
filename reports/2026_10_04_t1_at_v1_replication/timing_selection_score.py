"""Timing-regularized coverage selection over an unchanged coherent mode pool.

The objective is coverage - 10 * satellites - weight * timing_prior.
It is a regularized coverage score, NOT the downstream frequency likelihood.
The timing prior uses the same zero-sum gauge as localization: common shift is
the unweighted mean of selected total shifts; relative shifts sum to zero.
"""
import numpy as np


def timing_cost(count,total,total_square):
    """Gaussian sigma: 1 s relative, 10 s common; common hard bound +/-10 s."""
    if count==0:return 0.
    mean=np.asarray(total)/count
    variance_sum=np.maximum(0.,np.asarray(total_square)-np.asarray(total)**2/count)
    cost=.5*variance_sum+.5*(mean/10.)**2
    return np.where(abs(mean)<=10.+1e-10,cost,np.inf)


class TimingPriorMixin:
    """Adds a primary timing cost to the historical Search's narrow mode port."""
    def __init__(self,*args,timing_weight=1.,**kwargs):
        if not np.isfinite(timing_weight) or timing_weight<0:raise ValueError('Nonnegative finite timing weight required')
        self.timing_weight=float(timing_weight)
        super().__init__(*args,**kwargs)
        self.offsets=np.array([m['offset_s'] for m in self.modes])
        if np.any(~np.isfinite(self.offsets)) or np.any(abs(self.offsets)>20.+1e-7):raise ValueError('Timing pool outside +/-20 s')
        if len(np.unique(self.groups))!=len(self.groups):raise ValueError('Requires one top candidate per window')

    def statistics(self,chosen):
        offsets=np.array([self.offsets[v['mode_index']] for v in chosen.values()])
        return len(offsets),float(sum(offsets)),float(offsets@offsets)

    def objective(self,chosen):
        coverage_score=float(sum(v['count'] for v in chosen.values())-self.penalty*len(chosen))
        if self.timing_weight==0:return coverage_score
        return coverage_score-self.timing_weight*float(timing_cost(*self.statistics(chosen)))

    def fill(self,chosen,used,cache,forbidden=frozenset()):
        if self.timing_weight==0:
            return super().fill(chosen,used,cache,forbidden)
        additions=[]
        while True:
            n,total,square=self.statistics(chosen)
            prior=float(timing_cost(n,total,square))
            changes=timing_cost(n+1,total+self.offsets,square+self.offsets**2)-prior
            gains=np.array([v['count']-self.penalty for v in cache])-self.timing_weight*changes
            candidates=[i for i,m in enumerate(self.modes)
                if m['catalog_number'] not in chosen and m['catalog_number'] not in forbidden
                and cache[i]['count']>=self.minimum and gains[i]>1e-10]
            if not candidates:break
            i=max(candidates,key=lambda j:(gains[j],cache[j]['score'],-self.modes[j]['catalog_number'],-j))
            number=self.modes[i]['catalog_number'];v=dict(cache[i],mode_index=i,catalog_number=number)
            before=self.objective(chosen)
            assert not used[v['rows']].any()
            chosen[number]=v;used[v['rows']]=True
            after=self.objective(chosen)
            assert after>before and abs(after-before-gains[i])<1e-7
            additions.append(dict(catalog_number=number,mode_index=i,added=v['count'],
                marginal_score=float(gains[i]),objective=after,timing_prior_increment=float(changes[i])))
            self.refresh(self.affected(v['rows']),chosen,used,cache,forbidden)
        return additions

    def export(self,chosen):
        r=super().export(chosen);n,total,square=self.statistics(chosen)
        r.update(timing_weight=self.timing_weight,timing_prior_nll=float(timing_cost(n,total,square)),
                 common_timing_s=total/n if n else 0.,coverage_score=r['assigned']-self.penalty*r['satellites'])
        return r
