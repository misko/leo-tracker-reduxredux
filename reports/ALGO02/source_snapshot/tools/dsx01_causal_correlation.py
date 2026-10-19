"""Variance-matched causal correlations between orbital nuisance coordinates.

Latest/previous causal state disagreement determines a rank-one correlation
direction. Marginal engineering scales remain unchanged. Neither receiver
position nor observed frequencies determine the prior. The correlation strength
is a declared sensitivity control, not an estimated orbit covariance.
"""

import hashlib

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_satellite_prior_controls import SatellitePriorControls
from dsx01_structured_joint import eccentricity_bank
from probe_dsx01_scan_influence import OUTPUT as HISTORY
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

VARIANTS = ("diag_4", "corr_4_0p5", "corr_4_0p9", "diag_6", "corr_6_0p5", "corr_6_0p9")


def variance_matched_correlation(direction, fraction):
    z = np.asarray(direction, float)
    if z.ndim != 1 or not len(z) or not np.isfinite(z).all() or not 0 <= fraction < 1:
        raise ValueError("finite nonempty direction and fraction in [0,1) required")
    loading = np.sqrt(fraction) * z / max(1.0, float(np.max(abs(z))))
    return np.diag(1 - loading**2) + np.outer(loading, loading)


def project_state_difference(position, velocity, modes_position, modes_velocity):
    """Project at fixed epochs; 150 seconds converts velocity deviations to km."""
    dp, dv, up, uv = map(np.asarray, (position, velocity, modes_position, modes_velocity))
    if dp.shape != dv.shape or up.shape != uv.shape or up.shape[1:] != dp.shape:
        raise ValueError("matching state differences and mode-by-state coordinates required")
    design = np.vstack((up.reshape(len(up), -1).T, 150 * uv.reshape(len(uv), -1).T))
    target = np.r_[dp.ravel(), 150 * dv.ravel()]
    coefficient, _, rank, singular = np.linalg.lstsq(design, target, rcond=1e-10)
    error = target - design @ coefficient
    return dict(
        coefficient=coefficient,
        rank=int(rank),
        singular_values=singular,
        unexplained_fraction=float(error @ error / max(target @ target, 1e-30)),
    )


def causal_directions(problem, rank):
    p, scan = problem, problem.scan
    cache_key = (tuple(p.labels), tuple(p.supported), rank)
    if not hasattr(scan, "causal_correlation_cache"):
        scan.causal_correlation_cache = {}
    if cache_key in scan.causal_correlation_cache:
        return scan.causal_correlation_cache[cache_key]
    path = HISTORY / "causal_inputs" / scan.case / "previous.tle"
    if hashlib.sha256(path.read_bytes()).hexdigest() != scan.receipt["previous_tle_sha256"]:
        raise ValueError("previous causal element input differs from the frozen receipt")
    catalogue = parse_element_sets(path.read_text())
    lookup = dict(zip(catalogue.satellite_numbers, catalogue.satellites, strict=True))
    available = [k for k, j in enumerate(p.labels) if int(scan.norads[j]) in lookup]
    numbers = tuple(int(scan.norads[p.labels[k]]) for k in available)
    selected = ElementSetCatalogue(
        tuple(map(str, numbers)), numbers, tuple(lookup[n] for n in numbers)
    )
    times = np.array([0.0, 150.0, 300.0])
    old_p, old_v, good = ecef_states(selected, scan.receipt["origin_utc_ns"], times)
    if not good.all():
        raise ValueError("previous causal states failed propagation")
    nominal_p, nominal_v = phase_shifted_states(p.sky, times, 0.0)
    plus_p, plus_v = phase_shifted_states(p.sky, times, 0.01)
    minus_p, minus_v = phase_shifted_states(p.sky, times, -0.01)
    physical_p, physical_v = phase_shifted_states(p.mode_bank, times, 0.0)
    physical_p = physical_p.reshape(len(p.labels), 3, len(times), 3)
    physical_v = physical_v.reshape(len(p.labels), 3, len(times), 3)
    if rank == 6:
        ecc_p, ecc_v = phase_shifted_states(p.ecc_bank, times, 0.0)
        ecc_p = ecc_p.reshape(len(p.labels), 2, len(times), 3)
        ecc_v = ecc_v.reshape(len(p.labels), 2, len(times), 3)
    rows = {}
    for a, k in enumerate(available):
        j = p.labels[k]
        if j not in p.supported:
            continue
        phase_p = (plus_p[k] - minus_p[k]) / 0.02 * p.phase_sigma[k]
        phase_v = (plus_v[k] - minus_v[k]) / 0.02 * p.phase_sigma[k]
        up = np.concatenate((phase_p[None], physical_p[k]), axis=0)
        uv = np.concatenate((phase_v[None], physical_v[k]), axis=0)
        if rank == 6:
            up, uv = np.concatenate((up, ecc_p[k])), np.concatenate((uv, ecc_v[k]))
        result = project_state_difference(old_p[a] - nominal_p[k], old_v[a] - nominal_v[k], up, uv)
        rows[j] = dict(norad=int(scan.norads[j]), **result)
    scan.causal_correlation_cache[cache_key] = rows
    return rows


