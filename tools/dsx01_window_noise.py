"""Fixed radio-only per-observation noise in the robust joint likelihood."""

import hashlib
import json

import numpy as np
from dsx01_joint_marginal import JointMarginal
from dsx01_robust_joint import RobustJoint, student_joint_bound
from probe_dsx01_window_uncertainty import OUTPUT as NOISE


def window_student(raw, features, noise, groups):
    sigma = np.broadcast_to(np.asarray(noise, float), np.asarray(raw).shape)
    if not np.isfinite(sigma).all() or np.any(sigma < 40):
        raise ValueError("fixed radio scales must be finite and >=40 Hz")
    result = student_joint_bound(raw, features, sigma, groups)
    result["diagonal_logvolume"] = float(2 * np.log(sigma / 40).sum())
    result["residual"] = np.r_[result["residual"], np.sqrt(result["diagonal_logvolume"])]
    return result


class WindowNoise(RobustJoint):
    def __init__(self, scan, seed, fitted_c, *, variant, point_noise=None, **kwargs):
        if variant != "window_noise":
            raise ValueError("within-window noise control required")
        super().__init__(scan, seed, fitted_c, variant="robust", **kwargs)
        if not hasattr(scan, "fixed_window_noise"):
            path = NOISE / "noise_features.json"
            scan.fixed_window_noise = json.loads(path.read_text())[scan.case]
            scan.fixed_window_noise_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.noise_metadata = scan.fixed_window_noise
        self.noise_sha256 = scan.fixed_window_noise_sha256
        if point_noise is None:
            by_oid = self.noise_metadata["per_observation_noise_sigma_hz"]
            selected = self.noise_metadata["extra_parameter_BIC_gain"] > 0
            point_noise = [
                by_oid[oid] if selected else self.sigma
                for i in self.members
                for oid in scan.tracks[i]["observation_ids"]
            ]
        self.point_noise = np.asarray(point_noise, float)
        if (
            self.point_noise.shape != self.flat_times.shape
            or not np.isfinite(self.point_noise).all()
            or np.any(self.point_noise < 40)
        ):
            raise ValueError(
                "one fixed finite radio noise scale >=40 Hz per original observation required"
            )
        self.diagonal_logvolume = float(2 * np.log(self.point_noise / 40).sum())

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        updated = window_student(
            self.values - self.q * result["intercept"],
            result["features"],
            self.point_noise,
            self.noise_groups,
        )
        result.update(updated)
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            point_noise_sigma_hz=self.point_noise,
            point_noise_quantiles_hz=np.quantile(self.point_noise, [0, 0.1, 0.5, 0.9, 1]),
            diagonal_noise_logvolume_relative_40Hz=self.diagonal_logvolume,
            noise_features_sha256=self.noise_sha256,
            noise_feature_BIC_gain=self.noise_metadata["extra_parameter_BIC_gain"],
        )
        return result
