"""Direct Gaussian prior-strength controls for the measured regularization bias."""

import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_window_noise import WindowNoise

VARIANTS = ("phase_3", "bias_5", "phase_bias", "weak_3")


def scale_bound(raw, features, noise, groups, scales):
    scale = np.asarray(scales, float)
    u = np.asarray(features, float)
    if scale.shape != (u.shape[1],) or not np.isfinite(scale).all() or np.any(scale <= 0):
        raise ValueError("one finite positive covariance scale per nuisance mode required")
    result = hierarchical_bound(raw, u * scale, noise, groups)
    # Decode in the original physical coordinates; keep the optimized residual
    # vector in the correctly normalized coordinates of the scaled prior.
    result["coefficient"] *= scale
    result["coefficient_prior_precision"] /= scale**2
    return result


class PriorScaleControls(WindowNoise):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown Gaussian prior-strength control")
        self.hypothesis = variant
        super().__init__(scan, seed, fitted_c, variant="window_noise", **kwargs)

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        width = result["features"].shape[1]
        scale = np.ones(width)
        nb, ns = self.hardware.shape[1], self.smooth.shape[1]
        phase = slice(nb + ns, nb + ns + len(self.labels))
        if self.hypothesis in ("phase_3", "phase_bias", "weak_3"):
            scale[phase] = 3
        if self.hypothesis in ("bias_5", "phase_bias", "weak_3"):
            scale[-len(self.members) :] = 5
        if self.hypothesis == "weak_3":
            scale[nb : nb + ns] = 3
            scale[nb + ns + len(self.labels) : -len(self.members)] = 3
        bound = scale_bound(
            self.values - self.q * result["intercept"],
            result["features"],
            self.point_noise,
            self.noise_groups,
            scale,
        )
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        bound["prior_covariance_scales"] = scale
        result.update(bound)
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        bound = self.calculate(x)
        result.update(
            Gaussian_prior_scale_variant=self.hypothesis,
            phase_prior_sigma_multiplier=(
                3 if self.hypothesis in ("phase_3", "phase_bias", "weak_3") else 1
            ),
            fragment_constant_sigma_hz=(1000 if self.hypothesis == "phase_3" else 5000),
            rx_smooth_sigma_hz=(600 if self.hypothesis == "weak_3" else 200),
            physical_prior_sigma_multiplier=(3 if self.hypothesis == "weak_3" else 1),
            **{
                key: bound[key]
                for key in (
                    "coefficient_prior_precision",
                    "prior_covariance_scales",
                    "normalization_constant",
                    "negative_twice_elbo",
                    "full_objective_offset",
                    "effective_observations",
                    "noise_gamma_cost",
                    "prior_gamma_cost",
                )
            },
        )
        return result
