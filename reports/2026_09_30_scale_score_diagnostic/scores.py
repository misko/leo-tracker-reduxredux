import importlib.util
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

REPORTS=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('scale_model',REPORTS/'2026_09_30_ds10_scale_weighting/scaled_model.py')
scale_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(scale_model)
trend=scale_model.trend_module


def predictive(y,t,mask,prediction,visible,scale):
    y,t,mask=np.asarray(y),np.asarray(t),np.asarray(mask,bool)
    residual=y[None,:]-prediction
    count=int(visible.sum())
    if count==0:raise ValueError('No visible candidate')
    def normal(residual,values,times):
        signal,_=trend.contrast_density(residual,scale)
        signal=logsumexp(np.where(visible,signal,-np.inf))-np.log(count)
        background=trend.trend_density(values,times,scale,2000.)
        return float(np.logaddexp(np.log(.8)+signal,np.log(.2)+background))
    training=normal(residual[:,mask],y[mask],t[mask])
    joint=normal(residual,y,t)-training
    k,h=prediction.shape[0],int((~mask).sum())
    combined=np.concatenate([np.broadcast_to(residual[:,None,mask],(k,h,int(mask.sum()))),residual[:,~mask,None]],axis=2)
    signal,_=trend.contrast_density(combined.reshape(k*h,-1),scale)
    signal=logsumexp(np.where(visible[:,None],signal.reshape(k,h),-np.inf),axis=0)-np.log(count)
    background=np.array([trend.trend_density(np.r_[y[mask],y[j]],np.r_[t[mask],t[j]],scale,2000.) for j in np.flatnonzero(~mask)])
    individual=np.logaddexp(np.log(.8)+signal,np.log(.2)+background)-training
    return dict(training=training,joint=joint,marginal_sum=float(individual.sum()),individual=individual.tolist())
