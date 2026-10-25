"""Bounded physical log-density envelope; quadrature agreement is insufficient."""
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
import support_geometry as sg

MAX_PANELS=8192
REFINE_BATCH=512
K=11.5e9/299792.458


def log_lipschitz_integrals(midpoint_log_density,derivative_bound,width):
    ell=np.asarray(midpoint_log_density);width=np.asarray(width)
    argument=np.asarray(derivative_bound)*width/2
    safe=np.maximum(argument,1e-300)
    lower=np.log(-np.expm1(-safe))-np.log(safe)
    upper=argument+lower
    lower=np.where(argument==0,0.,lower);upper=np.where(argument==0,0.,upper)
    rounding=1024*np.finfo(float).eps*(1+abs(ell))
    return ell+np.log(width)+lower-rounding,ell+np.log(width)+upper+rounding


def derivative_bounds(d,centers,half,observer,q):
    """Uniform frequency/three-mode derivative bounds on each bank piece."""
    sky=d['target_sky'];mode=d['target_mode_bank'];knots=np.asarray(sky['time_s'])
    if not np.array_equal(knots,np.asarray(mode['time_s'])):raise ValueError('nominal/mode knot grids differ')
    times=np.asarray(d['target_track']['times']);request=centers[:,None]+times[None]
    index=np.clip(np.searchsorted(knots,request,side='right')-1,0,len(knots)-2)
    interval=knots[index+1]-knots[index]
    frac=(request-knots[index])/interval
    def values(bank,key):
        source=np.asarray(bank[key])
        if not np.isfinite(source).all():raise ValueError('nonfinite physical bank')
        source=source.transpose(1,0,2)
        slope=(source[index+1]-source[index])/interval[...,None,None]
        value=source[index]+frac[...,None,None]*(source[index+1]-source[index])
        h=half[:,None,None]
        maximum=np.linalg.norm(value,axis=-1)+h*np.linalg.norm(slope,axis=-1)
        rate=np.linalg.norm(slope,axis=-1)+abs(sg.OMEGA)*(np.linalg.norm(value[...,:2],axis=-1)+h*np.linalg.norm(slope[...,:2],axis=-1))
        return value,maximum,rate
    p,p0,p1=values(sky,'position_km');_,v0,v1=values(sky,'velocity_km_s')
    angle=sg.OMEGA*centers[:,None];c,s=np.cos(angle),np.sin(angle)
    position=p[:,:,0,:].copy();px=position[...,0].copy();py=position[...,1].copy()
    position[...,0]=c*px-s*py;position[...,1]=s*px+c*py
    distance=np.linalg.norm(position-observer,axis=-1)-p1[:,:,0]*half[:,None]
    if np.any(distance<=0):raise ValueError('range not bounded away from zero')
    dp,dp0,dp1=values(mode,'position_km');_,dv0,dv1=values(mode,'velocity_km_s')
    r1=p1[:,:,0];vv0=v0[:,:,0];vv1=v1[:,:,0]
    frequency=K*(vv1+vv0*r1/distance)*q[None]
    shape=K*((vv1/distance+3*vv0*r1/distance**2)[...,None]*dp0
        +(vv0/distance)[...,None]*dp1+(r1/distance)[...,None]*dv0+dv1)*q[None,:,None]
    return frequency,shape


