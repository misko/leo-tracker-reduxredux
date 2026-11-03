"""Numerical control: same fixed-noise model, better converged latent precisions."""

import numpy as np
from dsx01_grouped_student import student_joint_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_window_noise import WindowNoise


class PreciseWindow(WindowNoise):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant != "window_precise":
            raise ValueError("unknown numerical precision control")
        super().__init__(scan, seed, fitted_c, variant="window_noise", **kwargs)

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        updated = student_joint_bound(
            self.values - self.q * result["intercept"],
            result["features"],
            self.point_noise,
            self.noise_groups,
            iterations=256,
        )
        updated["diagonal_logvolume"] = self.diagonal_logvolume
        updated["residual"] = np.r_[updated["residual"], np.sqrt(self.diagonal_logvolume)]
        result.update(updated)
        return result
