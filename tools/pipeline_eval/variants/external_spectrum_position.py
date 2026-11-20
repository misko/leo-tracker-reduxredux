"""Position screening from frequency changes in unlabeled passive Doppler ridges."""

from dataclasses import dataclass

import numpy as np
from sgp4.api import SatrecArray

from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

from .external_spectrum import CENTER_HZ, Ridge

FIT = 6
SAMPLES = 10
CAP_HZ = 3600
SUPPORT_HZ = 1800
NANOSECOND = 1_000_000_000
LIGHT_KM_S = 299_792.458


@dataclass(frozen=True)
class Sites:
    coordinates: np.ndarray
    ecef: np.ndarray
    up: np.ndarray
    north: np.ndarray

    @classmethod
    def from_degrees(cls, points):
        lat, lon = np.deg2rad(points).T
        ecef = geodetic_to_ecef_km(points[:, 0], points[:, 1], 0.0).T
        up = np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))
        north = np.column_stack(
            (-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat))
        )
        return cls(points, ecef, up, north)


def eligible_elements(text, cutoff):
    parsed = parse_element_sets(text)
    elements = {}
    for sat, epoch in zip(parsed.satellites, parsed.element_epoch_utc_ns(), strict=True):
        if cutoff - 7 * 86400 * NANOSECOND <= epoch <= cutoff:
            old = elements.get(sat.satnum)
            if old is None or old[0] < epoch:
                elements[sat.satnum] = (epoch, sat)
    return tuple(row[1] for _, row in sorted(elements.items())), len(parsed.satellites)


def propagate(orbit, received_utc, clock):
    jd, fraction = julian_day_from_utc_ns(received_utc * NANOSECOND)
    fraction = fraction + clock / 86400
    error, position, velocity = orbit.sgp4(jd, fraction)
    p, v = teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(jd, fraction))
    return error, p, v


def change_cost(measured, predicted):
    residual = np.subtract(measured, predicted, dtype=np.float64)
    residual -= residual[..., :FIT].mean(axis=-1, keepdims=True)
    early = np.mean(residual[..., :FIT] ** 2, axis=-1)
    late = np.mean(residual[..., FIT:] ** 2, axis=-1)
    return early, late


def score_ridge(
    ridge: Ridge, sites: Sites, orbit, satellite_ids, clock, shift, *, directional=False
):
    chosen = np.rint(np.linspace(0, len(ridge.utc) - 1, SAMPLES)).astype(int)
    error, p, v = propagate(orbit, ridge.utc[chosen] + shift, clock)
    mid = SAMPLES // 2
    radial = np.linalg.norm(p[:, mid], axis=-1)
    orbit_ok = (error == 0).all(axis=1) & (radial > 6600) & (radial < 8250)
    keep = np.flatnonzero(orbit_ok)
    point = p[keep, mid]
    # A candidate enters on midpoint horizon geometry. Its whole sampled ridge must be visible.
    up_cosine = np.sin(np.deg2rad(5))
    middle_up = sites.up @ point.T - np.einsum("si,si->s", sites.ecef, sites.up)[:, None]
    site_ix, inner = np.where(middle_up > 0)
    satellite_ix = keep[inner]
    los = p[satellite_ix] - sites.ecef[site_ix, None, :]
    distance = np.linalg.norm(los, axis=-1)
    sin_elev = np.einsum("npi,ni->np", los, sites.up[site_ix]) / distance
    visible = (sin_elev >= up_cosine).all(axis=1)
    if directional:
        north_component = np.einsum("npi,ni->np", los, sites.north[site_ix]) / distance
        visible &= (np.abs(north_component) <= np.sin(np.deg2rad(18))).all(axis=1)
    site_ix, satellite_ix = site_ix[visible], satellite_ix[visible]
    los, distance, sin_elev = los[visible], distance[visible], sin_elev[visible]
    predicted = (
        -(CENTER_HZ / LIGHT_KM_S) * np.einsum("npi,npi->np", los, v[satellite_ix]) / distance
    )
    before, after = change_cost(ridge.frequency_hz[chosen], predicted)
    site_count = len(sites.coordinates)
    early = np.full(site_count, np.inf)
    late = np.full(site_count, np.inf)
    owners = np.full(site_count, -1, dtype=int)
    geometry = np.zeros(site_count)
    np.maximum.at(geometry, site_ix, sin_elev.min(axis=1))
    np.minimum.at(early, site_ix, before)
    qualifies = before == early[site_ix]
    index = np.full(site_count, len(site_ix))
    np.minimum.at(index, site_ix[qualifies], np.flatnonzero(qualifies))
    valid = index != len(site_ix)
    chosen = index[valid]
    late[valid], owners[valid] = after[chosen], satellite_ids[satellite_ix[chosen]]
    return early, late, owners, geometry


def grid_scores(ridges, sites, satellites, clock=0, shifts=None, *, directional=False):
    if not ridges:
        return dict(
            loss=np.ones(len(sites.ecef)),
            support=np.zeros(len(sites.ecef), dtype=int),
            geometry=np.zeros(len(sites.ecef)),
            early=np.full((0, len(sites.ecef)), np.inf),
            late=np.full((0, len(sites.ecef)), np.inf),
            ids=np.full((0, len(sites.ecef)), -1),
        )
    if not satellites:
        raise ValueError("no causal catalogue candidates")
    shifts = shifts if shifts is not None else np.zeros(len(ridges), dtype=int)
    orbit = SatrecArray(satellites)
    satellite_ids = np.array([sat.satnum for sat in satellites])
    results = [
        score_ridge(ridge, sites, orbit, satellite_ids, clock, shift, directional=directional)
        for ridge, shift in zip(ridges, shifts, strict=True)
    ]
    early, late, ids, geometry = map(np.stack, zip(*results, strict=True))
    matched = (early < SUPPORT_HZ**2) & (late < SUPPORT_HZ**2)
    owners = np.array([len(set(ids[matched[:, i], i])) for i in range(ids.shape[1])], dtype=int)
    # Give the held ridge portion twice the weight and cap each ridge's leverage.
    loss = np.minimum((early + 2 * late) / (3 * CAP_HZ**2), 1).mean(axis=0)
    return dict(
        loss=loss, support=owners, geometry=geometry.mean(axis=0), early=early, late=late, ids=ids
    )


def scramble_times(ridges, start, duration):
    offsets = []
    for i, ridge in enumerate(ridges):
        span = int(ridge.utc[-1] - ridge.utc[0])
        begin = (int(ridge.utc[0]) - start + 353 + i * 173) % (duration - span)
        offsets.append(start + begin - ridge.utc[0])
    return np.asarray(offsets, dtype=np.int64)
