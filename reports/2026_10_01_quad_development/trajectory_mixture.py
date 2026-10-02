"""Fixed-noise quadratic Gaussian mixture with normalized predictive scoring."""
import numpy as np


def log_density(y,means,weights,sigma):
    z=-.5*((np.asarray(y)[:,None]-means)/sigma)**2-np.log(sigma*np.sqrt(2*np.pi))+np.log(weights)[None,:]
    maximum=z.max(axis=1)
    return maximum+np.log(np.exp(z-maximum[:,None]).sum(axis=1))


def design(t,center,scale):
    u=(np.asarray(t)-center)/scale
    return np.column_stack((np.ones(len(u)),u,u*u))


def fit(t,y,sigma=100.):
    t=np.asarray(t,float);y=np.asarray(y,float)
    if len(t)<3 or y.shape!=t.shape or np.any(np.diff(t)<=0) or not np.isfinite(y).all() or sigma<=0:raise ValueError('invalid training data')
    center=float(t.mean());scale=max(float(np.ptp(t)),1.);offset=float(y.mean());v=y-offset;X=design(t,center,scale)
    single=np.linalg.lstsq(X,v,rcond=None)[0][:,None]
    ll=float(log_density(v,X@single,np.ones(1),sigma).sum())
    base=dict(center=center,scale=scale,offset=offset,sigma=sigma,single_beta=single.tolist(),single_loglik=ll)
    if len(t)<12 or np.ptp(t)<3:return dict(base,beta=single.tolist(),weights=[1.],mixture_loglik=ll,status='insufficient_support',starts=[])
    residual=v-X@single[:,0];order=np.argsort(residual,kind='stable');idx=np.arange(len(t));masks=[]
    for fraction in (.25,.5,.75):
        mask=np.zeros(len(t),bool);mask[order[:max(3,int(len(t)*fraction))]]=True;masks.append(mask)
    masks.extend((idx<len(t)//2,idx%2==0,(idx//3)%2==0))
    candidates=[];receipts=[]
    for seed,mask in enumerate(masks):
        beta=np.column_stack([np.linalg.lstsq(X[m],v[m],rcond=None)[0] for m in (mask,~mask)])
        weights=np.array([mask.mean(),1-mask.mean()]);last=-np.inf;converged=False
        for iteration in range(100):
            means=X@beta;z=-.5*((v[:,None]-means)/sigma)**2+np.log(weights)[None,:]
            z-=z.max(axis=1)[:,None];r=np.exp(z);r/=r.sum(axis=1)[:,None]
            weights=r.mean(axis=0);weights=np.maximum(weights,1e-12);weights/=weights.sum()
            for k in range(2):
                w=np.sqrt(r[:,k]);beta[:,k]=np.linalg.lstsq(X*w[:,None],v*w,rcond=None)[0]
            value=float(log_density(v,X@beta,weights,sigma).sum())
            if value<last-1e-6:raise AssertionError('EM likelihood decreased')
            if abs(value-last)<1e-7*len(t):converged=True;break
            last=value
        labels=np.argmax(-.5*((v[:,None]-X@beta)/sigma)**2+np.log(weights)[None,:],axis=1)
        supported=all(np.sum(labels==k)>=6 and np.ptp(t[labels==k])>=3 for k in range(2))
        receipts.append(dict(seed=seed,converged=converged,supported=bool(supported),iterations=iteration+1,loglik=value))
        if converged and supported:candidates.append((value,seed,beta.copy(),weights.copy()))
    if not candidates:return dict(base,beta=single.tolist(),weights=[1.],mixture_loglik=ll,status='no_supported_converged_start',starts=receipts)
    value,seed,beta,weights=max(candidates,key=lambda r:(r[0],-r[1]))
    return dict(base,beta=beta.tolist(),weights=weights.tolist(),mixture_loglik=value,status='mixture',chosen_seed=seed,starts=receipts)


def predict(model,t,y,*,single=False):
    X=design(t,model['center'],model['scale']);beta=np.array(model['single_beta'] if single else model['beta'])
    weights=np.ones(1) if single else np.array(model['weights'])
    return log_density(np.asarray(y)-model['offset'],X@beta,weights,model['sigma'])
