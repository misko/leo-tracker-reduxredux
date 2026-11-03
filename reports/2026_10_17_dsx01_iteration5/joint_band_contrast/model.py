"""Private shared-q objective with absolute receiver high-band offsets free.

All original physical/clock/detectability coordinates remain unchanged. The
original frozen contrast contribution is replaced by its variable counterpart,
with exactly one prior on absolute offsets (sigma50000Hz).
"""
from dataclasses import replace
import numpy as np
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.sequential_group_calibration import SequentialShift,freeze_sequential_calibration
from leo.analysis.shared_scan_model import SharedScanObjective,density,elevation_geometry,horizon_weight


class JointBandObjective(SharedScanObjective):
    def __init__(self,frozen):
        if type(frozen) is not SharedScanObjective:raise ValueError('Explicit original shared-q model required')
        raw=frozen.original;obs=raw.observations
        receivers=tuple(map(int,np.unique(obs.receiver[obs.channel>=5])))
        offsets=np.array([raw.baseline[(obs.receiver==rx)&(obs.channel>=5)][0] for rx in receivers])
        shift=SequentialShift(receivers,offsets)
        np.testing.assert_allclose(shift.predict(obs.receiver,obs.channel>=5),raw.baseline,atol=1e-10,rtol=0)
        super().__init__(raw,shift,mask=frozen.mask)
        self.frozen_model=frozen
        if 'score' in frozen.__dict__:self.score=frozen.score
        self.visibility_width=frozen.visibility_width
        self.band_receivers=receivers;self.band_count=len(receivers)
        self.original_offsets_hz=offsets.copy();self.original_offsets_hz.setflags(write=False)
        self.original_nuisance_count=len(frozen.initial_nuisance)
        self.band_design=np.column_stack([(obs.receiver==rx)&(obs.channel>=5) for rx in receivers]).astype(float)
        self.band_design.setflags(write=False)
        self.group_count=frozen.group_count+self.band_count
        self.group_limits=np.r_[frozen.group_limits,np.full(self.band_count,ALIAS_HZ/2)]
        self.group_scales=np.r_[frozen.group_scales,np.full(self.band_count,5000.)]
        self.initial_nuisance=np.r_[frozen.initial_nuisance,offsets]
        self.group_precision=np.zeros((self.group_count,self.group_count))
        width=frozen.group_count;self.group_precision[:width,:width]=frozen.group_precision
        self.group_precision[width:,width:]=np.eye(self.band_count)/50000.**2
        self.precision=np.zeros((len(self.initial_nuisance),len(self.initial_nuisance)))
        width=self.original_nuisance_count;self.precision[:width,:width]=frozen.precision
        self.precision[width:,width:]=np.eye(self.band_count)/50000.**2
        self.original_fixed_contrast_prior_penalty=frozen.fixed_contrast_prior_penalty
        self.fixed_contrast_prior_penalty=0.  # Every contrast is now variable.

    def unpack(self,nuisance):
        n=np.asarray(nuisance,float)
        self.split(n)
        return n[:self.original_nuisance_count],n[self.original_nuisance_count:]

    def pack(self,nuisance,offsets=None):
        n=np.asarray(nuisance,float)
        if n.shape!=(self.original_nuisance_count,):raise ValueError('Original nuisance layout required')
        band=self.original_offsets_hz if offsets is None else np.asarray(offsets,float)
        if band.shape!=(self.band_count,):raise ValueError('One absolute band offset per receiver required')
        return np.r_[n,band]

    def hyperparameters(self,tail):
        a=np.asarray(tail,float);width=self.frozen_model.observation_parameter_count
        if a.shape==(width+self.band_count,):a=a[:width]
        if a.shape!=(width,):raise ValueError('Original detectability tail plus optional explicit bands required')
        return self.frozen_model.hyperparameters(a)

    def evaluate_details(self,vector,nuisance):
        v=np.asarray(vector,float);old,band=self.unpack(nuisance)
        if v.shape!=(self.size,) or not np.isfinite(v).all():raise ValueError('Finite original physical vector required')
        raw,obs,mask=self.original,self.scored_observations,self.mask
        clock,group=raw.split(old[:self.base_nuisance_count]);tail=old[self.base_nuisance_count:]
        relative=self.basis@v[8:];tau=v[7]+relative
        prediction,hard,spatial,timing=predict_orbits(self.bank,obs,self.prior,v[:2],tau)
        sine,elevation_spatial,elevation_timing,cells=elevation_geometry(self.bank,obs,self.prior,v[:2],tau)
        weight,slope=horizon_weight(sine,self.visibility_width)
        baseline=raw.baseline+raw.group_design@group
        correction=raw.design[mask]@v[2:7]+baseline[mask]+raw.clock_design[mask]@clock
        correction+=self.band_design[mask]@(band-self.original_offsets_hz)
        prediction+=correction[:,None]
        sigma,_,q,q_jacobian,intercept=self.frozen_model.hyperparameters(tail)
        terms,details=density(obs.measured_hz,prediction,weight,sigma,q,self.score)
        frequency=terms.prediction_gradient
        elevation_weight=details['visibility_weight_gradient']*slope
        shift=np.sum(frequency*timing+elevation_weight*elevation_timing,axis=0)
        gradient=np.zeros(self.size)
        gradient[:2]=np.einsum('nk,nki->i',frequency,spatial)+np.einsum('nk,nki->i',elevation_weight,elevation_spatial)
        row_gradient=frequency.sum(1)
        gradient[2:7]=raw.design[mask].T@row_gradient
        gradient[7]=shift.sum()+v[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift+relative/self.score.relative_sigma_s**2)
        clock_gradient=raw.clock_design[mask].T@row_gradient+raw.base.precision@clock
        group_gradient=raw.group_design[mask].T@row_gradient+raw.group_precision@group
        tail_gradient=q_jacobian.T@details['detection_probability_gradient']+self.observation_precision*tail
        band_gradient=self.band_design[mask].T@row_gradient+band/50000.**2
        penalty=.5*(v[7]/self.score.common_sigma_s)**2+.5*np.sum((relative/self.score.relative_sigma_s)**2)
        penalty+=.5*float(clock@raw.base.precision@clock+group@raw.group_precision@group)
        penalty+=.5*float(tail@(self.observation_precision*tail))
        band_penalty=.5*float(band@band)/50000.**2
        # Same float64 addition order as the frozen objective at original bands.
        objective=terms.nll+float(penalty)+band_penalty
        details.update(sigma_hz=sigma,detection_probability=q,budget_intercept=intercept,
            observation_parameters=tail,sine_elevation=sine,visibility_weight=weight,hard_visible=hard,
            elevation_spatial=elevation_spatial,elevation_timing=elevation_timing,interpolation_cells=cells,
            visibility_width=self.visibility_width,prior_penalty=float(penalty)+band_penalty,
            fixed_contrast_prior=0.,variable_band_prior=band_penalty,absolute_band_offsets_hz=band,
            original_band_offsets_hz=self.original_offsets_hz,band_receivers=self.band_receivers)
        return (objective,gradient,np.r_[clock_gradient,group_gradient,tail_gradient,band_gradient],terms),details


