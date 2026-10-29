"""Physical residual tests under a fixed Gaussian predictive covariance.

The null calibration never reads residual values. Mean, trend, curvature and
searched steps are GLS contrasts; overlapping held blocks are tested jointly.
This is conditional on covariance, not a calibrated satellite probability.
"""
import numpy as np
from scipy.linalg import cho_solve, solve_triangular
from scipy.stats import chi2


def prepare(covariance, times, owners, training_masks=(), *, draws=4096, seed=82137, alpha=.01):
    c=np.asarray(covariance,float);t=np.asarray(times,float);o=np.asarray(owners)
    n=len(t)
    if n<4 or c.shape!=(n,n) or o.shape!=(n,) or not np.isfinite(c).all() or not np.isfinite(t).all():
        raise ValueError('finite matching observations required')
    if not np.allclose(c,c.T,atol=1e-9,rtol=1e-12) or draws<1000 or not 0<alpha<.1:
        raise ValueError('symmetric covariance, sufficient draws and valid alpha required')
    order=np.lexsort((o,t));c=c[np.ix_(order,order)];t=t[order];o=o[order]
    root=np.linalg.cholesky(c);contexts=[('full',np.eye(n),t,o)];seen=set()
    for mask in training_masks:
        mask=np.asarray(mask,bool)
        if mask.shape!=(n,) or not mask.any() or mask.all():raise ValueError('nonempty train and held sets required')
        mask=mask[order];key=tuple(np.flatnonzero(~mask))
        if key in seen:continue
        seen.add(key);b=np.eye(n)[~mask]
        b[:,mask]=-cho_solve((np.linalg.cholesky(c[np.ix_(mask,mask)]),True),c[np.ix_(mask,~mask)]).T
        contexts.append((f'held{len(seen)}',b,t[~mask],o[~mask]))
    probes=[];names=[];lag_specs=[];energy=[]
    for name,b,tt,oo in contexts:
        groups=[('joint',np.ones(len(tt),bool))]+[(str(g),oo==g) for g in np.unique(oo)] if len(np.unique(oo))>1 else [('joint',np.ones(len(tt),bool))]
        for group,use in groups:
            if use.sum()<4 or np.ptp(tt[use])==0:continue
            a=b[use];cc=a@c@a.T;rr=np.linalg.cholesky(cc);x=(tt[use]-np.mean(tt[use]))/np.ptp(tt[use]);one=np.ones(len(x))
            designs=[('mean',one,np.empty((len(x),0))),('slope',x,one[:,None]),
                     ('curvature',x*x,np.column_stack((one,x)))]
            for cut in range(3,len(x)-2):
                if x[cut]==x[cut-1]:continue
                designs.append((f'step{cut}',(x>=x[cut]).astype(float),np.column_stack((one,x))))
            for label,h,null in designs:
                wh=solve_triangular(rr,h,lower=True)
                if null.shape[1]:
                    wn=solve_triangular(rr,null,lower=True);wh-=wn@np.linalg.lstsq(wn,wh,rcond=None)[0]
                length=np.linalg.norm(wh)
                if length<1e-10:continue
                weight=solve_triangular(rr.T,wh/length,lower=False)@a
                probes.append(weight);names.append(f'{name}/{group}/{label}')
            energy.append((f'{name}/{group}',solve_triangular(rr,a,lower=True),len(x)))
            # Physical-time adjacent products, with model expectation removed.
            # Only within-channel neighbors: no arbitrary interleaved lane ACF.
            if group!='joint' or len(np.unique(oo))==1:
                pairs=np.arange(len(x)-1);den=np.sqrt(np.diag(cc)[:-1]*np.diag(cc)[1:])
                q=np.zeros_like(cc);q[pairs,pairs+1]=.5/den;q+=q.T
                scale=np.sqrt(2*np.trace(q@cc@q@cc))
                lag_specs.append((f'{name}/{group}/lag',a,den,float(np.trace(q@cc)),float(scale)))
    w=np.asarray(probes);z=np.random.default_rng(seed).normal(size=(n,draws));sim=root@z
    maximum=np.max(abs(w@sim),axis=0)
    for name,a,den,mean,scale in lag_specs:
        v=a@sim;s=(np.sum(v[:-1]*v[1:]/den[:,None],axis=0)-mean)/scale
        maximum=np.maximum(maximum,abs(s))
    threshold=float(np.quantile(maximum,1-alpha/2,method='higher'))
    return dict(order=order,weights=w,names=names,lag=lag_specs,energy=energy,threshold=threshold,
                alpha=alpha,draws=draws,seed=seed,contexts=len(contexts),simulated_maximum=maximum)


def evaluate(prepared,residual):
    y=np.asarray(residual,float)
    if y.shape!=(len(prepared['order']),) or not np.isfinite(y).all():raise ValueError('finite matching residual required')
    y=y[prepared['order']];z=prepared['weights']@y
    values=dict(zip(prepared['names'],map(float,z)))
    for name,a,den,mean,scale in prepared['lag']:
        v=a@y;values[name]=float((np.sum(v[:-1]*v[1:]/den)-mean)/scale)
    worst=max(values,key=lambda k:abs(values[k]));maximum=abs(values[worst])
    energy={name:float(chi2.sf(np.sum((w@y)**2),n)) for name,w,n in prepared['energy']}
    floor=prepared['alpha']/(2*len(energy))
    return dict(compatible=bool(maximum<=prepared['threshold'] and min(energy.values())>=floor),
        maximum_statistic=maximum,worst_contrast=worst,threshold=prepared['threshold'],
        simulated_tail_probability=float((1+np.sum(prepared['simulated_maximum']>=maximum))/(prepared['draws']+1)),
        contrasts=values,energy_upper_tail=energy,energy_tail_floor=floor,
        alpha=prepared['alpha'],draws=prepared['draws'],seed=prepared['seed'],contexts=prepared['contexts'],
        caveat='Conditional Gaussian null; covariance estimated independently and held fixed. No identity probability.')
