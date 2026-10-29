"""Satellite clock covariance, robust orbital priors and family influence controls."""

import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_window_noise import WindowNoise

VARIANTS = (
    "normal",
    "clock_shared",
    "clock_variance",
    "tail_4",
    "tail_8",
    "balance_100",
    "balance_50",
)


def clock_design(labels, rf_hz, supported, *, shared_sigma, reference_hz, preserve_variance):
    j, rf = np.asarray(labels), np.asarray(rf_hz, float)
    if (
        j.ndim != 1
        or rf.shape != j.shape
        or not np.isfinite(rf).all()
        or np.any(rf <= 0)
        or shared_sigma <= 0
        or reference_hz <= 0
        or len(set(supported)) != len(supported)
    ):
        raise ValueError("matching labels/RF and positive unique clock coordinates required")
    columns = (
        np.column_stack([(j == k) * shared_sigma * rf / reference_hz for k in supported])
        if len(supported)
        else np.empty((len(j), 0))
    )
    variance = np.full(len(j), 1000.0**2)
    if preserve_variance:
        variance -= np.sum(columns**2, axis=1)
    if np.any(variance <= 0):
        raise ValueError("shared clock exceeds the original marginal variance budget")
    return columns, np.sqrt(variance)


def family_powers(labels, noise_groups, cap):
    j, g = np.asarray(labels), np.asarray(noise_groups)
    if j.shape != g.shape or j.ndim != 1 or not len(j) or cap <= 0:
        raise ValueError("matching nonempty family/group identities and positive cap required")
    result = np.ones(int(g.max()) + 1)
    for k in np.unique(g):
        family = np.unique(j[g == k])
        if len(family) != 1:
            raise ValueError("a fragment noise group cannot contain several satellite labels")
        result[k] = min(1.0, cap / np.count_nonzero(j == family[0]))
    return result


def orbital_prior_groups(width, phase_start, labels, supported_local):
    result = np.full(width, -1, dtype=int)
    result[phase_start : phase_start + len(labels)] = np.arange(len(labels))
    start = phase_start + len(labels)
    for k, j in enumerate(supported_local):
        result[start + 3 * k : start + 3 * k + 3] = j
    return result


class SatellitePriorControls(WindowNoise):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown satellite-prior control")
        self.hypothesis = variant
        super().__init__(scan, seed, fitted_c, variant="window_noise", **kwargs)
        self.clock = np.empty((len(self.flat_times), 0))
        self.clock_reference_scale_hz = 0.0
        if variant.startswith("clock_"):
            preserve = variant == "clock_variance"
            reference = 12.5e9 if preserve else 11.5e9
            shared_sigma = np.sqrt(0.9) * 1000 if preserve else 3000.0
            self.clock, independent = clock_design(
                self.flat_labels,
                self.q * 11.5e9,
                self.supported_local,
                shared_sigma=shared_sigma,
                reference_hz=reference,
                preserve_variance=preserve,
            )
            self.clock_reference_scale_hz = shared_sigma * 11.5e9 / reference
            for k, sl in enumerate(self.slices):
                self.constants[sl, k] = independent[sl]
        self.power = (
            family_powers(self.flat_labels, self.noise_groups, float(variant.split("_")[-1]))
            if variant.startswith("balance_")
            else np.ones(len(self.slices))
        )
        self.point_power = self.power[self.noise_groups]
        self.diagonal_logvolume = float(
            2 * np.sum(self.point_power * np.log(self.point_noise / 40))
        )

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        stop = features.shape[1] - len(self.members)
        features = np.column_stack((features[:, :stop], self.clock, features[:, stop:]))
        prior = None
        if self.hypothesis.startswith("tail_"):
            prior = orbital_prior_groups(
                features.shape[1],
                self.hardware.shape[1] + self.smooth.shape[1],
                self.labels,
                self.supported_local,
            )
        bound = hierarchical_bound(
            self.values - self.q * result["intercept"],
            features,
            self.point_noise,
            self.noise_groups,
            prior_groups=prior,
            powers=self.power,
            prior_nu=float(self.hypothesis.split("_")[-1]) if prior is not None else 4,
        )
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        result.update(bound, features=features)
        return result

    def conditional_frequency(self, x):
        result = self.calculate(x)
        start = self.hardware.shape[1] + self.smooth.shape[1]
        stop = result["features"].shape[1] - len(self.members)
        frequency = (
            result["intercept"]
            + result["features"][:, start:stop] @ result["coefficient"][start:stop] / self.q
        )
        return frequency, result["elevation"]

    def state(self, x):
        result = super().state(x)
        if self.clock.shape[1]:
            a = self.calculate(x)["coefficient"]
            begin = len(a) - len(self.members) - self.clock.shape[1]
            result["satellite_clock_reference_hz"] = dict(
                zip(
                    self.supported,
                    a[begin : begin + self.clock.shape[1]] * self.clock_reference_scale_hz,
                    strict=True,
                )
            )
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        bound = self.calculate(x)
        result.update(
            satellite_prior_variant=self.hypothesis,
            likelihood_power_by_fragment=self.power,
            covariance_clock_columns=self.clock.shape[1],
            shared_clock_reference_scale_hz=self.clock_reference_scale_hz,
            **{
                k: bound[k]
                for k in (
                    "coefficient_prior_precision",
                    "prior_group_precision",
                    "noise_gamma_cost",
                    "prior_gamma_cost",
                    "normalization_constant",
                    "negative_twice_elbo",
                    "full_objective_offset",
                    "effective_observations",
                )
            },
            powers_are_generalized_scores_not_sampling_probabilities=self.hypothesis.startswith(
                "balance_"
            ),
        )
        return result
