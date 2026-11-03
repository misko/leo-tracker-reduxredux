"""Empirical probability of a raw opposite-RX timing match given an anchor."""
import numpy as np
from scipy.special import expit


def design(los,rf,anchor,arm):
    los=np.asarray(los,float);rf=np.asarray(rf,int);other=1-np.asarray(anchor,int)
    if arm not in ('receiver','elevation','signed','swapped'):raise ValueError(arm)
    x=np.zeros((len(los),8+(arm!='receiver')))
    x[np.arange(len(los)),2*rf+other]=1.
    if arm=='elevation':x[:,-1]=los[:,2]
    elif arm!='receiver':
        sign=(2*other-1)*(1 if arm=='signed' else -1)
        x[:,-1]=np.cos(np.radians(10))*los[:,2]+np.sin(np.radians(10))*sign*los[:,0]
    return x


def likelihood(parameters,x,hit,weights):
    eta=x@parameters;y=np.asarray(hit,float)
    scores=y*eta-np.logaddexp(0.,eta)
    return scores,x.T@(np.asarray(weights)*(y-expit(eta)))


def source_weights(source,mask):
    source=np.asarray(source);mask=np.asarray(mask,bool);weights=np.zeros(len(source))
    for s in np.unique(source[mask]):
        selected=mask & (source==s);weights[selected]=1/selected.sum()
    return weights
