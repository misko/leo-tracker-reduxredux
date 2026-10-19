"""Causal eccentricity and colored-residual alternatives to joint Student noise.

No evaluation GPS is read here. Causal TLE disagreement supplies a declared
uncertainty hypothesis; it is not a calibrated orbit-error distribution.
"""

import hashlib

import numpy as np
from dsx01_joint_marginal import JointMarginal
from dsx01_robust_joint import RobustJoint, student_joint_bound
from probe_dsx01_scan_influence import OUTPUT as CAUSAL
from prototype_dsx01_continuous_position import latlon
from sgp4.api import Satrec

from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.sky.propagation import parse_element_sets

VARIANTS = ("eccentric", "colored", "eccentric_colored")


def covariance_whitener(times, sigma, *, correlated_sigma=150.0, correlation_s=10.0):
    t = np.asarray(times, float)
    if t.ndim != 1 or not len(t) or not np.isfinite(t).all():
        raise ValueError("finite nonempty observation times required")
    if (
        not np.isfinite([sigma, correlated_sigma, correlation_s]).all()
        or sigma <= 0
        or correlated_sigma < 0
        or correlation_s <= 0
    ):
        raise ValueError("positive noise/time scales and nonnegative colored scale required")
    covariance = sigma**2 * np.eye(len(t)) + correlated_sigma**2 * np.exp(
        -abs(t[:, None] - t) / correlation_s
    )
    root = np.linalg.cholesky(covariance)
    return np.linalg.solve(root, np.eye(len(t))), float(2 * np.log(np.diag(root) / sigma).sum())


def whiten_blocks(raw, features, slices, matrices):
    y, u = np.asarray(raw, float), np.asarray(features, float)
    if y.ndim != 1 or u.ndim != 2 or u.shape[0] != len(y) or len(slices) != len(matrices):
        raise ValueError("matching observations, modes and whitening blocks required")
    coverage = np.zeros(len(y), dtype=int)
    z, a = np.empty_like(y), np.empty_like(u)
    for sl, w in zip(slices, matrices, strict=True):
        if w.shape != (sl.stop - sl.start, sl.stop - sl.start):
            raise ValueError("whitening block size differs from observation slice")
        coverage[sl] += 1
        z[sl], a[sl] = w @ y[sl], w @ u[sl]
    if np.any(coverage != 1):
        raise ValueError("blocks must cover every observation exactly once")
    return z, a


def eccentricity_sigma(current, previous):
    """Compare averaged eccentricity vectors at the latest TLE's own epoch.

    Transporting the earlier TLE avoids counting secular perigee rotation
    between epochs as catalog disagreement. Scales have explicit floors/caps.
    """
    if previous is None:
        return np.full(2, 1e-4), None
    code, _, _ = previous.sgp4(current.jdsatepoch, current.jdsatepochF)
    if code:
        raise ValueError("previous causal orbit cannot reach the latest causal epoch")
    latest = current.ecco * np.array([np.cos(current.argpo), np.sin(current.argpo)])
    earlier = previous.em * np.array([np.cos(previous.om), np.sin(previous.om)])
    difference = earlier - latest
    return np.clip(abs(difference), 1e-5, 5e-4), difference


