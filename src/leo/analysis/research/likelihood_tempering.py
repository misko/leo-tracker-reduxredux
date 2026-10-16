"""Observed native likelihood tempering, with unchanged physical priors.

This composite objective is not a normalized predictive density or a noise
estimate. Latent conditional probabilities are those of the original model.
"""

from dataclasses import replace

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.joint_association_sparse import SparseNativeJointObjective


class LikelihoodTemperedObjective:
    """Same lean parameters/frame; scale marginalized observation cost only."""

    def __init__(self, original, alpha):
        if isinstance(alpha, bool) or not np.isfinite(alpha) or not 0 < alpha <= 1:
            raise ValueError("Finite fixed likelihood alpha in (0,1] required")
        if (
            type(original) is not GroupCalibrationObjective
            or type(original.base) is not SparseNativeJointObjective
            or original.clock_count
            or original.drift_count
            or original.group_clock_count
            or original.group_count != original.offset_count
            or any(len(f) != 1 for f in original.base.families)
        ):
            raise ValueError("Original lean singleton native group model required")
        self.original_model, self.alpha = original, float(alpha)

    def __getattr__(self, name):
        return getattr(self.original_model, name)

    def prior_ledger(self, vector, nuisance):
        vector = np.asarray(vector, float)
        if vector.shape != (self.size,) or not np.isfinite(vector).all():
            raise ValueError("Original finite physical vector required")
        _, group = self.original_model.split(nuisance)
        relative = self.basis @ vector[8:]
        ledger = dict(
            common_timing=float(0.5 * (vector[7] / self.score.common_sigma_s) ** 2),
            relative_timing=float(0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)),
            group_calibration=float(0.5 * group @ self.group_precision @ group),
        )
        ledger["total"] = sum(ledger.values())
        gradient = np.zeros(self.size)
        gradient[7] = vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ relative / self.score.relative_sigma_s**2
        return ledger, gradient, self.group_precision @ group

    def evaluate_joint(self, vector, nuisance):
        value, gradient, extra, terms = self.original_model.evaluate_joint(vector, nuisance)
        ledger, prior_gradient, prior_extra = self.prior_ledger(vector, nuisance)
        # Algebraically alpha*L+P. alpha=1 runs this arithmetic too and closes
        # bit-for-bit with the original cost/gradients without cancellation.
        complement = 1 - self.alpha
        result = self.alpha * value + complement * ledger["total"]
        gradient = self.alpha * gradient + complement * prior_gradient
        extra = self.alpha * extra + complement * prior_extra
        terms = replace(
            terms,
            nll=self.alpha * terms.nll,
            prediction_gradient=self.alpha * terms.prediction_gradient,
        )
        return result, gradient, extra, terms
