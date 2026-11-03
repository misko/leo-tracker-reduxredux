"""Variational Student noise with jointly integrated Gaussian nuisance modes.

One positive latent precision per original curved fragment. Every observation
remains in the objective; no satellite label or point is removed by this model.
"""

import numpy as np
from dsx01_joint_marginal import JointMarginal, integrated_gaussian


def student_joint_bound(raw, features, sigma, groups, *, nu=4.0, iterations=24):
    """Coordinate-ascent Gaussian/Gamma bound to a shared-nuisance evidence.

    Cost is -2 ELBO relative to independent Student densities at zero. This is
    an upper bound to negative twice the exact integrated log likelihood, not
    an exactly marginalized Student likelihood. Posterior covariance enters
    precision updates; fitting residuals alone would overstate reliability.
    """
    y, u, g = np.asarray(raw, float), np.asarray(features, float), np.asarray(groups)
    if g.shape != y.shape or not np.issubdtype(g.dtype, np.integer) or np.any(g < 0):
        raise ValueError("one nonnegative integer noise group per observation required")
    if not np.isfinite(nu) or nu <= 0 or iterations < 1:
        raise ValueError("positive Student degrees of freedom and iteration budget required")
    _, g = np.unique(g, return_inverse=True)
    counts = np.bincount(g)
    alpha, b0 = (nu + counts) / 2, nu / 2
    rate = alpha.copy()  # Initial precision one for every fragment.
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    history = []
    for _ in range(iterations):
        weight = alpha / rate
        result = integrated_gaussian(y, u, s / np.sqrt(weight[g]))
        a = u * np.sqrt(weight[g, None]) / s[:, None]
        root = np.linalg.cholesky(np.eye(u.shape[1]) + a.T @ a)
        posterior_features = np.linalg.solve(root, u.T / s[None, :])
        variance = np.sum(posterior_features**2, axis=0)
        energy = (result["conditional_residual_hz"] / s) ** 2 + variance
        updated = (nu + np.bincount(g, weights=energy)) / 2
        change = float(np.max(abs(np.log(updated / rate))))
        rate = updated
        history.append(change)
        if change < 1e-5:
            break
    weight = alpha / rate
    result = integrated_gaussian(y, u, s / np.sqrt(weight[g]))
    ratio = rate / b0
    gamma_cost = np.maximum(0.0, 2 * alpha * (np.log(ratio) + 1 / ratio - 1))
    result["residual"] = np.r_[result["residual"], np.sqrt(gamma_cost)]
    result.update(
        noise_precision=weight,
        gamma_cost=float(gamma_cost.sum()),
        precision_iterations=len(history),
        final_log_precision_change=history[-1],
    )
    return result


class RobustJoint(JointMarginal):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant != "robust":
            raise ValueError("robust joint control requires robust variant")
        super().__init__(scan, seed, fitted_c, variant="radio_noise", **kwargs)
        self.noise_groups = np.concatenate(
            [np.full(sl.stop - sl.start, k, dtype=int) for k, sl in enumerate(self.slices)]
        )

    def calculate(self, x):
        result = super().calculate(x)
        robust = student_joint_bound(
            self.values - self.q * result["intercept"],
            result["features"],
            self.sigma,
            self.noise_groups,
        )
        result.update(robust)
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        robust = self.calculate(x)
        result.update(
            {
                k: robust[k]
                for k in (
                    "noise_precision",
                    "gamma_cost",
                    "precision_iterations",
                    "final_log_precision_change",
                )
            }
        )
        return result
