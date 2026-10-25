"""Visibility certificates for the unchanged linear-bank/rotated phase model."""
import numpy as np
from scipy.optimize import brentq

DOMAIN=(-15.,15.)
ROOT_XTOL=1e-11
MAX_DEPTH=22
OMEGA=7.29211514670698e-5


def merge(intervals):
    result=[]
    for lo,hi in sorted(intervals):
        if hi<=lo:continue
        if result and lo<=result[-1][1]:result[-1][1]=max(hi,result[-1][1])
        else:result.append([float(lo),float(hi)])
    return result


def intersect(left,right):
    return merge([[max(a,c),min(b,d)] for a,b in left for c,d in right if max(a,c)<min(b,d)])


def remove(intervals,excluded):
    result=[]
    for lo,hi in intervals:
        cursor=lo
        for a,b in merge(excluded):
            if b<=cursor or a>=hi:continue
            if a>cursor:result.append([cursor,min(a,hi)])
            cursor=max(cursor,b)
        if cursor<hi:result.append([cursor,hi])
    return merge(result)


def piece_function(mid,position,slope,up,observer,omega=OMEGA):
    """Exact support sign and derivative on one bank interpolation piece."""
    def evaluate(phi):
        phi=np.asarray(phi);v=position+(phi[...,None]-mid)*slope
        c,s=np.cos(omega*phi),np.sin(omega*phi)
        rotated=np.stack((c*v[...,0]-s*v[...,1],s*v[...,0]+c*v[...,1],v[...,2]),axis=-1)
        velocity=np.broadcast_to(slope,v.shape).copy()
        velocity[...,0]-=omega*v[...,1];velocity[...,1]+=omega*v[...,0]
        derivative=np.stack((c*velocity[...,0]-s*velocity[...,1],s*velocity[...,0]+c*velocity[...,1],velocity[...,2]),axis=-1)
        return rotated@up-observer@up,derivative@up
    return evaluate


def certify_piece(lo,hi,mid,position,slope,up,observer,omega=OMEGA,depth=0):
    evaluate=piece_function(mid,position,slope,up,observer,omega)
    center=(lo+hi)/2;half=(hi-lo)/2;h,der=evaluate(center)
    xy=max(np.linalg.norm((position+(p-mid)*slope)[:2]) for p in (lo,hi))
    curvature=2*abs(omega)*np.linalg.norm(slope[:2])+omega**2*xy
    rounding=128*np.finfo(float).eps*(np.linalg.norm(observer)+np.linalg.norm(position)+np.linalg.norm(slope)*(hi-lo)+1)
    radius=abs(float(der))*half+.5*curvature*half**2+rounding
    if h-radius>0:return dict(visible=[[lo,hi]],roots=[],unresolved=[],pieces=1)
    if h+radius<0:return dict(visible=[],roots=[],unresolved=[],pieces=1)
    left,right=map(float,evaluate(np.array([lo,hi]))[0])
    minimum_slope=abs(float(der))-curvature*half
    if minimum_slope>rounding/max(half,1e-30):
        if left>rounding and right>rounding:return dict(visible=[[lo,hi]],roots=[],unresolved=[],pieces=1)
        if left<-rounding and right<-rounding:return dict(visible=[],roots=[],unresolved=[],pieces=1)
        if left*right<=0:
            root=brentq(lambda x:float(evaluate(x)[0]),lo,hi,xtol=ROOT_XTOL,rtol=8*np.finfo(float).eps)
            uncertainty=ROOT_XTOL+rounding/minimum_slope
            a,b=max(lo,root-uncertainty),min(hi,root+uncertainty)
            visible=[[lo,a]] if der<0 else [[b,hi]]
            return dict(visible=visible,roots=[[a,b]],unresolved=[],pieces=1)
    if depth>=MAX_DEPTH or hi-lo<=1e-10:
        return dict(visible=[],roots=[],unresolved=[[lo,hi]],pieces=1)
    first=certify_piece(lo,center,mid,position,slope,up,observer,omega,depth+1)
    second=certify_piece(center,hi,mid,position,slope,up,observer,omega,depth+1)
    return {key:first[key]+second[key] for key in ('visible','roots','unresolved','pieces')}


def support(bank,times,up,observer,omega=OMEGA):
    knots=np.asarray(bank['time_s']);positions=np.asarray(bank['position_km'])[0]
    times=np.asarray(times);lo,hi=DOMAIN
    up,observer=np.asarray(up,float),np.asarray(observer,float)
    if (knots.ndim!=1 or len(knots)<2 or not np.isfinite(knots).all() or np.any(np.diff(knots)<=0)
        or positions.shape!=(len(knots),3) or not np.isfinite(positions).all()
        or times.ndim!=1 or not len(times) or not np.isfinite(times).all()
        or up.shape!=(3,) or observer.shape!=(3,) or not np.isfinite(up).all() or not np.isfinite(observer).all()
        or abs(np.linalg.norm(up)-1)>1e-12 or not np.isfinite(omega)):
        raise ValueError('finite increasing bank, aligned positions/times and unit observer-up required')
    if min(times)+lo<knots[0] or max(times)+hi>knots[-1]:raise ValueError('phase support would extrapolate original bank')
    possible=[[lo,hi]];all_roots=[];unresolved=[];piece_count=0
    for t in times:
        cuts=np.unique(np.r_[lo,knots[(knots>t+lo)&(knots<t+hi)]-t,hi]);visible=[];roots=[]
        for left,right in zip(cuts[:-1],cuts[1:],strict=True):
            mid=(left+right)/2;index=int(np.clip(np.searchsorted(knots,t+mid,side='right')-1,0,len(knots)-2))
            slope=(positions[index+1]-positions[index])/(knots[index+1]-knots[index])
            position=positions[index]+(t+mid-knots[index])*slope
            result=certify_piece(float(left),float(right),mid,position,slope,up,observer,omega)
            visible+=result['visible'];roots+=result['roots'];unresolved+=result['unresolved'];piece_count+=result['pieces']
        possible=intersect(possible,merge(visible+roots))
        all_roots+=roots
    root_brackets=intersect(possible,merge(all_roots))
    inner=remove(possible,root_brackets)
    # All interpolation breakpoints are retained for numerical integration,
    # including nominal derivative discontinuities. The scientific loader must
    # assert equality to the physical-mode knots before reusing this partition.
    cuts=np.unique(np.concatenate([knots[(knots>t+lo)&(knots<t+hi)]-t for t in times]))
    return dict(certified=not unresolved,inner_visible_intervals=inner,root_brackets=root_brackets,
        unresolved_intervals=merge(unresolved),interpolation_breakpoints=cuts,
        certified_piece_count=piece_count,root_xtol_s=ROOT_XTOL,maximum_subdivision_depth=MAX_DEPTH)


def panels(intervals,breakpoints):
    result=[]
    for lo,hi in intervals:
        cuts=np.r_[lo,breakpoints[(breakpoints>lo)&(breakpoints<hi)],hi]
        result.extend([[a,b] for a,b in zip(cuts[:-1],cuts[1:],strict=True) if b>a])
    return np.asarray(result,float).reshape(-1,2)
