"""Offline joint frequency-bias adapter; no satellite-specific rules or time edits."""
import numpy as np
from leo.analysis.shared_scan_model import density, elevation_geometry, horizon_weight
from leo.analysis.hard60_score import predict_orbits


class FrozenBandBiasJoint:
    def __init__(self, base, full_basis, satellite_indices, *, sigma_s=.5):
        if base.original.group_count:
            raise ValueError('Fixed high-band contrast required')
        self.base=base
        self.satellite_indices=np.asarray(satellite_indices,int)
        if len(np.unique(self.satellite_indices))!=len(self.satellite_indices):
            raise ValueError('One lower-band frequency slot per satellite required')
        self.full_basis=np.asarray(full_basis,float)
        if self.full_basis.shape!=(len(base.observations.times_s),len(self.satellite_indices)):
            raise ValueError('One fixed frequency basis per original observation and declared satellite')
        self.bias_basis=self.full_basis[base.mask]
        self.base_count=len(base.initial_nuisance)
        self.initial_nuisance=np.r_[base.initial_nuisance,np.zeros(len(self.satellite_indices))]
        self.group_limits=np.r_[base.group_limits,np.full(len(self.satellite_indices),2.)]
        self.group_scales=np.r_[base.group_scales,np.full(len(self.satellite_indices),.1)]
        self.group_count=base.group_count+len(self.satellite_indices)
        self.group_precision=np.zeros((self.group_count,self.group_count))
        self.group_precision[:base.group_count,:base.group_count]=base.group_precision
        self.group_precision[base.group_count:,base.group_count:]=np.eye(len(self.satellite_indices))/sigma_s**2
        self.bias_precision=1/sigma_s**2

    def __getattr__(self,name):
        if name=='base':raise AttributeError(name)
        return getattr(self.base,name)

    def split(self,nuisance):
        n=np.asarray(nuisance,float)
        if n.shape!=self.initial_nuisance.shape or not np.isfinite(n).all():
            raise ValueError('Finite base nuisance and declared band coefficients required')
        return n[:self.clock_count],n[self.clock_count:]

    def evaluate_details(self,vector,nuisance):
        self.split(nuisance)
        v=np.asarray(vector,float);n=np.asarray(nuisance,float);old_n=n[:self.base_count];amplitude=n[self.base_count:]
        old,old_d=self.base.evaluate_details(v,old_n)
        obs=self.base.scored_observations;shifts=v[7]+self.base.basis@v[8:]
        prediction,_,spatial,timing=predict_orbits(self.bank,obs,self.prior,v[:2],shifts)
        prediction+=self.original.correction(v,old_n[:self.clock_count])[self.base.mask,None]
        prediction[:,self.satellite_indices]+=self.bias_basis*amplitude
        sigma,_,q,q_jac,_=self.base.hyperparameters(old_n[self.base.base_nuisance_count:])
        terms,details=density(obs.measured_hz,prediction,old_d['visibility_weight'],sigma,q,self.score)
        dw=terms.prediction_gradient-old[3].prediction_gradient
        _,es,et,_=elevation_geometry(self.bank,obs,self.prior,v[:2],shifts)
        _,slope=horizon_weight(old_d['sine_elevation'],self.visibility_width)
        de=(details['visibility_weight_gradient']-old_d['visibility_weight_gradient'])*slope
        gradient=old[1].copy()
        gradient[:2]+=np.einsum('nk,nki->i',dw,spatial)+np.einsum('nk,nki->i',de,es)
        gradient[2:7]+=self.original.design[self.base.mask].T@dw.sum(axis=1)
        dt=np.sum(dw*timing+de*et,axis=0);gradient[7]+=dt.sum();gradient[8:]+=self.base.basis.T@dt
        extra=old[2].copy()
        extra[:self.clock_count]+=self.original.clock_design[self.base.mask].T@dw.sum(axis=1)
        extra[self.base.base_nuisance_count:]+=q_jac.T@(details['detection_probability_gradient']-old_d['detection_probability_gradient'])
        amp_gradient=np.sum(terms.prediction_gradient[:,self.satellite_indices]*self.bias_basis,axis=0)+self.bias_precision*amplitude
        penalty=.5*self.bias_precision*float(amplitude@amplitude)
        value=old[0]+terms.nll-old[3].nll+penalty
        details={**old_d,**details,'band_frequency_amplitude_s':amplitude,'prior_penalty':old_d['prior_penalty']+penalty}
        return (float(value),gradient,np.r_[extra,amp_gradient],terms),details

    def evaluate_joint(self,vector,nuisance):
        return self.evaluate_details(vector,nuisance)[0]
