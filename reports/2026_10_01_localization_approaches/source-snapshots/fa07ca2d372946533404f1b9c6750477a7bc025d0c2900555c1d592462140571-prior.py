"""Deterministic Gaussian approximation to a uniform horizontal disk."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin

import numpy as np

from leo.analysis.gaussian_sum_location import FilterState, GaussianComponent

SACRAMENTO_CENTER_LATITUDE_DEG = 38.5816
SACRAMENTO_CENTER_LONGITUDE_DEG = -121.4944


@dataclass(frozen=True)
class UniformDiskApproximation:
    radius_km: float = 250.0
    radial_rings: int = 4
    angular_sectors: int = 8
    height_sigma_km: float = 0.1
    clock_sigma_s: float = 1.0
    receiver_drift_sigma_hz_s: float = 0.5
    satellite_epoch_sigma_s: float = 0.5

    @property
    def component_count(self) -> int:
        return self.radial_rings * self.angular_sectors


def _cell_moments(inner: float, outer: float, center: float, half_angle: float):
    """Exact first two Cartesian moments of one uniform annular sector."""
    radial_mean = (2.0 / 3.0) * (outer**3 - inner**3) / (outer**2 - inner**2)
    radial_second = 0.5 * (outer**2 + inner**2)
    angular_mean = sin(half_angle) / half_angle
    mean = radial_mean * angular_mean * np.array([cos(center), sin(center)])
    second_harmonic = sin(2.0 * half_angle) / (4.0 * half_angle)
    second = radial_second * np.array(
        [
            [0.5 + second_harmonic * cos(2.0 * center),
             second_harmonic * sin(2.0 * center)],
            [second_harmonic * sin(2.0 * center),
             0.5 - second_harmonic * cos(2.0 * center)],
        ]
    )
    return mean, second - np.outer(mean, mean)


def build_uniform_disk_prior(layout, specification: UniformDiskApproximation) -> FilterState:
    """Moment-match equal-area disk cells; this is not an exact uniform density."""
    if (
        specification.radius_km <= 0
        or specification.radial_rings <= 0
        or specification.angular_sectors < 3
    ):
        raise ValueError("disk radius, ring count, and sector count must be positive")
    radius = specification.radius_km
    half_angle = pi / specification.angular_sectors
    components = []
    for ring in range(specification.radial_rings):
        inner = radius * np.sqrt(ring / specification.radial_rings)
        outer = radius * np.sqrt((ring + 1) / specification.radial_rings)
        for sector in range(specification.angular_sectors):
            angle = 2.0 * pi * (sector + 0.5) / specification.angular_sectors
            horizontal_mean, horizontal_covariance = _cell_moments(inner, outer, angle, half_angle)
            mean = np.zeros(layout.dimension)
            mean[:2] = horizontal_mean
            covariance = np.zeros((layout.dimension, layout.dimension))
            covariance[:2, :2] = horizontal_covariance
            diagonal = np.array([
                specification.height_sigma_km**2,
                specification.clock_sigma_s**2,
                specification.receiver_drift_sigma_hz_s**2,
                specification.receiver_drift_sigma_hz_s**2,
                *([specification.satellite_epoch_sigma_s**2] * len(layout.norad_ids)),
            ])
            covariance[np.arange(2, layout.dimension), np.arange(2, layout.dimension)] = diagonal
            components.append(
                GaussianComponent(1.0 / specification.component_count, mean, covariance)
            )
    return FilterState(tuple(components))


def disk_probability(state: FilterState, radius_km: float, *, radial_order: int = 64,
                     angular_order: int = 128) -> float:
    """Deterministic Gauss-Legendre quadrature of mixture mass inside a disk."""
    nodes, weights = np.polynomial.legendre.leggauss(radial_order)
    radii = radius_km * (nodes + 1.0) / 2.0
    radial_weights = radius_km * weights / 2.0
    angles = 2.0 * pi * (np.arange(angular_order) + 0.5) / angular_order
    points = np.stack((radii[:, None] * np.cos(angles), radii[:, None] * np.sin(angles)), axis=-1)
    result = 0.0
    for component in state.components:
        covariance = component.covariance[:2, :2]
        inverse = np.linalg.inv(covariance)
        delta = points - component.mean[:2]
        exponent = np.einsum("...i,ij,...j->...", delta, inverse, delta)
        density = np.exp(-0.5 * exponent) / (2.0 * pi * np.sqrt(np.linalg.det(covariance)))
        result += component.weight * np.sum(
            density * radii[:, None] * radial_weights[:, None] * (2.0 * pi / angular_order)
        )
    return float(result)


def build_uniform_prior(layout) -> FilterState:
    """Build the frozen Sacramento uniform-disk approximation."""
    return build_uniform_disk_prior(layout, UniformDiskApproximation())


def prior_description() -> dict[str, object]:
    specification = UniformDiskApproximation()
    state = build_uniform_prior(type("EmptyLayout", (), {"dimension": 6, "norad_ids": ()})())
    five_sigma_radius = max(
        np.linalg.norm(component.mean[:2])
        + 5.0 * np.sqrt(np.linalg.eigvalsh(component.covariance[:2, :2])[-1])
        for component in state.components
    )
    inside = disk_probability(state, specification.radius_km, radial_order=96, angular_order=192)
    return {
        "name": "sacramento_uniform",
        "intended_center_latitude_deg": SACRAMENTO_CENTER_LATITUDE_DEG,
        "intended_center_longitude_deg": SACRAMENTO_CENTER_LONGITUDE_DEG,
        "intended_radius_km": specification.radius_km,
        "intended_density": "uniform_horizontal_disk",
        "prior_point_estimate": "center",
        "approximation": "equal_area_annular_sector_cell_moment_gaussians",
        "radial_rings": specification.radial_rings,
        "angular_sectors": specification.angular_sectors,
        "component_count": specification.component_count,
        "component_weight": 1.0 / specification.component_count,
        "represented_mass_inside_intended_disk": inside,
        "represented_mass_outside_intended_disk": 1.0 - inside,
        "physics_support_radius_km": float(np.ceil(five_sigma_radius)),
        "posterior_interpretation": "conditional_on_gaussian_approximation_to_uniform_disk",
    }


def make_config():
    """Return physics centered on Sacramento with support for represented 5-sigma tails."""
    from physics import PhysicsConfig

    description = prior_description()
    return PhysicsConfig(
        prior_center_lat_deg=SACRAMENTO_CENTER_LATITUDE_DEG,
        prior_center_lon_deg=SACRAMENTO_CENTER_LONGITUDE_DEG,
        support_radius_km=description["physics_support_radius_km"],
    )
