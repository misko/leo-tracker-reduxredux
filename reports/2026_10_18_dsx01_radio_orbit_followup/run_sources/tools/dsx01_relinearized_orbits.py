"""Iterated joint integration around exact SGP4 physical-parameter references.

The priors stay centered on the original causal orbit. Moving a numerical
reference is not permission to recenter a satellite's physical prior.
"""

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from dsx01_robust_joint import RobustJoint, student_joint_bound
from dsx01_structured_joint import StructuredJoint
from fit_s01_69333_tle_parameter import perturb
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_mean_motion import reference_motion_satellite
from sgp4.api import Satrec

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.sky.propagation import ElementSetCatalogue

VARIANTS = ("fixed_3", "relinearized_3", "fixed_5", "relinearized_5")


def absolute_intercept(frequency, phase_derivative, phase_reference, modes, orbit_reference):
    f, h, phi, u, theta = (
        np.asarray(a)
        for a in (frequency, phase_derivative, phase_reference, modes, orbit_reference)
    )
    if (
        f.ndim != 1
        or h.shape != f.shape
        or phi.shape != f.shape
        or u.ndim != 2
        or theta.shape != u.shape
        or u.shape[0] != len(f)
    ):
        raise ValueError("one phase and orbital-reference row per frequency required")
    return f - h * phi - np.sum(u * theta, axis=1)


def physical_satellite(base, standardized, scales, origin_ns):
    theta, sigma = np.asarray(standardized), np.asarray(scales)
    if (
        theta.shape not in ((3,), (5,))
        or sigma.shape != theta.shape
        or not np.isfinite(theta).all()
        or not np.isfinite(sigma).all()
        or np.any(sigma < 0)
    ):
        raise ValueError(
            "finite three/five-parameter reference and nonnegative fixed scales required"
        )
    delta = theta * sigma
    elapsed = (origin_ns / 1e9 + 150) / 86400 + 2440587.5 - base.jdsatepoch - base.jdsatepochF
    sat = reference_motion_satellite(base, delta[0], elapsed)
    parameters = ("inclination_deg", "raan_deg", "e_cos_omega", "e_sin_omega")
    for name, shift in zip(parameters[: len(delta) - 1], delta[1:], strict=True):
        sat = perturb(sat, name, shift)
    return sat


def reference_banks(satellites, origin_ns, times, scales, reference, supported, *, step=0.01):
    """Exact state mean and derivatives in absolute standardized coordinates."""
    sigma, theta = np.asarray(scales, float), np.asarray(reference, float)
    if (
        sigma.shape != theta.shape
        or theta.ndim != 2
        or theta.shape[0] != len(satellites)
        or theta.shape[1] not in (3, 5)
        or step <= 0
    ):
        raise ValueError("matching satellite-by-parameter scales/references required")
    if not np.isfinite(theta).all() or not np.isfinite(sigma).all():
        raise ValueError("finite reference and prior scales required")
    supported = set(supported)
    if any(k < 0 or k >= len(satellites) for k in supported):
        raise ValueError("supported local satellite index out of bounds")
    packed, nominal, pairs = [], [], {}
    rank = theta.shape[1]
    for j, base in enumerate(satellites):
        nominal.append(len(packed))
        packed.append(physical_satellite(base, theta[j], sigma[j], origin_ns))
        if j in supported:
            for k in range(rank):
                indexes = []
                for sign in (1, -1):
                    point = theta[j].copy()
                    point[k] += sign * step
                    indexes.append(len(packed))
                    packed.append(physical_satellite(base, point, sigma[j], origin_ns))
                pairs[j, k] = indexes
    numbers = tuple(s.satnum for s in packed)
    catalogue = ElementSetCatalogue(tuple(map(str, numbers)), numbers, tuple(packed))
    p, v, good = ecef_states(catalogue, origin_ns, times)
    if not good.all():
        raise ValueError("SGP4 failed at a physical reference or derivative probe")
    mean = dict(time_s=np.asarray(times), position_km=p[nominal], velocity_km_s=v[nominal])
    modes = dict(time_s=np.asarray(times))
    for key, states in (("position_km", p), ("velocity_km_s", v)):
        derivative = np.zeros((len(satellites), rank, *states.shape[1:]))
        for (j, k), (a, b) in pairs.items():
            derivative[j, k] = (states[a] - states[b]) / (2 * step)
        modes[key] = derivative.reshape(-1, *states.shape[1:])
    return mean, modes


