"""Exact penalized chronological quadratic segmentation; no observations dropped."""
import numpy as np


def partition(times,frequencies,*,sigma=100.,penalty_factor=6.,minimum_points=6,minimum_span=3.,maximum_segments=4):
    t=np.asarray(times,float);y=np.asarray(frequencies,float);n=len(t)
    if t.ndim!=1 or y.shape!=t.shape or n<minimum_points or np.any(np.diff(t)<=0) or not np.isfinite(t).all() or not np.isfinite(y).all():raise ValueError('invalid ordered observations')
    if sigma<=0 or penalty_factor<0 or minimum_points<3 or maximum_segments<1:raise ValueError('invalid policy')
    costs=np.full((n+1,n+1),np.inf)
    for a in range(n):
        for b in range(a+minimum_points,n+1):
            if t[b-1]-t[a]<minimum_span:continue
            x=(t[a:b]-t[a:b].mean())/max(float(np.ptp(t[a:b])),1.)
            design=np.column_stack((np.ones(len(x)),x,x*x))
            values=y[a:b]-y[a];beta=np.linalg.lstsq(design,values,rcond=None)[0]
            residual=values-design@beta;costs[a,b]=float(residual@residual)
    if not np.isfinite(costs[0,n]):raise ValueError('insufficient total support')
    penalty=penalty_factor*np.log(n);dp=np.full((maximum_segments+1,n+1),np.inf);back=np.full(dp.shape,-1,int);dp[0,0]=0.
    for k in range(1,maximum_segments+1):
        for b in range(minimum_points*k,n+1):
            options=dp[k-1,:b]+costs[:b,b]/sigma**2+(penalty if k>1 else 0.)
            a=int(np.argmin(options));dp[k,b]=options[a];back[k,b]=a
    k=int(np.argmin(dp[:,n]));value=float(dp[k,n]);segments=[];b=n
    while k:
        a=int(back[k,b]);segments.append(dict(start=a,stop=b,points=b-a,span_s=float(t[b-1]-t[a]),sse_hz2=float(costs[a,b])));b=a;k-=1
    segments.reverse()
    assert b==0 and sum(s['points'] for s in segments)==n
    sse=sum(s['sse_hz2'] for s in segments)
    assert abs(value-(sse/sigma**2+penalty*(len(segments)-1)))<1e-7
    return dict(segments=segments,objective=value,sigma_hz=sigma,penalty_per_split=float(penalty),
                unsplit_sse_hz2=float(costs[0,n]),segmented_sse_hz2=sse,
                rms_before_hz=float(np.sqrt(costs[0,n]/n)),rms_after_hz=float(np.sqrt(sse/n)))
