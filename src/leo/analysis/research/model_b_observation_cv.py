"""Fixed-geography B likelihood arms using only the declared fold's measured values."""

from dataclasses import replace

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective, fit_group_calibration
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.regional_position_score import zero_sum_basis
from leo.analysis.research import model_b_conditional_cfo as density

ARMS = ["legacy", "conditional", "dispersion", "detectability"]
DISPERSION_PRIOR_SIGMA = .25
DETECTABILITY_PRIOR_SIGMA = 1.


def subset(obs, mask):
    return replace(obs, window_ids=tuple(k for k, keep in zip(obs.window_ids, mask, strict=True)
                                        if keep),
        **{name: getattr(obs, name)[mask] for name in
           ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")})


class ObservationModel:
    """Private source-fitter tail adapter; extra fields are NOT physical group clocks."""

    def __init__(self, original, mask, arm):
        if (not isinstance(original, GroupCalibrationObjective)
                or type(original.base) is not JointClockObjective
                or original.base.likelihood_port is not likelihood
                or original.drift_count or original.group_clock_count
                or original.score.sigma_hz != 125 or arm not in ARMS):
            raise ValueError("Original fitted-c B and one declared observation arm required")
        mask = np.asarray(mask)
        if (mask.dtype != bool or mask.shape != original.observations.times_s.shape
                or not mask.any() or not set(original.observations.channel) <= set(range(1, 9))):
            raise ValueError("Nonempty boolean training mask and eight-channel IDs required")
        self.original, self.mask, self.arm = original, mask.copy(), arm
        self.mask.setflags(write=False)
        # Full original metadata/domain remain fixed; no excluded measurement values enter evaluate.
        self.scored_observations = subset(original.observations, mask)
        self.base_nuisance_count = len(original.initial_nuisance)
        self.catalogue_basis = zero_sum_basis(len(original.bank.numbers))
        self.channel_basis = zero_sum_basis(8)
        if arm == "dispersion":
            limits = np.r_[np.full(2, np.log(2)/2), np.full(7,
                np.log(2)/(2*np.abs(self.channel_basis).sum(axis=1).max()))]
            prior_sigma, scale = DISPERSION_PRIOR_SIGMA, .2
        elif arm == "detectability":
            limits = np.full(len(original.bank.numbers)-1, 2.)
            prior_sigma, scale = DETECTABILITY_PRIOR_SIGMA, .5
        else:
            limits, prior_sigma, scale = np.empty(0), 1., 1.
        self.observation_parameter_count = len(limits)
        self.observation_precision = np.full(len(limits), 1/prior_sigma**2)
        self.group_count = original.group_count+len(limits)
        self.group_limits = np.r_[original.group_limits, limits]
        self.group_scales = np.r_[original.group_scales, np.full(len(limits), scale)]
        self.group_precision = np.zeros((self.group_count, self.group_count))
        width = original.group_count
        self.group_precision[:width, :width] = original.group_precision
        self.group_precision[original.group_count:, original.group_count:] = np.diag(
            self.observation_precision)
        self.initial_nuisance = np.r_[original.initial_nuisance, np.zeros(len(limits))]
        self.precision = np.zeros((len(self.initial_nuisance), len(self.initial_nuisance)))
        self.precision[:self.base_nuisance_count, :self.base_nuisance_count] = original.precision
        self.precision[self.base_nuisance_count:, self.base_nuisance_count:] = np.diag(
            self.observation_precision)

    def __getattr__(self, name):
        if name == "original":
            raise AttributeError(name)
        return getattr(self.original, name)

    def split(self, nuisance):
        n = np.asarray(nuisance, float)
        if n.shape != self.initial_nuisance.shape or not np.isfinite(n).all():
            raise ValueError("Finite original nuisance plus declared observation tail required")
        return n[:self.clock_count], n[self.clock_count:]

    def hyperparameters(self, tail):
        obs = self.scored_observations
        sigma = np.full(len(obs.window_ids), 125.)
        sigma_design = np.empty((len(sigma), 0))
        q = np.full(len(self.bank.numbers), self.score.detection_budget/len(self.bank.numbers))
        q_jacobian, intercept = np.empty((len(q), 0)), None
        if self.arm == "dispersion":
            sigma_design = np.column_stack(((obs.receiver == 0), (obs.receiver == 1),
                                           self.channel_basis[obs.channel-1]))
            sigma *= np.exp(sigma_design@tail)
        elif self.arm == "detectability":
            q, q_jacobian, intercept = density.detection_probabilities(
                self.catalogue_basis, tail, self.score.detection_budget)
        return sigma, sigma_design, q, q_jacobian, intercept

    def evaluate_details(self, vector, nuisance):
        v, n = np.asarray(vector, float), np.asarray(nuisance, float)
        self.split(n)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError("Original finite physical B vector required")
        base = self.original
        clock, group = base.split(n[:self.base_nuisance_count])
        tail = n[self.base_nuisance_count:]
        obs, mask = self.scored_observations, self.mask
        relative = self.basis@v[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, obs, self.prior, v[:2], v[7]+relative)
        baseline = base.baseline+base.group_design@group
        correction = base.design[mask]@v[2:7]+baseline[mask]+base.clock_design[mask]@clock
        prediction += correction[:, None]
        sigma, sigma_design, q, q_jacobian, intercept = self.hyperparameters(tail)
        terms, details = density.score(obs.measured_hz, prediction, visible, sigma, q, self.score,
                                        conditional=self.arm != "legacy")
        weight = terms.prediction_gradient
        shift = np.sum(weight*timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("mk,mki->i", weight, spatial)
        gradient[2:7] = base.design[mask].T@weight.sum(axis=1)
        gradient[7] = shift.sum()+v[7]/self.score.common_sigma_s**2
        gradient[8:] = self.basis.T@(shift+relative/self.score.relative_sigma_s**2)
        clock_gradient = base.clock_design[mask].T@weight.sum(axis=1)+base.base.precision@clock
        group_gradient = base.group_design[mask].T@weight.sum(axis=1)+base.group_precision@group
        if self.arm == "dispersion":
            tail_gradient = sigma_design.T@details["sigma_log_gradient"]
        elif self.arm == "detectability":
            tail_gradient = q_jacobian.T@details["detection_probability_gradient"]
        else:
            tail_gradient = np.empty(0)
        tail_gradient += self.observation_precision*tail
        penalty = .5*(v[7]/self.score.common_sigma_s)**2
        penalty += .5*np.sum((relative/self.score.relative_sigma_s)**2)
        penalty += .5*float(clock@base.base.precision@clock+group@base.group_precision@group)
        penalty += .5*float(tail@(self.observation_precision*tail))
        details.update(sigma_hz=sigma, detection_probability=q,
                       budget_intercept=intercept, observation_parameters=tail)
        return (terms.nll+float(penalty), gradient,
                np.r_[clock_gradient, group_gradient, tail_gradient], terms), details

    def evaluate_joint(self, vector, nuisance):
        return self.evaluate_details(vector, nuisance)[0]


def fit(model, vector, nuisance, **options):
    """Reuse the original solver while explicitly labelling observation-only private tails."""
    result = fit_group_calibration(model, vector, nuisance, **options)
    original = model.original
    n = np.asarray(result["nuisance"])
    group = n[original.clock_count:model.base_nuisance_count]
    tail = n[model.base_nuisance_count:]
    result["source_fitter_tail_metadata"] = dict(
        generic_group_clock_coefficients=result["group_clock_coefficients"],
        generic_group_prior_penalty=result["group_prior_penalty"])
    result["group_clock_coefficients"] = np.empty(0)
    result["group_prior_penalty"] = .5*float(group@original.group_precision@group)
    result["observation_parameters"] = tail.copy()
    result["observation_prior_penalty"] = .5*float(tail@(model.observation_precision*tail))
    result["observation_arm"] = model.arm
    return result