def free_context(context,offsets=None):
    model=JointBandObjective(context.model)
    full=model if context.full_model is context.model else JointBandObjective(context.full_model)
    nuisance=model.pack(context.nuisance,offsets)
    return replace(context,model=model,full_model=full,vector=context.vector.copy(),nuisance=nuisance)


def predict_joint(context,vector,nuisance,metadata):
    """Explicit metadata-only adapter retaining the complete learned band function."""
    model=context.model
    if type(model) is not JointBandObjective:raise ValueError('Explicit joint-band prediction adapter required')
    v=np.asarray(vector,float);old,band=model.unpack(nuisance)
    original_shift=SequentialShift(model.band_receivers,model.original_offsets_hz)
    frozen=freeze_sequential_calibration(model.original,
        dict(vector=v,nuisance=old[:model.base_nuisance_count]),original_shift)
    correction=frozen.predict(metadata.times_s,metadata.rf_hz,metadata.receiver,metadata.channel>=5)
    correction+=sum((metadata.receiver==rx)*(metadata.channel>=5)*(new-oldvalue)
        for rx,new,oldvalue in zip(model.band_receivers,band,model.original_offsets_hz))
    tau=v[7]+model.basis@v[8:]
    prediction=predict_orbits(context.bank,metadata,context.prior,v[:2],tau,derivatives=False)[0]+correction[:,None]
    visibility=horizon_weight(elevation_geometry(context.bank,metadata,context.prior,v[:2],tau)[0],model.visibility_width)[0]
    q=model.frozen_model.hyperparameters(old[model.base_nuisance_count:])[2]
    return dict(prediction_hz=prediction,visibility_weight=visibility,correction_hz=correction,
        detection_probability=q,number=context.bank.numbers.copy())