def eccentricity_bank(scan, labels, supported):
    cache_key = tuple(labels), tuple(supported)
    if not hasattr(scan, "joint_eccentricity_cache"):
        scan.joint_eccentricity_cache = {}
    if cache_key in scan.joint_eccentricity_cache:
        return scan.joint_eccentricity_cache[cache_key]
    previous_path = getattr(
        scan, "previous_tle_path", CAUSAL / "causal_inputs" / scan.case / "previous.tle"
    )
    if (
        hashlib.sha256(previous_path.read_bytes()).hexdigest()
        != scan.receipt["previous_tle_sha256"]
    ):
        raise ValueError("causal prior TLE differs from the frozen bank receipt")
    old = parse_element_sets(previous_path.read_text())
    by_norad = dict(zip(old.satellite_numbers, old.satellites, strict=True))
    shape = (len(labels), 2, *scan.sky["position_km"].shape[1:])
    dp, dv = np.zeros(shape), np.zeros(shape)
    metadata = {}
    for k, j in enumerate(labels):
        if j not in supported:
            continue
        norad = int(scan.norads[j])
        latest = Satrec.twoline2rv(*scan.elements[str(norad)]["lines"])
        sigma, difference = eccentricity_sigma(latest, by_norad.get(norad))
        p, v = scan.element_basis(j)
        dp[k], dv[k] = p * sigma[:, None, None], v * sigma[:, None, None]
        metadata[j] = dict(
            norad=norad,
            sigma=sigma,
            prior_difference_at_latest_epoch=difference,
            previous_available=norad in by_norad,
        )
    bank = dict(
        time_s=scan.sky["time_s"],
        position_km=dp.reshape(-1, *dp.shape[2:]),
        velocity_km_s=dv.reshape(-1, *dv.shape[2:]),
    )
    result = bank, metadata
    scan.joint_eccentricity_cache[cache_key] = result
    return result


class StructuredJoint(RobustJoint):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown structured-residual control")
        super().__init__(scan, seed, fitted_c, variant="robust", **kwargs)
        self.extension = variant
        self.ecc_bank, self.ecc_metadata = (None, {})
        if "eccentric" in variant:
            self.ecc_bank, self.ecc_metadata = eccentricity_bank(scan, self.labels, self.supported)
        self.whiteners, self.base_volume = [], 0.0
        if "colored" in variant:
            for i in self.members:
                w, volume = covariance_whitener(scan.tracks[i]["times"], self.sigma)
                self.whiteners.append(w)
                self.base_volume += volume

    def calculate(self, x):
        # Start with the same fixed-scale Gaussian design; replace only the
        # orbital covariance span and/or the residual covariance alternative.
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
            extra = np.zeros((len(self.flat_times), 2 * len(self.supported)))
            for k, j in enumerate(self.supported_local):
                use = self.flat_labels == j
                extra[use, 2 * k : 2 * k + 2] = self.q[use, None] * modes[use]
            end = features.shape[1] - len(self.members)
            features = np.column_stack((features[:, :end], extra, features[:, end:]))
        raw = self.values - self.q * result["intercept"]
        if self.whiteners:
            z, u = whiten_blocks(raw, features, self.slices, self.whiteners)
            robust = student_joint_bound(z, u, 1.0, self.noise_groups)
            robust["whitened_conditional_residual"] = robust["conditional_residual_hz"]
            robust["conditional_residual_hz"] = raw - features @ robust["coefficient"]
            robust["residual"] = np.r_[robust["residual"], np.sqrt(self.base_volume)]
        else:
            robust = student_joint_bound(raw, features, self.sigma, self.noise_groups)
        result.update(robust, features=features, base_covariance_logvolume=self.base_volume)
        return result

    def conditional_frequency(self, x):
        result = self.calculate(x)
        a = result["coefficient"]
        start = self.hardware.shape[1] + self.smooth.shape[1]
        stop = result["features"].shape[1] - len(self.members)
        return result["intercept"] + result["features"][:, start:stop] @ a[
            start:stop
        ] / self.q, result["elevation"]

    def diagnostics(self, x):
        result = super().diagnostics(x)
        details = self.calculate(x)
        result.update(
            extension=self.extension,
            eccentricity_prior=self.ecc_metadata,
            base_covariance_logvolume=self.base_volume,
        )
        if self.ecc_bank is not None:
            begin = (
                self.hardware.shape[1]
                + self.smooth.shape[1]
                + len(self.labels)
                + 3 * len(self.supported)
            )
            result["eccentricity_posterior_standard_coefficients"] = details["coefficient"][
                begin : begin + 2 * len(self.supported)
            ]
        return result
