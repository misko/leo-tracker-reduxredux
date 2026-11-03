"""Normalized latent GLRT-peak likelihood, one contribution per probe group.

Research-only subclass; original physical model, q budget, bounds and priors.
Uniform peak priors are independent of measured CFO and GLRT score magnitude.
"""
import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import WindowLikelihood
from leo.analysis.shared_scan_model import (
    SharedScanObjective, density, elevation_geometry, horizon_weight,
)


def normalized_rows(row_nll, group):
    """Return group -log mean density and per-peak conditional probabilities."""
    rows=np.asarray(row_nll,float);group=np.asarray(group,int)
    if rows.ndim!=1 or group.shape!=rows.shape or not len(rows) or np.any(group<0):
        raise ValueError('Aligned nonempty rows and nonnegative group IDs required')
    count=np.bincount(group)
    if np.any(count==0) or not np.isfinite(rows).all():
        raise ValueError('Contiguous groups and finite row likelihoods required')
    if np.all(count==1):
        # Preserve the original float64 path exactly in the singleton model.
        return rows[np.argsort(group)].copy(),np.ones(len(rows)),count
    log_terms=-rows-np.log(count[group])
    maximum=np.full(len(count),-np.inf)
    np.maximum.at(maximum,group,log_terms)
    mass=np.exp(log_terms-maximum[group])
    total=np.bincount(group,weights=mass,minlength=len(count))
    return -(maximum+np.log(total)),mass/total[group],count


def mixture_density(measured,prediction,visibility,sigma,q,score,group):
    """Reweight both terms of the original normalized singleton density gradient."""
    terms,details=density(measured,prediction,visibility,sigma,q,score)
    rows,posterior,count=normalized_rows(details['row_nll'],group)
    if np.all(count==1):
        details.update(group_nll=rows,peak_posterior=posterior,group_peak_count=count,
            group_responsibilities=terms.responsibilities[np.argsort(group)],
            group_clutter_probability=terms.clutter_probability[np.argsort(group)])
        return terms,details
    # Original weight derivative = q * d(row_nll)/d(p). This retains the
    # selected-singleton normalizer term, including zero-signal candidates.
    q_gradient=np.sum((details['visibility_weight_gradient']/q[None,:]) *
                      visibility * posterior[:,None],axis=0)
    visibility_gradient=details['visibility_weight_gradient']*posterior[:,None]
    joint_responsibility=terms.responsibilities*posterior[:,None]
    joint_clutter=terms.clutter_probability*posterior
    group_responsibility=np.column_stack([np.bincount(group,weights=joint_responsibility[:,k],
        minlength=len(count)) for k in range(prediction.shape[1])])
    group_clutter=np.bincount(group,weights=joint_clutter,minlength=len(count))
    mixed=WindowLikelihood(float(rows.sum()),joint_responsibility,joint_clutter,
        terms.prediction_gradient*posterior[:,None],terms.residual_hz)
    details.update(group_nll=rows,peak_posterior=posterior,group_peak_count=count,
        group_responsibilities=group_responsibility,group_clutter_probability=group_clutter,
        detection_probability_gradient=q_gradient,visibility_weight_gradient=visibility_gradient)
    return mixed,details


class PeakMixtureObjective(SharedScanObjective):
    """Original shared physics with a normalized latent observed-peak choice."""
    def __init__(self,original,shift,group,mask=None):
        super().__init__(original,shift,mask=mask)
        full=np.asarray(group)
        if full.dtype.kind not in 'iu' or full.shape!=self.mask.shape or np.any(full<0):
            raise ValueError('One nonnegative integer group ID per peak required')
        _,labels=np.unique(full,return_inverse=True)
        total=np.bincount(labels);trained=np.bincount(labels[self.mask],minlength=len(total))
        if np.any((trained!=0)&(trained!=total)):
            raise ValueError('Training masks must include or exclude complete probe groups')
        self.peak_group_full=labels.copy()
        self.peak_group_full.setflags(write=False)
        _,self.peak_group=np.unique(labels[self.mask],return_inverse=True)
        self.peak_group.setflags(write=False)

    def evaluate_details(self,vector,nuisance):
        # This is the audited SmoothVisibilityModel body, with only its density
        # aggregation changed. Physical prior and fixed-contrast penalty appear once.
        v,n=np.asarray(vector,float),np.asarray(nuisance,float)
        self.split(n)
        if v.shape!=(self.size,) or not np.isfinite(v).all():
            raise ValueError('Original finite physical vector required')
        base,obs,mask=self.original,self.scored_observations,self.mask
        clock,group=base.split(n[:self.base_nuisance_count])
        tail=n[self.base_nuisance_count:]
        relative=self.basis@v[8:];shifts=v[7]+relative
        prediction,hard_visible,spatial,timing=predict_orbits(self.bank,obs,self.prior,v[:2],shifts)
        sine,elevation_spatial,elevation_timing,cells=elevation_geometry(self.bank,obs,self.prior,v[:2],shifts)
        weight,slope=horizon_weight(sine,self.visibility_width)
        baseline=base.baseline+base.group_design@group
        correction=base.design[mask]@v[2:7]+baseline[mask]+base.clock_design[mask]@clock
        prediction+=correction[:,None]
        sigma,_,q,q_jacobian,intercept=self.hyperparameters(tail)
        terms,details=mixture_density(obs.measured_hz,prediction,weight,sigma,q,self.score,self.peak_group)
        frequency_weight=terms.prediction_gradient
        elevation_weight=details['visibility_weight_gradient']*slope
        shift=np.sum(frequency_weight*timing+elevation_weight*elevation_timing,axis=0)
        gradient=np.zeros(self.size)
        gradient[:2]=np.einsum('nk,nki->i',frequency_weight,spatial)+np.einsum('nk,nki->i',elevation_weight,elevation_spatial)
        gradient[2:7]=base.design[mask].T@frequency_weight.sum(axis=1)
        gradient[7]=shift.sum()+v[7]/self.score.common_sigma_s**2
        gradient[8:]=self.basis.T@(shift+relative/self.score.relative_sigma_s**2)
        clock_gradient=base.clock_design[mask].T@frequency_weight.sum(axis=1)+base.base.precision@clock
        group_gradient=base.group_design[mask].T@frequency_weight.sum(axis=1)+base.group_precision@group
        tail_gradient=q_jacobian.T@details['detection_probability_gradient']+self.observation_precision*tail
        penalty=.5*(v[7]/self.score.common_sigma_s)**2
        penalty+=.5*np.sum((relative/self.score.relative_sigma_s)**2)
        penalty+=.5*float(clock@base.base.precision@clock+group@base.group_precision@group)
        penalty+=.5*float(tail@(self.observation_precision*tail))
        fixed=self.fixed_contrast_prior_penalty
        details.update(sigma_hz=sigma,detection_probability=q,budget_intercept=intercept,
            observation_parameters=tail,sine_elevation=sine,visibility_weight=weight,
            hard_visible=hard_visible,elevation_spatial=elevation_spatial,
            elevation_timing=elevation_timing,interpolation_cells=cells,
            visibility_width=self.visibility_width,prior_penalty=float(penalty)+fixed,
            fixed_contrast_prior=fixed,normalized_uniform_peak_prior=True)
        return (terms.nll+float(penalty)+fixed,gradient,
                np.r_[clock_gradient,group_gradient,tail_gradient],terms),details
