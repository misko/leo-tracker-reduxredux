"""Uniform nuisance-prior and point-contamination controls; pure array kernels.

No evaluation position, storage reader or satellite selection enters this file.
The Gaussian mixtures express declared core/tail hypotheses, not calibrated
empirical probabilities about DSX01 hardware or catalog errors.
"""

import numpy as np
from dsx01_warm_initialization import restore_radio_initialization
from prototype_dsx01_pair_difference import PairDifferenceFamilies
from prototype_s01_receiver_drift import ReceiverDriftProblem

MODES = ("tight_causal", "wide_causal", "sparse_drift", "sparse_both", "point_mixture")


def mixture_cost(values, narrow, broad, probability):
    x, a, b = np.broadcast_arrays(values, narrow, broad)
    if not np.isfinite([probability]).all() or not 0 <= probability <= 1:
        raise ValueError("probability must lie in [0,1]")
    if (
        not np.isfinite(x).all()
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
        or np.any(a <= 0)
        or np.any(b <= 0)
    ):
        raise ValueError("finite values and positive component scales required")
    if probability == 1:
        return (x / a) ** 2
    if probability == 0:
        return (x / b) ** 2
    small = np.log(probability) - np.log(a)
    large = np.log1p(-probability) - np.log(b)
    peak = np.logaddexp(small, large)
    actual = np.logaddexp(small - 0.5 * (x / a) ** 2, large - 0.5 * (x / b) ** 2)
    return np.maximum(0, 2 * (peak - actual))


def grouped_mixture_profile(
    values,
    design,
    groups,
    count,
    *,
    narrow=150.0,
    broad=5000.0,
    probability=0.98,
    bias_sigma=1000.0,
    iterations=12,
):
    """EM-like profiling of source constants; every point retains a likelihood.

    A broad Gaussian models contamination, so no observation is deleted. Two
    deterministic bias starts are compared per group; global profiling is not
    guaranteed for this nonconvex mixture.
    """
    y, c, g = np.asarray(values), np.asarray(design), np.asarray(groups, dtype=int)
    if (
        y.ndim != 1
        or c.shape != y.shape
        or g.shape != y.shape
        or not len(y)
        or np.any(g < 0)
        or np.any(g >= count)
    ):
        raise ValueError("matching nonempty grouped coordinates required")
    denominator = np.bincount(g, weights=c * c, minlength=count) + narrow**2 / bias_sigma**2
    initial = np.bincount(g, weights=c * y, minlength=count) / denominator
    solutions = []
    for beta in [initial, np.zeros(count)]:
        for _ in range(iterations):
            r = y - c * beta[g]
            small = np.log(probability / narrow) - 0.5 * (r / narrow) ** 2
            large = np.log((1 - probability) / broad) - 0.5 * (r / broad) ** 2
            gamma = np.exp(small - np.logaddexp(small, large))
            precision = gamma / narrow**2 + (1 - gamma) / broad**2
            beta = np.bincount(g, weights=precision * c * y, minlength=count) / (
                np.bincount(g, weights=precision * c * c, minlength=count) + 1 / bias_sigma**2
            )
        cost = mixture_cost(y - c * beta[g], narrow, broad, probability)
        group_cost = np.bincount(g, weights=cost, minlength=count) + (beta / bias_sigma) ** 2
        solutions.append((beta, cost, group_cost))
    beta = np.where(solutions[0][2] <= solutions[1][2], solutions[0][0], solutions[1][0])
    residual = y - c * beta[g]
    cost = mixture_cost(residual, narrow, broad, probability)
    small = np.log(probability / narrow) - 0.5 * (residual / narrow) ** 2
    large = np.log((1 - probability) / broad) - 0.5 * (residual / broad) ** 2
    gamma = np.exp(small - np.logaddexp(small, large))
    return dict(bias=beta, cost=cost, signal_probability=gamma, residual_hz=residual)


