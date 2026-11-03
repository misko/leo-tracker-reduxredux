"""IID satellite profiles plus a dimensionally matched linear-trend null."""
import math
from pathlib import Path
import sys

import numpy as np
from scipy.special import logsumexp

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import ds7_fast_baseline_adapter as fast

VARIANTS={'q000':0.,'q005':.05,'q020':.20,'q050':.50}


def trend_score(y,t,mask,noise=100.,slope_sd=2000.):
    """Profile CFO after analytically marginalizing a Gaussian slope.

    Training centering makes the constant and slope columns orthogonal; the
    CFO prior remains centered at zero in the centered time convention.
    """
    values=np.asarray(y)[mask]
    times=np.asarray(t)[mask]
    centered=times-times.mean()
    n=len(values)
    variance=noise**2
    length=float(centered@centered)
    denominator=variance+slope_sd**2*length
    offset=float(values.sum()/(n+variance/1e12))
    residual=values-offset
    quadratic=(residual@residual-slope_sd**2*(centered@residual)**2/denominator)/variance
    logdet=n*math.log(variance)+math.log1p(slope_sd**2*length/variance)
    return float(-.5*(n*math.log(2*math.pi)+logdet+quadratic)-.5*offset**2/1e12)


class Model:
    def __init__(self,documents,config,q):
        self.models=[fast.Stationary(d,config) for d in documents]
        self.documents=documents
        self.q=q
        self.null_scores=[]
        for document in documents:
            local=[]
            for track in document['tracks']:
                local.append(trend_score(track['y'],track['times_s'],track['mask']))
            self.null_scores.append(local)
        self.metadata=dict(variant=next(k for k,v in VARIANTS.items() if v==q),
            null_prior=q,signal='original full-catalogue divisor; IID Student-t4 scale100Hz',
            null='Gaussian100Hz plus marginalized linear slope SD2000Hz/s; profiled CFO',
            normalized_posterior=False,null_time_center='training mean only')

    def evaluate(self,x,gradient=True):
        x=np.asarray(x,dtype=float)
        derivative=np.zeros_like(x)
        total=0.
        weights=[]
        for di,(document,engine) in enumerate(zip(self.documents,self.models)):
            local=x[[0,1,di+2]]
            for ti,track in enumerate(document['tracks']):
                prediction,visible=engine.prediction(track,local)
                score,_,audits,offsets=fast.profile(track['y'][None,:]-prediction,track['mask'])
                if not all(a['converged'] for a in audits):
                    raise RuntimeError('offset profile did not converge')
                if not np.any(visible):
                    raise ValueError('empty visible candidate bank')
                candidate=np.where(visible,score,-np.inf)
                normalization=logsumexp(candidate)
                signal=normalization-math.log(track['catalogue_size'])
                if self.q:
                    combined=np.logaddexp(math.log1p(-self.q)+signal,
                                         math.log(self.q)+self.null_scores[di][ti])
                    signal_weight=math.exp(math.log1p(-self.q)+signal-combined)
                else:
                    combined,signal_weight=signal,1.
                total+=float(combined)
                weights.append(signal_weight)
                if not gradient:
                    continue
                residual=(track['y'][None,:]-prediction)[:,track['mask']]-offsets[:,None]
                influence=5*residual/(40000+residual**2)
                responsibility=np.exp(candidate-normalization)
                g=np.zeros(3)
                for axis,step in enumerate((1e-4,1e-4,1e-5)):
                    plus,minus=local.copy(),local.copy()
                    plus[axis]+=step
                    minus[axis]-=step
                    if axis==2:
                        plus[axis],minus[axis]=min(5.,plus[axis]),max(-5.,minus[axis])
                    delta=(engine.prediction(track,plus)[0]-engine.prediction(track,minus)[0])/(plus[axis]-minus[axis])
                    g[axis]=signal_weight*(responsibility@np.sum(influence*delta[:,track['mask']],axis=1))
                derivative[:2]+=g[:2]
                derivative[di+2]+=g[2]
        return dict(score=total,gradient=derivative,signal_weights=weights)


def build_model(documents,config,variant,index=None):
    return Model(documents,config,VARIANTS[variant])
