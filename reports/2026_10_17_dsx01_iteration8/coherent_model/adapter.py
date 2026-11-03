"""Research fixed-partition coherent likelihood on unchanged joint-band state.

Automatic TRAIN-CFO-selected partitions are a working-likelihood assumption.
The kernel is normalized for a supplied fixed partition, not for its selection
event. New-point/held prediction always uses the normalized singleton marginal.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import numpy as np
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ,WindowLikelihood
from leo.analysis.shared_scan_model import SharedScanObjective,elevation_geometry,horizon_weight
from leo.analysis.sequential_group_calibration import SequentialShift

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]


def _module(name,path):
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]


joint=_module('dsx_coherent_joint_port',REPORTS/'2026_10_17_dsx01_iteration5/joint_band_contrast/model.py')
tracklets=_module('dsx_coherent_tracklet_port',REPORTS/'2026_10_16_dsx01_models/model_b.py')
kernel=_module('dsx_coherent_density_port',HERE.parent/'coherent_density/kernel.py')


def training_labels(context,policy):
    """Construct once, exclusively from scored raw winning TRAIN observations."""
    if not np.array_equal(context.model.mask,context.train_mask):
        raise ValueError('Model scoring and full-length TRAIN masks must agree')
    observations=tracklets.training_observations(context)
    scored=context.model.scored_observations
    for name in ['times_s','measured_hz','rf_hz','receiver','channel']:
        if not np.array_equal(getattr(observations,name),getattr(scored,name)):
            raise ValueError('Ordered raw TRAIN observations differ from model scoring')
    if policy=='independent':return np.arange(len(observations.times_s))
    if policy!='automatic':raise ValueError('Declared independent or automatic policy required')
    for receiver,channel in set(zip(observations.receiver,observations.channel)):
        lane=(observations.receiver==receiver)&(observations.channel==channel)
        if len(np.unique(observations.rf_hz[lane]))!=1:
            raise ValueError('Automatic RX/channel tracklets require a single actual RF per lane')
    return tracklets.build_tracklets(observations,gate_hz=450.,maximum_duration_s=45.,maximum_points=24)


class CoherentBandObjective(joint.JointBandObjective):
    """Identical physical/nuisance layout, bounds and priors; replace density only."""
    def __init__(self,joint_model,labels,*,eta=.10,epsilon=.12):
        if type(joint_model) is not joint.JointBandObjective:
            raise ValueError('Explicit complete joint-band model from this adapter port required')
        labels=np.asarray(labels)
        if labels.ndim!=1 or len(labels)!=len(joint_model.scored_observations.times_s):
            raise ValueError('One fixed partition label per scored TRAIN observation required')
        if not 0<eta<1 or not 0<epsilon<1:raise ValueError('Interior eta/epsilon required')
        self.__dict__.update(joint_model.__dict__)
        self.joint_model=joint_model;self.labels=labels.copy();self.labels.flags.writeable=False
        self.eta=float(eta);self.epsilon=float(epsilon)

    def evaluate_details(self,vector,nuisance):
        v=np.asarray(vector,float);old,band=self.unpack(nuisance)
        if v.shape!=(self.size,) or not np.isfinite(v).all():raise ValueError('Finite original physical vector required')
        raw,obs,mask=self.original,self.scored_observations,self.mask
        clock,group=raw.split(old[:self.base_nuisance_count]);tail=old[self.base_nuisance_count:]
        relative=self.basis@v[8:];tau=v[7]+relative
        prediction,hard,spatial,timing=predict_orbits(self.bank,obs,self.prior,v[:2],tau)
        sine,elevation_spatial,elevation_timing,cells=elevation_geometry(self.bank,obs,self.prior,v[:2],tau)
        weight,slope=horizon_weight(sine,self.visibility_width)
        correction=raw.design[mask]@v[2:7]+(raw.baseline+raw.group_design@group)[mask]+raw.clock_design[mask]@clock
        correction+=self.band_design[mask]@(band-self.original_offsets_hz)
        prediction+=correction[:,None]
        sigma,_,q,q_jacobian,intercept=self.frozen_model.hyperparameters(tail)
        result=kernel.coherent_terms(obs.measured_hz,prediction,weight,q,self.labels,
            sigma_hz=sigma,alias_hz=ALIAS_HZ,eta=self.eta,epsilon=self.epsilon)
        frequency=result.prediction_gradient;elevation_weight=result.visibility_gradient*slope
        shift=np.sum(frequency*timing+elevation_weight*elevation_timing,axis=0)
        gradient=np.zeros(self.size)
        gradient[:2]=np.einsum('nk,nki->i',frequency,spatial)+np.einsum('nk,nki->i',elevation_weight,elevation_spatial)
        row_gradient=frequency.sum(1)
        gradient[2:7]=raw.design[mask].T@row_gradient
        gradient[7]=shift.sum()+v[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift+relative/self.score.relative_sigma_s**2)
        clock_gradient=raw.clock_design[mask].T@row_gradient+raw.base.precision@clock
        group_gradient=raw.group_design[mask].T@row_gradient+raw.group_precision@group
        tail_gradient=q_jacobian.T@result.q_gradient+self.observation_precision*tail
        band_gradient=self.band_design[mask].T@row_gradient+band/50000.**2
        penalty=.5*(v[7]/self.score.common_sigma_s)**2+.5*np.sum((relative/self.score.relative_sigma_s)**2)
        penalty+=.5*float(clock@raw.base.precision@clock+group@raw.group_precision@group)
        penalty+=.5*float(tail@(self.observation_precision*tail))
        band_penalty=.5*float(band@band)/50000.**2
        terms=WindowLikelihood(result.nll,result.signal_responsibility,result.clutter_probability,
            result.prediction_gradient,result.residual_hz)
        details=dict(sigma_hz=sigma,detection_probability=q,budget_intercept=intercept,
            observation_parameters=tail,sine_elevation=sine,visibility_weight=weight,hard_visible=hard,
            elevation_spatial=elevation_spatial,elevation_timing=elevation_timing,interpolation_cells=cells,
            visibility_width=self.visibility_width,prior_penalty=float(penalty)+band_penalty,
            fixed_contrast_prior=0.,variable_band_prior=band_penalty,absolute_band_offsets_hz=band,
            original_band_offsets_hz=self.original_offsets_hz,band_receivers=self.band_receivers,
            prediction_hz=prediction,correction_hz=correction,group_nll=result.group_nll,
            group_labels=result.group_labels,group_index=result.group_index,group_posterior=result.group_posterior,
            coherent_terms=result,eta=self.eta,epsilon=self.epsilon,
            likelihood='Normalized fixed-partition coherent density; singleton control differs from original shared density')
        if len(result.group_nll)==len(obs.times_s):details['row_nll']=result.group_nll[result.group_index]
        return (result.nll+float(penalty)+band_penalty,gradient,
            np.r_[clock_gradient,group_gradient,tail_gradient,band_gradient],terms),details


def make_context(context,*,policy,eta=.10,epsilon=.12):
    """Convert original Shared context or this port's complete Joint context."""
    if type(context.model) is SharedScanObjective:base=joint.free_context(context)
    elif type(context.model) is joint.JointBandObjective:base=context
    else:raise ValueError('Original Shared context or this port Joint context required')
    labels=training_labels(base,policy)
    model=CoherentBandObjective(base.model,labels,eta=eta,epsilon=epsilon)
    full_joint=base.full_model
    if not full_joint.mask.all():
        frozen=full_joint.frozen_model
        shift=SequentialShift(full_joint.band_receivers,full_joint.original_offsets_hz)
        full_shared=SharedScanObjective(frozen.original,shift,
            mask=np.ones(len(frozen.observations.times_s),dtype=bool))
        full_shared.visibility_width=frozen.visibility_width
        if 'score' in frozen.__dict__:full_shared.score=frozen.score
        full_joint=joint.JointBandObjective(full_shared)
    full=CoherentBandObjective(full_joint,np.arange(len(full_joint.scored_observations.times_s)),eta=eta,epsilon=epsilon)
    return replace(base,model=model,full_model=full,vector=base.vector.copy(),nuisance=base.nuisance.copy())


