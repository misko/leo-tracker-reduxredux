"""Joint point-noise likelihoods constrained by independent frame-timing links.

Timing agreement is source evidence, not proof that carrier clocks are equal.
Bias correlations and shared residual scales remain explicit model hypotheses.
Only original curved fragments enter calibration or create linked groups.
"""

import numpy as np
from dsx01_causal_correlation import CausalCorrelation
from dsx01_causal_forecast import CausalForecast
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_frame_bias import linked_tracks

from leo.analysis.research.orbit_uncertainty import paired_frequency_modes

VARIANTS = (
    "independent",
    "linked_700",
    "linked_300",
    "linked_100",
    "pooled_300",
    "trend_300",
    "history_300",
    "eccentric_300",
)


def linked_bias_covariance(count, groups, independent_sigma):
    if count < 1 or not np.isfinite(independent_sigma) or not 0 < independent_sigma <= 1000:
        raise ValueError("positive fragment count and independent sigma in (0,1000] required")
    result = np.eye(count)
    seen = set()
    for group in groups:
        group = list(group)
        if (
            len(group) < 2
            or len(set(group)) != len(group)
            or any(i < 0 or i >= count or i in seen for i in group)
        ):
            raise ValueError("disjoint groups with at least two valid unique fragments required")
        seen.update(group)
        rho = 1 - (independent_sigma / 1000) ** 2
        result[np.ix_(group, group)] = rho + (1 - rho) * np.eye(len(group))
    return result


def pooled_fragment_groups(count, groups):
    labels = np.arange(count)
    for group in groups:
        labels[group] = min(group)
    return np.unique(labels, return_inverse=True)[1]


class FrameJoint(CausalForecast):
    def __init__(self, scan, seed, fitted_c, *, variant, provided_links=None, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown frame-linked joint control")
        self.frame_variant = variant
        if variant in ("trend_300", "history_300"):
            CausalForecast.__init__(
                self,
                scan,
                seed,
                fitted_c,
                variant="full_trend" if variant == "trend_300" else "full_history",
                **kwargs,
            )
        else:
            CausalCorrelation.__init__(
                self,
                scan,
                seed,
                fitted_c,
                variant="diag_6" if variant == "eccentric_300" else "diag_4",
                **kwargs,
            )
            self.prior_mean = np.zeros(self.transform.shape[0])
            self.forecast_variant, self.forecast_metadata = None, {}
            self.history_selection = None
        if provided_links is None:
            original_groups, self.frame_link_metadata = linked_tracks(scan, seed)
        else:
            original_groups, self.frame_link_metadata = provided_links, {}
        member_index = {i: k for k, i in enumerate(self.members)}
        self.frame_groups = [[member_index[i] for i in group] for group in original_groups]
        self.independent_bias_sigma = (
            1000.0
            if variant == "independent"
            else float(variant.split("_")[-1])
            if variant.startswith("linked_")
            else 300.0
        )
        self.bias_correlation = linked_bias_covariance(
            len(self.members), self.frame_groups, self.independent_bias_sigma
        )
        stop = len(self.transform) - len(self.members)
        self.transform[stop:, stop:] = np.linalg.cholesky(self.bias_correlation)
        inverse = np.linalg.solve(self.transform, np.eye(len(self.transform)))
        self.prior_precision = inverse.T @ inverse
        self.fragment_noise_groups = (
            pooled_fragment_groups(len(self.members), self.frame_groups)
            if variant == "pooled_300"
            else np.arange(len(self.members))
        )
        self.noise_groups = np.concatenate(
            [
                np.full(sl.stop - sl.start, self.fragment_noise_groups[k], dtype=int)
                for k, sl in enumerate(self.slices)
            ]
        )

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        if self.ecc_bank is not None:
            modes = paired_frequency_modes(
                self.sky,
                self.ecc_bank,
                self.flat_times,
                self.flat_labels,
                self.reference,
                *latlon(x[:2]),
            )
            extra = np.zeros((len(self.values), 2 * len(self.supported)))
            for k, j in enumerate(self.supported_local):
                use = self.flat_labels == j
                extra[use, 2 * k : 2 * k + 2] = self.q[use, None] * modes[use]
            end = features.shape[1] - len(self.members)
            features = np.column_stack((features[:, :end], extra, features[:, end:]))
        latent_features = features @ self.transform
        raw = self.values - self.q * result["intercept"] - features @ self.prior_mean
        bound = hierarchical_bound(raw, latent_features, self.point_noise, self.noise_groups)
        latent = bound["coefficient"].copy()
        bound["coefficient"] = self.prior_mean + self.transform @ latent
        bound["latent_coefficient"] = latent
        bound["coefficient_prior_precision"] = self.prior_precision
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        result.update(bound, features=features, latent_features=latent_features)
        return result

    def diagnostics(self, x):
        result = CausalCorrelation.diagnostics(self, x)
        result.update(
            frame_joint_variant=self.frame_variant,
            independent_linked_bias_sigma_hz=self.independent_bias_sigma,
            all_native_curve_bias_marginal_variances_hz2=1000000.0,
            linked_curved_groups=[
                [self.scan.tracks[self.members[k]]["key"] for k in group]
                for group in self.frame_groups
            ],
            frame_link_metadata=self.frame_link_metadata,
            fragment_noise_groups=self.fragment_noise_groups,
            prior_mean=self.prior_mean,
            causal_forecast_variant=self.forecast_variant,
            causal_forecast=self.forecast_metadata,
            history_selection=self.history_selection,
            frame_timing_does_not_prove_carrier_clock_equality=True,
        )
        return result
