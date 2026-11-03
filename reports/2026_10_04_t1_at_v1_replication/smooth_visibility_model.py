"""Pure smooth-horizon prototype for the frozen single-window position model.

Visibility enters each satellite's Bernoulli detection probability, including
the finite-set empty/nonempty normalizer. No new detections or orbit parameters.
Coordinate frame and ephemeris arrays are explicit inputs; no storage access.
"""
import numpy as np
from scipy.special import expit, ndtr, ndtri, logsumexp

from prediction_jacobian import PairedPredictionJacobian
from position_structure_study import ALIAS, density_terms

GATES={
    'H':dict(label='Hard horizon',family='hard',width_deg=0.),
    'L1':dict(label='Logistic · 1°',family='logistic',width_deg=1.),
    'L4':dict(label='Logistic · 4°',family='logistic',width_deg=4.),
    'P1':dict(label='Gaussian CDF · 1°',family='probit',width_deg=1.),
    'Q1':dict(label='Above-horizon ramp · 0–1°',family='quintic',width_deg=1.),
}


def gate_terms(sine, mode):
    """Return weight and derivative w.r.t. sin(elevation).

    Centered widths mean full 10--90% angular transition. The compact quintic
    has support [0,width] and vanishing first/second derivatives at endpoints.
    Using sine avoids the arcsin derivative singularity at the zenith.
    """
    s=np.asarray(sine,float);spec=GATES[mode];family=spec['family']
    width=np.deg2rad(spec['width_deg'])
    if family=='hard':return (s>=0).astype(float),np.zeros_like(s)
    if family=='logistic':
        scale=np.sin(width/2)/np.log(9.)
        w=expit(s/scale);return w,w*(1-w)/scale
    if family=='probit':
        scale=np.sin(width/2)/ndtri(.9);z=s/scale
        return ndtr(z),np.exp(-.5*z*z)/(np.sqrt(2*np.pi)*scale)
    if family=='quintic':
        scale=np.sin(width);x=np.clip(s/scale,0.,1.)
        return x**3*(10.+x*(-15.+6.*x)),30.*x*x*(1.-x)**2/scale
    raise ValueError('Unknown visibility family')


def observer_pose(point, frame_deg):
    """Existing spherical offset frame -> WGS84 ECEF (km) and geodetic up."""
    east,north=np.asarray(point,float)
    angle=np.hypot(east,north)/6371.0088;bearing=np.arctan2(east,north)
    lat0,lon0=np.deg2rad(frame_deg)
    lat=np.arcsin(np.sin(lat0)*np.cos(angle)+np.cos(lat0)*np.sin(angle)*np.cos(bearing))
    lon=lon0+np.arctan2(np.sin(bearing)*np.sin(angle)*np.cos(lat0),np.cos(angle)-np.sin(lat0)*np.sin(lat))
    e2=(1./298.257223563)*(2.-1./298.257223563)
    radius=6378.137/np.sqrt(1.-e2*np.sin(lat)**2)
    up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
    xyz=radius*up;xyz[2]*=1.-e2
    return xyz,up


