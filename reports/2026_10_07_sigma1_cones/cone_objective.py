"""Pure cone-prior adapter for the deployed V16 model, not legacy numerics.

Cone marginals/support/tilt are the Oct5 pure geometry helpers; only frame()
is reused from the pure receiver model. All frequency/orbit scoring is deployed.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.analysis.regional_position_score import (PositionObjective,WindowLikelihood,
    predict_orbits,observer,coordinates,circular,ALIAS_HZ)

REPORTS=Path(__file__).resolve().parent.parent
def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
_geometry=_load('frozen_cone_geometry',REPORTS/'2026_10_05_cone_prior_localization/cone_geometry.py')
_model=_load('frozen_receiver_cone_model',REPORTS/'2026_10_05_receiver_cones/cone_model.py')
cone_marginals,tilt,Support=_geometry.cone_marginals,_geometry.tilt,_geometry.Support
CONE_BUNDLE_DIGESTS={}

def cone_bundle():
    folder=REPORTS/'2026_10_05_receiver_cones'
    summary=folder/'summary.json';maps=folder/'sky-maps.npz'
    for path in (summary,maps,Path(_geometry.__file__),Path(_model.__file__)):
        CONE_BUNDLE_DIGESTS[str(path.relative_to(REPORTS))]='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    theta=np.asarray(json.loads(summary.read_text())['primary']['theta'],float)
    frames=np.array([_model.frame(270,70),_model.frame(90,70)])
    with np.load(maps) as z:support=Support(z['inside'],z['supported'])
    return theta,frames,support

def _enu(prior,point):
    latitude,longitude=np.radians(coordinates(prior,point));s,c=np.sin(longitude),np.cos(longitude)
    sl,cl=np.sin(latitude),np.cos(latitude)
    return np.array([[-s,c,0],[-sl*c,-sl*s,cl],[cl*c,cl*s,sl]])

def directions(bank,obs,prior,vector,basis,derivatives=True):
    vector=np.asarray(vector);shifts=vector[7]+basis@vector[8:]
    query=obs.times_s[:,None]+shifts[None,:];step=bank.nodes_s[1]-bank.nodes_s[0]
    if np.any(query<bank.nodes_s[0]) or np.any(query>bank.nodes_s[-1]):raise ValueError('orbit query outside ephemeris support')
    fractional=(query-bank.nodes_s[0])/step
    lower=np.minimum(np.floor(fractional).astype(int),len(bank.nodes_s)-2)
    weight=(fractional-lower)[...,None];sat=np.arange(len(bank.numbers))[None,:]
    p0,p1=bank.position_km[sat,lower],bank.position_km[sat,lower+1]
    position=p0+weight*(p1-p0);site=observer(prior,vector[:2])[0]
    delta=position-site;distance=np.linalg.norm(delta,axis=2);unit=delta/distance[...,None]
    rotation=_enu(prior,vector[:2]);enu=np.einsum('ij,nkj->nki',rotation,unit)
    if not derivatives:return enu,None,None
    eye=np.eye(2)*.001
    site_jac=np.stack([(observer(prior,vector[:2]+d)[0]-observer(prior,vector[:2]-d)[0])/.002 for d in eye])
    rotate_jac=np.stack([(_enu(prior,vector[:2]+d)-_enu(prior,vector[:2]-d))/.002 for d in eye])
    du=(-site_jac[None,None,:,:]+unit[:,:,None,:]*np.einsum('nkj,ij->nki',unit,site_jac)[...,None])/distance[:,:,None,None]
    dp=np.einsum('lj,nkij->nkli',rotation,du)+np.einsum('ilj,nkj->nkli',rotate_jac,unit)
    rate=(p1-p0)/step;dt=(rate-unit*np.sum(unit*rate,axis=2)[...,None])/distance[...,None]
    return enu,dp,np.einsum('ij,nkj->nki',rotation,dt)

def likelihood_q(measured,prediction,q,score):
    if np.any(q<0) or np.any(q>=1):raise ValueError('cone tilted detection probability outside [0,1)')
    residual=circular(measured[:,None]-prediction);sigma=score.sigma_hz
    count=max(1,int(np.ceil((sigma*np.sqrt(-2*np.log(1e-15))+ALIAS_HZ/2)/ALIAS_HZ)))
    images=residual[...,None]+np.arange(-count,count+1)*ALIAS_HZ
    logs=-.5*(images/sigma)**2-np.log(sigma*np.sqrt(2*np.pi))
    phi=logsumexp(logs,axis=2);mean=np.sum(np.exp(logs-phi[...,None])*images,axis=2)
    positive=q>0;odds=np.full_like(q,-np.inf);odds[positive]=np.log(q[positive])-np.log1p(-q[positive])
    signal=odds+phi;clutter=np.log(score.clutter_rate/ALIAS_HZ)
    h=np.logaddexp(clutter,logsumexp(signal,axis=1));p0=-score.clutter_rate+np.log1p(-q).sum(axis=1)
    density=p0-np.log(-np.expm1(p0))+h;responsibility=np.exp(signal-h[:,None])
    terms=WindowLikelihood(float(-density.sum()),responsibility,np.exp(clutter-h),-responsibility*mean/sigma**2,residual)
    gq=1/((-np.expm1(p0))[:,None]*(1-q))
    gq[positive]-=responsibility[positive]/(q[positive]*(1-q[positive]))
    return terms,gq

class ConeObjective(PositionObjective):
    def __init__(self,observations,bank,prior,score,*,receiver_baseline_hz=None,strength=0.,theta=None,frames=None,support=None):
        super().__init__(observations,bank,prior,score,receiver_baseline_hz=receiver_baseline_hz)
        if score.relative_sigma_s!=1.:raise ValueError('cone experiment requires fixed sigma=1')
        if not np.isfinite(strength) or strength<0:raise ValueError('invalid cone strength')
        self.strength=float(strength)
        if theta is None or frames is None or support is None:theta,frames,support=cone_bundle()
        self.theta,self.frames,self.support=theta,frames,support
    def evaluate(self,vector):
        if self.strength==0:return super().evaluate(vector)
        vector=np.asarray(vector,float);relative=self.basis@vector[8:];shifts=vector[7]+relative
        prediction,visible,spatial,timing=predict_orbits(self.bank,self.observations,self.prior,vector[:2],shifts)
        prediction+=(self.design@vector[2:7]+self.baseline)[:,None]
        unit,dp,dt=directions(self.bank,self.observations,self.prior,vector,self.basis)
        marg,jm=cone_marginals(unit,self.theta,self.frames);support,js=self.support.evaluate(unit)
        receiver=self.observations.receiver[:,None,None]
        selected=np.take_along_axis(marg,receiver,axis=2)[...,0]
        jac=np.take_along_axis(jm,receiver[...,None],axis=2)[...,0,:]
        amplitude=.1+.9*selected;logfactor=self.strength*support*np.log(amplitude)
        jlog=self.strength*(js*np.log(amplitude)[...,None]+support[...,None]*.9/amplitude[...,None]*jac)
        base=np.where(visible,self.score.detection_budget/len(self.bank.numbers),0.)
        q=tilt(base,logfactor);terms,gq=likelihood_q(self.observations.measured_hz,prediction,q,self.score)
        _,_,glog=tilt(base,logfactor,gq);geometry=glog[...,None]*jlog
        weight=terms.prediction_gradient;shift_gradient=np.sum(weight*timing+np.sum(geometry*dt,axis=2),axis=0)
        gradient=np.zeros(self.size)
        gradient[:2]=np.einsum('nk,nki->i',weight,spatial)+np.einsum('nkj,nkji->i',geometry,dp)
        gradient[2:7]=self.design.T@weight.sum(axis=1)
        gradient[7]=shift_gradient.sum()+vector[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift_gradient+relative/self.score.relative_sigma_s**2)
        penalty=.5*(vector[7]/self.score.common_sigma_s)**2+.5*np.sum((relative/self.score.relative_sigma_s)**2)
        self.last_geometry={'unit_enu':unit,'q':q,'base_q':base,'log_factor':logfactor,'support':support,'marginal':selected}
        return terms.nll+float(penalty),gradient,terms