class PointMixtureFamilies(PairDifferenceFamilies):
    """Same pair transform, with per-point Gaussian signal/contamination modes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        left = []
        right = []
        factor = []
        groups = []
        difference_left = []
        difference_right = []
        for group, (positions, a, b, _) in enumerate(self.pair_groups):
            unpaired = np.setdiff1d(np.arange(len(positions)), np.r_[a, b])
            left.extend(positions[unpaired])
            right.extend([-1] * len(unpaired))
            factor.extend([1.0] * len(unpaired))
            left.extend(positions[a])
            right.extend(positions[b])
            factor.extend([1 / np.sqrt(2)] * len(a))
            groups.extend([group] * (len(unpaired) + len(a)))
            difference_left.extend(positions[a])
            difference_right.extend(positions[b])
        self.common_left = np.array(left)
        self.common_right = np.array(right)
        self.common_factor = np.array(factor)
        self.common_groups = np.array(groups, dtype=int)
        self.difference_left = np.array(difference_left, dtype=int)
        self.difference_right = np.array(difference_right, dtype=int)
        self.group_count = len(self.pair_groups)
        self.group_weights = np.minimum(1, 50 / np.bincount(self.common_groups))
        self.constant_design = np.where(self.common_right >= 0, np.sqrt(2), 1.0)
        self.flat_values = np.empty(len(self.flat_times))
        self.flat_rf = np.empty(len(self.flat_times))
        self.hardware_design = np.empty((len(self.flat_times), len(self.starts["beta"])))
        self.smooth_design = np.zeros((len(self.flat_times), self.starts["smooth"].size))
        width = self.starts["smooth"].shape[1]
        for i, sl, alias in zip(self.members, self.slices, self.alias, strict=True):
            t = self.scan.tracks[i]
            q = t["rf_hz"] / 11.5e9
            self.flat_values[sl] = t["values"] + alias / 4.4e-6
            self.flat_rf[sl] = q
            self.hardware_design[sl] = np.column_stack(
                [self.scan.hardware(t, unit) for unit in np.eye(len(self.starts["beta"]))]
            )
            begin = (t["receiver"] - 1) * width
            self.smooth_design[sl, begin : begin + width] = q * self.scan.rx_basis[i]

    def residual(self, x, *, details=False):
        state = self.decode(x)
        f, e = self.predicted(x)
        # Aliases may be locked after construction by a caller; refresh only
        # their constant lift, keeping the original observations untouched.
        values = np.concatenate(
            [
                self.scan.tracks[i]["values"] + a / 4.4e-6
                for i, a in zip(self.members, self.alias, strict=True)
            ]
        )
        raw = values - self.hardware_design @ state["beta"] - self.flat_rf * f
        if self.method == "receiver_smooth":
            raw -= self.smooth_design @ state["smooth"].ravel()
        common = (
            raw[self.common_left]
            + np.where(self.common_right >= 0, raw[np.maximum(self.common_right, 0)], 0)
        ) * self.common_factor
        result = grouped_mixture_profile(
            common, self.constant_design, self.common_groups, self.group_count
        )
        weights = np.sqrt(self.group_weights[self.common_groups])
        z = np.sign(result["residual_hz"]) * np.sqrt(result["cost"]) * weights
        diff = (raw[self.difference_left] - raw[self.difference_right]) / (np.sqrt(2) * 150)
        residuals = [
            np.maximum(0, -e) / 2,
            z,
            result["bias"] / 1000 * np.sqrt(self.group_weights),
            np.sign(diff) * np.sqrt(np.where(abs(diff) <= 3, diff * diff, 6 * abs(diff) - 9)),
            state["beta"][4:8] / 75,
            state["phases"][self.labels]
            / np.maximum(0.1, self.scan.sky["phase_sigma_s"][self.labels]),
        ]
        if self.method == "receiver_smooth":
            residuals.append(state["smooth"].ravel() / 200)
        r = np.concatenate(residuals)
        return (
            (
                r,
                [
                    dict(
                        self.pair_metadata,
                        mean_signal_probability=float(np.mean(result["signal_probability"])),
                    )
                ],
            )
            if details
            else r
        )


class SparsePriors:
    def __init__(self, problem, *, phase_mixture):
        self.problem = problem
        self.phase_mixture = phase_mixture

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def residual(self, x, *, details=False):
        result = self.problem.residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        state = self.problem.decode(x)
        tail = len(self.labels) + (state["smooth"].size if self.method == "receiver_smooth" else 0)
        start = len(r) - tail - 4
        rates = np.array(
            [
                (state["beta"][4] + state["beta"][5]) / 300,
                (state["beta"][6] + state["beta"][7]) / 300,
            ]
        )
        r[start + np.array([0, 2])] = np.sign(rates) * np.sqrt(mixture_cost(rates, 0.5, 10.0, 0.9))
        if self.phase_mixture:
            phase = state["phases"][self.labels]
            sigma = np.maximum(0.1, self.scan.sky["phase_sigma_s"][self.labels])
            r[start + 4 : start + 4 + len(self.labels)] = np.sign(phase) * np.sqrt(
                mixture_cost(phase, sigma, np.maximum(3.0, 3 * sigma), 0.9)
            )
        return (r, diagnostics) if details else r


def transfer_problem(*args, pairs, mode):
    if mode not in MODES:
        raise ValueError("unknown uniform prior mode")
    cls = PointMixtureFamilies if mode == "point_mixture" else PairDifferenceFamilies
    problem = cls(*args, provided_pairs=pairs, phase_mode="causal", use_pairs=True)
    if mode == "tight_causal":
        return problem
    problem = restore_radio_initialization(ReceiverDriftProblem(problem, mean_sigma=10))
    return (
        SparsePriors(problem, phase_mixture=mode in ("sparse_both", "point_mixture"))
        if mode.startswith("sparse_") or mode == "point_mixture"
        else problem
    )
