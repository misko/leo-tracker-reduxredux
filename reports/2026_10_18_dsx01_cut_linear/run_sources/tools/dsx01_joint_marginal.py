"""Joint Gaussian integration of radio, phase and causal orbital nuisance modes.

This research model has no evaluation-site input. Gaussian engineering scales
are hypotheses, not calibrated confidence. Satellite nominations remain fixed.
"""

import numpy as np
from build_dsx01_orbit_modes import build_modes
from iterate_dsx01_position_nominations import AnchoredFamilies
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD


def integrated_gaussian(raw, features, sigma):
    """Exact diagonal-plus-low-rank Gaussian cost, conditional mean and volume.

    Unit-normal nuisance coefficients are integrated, not treated as free
    parameters. The diagonal-noise determinant is omitted because sigma is
    fixed before each search. It must be restored for cross-noise evidences.
    """
    y, u = np.asarray(raw, float), np.asarray(features, float)
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if y.ndim != 1 or u.ndim != 2 or u.shape[0] != len(y):
        raise ValueError("matching vector observations and matrix modes required")
    if (
        not np.isfinite(y).all()
        or not np.isfinite(u).all()
        or not np.isfinite(s).all()
        or np.any(s <= 0)
    ):
        raise ValueError("finite inputs and strictly positive fixed noise required")
    r, a = y / s, u / s[:, None]
    gram = np.eye(u.shape[1]) + a.T @ a
    root = np.linalg.cholesky(gram)
    coefficient = np.linalg.solve(root.T, np.linalg.solve(root, a.T @ r))
    innovation = r - a @ coefficient
    logvolume = max(0.0, float(2 * np.log(np.diag(root)).sum()))
    residual = np.r_[innovation, coefficient, np.sqrt(logvolume)]
    return dict(
        residual=residual,
        coefficient=coefficient,
        quadratic=float(innovation @ innovation + coefficient @ coefficient),
        logvolume=logvolume,
        conditional_residual_hz=y - u @ coefficient,
    )


def absolute_phase_linearization(frequency, derivative, reference):
    """Intercept for an absolute zero-mean phase prior, even after relinearizing."""
    return np.asarray(frequency) - np.asarray(derivative) * np.asarray(reference)