class CausalCorrelation(SatellitePriorControls):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown causal correlation control")
        self.correlation_variant = variant
        self.orbit_rank = int(variant.split("_")[1])
        self.correlation_fraction = (
            0.0 if variant.startswith("diag") else float(variant.split("_")[-1].replace("p", "."))
        )
        super().__init__(scan, seed, fitted_c, variant="normal", **kwargs)
        self.ecc_bank, self.ecc_metadata = (None, {})
        if self.orbit_rank == 6:
            self.ecc_bank, self.ecc_metadata = eccentricity_bank(scan, self.labels, self.supported)
        self.causal_direction = causal_directions(self, self.orbit_rank)
        phase_start = self.hardware.shape[1] + self.smooth.shape[1]
        physical_start = phase_start + len(self.labels)
        ecc_start = physical_start + 3 * len(self.supported)
        width = (
            ecc_start + (2 * len(self.supported) if self.orbit_rank == 6 else 0) + len(self.members)
        )
        self.transform = np.eye(width)
        self.correlation_metadata = {}
        for k, j in enumerate(self.supported):
            indices = [
                phase_start + list(self.labels).index(j),
                *range(physical_start + 3 * k, physical_start + 3 * k + 3),
            ]
            if self.orbit_rank == 6:
                indices.extend(range(ecc_start + 2 * k, ecc_start + 2 * k + 2))
            row = self.causal_direction.get(j)
            direction = np.zeros(self.orbit_rank) if row is None else row["coefficient"]
            correlation = variance_matched_correlation(direction, self.correlation_fraction)
            self.transform[np.ix_(indices, indices)] = np.linalg.cholesky(correlation)
            self.correlation_metadata[j] = dict(
                norad=int(scan.norads[j]),
                indices=indices,
                correlation=correlation,
                previous_available=row is not None,
                standardized_disagreement=direction,
                projection_unexplained_fraction=None
                if row is None
                else row["unexplained_fraction"],
            )
        inverse = np.linalg.solve(self.transform, np.eye(width))
        self.prior_precision = inverse.T @ inverse

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
        transformed = features @ self.transform
        bound = hierarchical_bound(
            self.values - self.q * result["intercept"],
            transformed,
            self.point_noise,
            self.noise_groups,
        )
        latent = bound["coefficient"].copy()
        bound["coefficient"] = self.transform @ latent
        bound["latent_coefficient"] = latent
        bound["coefficient_prior_precision"] = self.prior_precision
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        result.update(bound, features=features, latent_features=transformed)
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        bound = self.calculate(x)
        # Store compact blocks rather than a mostly identity dense matrix.
        result.pop("coefficient_prior_precision", None)
        result.update(
            causal_correlation_variant=self.correlation_variant,
            causal_correlation_fraction=self.correlation_fraction,
            orbital_coordinates_per_supported_satellite=self.orbit_rank,
            causal_correlation=self.correlation_metadata,
            causal_state_projection=self.causal_direction,
            prior_precision_coordinates="Decoded physical standardized coordinates",
            prior_precision_reconstruction=(
                "Inverse of each saved correlation block; identity elsewhere"
            ),
            latent_prior_standard_normal=True,
            latent_coefficient=bound["latent_coefficient"],
            eccentricity_prior=self.ecc_metadata,
            no_GPS_radio_or_future_TLE_in_correlation=True,
            marginal_orbit_variances_preserved=True,
        )
        return result