class RelinearizedOrbits(StructuredJoint):
    def __init__(self, scan, seed, fitted_c, *, variant, orbit_reference=None, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown physical-reference control")
        self.orbit_variant, self.orbit_rank = variant, int(variant[-1])
        if self.orbit_rank == 5:
            super().__init__(scan, seed, fitted_c, variant="eccentric", **kwargs)
        else:
            RobustJoint.__init__(self, scan, seed, fitted_c, variant="robust", **kwargs)
            self.ecc_bank, self.ecc_metadata = None, {}
            self.extension, self.base_volume, self.whiteners = variant, 0.0, []
        self.orbit_reference = (
            np.zeros((len(self.labels), self.orbit_rank))
            if orbit_reference is None
            else np.asarray(orbit_reference, float)
        )
        if self.orbit_reference.shape != (len(self.labels), self.orbit_rank):
            raise ValueError("one standardized physical reference per nominated satellite required")
        scales = np.zeros_like(self.orbit_reference)
        for k, j in enumerate(self.labels):
            if j not in self.supported:
                continue
            m = self.mode_metadata[j]
            scales[k, :3] = (
                m["mean_motion_sigma_rev_day"],
                m["inclination_sigma_deg"],
                m["raan_sigma_deg"],
            )
            if self.orbit_rank == 5:
                scales[k, 3:] = self.ecc_metadata[j]["sigma"]
        key = (
            tuple(self.labels),
            tuple(self.supported_local),
            self.orbit_rank,
            self.orbit_reference.tobytes(),
        )
        if not hasattr(scan, "exact_joint_reference_cache"):
            scan.exact_joint_reference_cache = {}
        if key not in scan.exact_joint_reference_cache:
            satellites = [
                Satrec.twoline2rv(*scan.elements[str(int(scan.norads[j]))]["lines"])
                for j in self.labels
            ]
            scan.exact_joint_reference_cache[key] = reference_banks(
                satellites,
                scan.receipt["origin_utc_ns"],
                self.sky["time_s"],
                scales,
                self.orbit_reference,
                self.supported_local,
            )
        self.sky, self.mode_bank = scan.exact_joint_reference_cache[key]

    def calculate(self, x):
        xy = latlon(x[:2])
        frequency, elevation = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference, *xy
        )
        h = 0.01
        plus = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference + h, *xy
        )[0]
        minus = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, self.reference - h, *xy
        )[0]
        phase_derivative = (plus - minus) / (2 * h)
        modes = paired_frequency_modes(
            self.sky, self.mode_bank, self.flat_times, self.flat_labels, self.reference, *xy
        )
        intercept = absolute_intercept(
            frequency,
            phase_derivative,
            self.reference[self.flat_labels],
            modes,
            self.orbit_reference[self.flat_labels],
        )
        phases = np.zeros((len(frequency), len(self.labels)))
        phases[np.arange(len(frequency)), self.flat_labels] = (
            self.q * phase_derivative * self.phase_sigma[self.flat_labels]
        )
        orbital = np.zeros((len(frequency), self.orbit_rank * len(self.supported)))
        for k, j in enumerate(self.supported_local):
            use = self.flat_labels == j
            orbital[use, 3 * k : 3 * k + 3] = self.q[use, None] * modes[use, :3]
            if self.orbit_rank == 5:
                begin = 3 * len(self.supported) + 2 * k
                orbital[use, begin : begin + 2] = self.q[use, None] * modes[use, 3:]
        hardware = self.hardware.copy()
        hardware[:, [4, 6]] *= 10
        features = np.column_stack((hardware, self.smooth * 200, phases, orbital, self.constants))
        result = student_joint_bound(
            self.values - self.q * intercept, features, self.sigma, self.noise_groups
        )
        result.update(
            features=features,
            scales=np.ones(3),
            elevation=elevation,
            frequency=frequency,
            intercept=intercept,
            derivative=phase_derivative,
        )
        return result

    def posterior_orbit_reference(self, x):
        a = self.calculate(x)["coefficient"]
        begin = self.hardware.shape[1] + self.smooth.shape[1] + len(self.labels)
        result = np.zeros_like(self.orbit_reference)
        for k, j in enumerate(self.supported_local):
            result[j, :3] = a[begin + 3 * k : begin + 3 * k + 3]
            if self.orbit_rank == 5:
                start = begin + 3 * len(self.supported) + 2 * k
                result[j, 3:] = a[start : start + 2]
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        posterior = self.posterior_orbit_reference(x)
        result.update(
            orbit_variant=self.orbit_variant,
            orbit_reference_standard=self.orbit_reference,
            posterior_orbit_standard=posterior,
            largest_orbit_reference_change=float(np.max(abs(posterior - self.orbit_reference))),
        )
        return result
