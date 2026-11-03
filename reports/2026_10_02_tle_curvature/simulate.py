"""Synthetic SGP4 element sensitivity; run with the repository's Python environment.

No real TLE, radio observations, or empirical error priors are used. Units are
km, seconds, radians internally. Each element is changed independently.
"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sgp4.api import Satrec, WGS72, jday

from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad, teme_to_ecef, geodetic_to_ecef_km,
)

OUT = Path(__file__).resolve().parent
JD, FR = jday(2026, 10, 2, 0, 0, 0)
FC = 11.7e9
BASE = dict(bstar=1e-4, ecco=0.0002, argpo=0.4, inclo=np.deg2rad(53),
            mo=0.6, no_kozai=15.05 * 2*np.pi/1440, nodeo=1.0)
CHANGES = [
    ("Mean anomaly", "mo", np.deg2rad(.01), "+0.01 deg"),
    ("Mean motion", "no_kozai", 1e-4*2*np.pi/1440, "+0.0001 rev/day"),
    ("Inclination", "inclo", np.deg2rad(.01), "+0.01 deg"),
    ("RAAN", "nodeo", np.deg2rad(.01), "+0.01 deg"),
    ("Eccentricity", "ecco", 1e-4, "+0.0001"),
    ("Argument of perigee", "argpo", np.deg2rad(.01), "+0.01 deg"),
    ("B-star drag", "bstar", 1e-5, "+0.00001 /Earth radius"),
]


def satellite(key=None, delta=0):
    p = BASE.copy()
    if key:
        p[key] += delta
    s = Satrec()
    s.sgp4init(WGS72, "i", 99999, JD+FR-2433281.5, p['bstar'], 0., 0.,
               p['ecco'], p['argpo'], p['inclo'], p['mo'], p['no_kozai'], p['nodeo'])
    return s


def state(s, seconds):
    seconds = np.atleast_1d(seconds).astype(float)
    jd = np.full(seconds.shape, JD)
    fr = FR + seconds/86400
    err, r, v = s.sgp4_array(jd, fr)
    if np.any(err):
        raise ValueError(f"SGP4 errors: {np.unique(err)}")
    return teme_to_ecef(r, v, greenwich_mean_sidereal_time_rad(jd, fr))


def frequency(s, seconds, observer):
    r, v = state(s, seconds)
    rel = r-observer
    return -FC/299792.458 * np.sum(rel*v, axis=1)/np.linalg.norm(rel, axis=1)


def fit_residual(u, residual, degree):
    # Scale to [-1,1] to avoid conditioning differences between durations.
    z = u/max(np.max(np.abs(u)), 1)
    design = np.polynomial.polynomial.polyvander(z, degree)
    coeff = np.linalg.lstsq(design, residual, rcond=None)[0]
    remaining = residual-design@coeff
    return float(np.sqrt(np.mean(remaining**2))), remaining, coeff


def profile_delay(nominal, t, observed, observer, degree):
    u = t-t.mean()
    center, width = 0., 5.
    for _ in range(6):
        delays = np.linspace(center-width, center+width, 41)
        fits = [fit_residual(u, observed-frequency(nominal, t+d, observer), degree)
                for d in delays]
        idx = int(np.argmin([f[0] for f in fits]))
        if _ == 0 and idx in (0, 40):
            raise AssertionError("delay search boundary reached")
        center = float(delays[idx])
        width /= 10
    return center, fits[idx]


def geometry(nominal, latitude_offset):
    r, _ = state(nominal, [21600])
    lon = np.rad2deg(np.arctan2(r[0, 1], r[0, 0]))
    # This only chooses a synthetic station; it is not a geodetic inversion.
    lat = np.rad2deg(np.arctan2(r[0, 2], np.hypot(r[0, 0], r[0, 1])))
    lat += latitude_offset
    obs = geodetic_to_ecef_km(lat, lon, 0)
    center, width = 21600., 500.
    for _ in range(5):
        t = np.linspace(center-width, center+width, 101)
        positions, _ = state(nominal, t)
        center = float(t[np.argmin(np.linalg.norm(positions-obs, axis=1))])
        width /= 10
    positions, _ = state(nominal, [center])
    up = np.array([np.cos(np.deg2rad(lat))*np.cos(np.deg2rad(lon)),
                   np.cos(np.deg2rad(lat))*np.sin(np.deg2rad(lon)),
                   np.sin(np.deg2rad(lat))])
    rel = positions[0]-obs
    el = float(np.rad2deg(np.arcsin(np.dot(rel, up)/np.linalg.norm(rel))))
    return obs, center, el, float(lat), float(lon)


def run():
    nominal = satellite()
    rows = []
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    selected = {"Mean anomaly": 0, "Inclination": 1, "Eccentricity": 2}
    for offset in (.2, 3., 6.):
        obs, center, elevation, lat, lon = geometry(nominal, offset)
        for label, key, delta, description in CHANGES:
            changed = satellite(key, delta)
            pos, _ = state(changed, [center])
            ref, _ = state(nominal, [center])
            displacement = float(np.linalg.norm(pos-ref))
            for phase in (-120., 0., 120.):
                for duration in (10., 20., 60.):
                    u = np.linspace(-duration/2, duration/2, 121)
                    t = center+phase+u
                    y = frequency(changed, t, obs)
                    residual = y-frequency(nominal, t, obs)
                    fits = [fit_residual(u, residual, degree) for degree in range(3)]
                    prof = [profile_delay(nominal, t, y, obs, degree)
                            for degree in range(3)]
                    row = dict(element=label, perturbation=description,
                               station_latitude=lat, station_longitude=lon,
                               geometry_offset_deg=offset, peak_elevation_deg=elevation,
                               orbit_age_hours=center/3600, phase_seconds=phase,
                               duration_seconds=duration, position_error_km=displacement,
                               rms_hz=[f[0] for f in fits],
                               profiled_rms_hz=[p[1][0] for p in prof],
                               fitted_delays_seconds=[p[0] for p in prof],
                               quadratic_edge_hz=float(abs(fits[2][2][2])),
                               linear_end_to_end_hz=float(abs(2*fits[2][2][1])))
                    rows.append(row)
                    if offset == 3. and phase == 0 and duration == 20 and label in selected:
                        col = selected[label]
                        wide_u = np.linspace(-300, 300, 1201)
                        wide = (frequency(changed, center+wide_u, obs)
                                -frequency(nominal, center+wide_u, obs))
                        a, b, c = fits[2][2]
                        axes[0, col].plot(wide_u, wide-a, label="SGP4 residual minus local offset")
                        axes[0, col].plot(wide_u, b*wide_u/10+c*(wide_u/10)**2,
                                          '--', label="20-second quadratic extrapolated")
                        axes[0, col].set_ylim(min(wide-a)*1.2-1, max(wide-a)*1.2+1)
                        axes[0, col].axvspan(-10, 10, alpha=.15, color="gray")
                        axes[0, col].set_title(f"{label}: {description}\nposition difference {displacement:.3f} km")
                        axes[1, col].plot(u, fits[0][1], label="Offset removed")
                        axes[1, col].plot(u, fits[1][1], '--', label="Offset + slope removed")
                        axes[1, col].plot(u, fits[2][1], ':', label="Offset + slope + quadratic removed")
                        axes[1, col].plot(u, prof[0][1][1], label="Timing + offset fitted", alpha=.8)
    for ax in axes.flat:
        ax.grid(alpha=.25)
        ax.set_xlabel("Seconds from closest approach")
        ax.set_ylabel("Frequency residual (Hz)")
        ax.legend(fontsize=7)
    fig.suptitle("Synthetic 11.7 GHz LEO: small TLE-element errors at ~6 hours age\n"
                 "Top: whole pass. Bottom: central 20 seconds. No measurement noise.", fontsize=15)
    fig.savefig(OUT/'curvature.png', dpi=160)
    plt.close(fig)
    result = dict(description=__doc__, base_elements=BASE, carrier_hz=FC,
                  epoch_jd=JD+FR, rows=rows)
    (OUT/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    for row in rows:
        if row['geometry_offset_deg'] == 3 and row['phase_seconds'] == 0 and row['duration_seconds'] == 20:
            print(row['element'], 'km=', round(row['position_error_km'], 4),
                  'RMS=', np.round(row['rms_hz'], 6),
                  'timing profiled=', np.round(row['profiled_rms_hz'], 6))
    print('Saved', OUT/'curvature.png', 'cases=', len(rows))


if __name__ == '__main__':
    run()
