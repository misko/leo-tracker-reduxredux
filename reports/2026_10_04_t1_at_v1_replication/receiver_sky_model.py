"""Pure conditional sky estimators: spherical kernel and regularized softmax.

Inputs are matched satellite/channel/probe outcomes conditional on at least
one receiver having unique frequency support. These are NOT absolute beam gain
or probability of detection from an arbitrary transmitting satellite.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


def directions(azimuth_deg, elevation_deg):
    az, el = np.deg2rad(azimuth_deg), np.deg2rad(elevation_deg)
    return np.stack((np.cos(el)*np.sin(az), np.cos(el)*np.cos(az), np.sin(el)), axis=-1)


def disk_grid(size=101):
    axis=np.linspace(-1,1,size); x,y=np.meshgrid(axis,axis)
    r=np.hypot(x,y); inside=r<=1
    az=np.rad2deg(np.arctan2(x[inside],y[inside])); el=90*(1-r[inside])
    return x,y,inside,directions(az,el)


def sky_xy(unit):
    u=np.asarray(unit); angle=np.arccos(np.clip(u[:,2],-1,1))/(np.pi/2)
    norm=np.linalg.norm(u[:,:2],axis=1)
    return u[:,:2]*np.divide(angle,norm,out=np.zeros_like(angle),where=norm>0)[:,None]


def prepare(events):
    scans=sorted(set(r['scan'] for r in events))
    ids=np.array([scans.index(r['scan']) for r in events])
    u=np.array([[r['east'],r['north'],r['up']] for r in events])
    y=np.array([r['outcome'] for r in events],int)
    ch=np.array([r['channel'] for r in events],int)
    blocks=[(r['scan'],r['satellite'],int(r['time_s']//5)) for r in events]
    _,inverse,count=np.unique(np.array(blocks,dtype=str),axis=0,return_inverse=True,return_counts=True)
    w=1./count[inverse]
    per_scan=np.bincount(ids,weights=w,minlength=len(scans))
    w*=np.mean(per_scan)/per_scan[ids]
    return dict(unit=u,outcome=y,channel=ch,scan=ids,scan_names=scans,block=inverse,weight=w)


def compress(data):
    # Preserve different outcomes and channel strata within each encounter block.
    keys=np.column_stack((data['block'],data['outcome'],data['channel']))
    _,inverse=np.unique(keys,axis=0,return_inverse=True)
    n=inverse.max()+1; weight=np.bincount(inverse,weights=data['weight'],minlength=n)
    unit=np.column_stack([np.bincount(inverse,weights=data['weight']*data['unit'][:,j],minlength=n)/weight for j in range(3)])
    unit/=np.linalg.norm(unit,axis=1)[:,None]
    first=np.full(n,-1,int)
    for i,g in enumerate(inverse):
        if first[g]<0:first[g]=i
    return {**data,'unit':unit,'weight':weight,
            **{k:data[k][first] for k in ('outcome','channel','scan','block')}}


def kernel(data, grid, bandwidth_deg=10., bootstrap=250, seed=20261005):
    """Gaussian angular smoothing, 3-sigma cutoff; scan-cluster resampling.

    Support mask requires >=5 scans and >=20 distinct scan/satellite/5s blocks
    within 15 degrees. All rows contribute; mask affects display, not training.
    Bootstrap bands quantify scan-sampling stability, not identity uncertainty.
    """
    d=compress(data); nscan=len(data['scan_names']); ng=len(grid)
    contribution=np.zeros((nscan,ng,3)); scans=np.zeros(ng,int); blocks=np.zeros(ng,int)
    for lo in range(0,ng,128):
        hi=min(lo+128,ng)
        angle=np.rad2deg(np.arccos(np.clip(grid[lo:hi]@d['unit'].T,-1,1)))
        k=np.exp(-.5*(angle/bandwidth_deg)**2)*(angle<=3*bandwidth_deg)
        for s in range(nscan):
            sm=d['scan']==s
            scans[lo:hi]+=np.any(angle[:,sm]<=15.,axis=1)
            for c in range(3):
                m=sm&(d['outcome']==c)
                contribution[s,lo:hi,c]=k[:,m]@d['weight'][m]
        for j in range(hi-lo):blocks[lo+j]=len(np.unique(d['block'][angle[j]<=15.]))
    totals=contribution.sum(axis=0); denominator=totals.sum(axis=1)
    probability=np.divide(totals,denominator[:,None],out=np.full_like(totals,np.nan),where=denominator[:,None]>0)
    supported=(scans>=5)&(blocks>=20)
    result=dict(probability=probability,scans=scans,blocks=blocks,supported=supported,
                bandwidth_deg=bandwidth_deg,weight=denominator)
    if bootstrap:
        rng=np.random.default_rng(seed)
        multiplicity=rng.multinomial(nscan,np.full(nscan,1/nscan),size=bootstrap)
        # Fractional pseudocount only avoids zero-denominator bootstrap draws;
        # unsupported grids are masked and are never presented as calibrated.
        draws=np.einsum('bs,sgc->bgc',multiplicity,contribution)
        draws=np.divide(draws,draws.sum(axis=2,keepdims=True),out=np.full_like(draws,np.nan),where=draws.sum(axis=2,keepdims=True)>0)
        valid=np.isfinite(draws[:,:,0]).sum(axis=0)
        intervals=np.full((2,ng,3),np.nan)
        ok=valid>=.95*bootstrap
        intervals[:,ok]=np.nanquantile(draws[:,ok],[.025,.975],axis=0)
        result.update(intervals=intervals,bootstrap_valid=valid)
    return result


def design(unit, channel, scan, nscan):
    e,n,u=np.asarray(unit).T
    spatial=np.column_stack((np.ones(len(e)),e,n,u,e*e,n*n,e*n,e*u,n*u))
    channel_effect=np.eye(4)[np.asarray(channel)-1][:,:3]
    scan_effect=np.eye(nscan)[np.asarray(scan)][:,:-1]
    return np.column_stack((spatial,channel_effect,scan_effect))


def softmax_loss(beta, x, y, weight, ridge):
    b=beta.reshape(x.shape[1],2)
    logits=np.column_stack((x@b,np.zeros(len(x))))
    normalizer=logsumexp(logits,axis=1)
    p=np.exp(logits-normalizer[:,None])
    loss=weight@(normalizer-logits[np.arange(len(y)),y])+.5*np.sum(ridge[:,None]*b*b)
    error=p.copy(); error[np.arange(len(y)),y]-=1
    grad=x.T@(weight[:,None]*error[:,:2])+ridge[:,None]*b
    return float(loss),grad.ravel()


def fit_softmax(data):
    x=design(data['unit'],data['channel'],data['scan'],len(data['scan_names']))
    ridge=np.r_[.01,np.full(8,2.),np.full(3,5.),np.full(x.shape[1]-12,10.)]
    opt=minimize(softmax_loss,np.zeros(x.shape[1]*2),args=(x,data['outcome'],data['weight'],ridge),
                 jac=True,method='L-BFGS-B',options=dict(maxiter=1200,ftol=1e-12,gtol=1e-6))
    coef=opt.x.reshape(-1,2)
    def predict(x):
        scores=np.column_stack((x@coef,np.zeros(len(x))))
        return np.exp(scores-logsumexp(scores,axis=1)[:,None])
    p=predict(x); y=data['outcome']; w=data['weight']
    baseline=np.bincount(y,weights=w,minlength=3)/sum(w)
    return dict(coefficients=coef,converged=bool(opt.success),status=str(opt.message),
        gradient_inf=float(max(abs(opt.jac))),ridge=ridge,
        in_sample_log_loss=float(-np.sum(w*np.log(p[np.arange(len(y)),y]))/sum(w)),
        null_log_loss=float(-np.sum(w*np.log(baseline[y]))/sum(w)),
        in_sample_brier=float(np.sum(w*np.sum((p-np.eye(3)[y])**2,axis=1))/sum(w)),
        null_brier=float(np.sum(w*np.sum((baseline-np.eye(3)[y])**2,axis=1))/sum(w)))


def softmax_map(fit, grid, nscan):
    # Equal mixture over all observed scans and four channels; do not paint a
    # particular channel/scan's detection advantage into the directional map.
    total=np.zeros((len(grid),3))
    for scan in range(nscan):
        for channel in range(1,5):
            x=design(grid,np.full(len(grid),channel),np.full(len(grid),scan),nscan)
            scores=np.column_stack((x@fit['coefficients'],np.zeros(len(grid))))
            total+=np.exp(scores-logsumexp(scores,axis=1)[:,None])
    return total/(4*nscan)