class JointMarginal:
    def __init__(self, scan, seed, fitted_c, *, variant, sigma=150.0, reference=None, aliases=None):
        if variant not in ("fixed", "radio_noise", "empirical"):
            raise ValueError("unknown joint covariance control")
        base = AnchoredFamilies(scan, seed, "receiver_smooth", fitted_c, [0, 0])
        self.scan, self.rows, self.members = scan, base.rows, base.members
        self.labels, self.flat_labels = base.labels, base.flat_labels
        self.flat_times, self.slices, self.sky = base.flat_times, base.slices, base.sky
        self.alias = list(base.alias if aliases is None else aliases)
        if len(self.alias) != len(self.members):
            raise ValueError("one fixed alias for each original curved fragment required")
        self.reference = (
            np.array(seed["state"]["phases"])[self.labels]
            if reference is None
            else np.asarray(reference)
        )
        self.variant, self.fitted_c = variant, fitted_c
        self.sigma = 150.0 if variant == "fixed" else float(sigma)
        self.phase_sigma = np.maximum(1.0, scan.sky["phase_sigma_s"][self.labels])
        self.values = np.concatenate(
            [
                scan.tracks[i]["values"] + a * PERIOD
                for i, a in zip(self.members, self.alias, strict=True)
            ]
        )
        self.q = np.concatenate(
            [
                np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["rf_hz"] / 11.5e9)
                for i in self.members
            ]
        )
        width = scan.rx_basis[0].shape[1]
        n = len(self.flat_times)
        self.hardware = np.zeros((n, 8 + int(fitted_c)))
        self.smooth = np.zeros((n, 2 * width))
        self.constants = np.zeros((n, len(self.members)))
        for k, (i, sl) in enumerate(zip(self.members, self.slices, strict=True)):
            t = scan.tracks[i]
            g = 2 * (t["receiver"] - 1) + int(t["channel"] > 4)
            self.hardware[sl, g] = PERIOD / np.sqrt(12)
            self.hardware[sl, 4 + 2 * (t["receiver"] - 1)] = t["times"] - 150
            self.hardware[sl, 5 + 2 * (t["receiver"] - 1)] = (
                (t["times"] - 150) * (-1 if t["channel"] <= 4 else 1) * 0.5
            )
            if fitted_c:
                self.hardware[sl, -1] = (t["rf_hz"] / 1e9 - 11.5) * 200000
            begin = (t["receiver"] - 1) * width
            self.smooth[sl, begin : begin + width] = self.q[sl, None] * scan.rx_basis[i]
            self.constants[sl, k] = 1000
        owners = {
            j: {
                (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                for i, row in zip(self.members, self.rows, strict=True)
                if row["candidate_index"] == j
            }
            for j in self.labels
        }
        self.supported = [j for j in self.labels if len(owners[j]) >= 2]
        self.mode_bank, self.mode_metadata = build_modes(
            scan, self.labels, self.supported, "physical"
        )
        self.supported_local = [base.local_j[j] for j in self.supported]
        self.initial = np.array([0.0, 0.0] + ([0.0, 0.0, 0.0] if variant == "empirical" else []))
        self.lower = np.array(
            [-12.5, -12.5]
            + (list(np.log([0.2 / 10, 10 / 200, 0.05])) if variant == "empirical" else [])
        )
        self.upper = np.array(
            [12.5, 12.5]
            + (list(np.log([30 / 10, 1000 / 200, 5])) if variant == "empirical" else [])
        )

    def calculate(self, x):
        xy = np.asarray(x)[:2]
        scales = np.exp(x[2:]) if self.variant == "empirical" else np.ones(3)
        frequency, elevation = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference, *latlon(xy)
        )
        h = 0.01
        plus = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference + h, *latlon(xy)
        )[0]
        minus = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference - h, *latlon(xy)
        )[0]
        derivative = (plus - minus) / (2 * h)
        intercept = absolute_phase_linearization(
            frequency, derivative, self.reference[self.flat_labels]
        )
        phases = np.zeros((len(frequency), len(self.labels)))
        phases[np.arange(len(frequency)), self.flat_labels] = (
            self.q * derivative * self.phase_sigma[self.flat_labels]
        )
        modes = paired_frequency_modes(
            self.sky, self.mode_bank, self.flat_times, self.flat_labels, self.reference, *latlon(xy)
        )
        orbital = np.zeros((len(frequency), 3 * len(self.supported)))
        for k, j in enumerate(self.supported_local):
            use = self.flat_labels == j
            orbital[use, 3 * k : 3 * k + 3] = self.q[use, None] * modes[use] * scales[2]
        hardware = self.hardware.copy()
        hardware[:, [4, 6]] *= 10 * scales[0]
        features = np.column_stack(
            (hardware, self.smooth * 200 * scales[1], phases, orbital, self.constants)
        )
        result = integrated_gaussian(self.values - self.q * intercept, features, self.sigma)
        result.update(
            features=features,
            elevation=elevation,
            scales=scales,
            frequency=frequency,
            intercept=intercept,
            derivative=derivative,
        )
        return result

    def residual(self, x):
        result = self.calculate(x)
        return np.r_[result["residual"], np.maximum(0, -result["elevation"]) / 2]

    def state(self, x):
        result = self.calculate(x)
        a = result["coefficient"]
        scales = result["scales"]
        nb, ns = self.hardware.shape[1], self.smooth.shape[1]
        beta = np.zeros(nb)
        beta[:4] = a[:4] * PERIOD / np.sqrt(12)
        for rx in range(2):
            mean, contrast = a[4 + 2 * rx] * 10 * scales[0], a[5 + 2 * rx] * 0.5
            beta[4 + 2 * rx : 6 + 2 * rx] = 150 * np.array([mean - contrast, mean + contrast])
        if self.fitted_c:
            beta[-1] = a[nb - 1] * 200000
        phase = np.zeros(len(self.scan.norads))
        phase[self.labels] = a[nb + ns : nb + ns + len(self.labels)] * self.phase_sigma
        return dict(
            beta=beta,
            phases=phase,
            extra={},
            smooth=(a[nb : nb + ns] * 200 * scales[1]).reshape(2, -1),
        )

    def diagnostics(self, x):
        result = self.calculate(x)
        state = self.state(x)
        return dict(
            quadratic=result["quadratic"],
            logvolume=result["logvolume"],
            noise_sigma_hz=self.sigma,
            rx_drift_mean_sigma_hz_s=10 * result["scales"][0],
            rx_smooth_sigma_hz=200 * result["scales"][1],
            physical_orbit_scale=result["scales"][2],
            conditional_residual_rms_hz=float(
                np.sqrt(np.mean(result["conditional_residual_hz"] ** 2))
            ),
            largest_posterior_absolute_phase_s=float(np.max(abs(state["phases"]))),
            largest_phase_linearization_change_s=float(
                np.max(abs(state["phases"][self.labels] - self.reference))
            ),
            conditional_residual_hz=result["conditional_residual_hz"],
            coefficients=result["coefficient"],
            phase_reference_s=self.reference,
        )

    def conditional_frequency(self, x):
        """Reference-Hz orbit prediction, excluding hardware and curve constants."""
        result = self.calculate(x)
        a = result["coefficient"]
        start = self.hardware.shape[1] + self.smooth.shape[1]
        stop = start + len(self.labels) + 3 * len(self.supported)
        frequency = result["intercept"] + result["features"][:, start:stop] @ a[start:stop] / self.q
        return frequency, result["elevation"]
