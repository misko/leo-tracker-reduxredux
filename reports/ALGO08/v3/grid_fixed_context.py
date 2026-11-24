"""Keep fixed selected-likelihood scaffolding for one serial standard grid."""

from collections import Counter
from hashlib import sha256
from inspect import getsource

import numpy as np


def curved_factory(original, expected, select=None):
    """Compile the checked ordinary arithmetic with fixed retained row inputs."""
    source = getsource(original)
    if sha256(source.encode()).hexdigest() != expected:
        raise ValueError("Unreviewed curved selected likelihood")
    first = "    def calculate(x):\n"
    replacements = {
        first: """    scale = np.ones(width)
    scale[-len(p.members) :] = 0.3
    row_sigma = p.point_noise[keep]
    row_groups = p.noise_groups[keep]
    present = np.unique(row_groups)
    active_powers = weights[present]
    volume = np.sqrt(float(2 * np.sum(weights[row_groups] * np.log(row_sigma / 40))))

""" + first,
        "        scale = np.ones(width)\n        scale[-len(p.members) :] = 0.3\n": "",
        "        present = np.unique(p.noise_groups[keep])\n": "",
        "            p.point_noise[keep],\n            p.noise_groups[keep],\n"
        "            powers=weights[present],\n":
        "            row_sigma,\n            row_groups,\n            powers=active_powers,\n",
        "        volume = float(2 * np.sum(weights[p.noise_groups[keep]] * np.log(p.point_noise[keep] / 40)))\n"
        "        bound[\"residual\"] = np.r_[bound[\"residual\"], np.sqrt(volume)]\n":
        "        bound[\"residual\"] = np.r_[bound[\"residual\"], volume]\n",
    }
    if select is not None:
        replacements["(features * scale)[keep]"] = "_select(features, scale, keep)"
    for anchor, changed in replacements.items():
        if source.count(anchor) != 1:
            raise ValueError("Unexpected fixed curved input boundary")
        source = source.replace(anchor, changed)
    namespace = dict(original.__globals__, _select=select)
    exec(compile(source, original.__code__.co_filename, "exec"), namespace)
    return namespace[original.__name__]


class PredictiveWorkspace:
    """Private scratch arrays for one immutable predictive design topology."""

    def __init__(self, sigma, groups, width, member_count):
        if (type(sigma) is not np.ndarray or type(groups) is not np.ndarray
                or sigma.dtype != np.dtype(float) or sigma.ndim != 1
                or not len(sigma) or groups.shape != sigma.shape
                or not np.issubdtype(groups.dtype, np.integer) or np.any(groups < 0)
                or not (0 < member_count <= width) or not np.isfinite(sigma).all()
                or np.any(sigma <= 0)):
            raise ValueError("Incompatible fixed predictive Gaussian inputs")
        self.sigma = sigma.copy()
        self.groups = groups
        self.scales = np.ones(width)
        self.scales[-member_count:] = 0.3
        self.member_count = member_count
        self.weight = 1. / sigma
        self.normalization = float(np.sum(np.log(2 * np.pi) + 2 * np.log(sigma)))
        biases = np.zeros((len(sigma), int(groups.max()) + 1))
        biases[np.arange(len(sigma)), groups] = 300.
        self.design = np.empty((len(sigma), width + biases.shape[1]))
        self.design[:, width:] = biases
        self.weighted = np.empty_like(self.design)
        self.weighted[:, width:] = biases * self.weight[:, None]
        self.prior = np.ones(self.design.shape[1])
        self.diagonal = np.diag(self.prior)

    @property
    def bytes(self):
        return sum(value.nbytes for name, value in vars(self).items()
                   if isinstance(value, np.ndarray) and name != "groups")

    def evaluate(self, whiten, raw, design, capture):
        if (type(raw) is not np.ndarray or raw.dtype != np.dtype(float)
                or raw.shape != self.sigma.shape
                or design.shape != (len(raw), capture.width) or not np.isfinite(raw).all()):
            raise ValueError("Incompatible dynamic predictive Gaussian inputs")
        uncertainty = whiten(design, capture.lower, capture.order, self.scales)
        if not np.isfinite(uncertainty).all():
            raise ValueError("Nonfinite predictive uncertainty")
        self.design[:, :capture.width] = uncertainty
        np.multiply(uncertainty, self.weight[:, None], out=self.weighted[:, :capture.width])
        a, b = self.weighted, raw * self.weight
        root = np.linalg.cholesky(self.diagonal + a.T @ a)
        coefficient = np.linalg.solve(root.T, np.linalg.solve(root, a.T @ b))
        innovation = (raw - self.design @ coefficient) * self.weight
        # The proper predictive prior has unit precision and volume weight.
        # The diagonal, log-prior sum (zero), and ridge scales (one) are fixed.
        volume = max(0., float(2 * np.log(np.diag(root)).sum()))
        quadratic = float(innovation @ innovation + coefficient @ coefficient)
        objective = quadratic + volume + self.normalization
        return dict(coefficient=coefficient, residual=np.r_[innovation, coefficient, np.sqrt(volume)],
                    quadratic=quadratic, logvolume=volume, normalization_constant=self.normalization,
                    objective=objective, coefficient_prior_precision=self.prior.copy(),
                    objective_kind="conditional_Gaussian_marginal", is_generalized_evidence=False,
                    negative_twice_elbo=objective)


class PredictiveByView:
    """Install within one grid, with the stock Gaussian fallback intact."""

    def __init__(self, ordinary, whiten):
        self.ordinary = ordinary
        self.whiten = whiten
        self.views = {}
        self.counts = Counter()

    def __call__(self, raw, design, sigma, groups, capture, member_count):
        key = id(groups), capture.width, member_count
        try:
            workspace = self.views.get(key)
            if workspace is None:
                workspace = PredictiveWorkspace(sigma, groups, capture.width, member_count)
                self.views[key] = workspace
                self.counts["prepared_views"] += 1
                self.counts["scratch_bytes"] += workspace.bytes
            elif not np.array_equal(sigma, workspace.sigma):
                raise ValueError("The fixed predictive noise changed")
            result = workspace.evaluate(self.whiten, raw, design, capture)
        except (ValueError, ArithmeticError, np.linalg.LinAlgError):
            self.counts["original_calls"] += 1
            return self.ordinary(raw, design, sigma, groups, capture, member_count)
        self.counts["prepared_calls"] += 1
        return result
