"""Band-specific bounded detectability with a nested shared-plus-contrast prior.

Each effective band's coefficients retain the original [-2,2] domain. The
full-training band fraction is fixed across observation masks. No geography,
calibration, satellite timing, horizon width or detection budget is changed.
"""

import model_a_smooth_visibility_v2 as smooth
import numpy as np

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.regional_position_score import WindowLikelihood
from leo.analysis.research.model_b_observation_cv import ObservationModel


def contrast_precision(dimension, high_fraction):
    if dimension < 1 or not 0 < high_fraction < 1:
        raise ValueError("Positive contrast dimension and both training bands required")
    low_fraction = 1-high_fraction
    matrix = np.array([[low_fraction**2+1, low_fraction*high_fraction-1],
                       [low_fraction*high_fraction-1, high_fraction**2+1]])
    return np.kron(matrix, np.eye(dimension))


class BandDetectabilityModel(ObservationModel):
    def __init__(self, original, mask, *, width=smooth.DEFAULT_WIDTH):
        super().__init__(original, mask, "detectability")
        self.arm = "band-detectability"
        self.visibility_width = float(width)
        self.band_dimension = len(original.bank.numbers)-1
        channel = original.observations.channel
        self.high_fraction = float(np.mean(channel >= 5))
        self.observation_precision = contrast_precision(self.band_dimension, self.high_fraction)
        self.observation_parameter_count = 2*self.band_dimension
        self.group_count = original.group_count+self.observation_parameter_count
        self.group_limits = np.r_[original.group_limits,
                                  np.full(self.observation_parameter_count,2.)]
        self.group_scales = np.r_[original.group_scales,
                                  np.full(self.observation_parameter_count,.5)]
        self.group_precision = np.zeros((self.group_count,self.group_count))
        g = original.group_count
        self.group_precision[:g,:g] = original.group_precision
        self.group_precision[g:,g:] = self.observation_precision
        m = self.base_nuisance_count
        self.initial_nuisance = np.r_[original.initial_nuisance,
                                      np.zeros(self.observation_parameter_count)]
        self.precision = np.zeros((len(self.initial_nuisance),)*2)
        self.precision[:m,:m] = original.precision
        self.precision[m:,m:] = self.observation_precision
        self.children = {}
        for index, band in enumerate((channel <= 4, channel >= 5)):
            selected = self.mask & band
            if selected.any():
                self.children[index] = (smooth.SmoothVisibilityModel(original,selected,width=width),
                                        band[self.mask])

    def expand_shared(self, nuisance):
        n = np.asarray(nuisance,float)
        expected = self.base_nuisance_count+self.band_dimension
        if n.shape != (expected,) or not np.isfinite(n).all():
            raise ValueError("Finite original shared-detectability state required")
        return np.r_[n,n[self.base_nuisance_count:]]

    def evaluate_details(self, vector, nuisance):
        v,n = np.asarray(vector,float),np.asarray(nuisance,float)
        self.split(n)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError("Finite original physical state required")
        m,d = self.base_nuisance_count,self.band_dimension
        relative = self.basis@v[8:]
        pg = np.zeros_like(v)
        pg[7] = v[7]/self.score.common_sigma_s**2
        pg[8:] = self.basis.T@relative/self.score.relative_sigma_s**2
        physical_prior = .5*(v[7]/self.score.common_sigma_s)**2
        physical_prior += .5*np.sum((relative/self.score.relative_sigma_s)**2)
        original_prior_gradient = self.original.precision@n[:m]
        prior = physical_prior+.5*float(n@self.precision@n)
        gradient, extra = pg.copy(), self.precision@n
        shape = (int(self.mask.sum()),len(self.bank.numbers))
        posterior, prediction_gradient, residual = (np.zeros(shape) for _ in range(3))
        clutter, row_nll = np.zeros(shape[0]), np.zeros(shape[0])
        details, nll = {}, 0.
        for index,(child,positions) in self.children.items():
            sl = slice(m+index*d,m+(index+1)*d)
            theta = n[sl]
            child_nuisance = np.r_[n[:m],theta]
            e,cd = child.evaluate_details(v,child_nuisance)
            gradient += e[1]-pg
            extra[:m] += e[2][:m]-original_prior_gradient
            extra[sl] += e[2][m:]-child.observation_precision*theta
            nll += e[3].nll
            posterior[positions] = e[3].responsibilities
            prediction_gradient[positions] = e[3].prediction_gradient
            residual[positions] = e[3].residual_hz
            clutter[positions] = e[3].clutter_probability
            row_nll[positions] = cd["row_nll"]
            details[str(index)] = dict(detection_probability=cd["detection_probability"],
                budget_intercept=cd["budget_intercept"],
                transition_pairs=int(np.sum((cd["visibility_weight"] > 0)
                                            & (cd["visibility_weight"] < 1))))
        low,high = n[m:m+d],n[m+d:]
        shared = (1-self.high_fraction)*low+self.high_fraction*high
        contrast = high-low
        terms = WindowLikelihood(float(nll),posterior,clutter,prediction_gradient,residual)
        return (float(nll+prior),gradient,extra,terms),dict(bands=details,row_nll=row_nll,
            shared_parameters=shared,contrast_parameters=contrast,prior_penalty=prior,
            shared_prior=.5*float(shared@shared),contrast_prior=.5*float(contrast@contrast))


def fit(model, vector, nuisance, **options):
    """Original constrained fitter with explicit non-diagonal observation-prior metadata."""
    result = fit_group_calibration(model,vector,nuisance,**options)
    n = np.asarray(result["nuisance"])
    original = model.original
    group = n[model.clock_count:model.base_nuisance_count]
    tail = n[model.base_nuisance_count:]
    result["source_fitter_tail_metadata"] = dict(
        generic_group_clock_coefficients=result["group_clock_coefficients"],
        generic_group_prior_penalty=result["group_prior_penalty"])
    result["group_clock_coefficients"] = np.empty(0)
    result["group_prior_penalty"] = .5*float(group@original.group_precision@group)
    result["observation_parameters"] = tail.copy()
    result["observation_prior_penalty"] = .5*float(tail@model.observation_precision@tail)
    result["observation_arm"] = model.arm
    return result
