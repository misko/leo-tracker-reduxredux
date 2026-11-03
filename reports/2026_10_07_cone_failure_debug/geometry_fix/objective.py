"""Research gates: no learned-shape refit, no truth pruning, no mass redistribution."""
import importlib.util
from pathlib import Path
import numpy as np
from scipy.special import expit,log_expit
from leo.analysis.regional_position_score import PositionObjective,predict_orbits
HERE=Path(__file__).resolve().parent
CONES=HERE.parent.parent/'2026_10_07_sigma1_cones'
spec=importlib.util.spec_from_file_location('previous_cone_adapter',CONES/'cone_objective.py')
cones=importlib.util.module_from_spec(spec);spec.loader.exec_module(cones)

def receiver_logits(unit,theta,frames,sharpness=1.):
    alpha,beta,logwidth,roll0,roll1=theta
    matrices=np.array([np.stack([np.cos(r)*f[0]+np.sin(r)*f[1],-np.sin(r)*f[0]+np.cos(r)*f[1],f[2]]) for f,r in zip(frames,(roll0,roll1))])
    xyz=np.einsum('...i,rji->...rj',unit,matrices);x,y,z=np.moveaxis(xyz,-1,0)
    ca,cb=1/np.tan(alpha),1/np.tan(beta);h=np.sqrt((x*ca)**2+(y*cb)**2+1e-24)
    scale=np.exp(-logwidth)*sharpness;logits=(z-h)*scale
    jac=(matrices[:,2]-x[...,None]*ca**2/h[...,None]*matrices[:,0]-y[...,None]*cb**2/h[...,None]*matrices[:,1])*scale
    return logits,jac

class GeometryObjective(PositionObjective):
    def __init__(self,obs,bank,prior,score,*,receiver_baseline_hz=None,mode='control',theta=None,frames=None,support=None):
        super().__init__(obs,bank,prior,score,receiver_baseline_hz=receiver_baseline_hz)
        if score.relative_sigma_s!=1:raise ValueError('sigma must remain 1 s')
        if mode not in ('control','conditional','absolute','absolute2'):raise ValueError('unknown geometry mode')
        self.mode=mode
        if theta is None:theta,frames,support=cones.cone_bundle()
        self.theta,self.frames,self.support=theta,frames,support
    def evaluate(self,vector):
        if self.mode=='control':return super().evaluate(vector)
        vector=np.asarray(vector,float);relative=self.basis@vector[8:];shifts=vector[7]+relative
        prediction,visible,spatial,timing=predict_orbits(self.bank,self.observations,self.prior,vector[:2],shifts)
        prediction+=(self.design@vector[2:7]+self.baseline)[:,None]
        unit,dp,dt=cones.directions(self.bank,self.observations,self.prior,vector,self.basis)
        support,js=self.support.evaluate(unit);receiver=self.observations.receiver[:,None,None]
        marg,jm=cones.cone_marginals(unit,self.theta,self.frames)
        marginal=np.take_along_axis(marg,receiver,axis=2)[...,0]
        if self.mode=='conditional':
            selected_jac=np.take_along_axis(jm,receiver[...,None],axis=2)[...,0,:]
            amplitude=.1+.9*marginal;logamplitude=np.log(amplitude)
            jlogamplitude=.9/amplitude[...,None]*selected_jac
            selected_logits=None
        else:
            logits,jl=receiver_logits(unit,self.theta,self.frames,2. if self.mode=='absolute2' else 1.)
            selected_logits=np.take_along_axis(logits,receiver,axis=2)[...,0]
            selected_jac=np.take_along_axis(jl,receiver[...,None],axis=2)[...,0,:]
            logamplitude=log_expit(selected_logits)
            jlogamplitude=(1-expit(selected_logits))[...,None]*selected_jac
        logfactor=support*logamplitude;jlogfactor=js*logamplitude[...,None]+support[...,None]*jlogamplitude
        base=np.where(visible,self.score.detection_budget/len(self.bank.numbers),0.)
        factor=np.exp(logfactor);q=base*factor
        terms,gq=cones.likelihood_q(self.observations.measured_hz,prediction,q,self.score)
        geometry=(q*gq)[...,None]*jlogfactor;weight=terms.prediction_gradient
        shift_gradient=np.sum(weight*timing+np.sum(geometry*dt,axis=2),axis=0)
        gradient=np.zeros(self.size);gradient[:2]=np.einsum('nk,nki->i',weight,spatial)+np.einsum('nkj,nkji->i',geometry,dp)
        gradient[2:7]=self.design.T@weight.sum(axis=1)
        gradient[7]=shift_gradient.sum()+vector[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift_gradient+relative/self.score.relative_sigma_s**2)
        penalty=.5*(vector[7]/self.score.common_sigma_s)**2+.5*np.sum((relative/self.score.relative_sigma_s)**2)
        self.last_geometry={'unit_enu':unit,'q':q,'base_q':base,'factor':factor,'support':support,'marginal':marginal,'selected_logits':selected_logits,'log_factor':logfactor}
        return terms.nll+float(penalty),gradient,terms