def predict_coherent(context,vector,nuisance,metadata):
    """CFO-blind complete physical predictions; never construct held tracklets."""
    if type(context.model) is not CoherentBandObjective:raise ValueError('Explicit coherent model required')
    return joint.predict_joint(replace(context,model=context.model.joint_model),vector,nuisance,metadata)


def singleton_marginal(measured_hz,prediction,*,eta=.10,epsilon=.12):
    """Evaluation-only new-point forecast, with no held-CFO grouping."""
    count=len(np.asarray(measured_hz))
    return kernel.coherent_terms(measured_hz,prediction['prediction_hz'],prediction['visibility_weight'],
        prediction['detection_probability'],np.arange(count),sigma_hz=125.,alias_hz=ALIAS_HZ,eta=eta,epsilon=epsilon)


def classify(terms):
    """Point signal posterior versus total point clutter; no identity-truth claim."""
    signal=terms.signal_responsibility if hasattr(terms,'signal_responsibility') else terms.responsibilities
    best=np.argmax(signal,axis=1);rows=np.arange(len(best))
    return dict(best_index=best,associated=signal[rows,best]>terms.clutter_probability,
        residual_hz=terms.residual_hz[rows,best])


def group_summary(model):
    _,sizes=np.unique(model.labels,return_counts=True)
    return dict(observations=len(model.labels),groups=len(sizes),multi_point_groups=int((sizes>1).sum()),
        largest_group=int(sizes.max()),group_sizes=sizes.tolist(),eta=model.eta,epsilon=model.epsilon,
        assumption='Fixed TRAIN-selected partition working likelihood; no model for linking-selection event')
