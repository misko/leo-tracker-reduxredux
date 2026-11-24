"""Differentiate the executed dense Gamma recurrence in two input directions."""

from collections import Counter
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns

import numpy as np


RELEASE = "c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e"


def instrument(original):
    file = Path(original.__code__.co_filename)
    if sha256(file.read_bytes()).hexdigest() != RELEASE:
        raise ValueError("Expected the released dense Gamma recurrence")
    source = getsource(original)
    taps = {
        "def hierarchical_bound(\n": "def observed_bound(\n    observer,\n",
        "    history = []\n": "    observer.prepare(locals())\n    history = []\n",
        "            return mean, cov, None\n": (
            "            observer.posterior(weight, mean, cov)\n"
            "            return mean, cov, None\n"
        ),
        "        return mean, cov, max(0.0, logdet - np.log(precision).sum())\n": (
            "        observer.last(weight, precision, mean, lu, pivots, logdet)\n"
            "        return mean, cov, max(0.0, logdet - np.log(precision).sum())\n"
        ),
        "        rate, prior_rate = next_rate, next_prior_rate\n": (
            "        observer.advance(native, variance, next_rate, next_prior_rate, change)\n"
            "        rate, prior_rate = next_rate, next_prior_rate\n"
        ),
        "    return dict(\n": "    observer.finish(locals())\n    return dict(\n",
    }
    if any(source.count(anchor) != 1 for anchor in taps):
        raise ValueError("Original posterior or update boundary changed")
    for anchor, content in taps.items():
        source = source.replace(anchor, content)
    scope = dict(original.__globals__)
    exec(compile(source, str(file), "exec"), scope)
    return scope["observed_bound"]


def derivative_matrices(state, ddesign, dresponse):
    """Differentiate the ordered sparse Gram and RHS before the rate loop."""
    matrices, sides = [], []
    for group, (columns, _, _, _) in enumerate(state["blocks"]):
        keep = state["g"] == group
        u = state["a"][keep][:, columns]
        du = ddesign[:, keep][:, :, columns]
        y, dy = state["r"][keep], dresponse[:, keep]
        ij = np.swapaxes(du, 1, 2) @ u
        matrices.append((ij + np.swapaxes(ij, 1, 2)).reshape(2, -1))
        sides.append((du.transpose(0, 2, 1) @ y) + dy @ u)
    return np.concatenate(matrices, axis=1), np.concatenate(sides, axis=1)


def sqrt_derivative(primal, tangent):
    """Same active piece of the released clipped-square-root residual."""
    return np.divide(tangent, 2 * np.sqrt(np.maximum(0, primal)), out=np.zeros_like(tangent),
                     where=np.asarray(primal) > 0)


