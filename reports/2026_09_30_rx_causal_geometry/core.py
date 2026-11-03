import numpy as np
from scipy.special import logsumexp


def design(lane, control=None):
    geometry=lane['geometry'].copy()
    if control=='swap': geometry[...,2]*=-1
    elif control=='reverse':
        for role in ('reception','held_frequency'):
            idx=np.flatnonzero(lane['roles']==role)
            geometry[idx,:,2]=geometry[idx[::-1],:,2]
    elif control=='permute': geometry[...,2]=np.roll(geometry[...,2],1,axis=1)
    elif control is not None: raise ValueError('unknown control')
    mass=np.exp(lane['prior'][:-1])[None,:]*lane['visible']
    features=np.sum(geometry*mass[...,None],axis=1)
    common=np.array([0.,1.,1.,2.]); differential=np.array([0.,-1.,1.,0.])
    return np.stack([np.broadcast_to(common,(len(features),4)),
                     np.broadcast_to(differential,(len(features),4)),
                     features[:,0,None]*common,features[:,1,None]*common,
                     features[:,2,None]*differential],axis=-1)


def log_probabilities(beta, x, offset):
    logits=offset+np.einsum('wcd,d->wc',x[...,:len(beta)],beta)
    return logits-logsumexp(logits,axis=1)[:,None]


def objective(beta,x,offset,y):
    lp=log_probabilities(beta,x,offset);sd=np.array([2.,2.,.5,.5,.5])[:len(beta)]
    value=-lp[np.arange(len(y)),y].sum()+.5*np.sum((beta/sd)**2)
    residual=np.exp(lp);residual[np.arange(len(y)),y]-=1
    gradient=np.einsum('wc,wcd->d',residual,x[...,:len(beta)])+beta/sd**2
    return float(value),gradient