def physical_panel_bounds(d,comp,geometry,law,pieces):
    pieces=np.asarray(pieces);center=pieces.mean(axis=1);half=np.diff(pieces,axis=1)[:,0]/2
    geo=geometry(center);mean=geo['frequency_hz']*comp['q'][None]
    shape=geo['shape_columns_hz']*comp['q'][None,:,None]
    root=comp['root'];white=solve_triangular(root,(comp['raw'][None]-mean).T,lower=True).T
    n,m,k=shape.shape
    wb=solve_triangular(root,shape.transpose(1,0,2).reshape(m,-1),lower=True).reshape(m,n,k).transpose(1,0,2)
    gram=np.eye(k)[None]+np.einsum('nki,nkj->nij',wb,wb)
    fd,bd=derivative_bounds(d,center,half,comp['observer'],comp['q'])
    lw=np.linalg.norm(fd,axis=1)/comp['noise_minimum_sd']
    lb=np.linalg.norm(bd,axis=(1,2))/comp['noise_minimum_sd']
    delta_w=lw*half;delta_b=lb*half;b0=np.linalg.norm(wb,axis=(1,2))
    determinant=comp['base_logdet']+np.linalg.slogdet(gram)[1]
    lo=[];hi=[]
    for shift in comp['whitened_aliases']:
        w=white+shift
        alpha=np.linalg.solve(gram,np.einsum('nki,nk->ni',wb,w)[...,None])[...,0]
        residual=w-np.einsum('nki,ni->nk',wb,alpha)
        t0=np.linalg.norm(residual,axis=1);a0=np.linalg.norm(alpha,axis=1)
        delta_t=delta_w+b0*delta_b*t0+delta_b*a0+delta_b**2*t0
        tt=t0+delta_t;aa=a0+delta_b*t0+(b0+delta_b)*delta_t
        derivative=lw*tt+lb*tt*aa+np.sqrt(k)/2*lb+2/law['sd']
        cost=np.sum(residual**2,axis=1)+np.sum(alpha**2,axis=1)+determinant+m*np.log(2*np.pi)
        ell=-.5*cost+law['distribution'].logpdf(center)-np.log(law['mass'])-np.log(len(comp['whitened_aliases']))
        lower,upper=log_lipschitz_integrals(ell,derivative,2*half)
        lo.append(lower);hi.append(upper)
    return logsumexp(np.array(lo),axis=0),logsumexp(np.array(hi),axis=0)


def enclosure(d,comp,geometry,law,pieces,stop_below=None):
    pieces=np.asarray(pieces,float).reshape(-1,2)
    if not len(pieces):return dict(success=True,lower_log_integral=None,upper_log_integral=None,objective_width=0.,panels=0,evaluations=0)
    if len(pieces)>MAX_PANELS:return dict(success=False,reason='initial interpolation pieces exceed fixed envelope cap',panels=len(pieces))
    def evaluate(part):
        lows=[];highs=[]
        for start in range(0,len(part),256):
            lo,hi=physical_panel_bounds(d,comp,geometry,law,part[start:start+256]);lows.append(lo);highs.append(hi)
        return np.concatenate(lows),np.concatenate(highs)
    lower,upper=evaluate(pieces);evaluations=len(pieces)
    while True:
        total_lo,total_hi=float(logsumexp(lower)),float(logsumexp(upper))
        width=2*(total_hi-total_lo)
        excluded=stop_below is not None and total_hi<stop_below
        if width<=1e-3 or excluded or len(pieces)>=MAX_PANELS:break
        # Refinement is a frozen integration algorithm, never a new scientific
        # attempt. Refine the largest possible missing mass, without truth.
        uncertainty=upper+np.log(-np.expm1(np.minimum(0.,lower-upper)))
        count=min(REFINE_BATCH,MAX_PANELS-len(pieces),len(pieces))
        chosen=np.argsort(uncertainty)[-count:];keep=np.ones(len(pieces),bool);keep[chosen]=False
        old=pieces[chosen];middle=old.mean(axis=1)
        new=np.vstack((np.column_stack((old[:,0],middle)),np.column_stack((middle,old[:,1]))))
        lo,hi=evaluate(new);evaluations+=len(new)
        pieces=np.vstack((pieces[keep],new));lower=np.r_[lower[keep],lo];upper=np.r_[upper[keep],hi]
    return dict(success=bool(np.isfinite(width) and width<=1e-3),lower_log_integral=total_lo,
        upper_log_integral=total_hi,objective_width=float(width),panels=len(pieces),evaluations=evaluations,
        stopped_for_certified_exclusion=bool(excluded),exclusion_log_threshold=stop_below,
        maximum_panels=MAX_PANELS,maximum_new_panels_per_refinement=REFINE_BATCH,
        all_physical_aliases_bounded=True,original_prior_normalization=True)
