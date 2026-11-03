"""Native-Hz LNB drift versus fractional RF-dependent nonlinear drift."""

import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_window_noise import WindowNoise
from report_dsx01_joint_marginal import EvaluationAdapter

from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

VARIANTS = ("native_rx", "native_band", "mixed_rx")


def smooth_columns(times, receiver, band, q, kind):
    t, rx, b, rf = (np.asarray(v) for v in (times, receiver, band, q))
    if (
        kind not in VARIANTS
        or t.ndim != 1
        or any(v.shape != t.shape for v in (rx, b, rf))
        or not np.isfinite(t).all()
        or not np.isfinite(rf).all()
        or np.any(rf <= 0)
        or np.any((rx != 1) & (rx != 2))
        or np.any((b != 0) & (b != 1))
    ):
        raise ValueError("matching valid RX/band/time/RF arrays and known drift model required")
    basis = projected_receiver_basis(t)
    width = basis.shape[1]
    result = np.zeros((len(t), width * (2 if kind == "native_rx" else 4)))
    for k in range(len(t)):
        group = 2 * (rx[k] - 1) + b[k] if kind == "native_band" else rx[k] - 1
        if kind == "mixed_rx":
            start = group * 2 * width
            result[k, start : start + width] = basis[k] / np.sqrt(2)
            result[k, start + width : start + 2 * width] = rf[k] * basis[k] / np.sqrt(2)
        else:
            result[k, group * width : (group + 1) * width] = basis[k]
    return result


class NativeDrift(WindowNoise):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown native drift covariance")
        self.hypothesis = variant
        super().__init__(scan, seed, fitted_c, variant="window_noise", **kwargs)
        receiver = np.concatenate(
            [
                np.full(sl.stop - sl.start, scan.tracks[i]["receiver"], int)
                for i, sl in zip(self.members, self.slices, strict=True)
            ]
        )
        band = np.concatenate(
            [
                np.full(sl.stop - sl.start, int(scan.tracks[i]["channel"] > 4), int)
                for i, sl in zip(self.members, self.slices, strict=True)
            ]
        )
        self.smooth = smooth_columns(self.flat_times, receiver, band, self.q, variant)

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        bound = hierarchical_bound(
            self.values - self.q * result["intercept"],
            result["features"],
            self.point_noise,
            self.noise_groups,
        )
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        result.update(bound)
        return result

    def nonlinear_radio_mean(self, x):
        a = self.calculate(x)["coefficient"]
        nb, ns = self.hardware.shape[1], self.smooth.shape[1]
        return self.smooth @ (200 * a[nb : nb + ns])

    def state(self, x):
        result = super().state(x)
        result["smooth_design_kind"] = self.hypothesis
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        bound = self.calculate(x)
        result.update(
            smooth_design_kind=self.hypothesis,
            nonlinear_radio_columns=self.smooth.shape[1],
            **{
                k: bound[k]
                for k in (
                    "coefficient_prior_precision",
                    "noise_gamma_cost",
                    "prior_gamma_cost",
                    "normalization_constant",
                    "full_objective_offset",
                    "negative_twice_elbo",
                    "effective_observations",
                    "prior_group_precision",
                )
            },
        )
        return result


class NativeDriftEvaluation(EvaluationAdapter):
    """Adapt the existing residual gates without assuming RF-scaled radio drift."""

    def association_state(self, x):
        result = super().association_state(x)
        # Only the compatibility adapter uses zeros: the complete native radio
        # prediction is added below. The persisted model state stays truthful.
        result["smooth"] = np.zeros((2, self.problem.scan.rx_basis[0].shape[1]))
        return result

    def predicted(self, x):
        frequency, elevation = self.problem.conditional_frequency(x)
        return frequency + self.problem.nonlinear_radio_mean(x) / self.problem.q, elevation