class Forward:
    def __init__(self, dy, du):
        self.dy, self.du = dy, du
        self.counts = Counter()
        self.change = []

    @property
    def derivative_ns(self):
        return sum(v for key, v in self.counts.items() if key.endswith("_ns"))

    def prepare(self, state):
        start = process_time_ns()
        if not state["width"] or self.du.shape != (2, *state["u"].shape) or self.dy.shape != (2, *state["y"].shape):
            raise ValueError("Expected two directions matching original observations and columns")
        if np.any((state["u"] == 0) & (self.du != 0)):
            raise ValueError("A tangent must respect the captured symbolic support")
        self.state = state
        self.rate, self.prior_rate = state["rate"], state["prior_rate"]
        self.drate = np.zeros((2, len(self.rate)))
        self.dprior_rate = np.zeros((2, len(self.prior_rate)))
        self.dnormalized_y = self.dy / state["s"]
        self.dnormalized_u = self.du / state["s"][None, :, None]
        self.dmatrices, self.drhs = derivative_matrices(state, self.dnormalized_u, self.dnormalized_y)
        self.counts["prepare_ns"] += process_time_ns() - start

    def sensitivities(self, weight, mean, covariance):
        start = process_time_ns()
        s = self.state
        self.dweight = -(weight / self.rate) * self.drate
        prior_precision = s["pa"] / self.prior_rate
        self.dprior_precision = -(prior_precision / self.prior_rate) * self.dprior_rate
        self.dprecision = np.zeros((2, s["width"]))
        selected = s["selected"]
        self.dprecision[:, selected] = self.dprior_precision[:, s["prior"][selected]]
        dgram = np.stack([np.diag(row) for row in self.dprecision])
        drhs = np.zeros_like(self.dprecision)
        w = s["power"] * weight
        dw = s["power"] * self.dweight
        mg, rg = s["matrix_groups"], s["rhs_groups"]
        for axis in range(2):
            np.add.at(dgram[axis].ravel(), s["matrix_indices"],
                      dw[axis, mg] * s["matrices"] + w[mg] * self.dmatrices[axis])
            np.add.at(drhs[axis], s["rhs_indices"],
                      dw[axis, rg] * s["right_sides"] + w[rg] * self.drhs[axis])
        self.dmean = (drhs - dgram @ mean) @ covariance.T
        self.dnative = self.dnormalized_y - self.dnormalized_u @ mean - self.dmean @ s["a"].T
        self.counts["mean_and_gram_ns"] += process_time_ns() - start
        return dgram

    def posterior(self, weight, mean, covariance):
        dgram = self.sensitivities(weight, mean, covariance)
        start = process_time_ns()
        self.dcovariance = -(covariance @ dgram @ covariance)
        self.counts["covariance_products_ns"] += process_time_ns() - start
        self.counts["covariance_products"] += 4
        self.counts["updates"] += 1
        self.mean, self.covariance = mean, covariance

    def advance(self, native, variance, next_rate, next_prior_rate, change):
        start = process_time_ns()
        s = self.state
        width = s["width"]
        dvariance = np.zeros((2, len(self.rate)))
        selected = s["selected"]
        dprior_energy = (2 * self.mean * self.dmean + self.dcovariance.diagonal(axis1=1, axis2=2))[:, selected]
        matrix_index = s["matrix_indices"]
        for axis in range(2):
            matrix_term = (self.dcovariance[axis].reshape(width*width)[matrix_index] * s["matrices"]
                           + self.covariance.ravel()[matrix_index] * self.dmatrices[axis])
            dvariance[axis] = np.bincount(s["matrix_groups"], weights=matrix_term, minlength=len(variance))
            energy = np.bincount(s["g"], weights=2 * native * self.dnative[axis])
            self.drate[axis] = s["power"] * (energy + (variance > 0) * dvariance[axis]) / 2
            self.dprior_rate[axis] = np.bincount(s["prior"][selected], weights=dprior_energy[axis],
                                                minlength=len(self.prior_rate)) / 2
        self.change.append(change)
        self.min_variance = min(getattr(self, "min_variance", float("inf")), float(np.min(abs(variance))))
        self.rate, self.prior_rate = next_rate, next_prior_rate
        self.counts["rate_update_ns"] += process_time_ns() - start

    def last(self, weight, precision, mean, lu, pivots, logdet):
        from scipy.linalg.lapack import dgetrs

        start = process_time_ns()
        inverse_root, status = dgetrs(lu, pivots, self.state["identity"])
        if status:
            raise np.linalg.LinAlgError("Original final factor did not admit a derivative solve")
        covariance = inverse_root.T @ inverse_root
        self.counts["extra_final_covariance_ns"] += process_time_ns() - start
        dgram = self.sensitivities(weight, mean, covariance)
        start = process_time_ns()
        raw_volume = logdet - np.log(precision).sum()
        self.dvolume = (np.sum(dgram * covariance, axis=(1, 2)) - np.sum(self.dprecision / precision, axis=1))
        self.dvolume *= raw_volume > 0
        self.counts["logdet_ns"] += process_time_ns() - start

    def finish(self, d):
        start = process_time_ns()
        rate, weight, v, groups = (d[key] for key in ("rate", "weight", "v", "g"))
        if not np.array_equal(rate, self.rate) or not np.array_equal(v, self.state["pa"] / self.prior_rate):
            raise ValueError("Observer rate sequence disagrees with the executed primal recurrence")
        native_sensitivity = self.dnative * np.sqrt((d["power"] * weight)[groups])
        dinnovation = native_sensitivity + d["innovation"] * self.dweight[:, groups] / (2 * weight[groups])
        dcoefficient = self.dmean * np.sqrt(d["precision"]) + d["coefficient"] * sqrt_derivative(d["precision"], self.dprecision)
        dnoise_gamma = (2 * d["alpha"] * (1 / rate - d["beta0"] / rate**2)) * self.drate
        dprior_gamma = (2 * d["pa0"] * (1. / d["v0"] - 1. / v)) * self.dprior_precision
        self.jacobian = np.concatenate((dinnovation, dcoefficient, sqrt_derivative(d["volume"], self.dvolume)[:, None],
                                        sqrt_derivative(d["noise_gamma"], dnoise_gamma),
                                        sqrt_derivative(d["prior_gamma"], dprior_gamma)), axis=1).T
        self.counts["residual_readout_ns"] += process_time_ns() - start
