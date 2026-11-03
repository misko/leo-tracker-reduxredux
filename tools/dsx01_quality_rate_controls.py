"""Evidence-based calibration weights and small shared satellite rate controls."""

import hashlib
import json

import numpy as np
from compare_dsx01_retention_localization import ROOT
from dsx01_joint_marginal import JointMarginal
from dsx01_satellite_prior_controls import SatellitePriorControls

QUALITY = (
    ROOT / "reports/2026_10_18_dsx01_satellite_prior_controls/conditional_smooth_background.json"
)
VARIANTS = ("quality", "rate_0p25", "rate_1", "quality_rate_1")


def rate_columns(labels, q, times, supported, sigma):
    j, scale, t = np.asarray(labels), np.asarray(q, float), np.asarray(times, float)
    if (
        j.shape != t.shape
        or scale.shape != t.shape
        or t.ndim != 1
        or not np.isfinite(t).all()
        or not np.isfinite(scale).all()
        or not np.isfinite(sigma)
        or sigma <= 0
    ):
        raise ValueError("matching finite times, RF scales and positive rate sigma required")
    return (
        np.column_stack([(j == k) * scale * sigma * (t - 150) for k in supported])
        if len(supported)
        else np.empty((len(t), 0))
    )


def reliability_weights(probabilities):
    p = np.asarray(probabilities, float)
    if p.ndim != 1 or not np.isfinite(p).all() or np.any(p < 0) or np.any(p > 1):
        raise ValueError(
            "one finite conditional evidence probability in [0,1] per fragment required"
        )
    return np.maximum(0.01, p)


class QualityRateControls(SatellitePriorControls):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown evidence/rate control")
        super().__init__(scan, seed, fitted_c, variant="normal", **kwargs)
        self.hypothesis = variant
        self.rate_sigma = 0.25 if variant == "rate_0p25" else 1.0 if "rate" in variant else 0
        if self.rate_sigma:
            self.clock = rate_columns(
                self.flat_labels,
                self.q,
                self.flat_times,
                self.supported_local,
                self.rate_sigma,
            )
        self.quality_sha256 = None
        if variant.startswith("quality"):
            if not hasattr(scan, "fixed_conditional_quality"):
                scan.fixed_conditional_quality = json.loads(QUALITY.read_text())[scan.case]
                scan.fixed_conditional_quality_sha256 = hashlib.sha256(
                    QUALITY.read_bytes()
                ).hexdigest()
            by_component = {
                r["component"]: r["conditional_signal_probability"]
                for r in scan.fixed_conditional_quality
            }
            if set(by_component) != {r["component"] for r in self.rows}:
                raise ValueError(
                    "quality evidence must cover exactly the unchanged curved population"
                )
            self.power = reliability_weights([by_component[r["component"]] for r in self.rows])
            self.quality_sha256 = scan.fixed_conditional_quality_sha256
        self.point_power = self.power[self.noise_groups]
        self.diagonal_logvolume = float(
            2 * np.sum(self.point_power * np.log(self.point_noise / 40))
        )

    def state(self, x):
        # The extra columns are rates, so do not decode them as clock offsets.
        result = JointMarginal.state(self, x)
        if self.rate_sigma:
            a = self.calculate(x)["coefficient"]
            begin = len(a) - len(self.members) - len(self.supported)
            result["satellite_frequency_rates_hz_s"] = dict(
                zip(
                    self.supported,
                    a[begin : begin + len(self.supported)] * self.rate_sigma,
                    strict=True,
                )
            )
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            satellite_rate_sigma_hz_s=self.rate_sigma,
            covariance_clock_columns=0,
            covariance_rate_columns=self.clock.shape[1],
            quality_evidence_sha256=self.quality_sha256,
            calibration_reliability_floor=0.01,
            quality_weights_frozen_from_normal_c0_endpoint=True,
            quality_weights_are_not_final_association_probabilities=True,
            powers_are_generalized_scores_not_sampling_probabilities=self.hypothesis.startswith(
                "quality"
            ),
        )
        return result
