"""Continuous Gaussian residual cost in the primary coherent-coverage score.

S = assigned_windows - 10 * satellites - timing_cost
    - frequency_weight * 0.5 * sum((residual / 200 Hz)**2).
This is a regularized coverage proxy, NOT the downstream finite-set NLL.
Keep the archived 600 Hz gate/coherence and one-out/greedy-repair neighborhood.
No truth locations enter selection. Zero frequency weight is the prior experiment.
"""
import numpy as np
from timing_selection_score import TimingPriorMixin,timing_cost


class FrequencyPriorMixin(TimingPriorMixin):
    def __init__(self,*args,frequency_weight=1.,sigma_hz=200.,**kwargs):
        if not np.isfinite(frequency_weight) or frequency_weight<0:raise ValueError('Invalid frequency weight')
        if not np.isfinite(sigma_hz) or sigma_hz<=0:raise ValueError('Invalid residual sigma')
        self.frequency_weight=float(frequency_weight);self.sigma_hz=float(sigma_hz)
        super().__init__(*args,**kwargs)

    def evaluate(self,i,used):
        result=super().evaluate(i,used)
        result['frequency_cost']=float(.5*np.sum((np.asarray(result['errors'])/self.sigma_hz)**2))
        return result

    def objective(self,chosen):
        return super().objective(chosen)-self.frequency_weight*sum(v['frequency_cost'] for v in chosen.values())

    def fill(self,chosen,used,cache,forbidden=frozenset()):
        if self.frequency_weight==0:return super().fill(chosen,used,cache,forbidden)
        additions=[]
        while True:
            n,total,square=self.statistics(chosen)
            prior=float(timing_cost(n,total,square))
            changes=timing_cost(n+1,total+self.offsets,square+self.offsets**2)-prior if self.timing_weight else np.zeros(len(cache))
            gains=np.array([v['count']-self.penalty-self.frequency_weight*v['frequency_cost'] for v in cache])-self.timing_weight*changes
            candidates=[i for i,m in enumerate(self.modes)
                if m['catalog_number'] not in chosen and m['catalog_number'] not in forbidden
                and cache[i]['count']>=self.minimum and gains[i]>1e-10]
            if not candidates:break
            i=max(candidates,key=lambda j:(gains[j],cache[j]['score'],-self.modes[j]['catalog_number'],-j))
            number=self.modes[i]['catalog_number'];value=dict(cache[i],mode_index=i,catalog_number=number)
            before=self.objective(chosen)
            assert not used[value['rows']].any()
            chosen[number]=value;used[value['rows']]=True
            after=self.objective(chosen)
            assert after>before and abs(after-before-gains[i])<1e-7
            additions.append(dict(catalog_number=number,mode_index=i,added=value['count'],
                marginal_score=float(gains[i]),objective=after,timing_prior_increment=float(changes[i]),
                frequency_cost=value['frequency_cost']))
            self.refresh(self.affected(value['rows']),chosen,used,cache,forbidden)
        return additions

    def export(self,chosen):
        result=super().export(chosen)
        result.update(frequency_weight=self.frequency_weight,frequency_sigma_hz=self.sigma_hz,
            frequency_cost=float(sum(v['frequency_cost'] for v in chosen.values())))
        return result