def horizon_geometry(data, parameters, frame_deg):
    """sin(elevation) and its position/timing Jacobian on the same orbit bank.

    Satellite interpolation is identical to the existing frequency predictor.
    Only the 2-D observer transform uses symmetric 1 m coordinate differences;
    LOS and per-satellite timing derivatives are analytic within each bank cell.
    """
    p=np.asarray(parameters);times=np.asarray(data.times);k=len(data.numbers)
    query=times[:,None]+p[6:][None,:];nodes=np.asarray(data.nodes)
    if np.any(query<nodes[0]) or np.any(query>=nodes[-1]):raise ValueError('Outside ephemeris')
    spacing=nodes[1]-nodes[0];fraction=(query-nodes[0])/spacing
    lower=np.floor(fraction).astype(int);weight=(fraction-lower)[...,None]
    indices=np.arange(k)[None,:]
    left=data.position[indices,lower];right=data.position[indices,lower+1]
    position=left*(1.-weight)+right*weight;rate=(right-left)/spacing
    observer,up=observer_pose(p[:2],frame_deg)
    dobs=np.empty((3,2));dup=np.empty((3,2));step=1e-3
    for axis in range(2):
        delta=np.eye(2)[axis]*step
        op,up1=observer_pose(p[:2]+delta,frame_deg);om,um=observer_pose(p[:2]-delta,frame_deg)
        dobs[:,axis]=(op-om)/(2*step);dup[:,axis]=(up1-um)/(2*step)
    los=position-observer;distance=np.linalg.norm(los,axis=-1);direction=los/distance[...,None]
    sine=direction@up
    ds_obs=-(up-direction*sine[...,None])/distance[...,None]
    shared=np.zeros(sine.shape+(6,))
    shared[...,:2]=ds_obs@dobs+direction@dup
    projected=(direction*rate).sum(axis=-1)
    tau=((rate-direction*projected[...,None])/distance[...,None])@up
    jac=PairedPredictionJacobian(shared.reshape(-1,6),tau.ravel(),
                                np.tile(np.arange(k),len(times)),k)
    return sine,jac


def finite_set_terms(measured,predicted,probability,weights,sigma_hz=200.,clutter=2.):
    """Exact variable-q single-observation finite-set likelihood and gradients.

    d log L / dq = exp(log f - log A)/(1-q)^2 - 1/[(1-q)(1-P0)],
    A = lambda/alias + sum(q f/(1-q)), P0 = exp(-lambda) prod(1-q).
    This remains finite at q=0, unlike using responsibility/q directly.
    """
    q=np.asarray(probability,float)
    if np.any(~np.isfinite(q)) or np.any(q<0) or np.any(q>=1):raise ValueError('q outside [0,1)')
    residual=(np.asarray(measured)[:,None]-predicted+ALIAS/2)%ALIAS-ALIAS/2
    logf,dg,precision=density_terms(residual,'C1',sigma_hz)
    logq=np.full_like(q,-np.inf);np.log(q,out=logq,where=q>0)
    log_signal=logq-np.log1p(-q)+logf
    logsum=np.logaddexp(np.log(clutter/ALIAS),logsumexp(log_signal,axis=1))
    logempty=-clutter+np.log1p(-q).sum(axis=1)
    nonempty=-np.expm1(logempty)
    perwindow=logempty+logsum-np.log(nonempty)
    probs=np.exp(log_signal-logsum[:,None])
    qgradient=np.exp(logf-logsum[:,None])/(1.-q)**2-1./((1.-q)*nonempty[:,None])
    return dict(total_log_likelihood=float(weights@perwindow),window_log_likelihood=perwindow,
        row_association_probability=probs,row_clutter_probability=1.-probs.sum(axis=1),
        prediction_gradient=weights[:,None]*probs*dg,
        probability_gradient=weights[:,None]*qgradient,
        irls_weights=weights[:,None]*probs*precision)


class SmoothLikelihood:
    def __init__(self,data,features,weights,gate):
        self.measured=np.asarray(data.measured);self.features=features
        self.coefficients=np.zeros(features.shape[1]);self.weights=weights
        self.alias_hz=ALIAS;self.detection_probability=.8/len(data.numbers);self.clutter_rate=2.
        self.gate=gate;self.sine=None;self.last_result=None

    def evaluate(self,predicted,visible,*,sigma_hz,**unused):
        if self.sine is None:raise RuntimeError('Geometry must be provided before likelihood evaluation')
        w,derivative=gate_terms(self.sine,self.gate)
        q=self.detection_probability*w
        pred=np.asarray(predicted)+(self.features@self.coefficients)[:,None]
        result=finite_set_terms(self.measured,pred,q,self.weights,sigma_hz,self.clutter_rate)
        dq=self.detection_probability*derivative
        result['elevation_gradient']=result['probability_gradient']*dq
        # Positive Bernoulli-information preconditioner, NOT an exact Hessian
        # of the conditioned marginal likelihood. Acceptance uses true NLL.
        result['elevation_precision']=self.weights[:,None]*dq*dq/np.maximum(q*(1.-q),1e-30)
        self.last_result=result
        return result
