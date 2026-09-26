"""Pure signed, age-conditioned historical equivalent-epoch density model."""
import numpy as np
from scipy.special import logsumexp,ndtr
from scipy.optimize import brentq

EDGES=(0.,6.,12.,24.,48.,72.,120.,float('inf'))


def kernel(rows):
    values=np.arcsinh([r['equivalent_tau_s'] for r in rows])
    groups=len({r['satellite_id'] for r in rows})
    robust=min(float(np.std(values,ddof=1)),float(np.subtract(*np.quantile(values,[.75,.25]))/1.349))
    bandwidth=max(.12,.9*robust*max(groups,2)**(-.2))
    return {'centers_asinh_s':values.tolist(),'bandwidth':bandwidth,'pairs':len(rows),'satellites':groups}


def fit_prior(rows):
    """Reject validation rows; preprocessing and bandwidth are training-only."""
    if any(r['validation_group'] for r in rows):raise ValueError('validation data must not train prior')
    if len(rows)<50:raise ValueError('insufficient history')
    pool=kernel(rows);bins=[]
    for lo,hi in zip(EDGES[:-1],EDGES[1:]):
        local=[r for r in rows if lo<=r['age_hours']<hi]
        groups=len({r['satellite_id'] for r in local})
        supported=len(local)>=50 and groups>=20
        bins.append({'lower_h':lo,'upper_h':None if np.isinf(hi) else hi,
                     'pairs':len(local),'satellites':groups,'supported':supported,
                     'local_weight':groups/(groups+20.) if supported else 0.,
                     'kernel':kernel(local) if supported else None})
    return {'model':'signed-asinh-gaussian-kernel-mixture-v1','asinh_scale_s':1.,
            'rules':'bandwidth floor 0.12; robust Silverman with satellite count; 20-group pooled shrinkage; unsupported bins use pooled history; all frozen before validation',
            'pool':pool,'bins':bins}


def age_bin(model,age):
    if not np.isfinite(age) or age<0:raise ValueError('nonnegative finite element age required')
    return next(b for b in model['bins'] if age>=b['lower_h'] and (b['upper_h'] is None or age<b['upper_h']))


def _kernel_value(k,x,cdf):
    x=np.atleast_1d(np.asarray(x,float));centers=np.asarray(k['centers_asinh_s']);h=k['bandwidth']
    result=[]
    for start in range(0,len(x),128):
        z=(np.arcsinh(x[start:start+128,None])-centers[None,:])/h
        if cdf:out=ndtr(z).mean(axis=1)
        else:out=logsumexp(-.5*z*z,axis=1)-np.log(len(centers)*h*np.sqrt(2*np.pi))-.5*np.log1p(x[start:start+128]**2)
        result.extend(out)
    return np.asarray(result)


def logpdf(model,age,x):
    b=age_bin(model,age);a=b['local_weight'];pooled=_kernel_value(model['pool'],x,False)
    if not a:return pooled
    local=_kernel_value(b['kernel'],x,False)
    return np.logaddexp(np.log(a)+local,np.log1p(-a)+pooled)


def cdf(model,age,x):
    b=age_bin(model,age);a=b['local_weight'];pooled=_kernel_value(model['pool'],x,True)
    return a*_kernel_value(b['kernel'],x,True)+(1-a)*pooled if a else pooled


def quantile(model,age,q):
    if not 0<q<1:raise ValueError('interior quantile required')
    k=model['pool'];lo=min(k['centers_asinh_s'])-12*max(k['bandwidth'],1.)
    hi=max(k['centers_asinh_s'])+12*max(k['bandwidth'],1.)
    return float(np.sinh(brentq(lambda y:float(cdf(model,age,[np.sinh(y)])[0])-q,lo,hi)))


def discrete_weights(model,age,grid):
    """Conditional numerical support, with omitted continuous mass reported."""
    grid=np.asarray(grid,float)
    if len(grid)<2 or not np.allclose(np.diff(grid),grid[1]-grid[0]):raise ValueError('uniform grid required')
    lp=logpdf(model,age,grid)
    mass=float(cdf(model,age,[grid[-1]])[0]-cdf(model,age,[grid[0]])[0])
    return lp-logsumexp(lp),1-mass
