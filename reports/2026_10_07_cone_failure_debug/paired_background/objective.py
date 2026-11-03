"""Shared unidentified emission background for frozen acquisition-epoch pairs.

Known-satellite sharing is delegated to the reviewed paired identity model.
Only clutter-clutter density is mixed with a same-frequency unidentified source.
This is soft pilot/frame phase evidence, not a decoded transmitter identity.
"""
import importlib.util
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.analysis.regional_position_score import ALIAS_HZ,WindowLikelihood,circular,predict_orbits

_SPEC=importlib.util.spec_from_file_location('_paired_identity_background_dependency',Path(__file__).resolve().parent.parent/'paired_identity/objective.py')
paired=importlib.util.module_from_spec(_SPEC);_SPEC.loader.exec_module(paired)

def wrapped_density(residual,sigma):
    count=max(1,int(np.ceil((sigma*np.sqrt(-2*np.log(1e-15))+ALIAS_HZ/2)/ALIAS_HZ)))
    images=circular(np.asarray(residual))[...,None]+np.arange(-count,count+1)*ALIAS_HZ
    logs=-.5*(images/sigma)**2-np.log(sigma*np.sqrt(2*np.pi))
    density=logsumexp(logs,axis=-1)
    mean=np.sum(np.exp(logs-density[...,None])*images,axis=-1)
    return density,mean

def background_likelihood(measured,prediction,visible,score,pairs,rho,eta,clock_hz):
    if not 0<=eta<=1:raise ValueError('invalid common-background probability')
    pairs=paired.validate_pairs(pairs,len(measured))
    clock=np.asarray(clock_hz,float)
    if clock.shape!=(len(measured),) or not np.isfinite(clock).all():raise ValueError('invalid receiver clock corrections')
    original=paired.coupled_likelihood(measured,prediction,visible,score,pairs,rho)
    extra_gradient=np.zeros(len(measured))
    if eta==0 or not len(pairs):
        return original,extra_gradient,dict(common_background_probability=np.zeros(len(pairs)))
    i,j=pairs.T
    q=np.where(visible,score.detection_budget/prediction.shape[1],0.)
    log_odds=np.full_like(q,-np.inf);log_odds[visible]=np.log(q[visible])-np.log1p(-q[visible])
    residual=circular(np.asarray(measured)[:,None]-prediction)
    phi,mean_image=wrapped_density(residual,score.sigma_hz)
    signals=log_odds+phi;signal_sum=logsumexp(signals,axis=1);prior_sum=logsumexp(log_odds,axis=1)
    clutter=np.log(score.clutter_rate/ALIAS_HZ)
    overlap=logsumexp(log_odds[i]+log_odds[j],axis=1)
    valid=np.isfinite(overlap)
    double=signal_sum[i]+signal_sum[j]
    if rho>0:
        boost=prior_sum[i[valid]]+prior_sum[j[valid]]-overlap[valid]
        log_independent=np.log1p(-rho) if rho<1 else -np.inf
        double[valid]=np.logaddexp(log_independent+double[valid],np.log(rho)+boost+logsumexp(signals[i[valid]]+signals[j[valid]],axis=1))
    single=logsumexp(np.stack([clutter+signal_sum[i],clutter+signal_sum[j],double]),axis=0)
    old_pair=np.logaddexp(2*clutter,single)
    difference=circular(np.asarray(measured)[j]-np.asarray(measured)[i]+clock[i]-clock[j])
    log_phi_difference,mean_difference=wrapped_density(difference,np.sqrt(2)*score.sigma_hz)
    common_cc=2*np.log(score.clutter_rate)+np.log(eta)-np.log(ALIAS_HZ)+log_phi_difference
    independent_cc=2*clutter+(np.log1p(-eta) if eta<1 else -np.inf)
    new_cc=np.logaddexp(independent_cc,common_cc)
    new_pair=np.logaddexp(new_cc,single)
    responsibility=original.responsibilities.copy();clutter_probability=original.clutter_probability.copy()
    # Rebuild log numerators: scaling an underflowed old zero by an overflowing
    # ratio is unsafe when eta=1 and an unidentified pair is far from equality.
    for row,peer in ((i,j),(j,i)):
        companion=np.broadcast_to(np.logaddexp(clutter,signal_sum[peer,None]),signals[row].shape).copy()
        if rho>0:
            companion[valid]=np.logaddexp(clutter,np.logaddexp(log_independent+signal_sum[peer[valid],None],np.log(rho)+boost[:,None]+signals[peer[valid]]))
        responsibility[row]=np.exp(signals[row]+companion-new_pair[:,None])
    clutter_probability[i]=np.exp(np.logaddexp(new_cc,clutter+signal_sum[j])-new_pair)
    clutter_probability[j]=np.exp(np.logaddexp(new_cc,clutter+signal_sum[i])-new_pair)
    common_probability=np.exp(common_cc-new_pair)
    derivative=common_probability*mean_difference/(2*score.sigma_hz**2)
    extra_gradient[i]=derivative;extra_gradient[j]=-derivative
    terms=WindowLikelihood(original.nll-float(np.sum(new_pair-old_pair)),responsibility,clutter_probability,-responsibility*mean_image/score.sigma_hz**2,residual)
    diagnostics=dict(common_background_probability=common_probability,independent_background_probability=np.exp(independent_cc-new_pair),corrected_pair_difference_hz=difference,clock_gradient=extra_gradient)
    return terms,extra_gradient,diagnostics

class BackgroundObjective(paired.PairedObjective):
    def __init__(self,*args,eta=.9,**kwargs):
        super().__init__(*args,**kwargs)
        if not 0<=eta<=1:raise ValueError('invalid common-background probability')
        self.eta=eta
    def evaluate(self,vector):
        if self.eta==0:
            self.last_background=dict(common_background_probability=np.zeros(len(self.pairs)))
            return super().evaluate(vector)
        vector=np.asarray(vector,float)
        if vector.shape!=(self.size,) or not np.isfinite(vector).all():raise ValueError('invalid position parameter vector')
        relative=self.basis@vector[8:];shifts=vector[7]+relative
        prediction,visible,spatial,timing=predict_orbits(self.bank,self.observations,self.prior,vector[:2],shifts)
        clock=self.design@vector[2:7]+self.baseline
        prediction+=clock[:,None]
        terms,clock_gradient,self.last_background=background_likelihood(self.observations.measured_hz,prediction,visible,self.score,self.pairs,self.rho,self.eta,clock)
        weight=terms.prediction_gradient;shift_gradient=np.sum(weight*timing,axis=0)
        gradient=np.zeros(self.size)
        gradient[:2]=np.einsum('nk,nki->i',weight,spatial)
        gradient[2:7]=self.design.T@(weight.sum(axis=1)+clock_gradient)
        gradient[7]=shift_gradient.sum()+vector[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift_gradient+relative/self.score.relative_sigma_s**2)
        penalty=.5*(vector[7]/self.score.common_sigma_s)**2+.5*np.sum((relative/self.score.relative_sigma_s)**2)
        return terms.nll+float(penalty),gradient,terms
