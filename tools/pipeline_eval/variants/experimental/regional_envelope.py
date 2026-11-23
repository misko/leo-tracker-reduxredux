"""Regional Doppler bounds for the released fine-salvage hard gate."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.research.continuous_curve_fit import (
    paired_phase_frequency, paired_phase_states, phase_frequency_from_states,
)
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants.algo08_salvage_bound import defer_noise, raw_error_limit

REFERENCE_RF = 11.5e9
LIGHT_KM_S = 299792.458
# Upper bound on WGS84 surface radii of curvature at the model's zero height.
SURFACE_RADIUS_KM = 6450.0
# Allow rounding in the WGS84 map, binary64 phase projection, and contrast.
# The guarded numeric domain below keeps position and velocity operations small.
GEOMETRY_PAD_KM = 1e-8
ANGLE_PAD_RAD = 1e-8
FREQUENCY_PAD_HZ = 1e-4


@dataclass(frozen=True)
class ObserverDisk:
    center_km: np.ndarray
    position_radius_km: float
    up_radius_rad: float

    @classmethod
    def from_region(cls, region, anchor):
        """Enclose the entire local square from a supplied point in the square."""
        half = region.half_width_km
        lower = np.asarray(region.latlon((-half, -half)), float)
        upper = np.asarray(region.latlon((half, half)), float)
        anchor = np.asarray(anchor, float)
        if (anchor.shape != (2,) or not np.isfinite([lower, upper, anchor]).all()
                or not np.all(lower <= anchor) or not np.all(anchor <= upper)
                or not (-90 < lower[0] < upper[0] < 90)
                or not (-180 <= lower[1] < upper[1] <= 180)):
            return None
        excursion = np.deg2rad(np.maximum(anchor - lower, upper - anchor))
        latitude_min_abs = max(0.0, lower[0], -upper[0])
        angular = np.hypot(excursion[0], excursion[1] * np.cos(np.deg2rad(latitude_min_abs)))
        return cls(geodetic_to_ecef_km(*anchor, 0.0),
                   SURFACE_RADIUS_KM * angular + GEOMETRY_PAD_KM, angular + ANGLE_PAD_RAD)


def projection_margins(position, velocity, observer, *, orbit_position_km=0.,
                       orbit_velocity_km_s=0.):
    """Bound Doppler and elevation around a nominal state and observer.

    Perturbations are Euclidean balls. An unsupported geometry returns infinite
    margins. Per-row orbit radii may be broadcast over the phase and time axes.
    """
    position, velocity = np.asarray(position), np.asarray(velocity)
    orbit_position_km, orbit_velocity_km_s = map(np.asarray, (orbit_position_km, orbit_velocity_km_s))
    if np.any(orbit_position_km < 0) or np.any(orbit_velocity_km_s < 0):
        raise ValueError("Nonnegative orbit uncertainty required")
    distance = np.linalg.norm(position - observer.center_km, axis=-1)
    speed = np.linalg.norm(velocity, axis=-1)
    delta = observer.position_radius_km + orbit_position_km + GEOMETRY_PAD_KM
    minimum_range = distance - delta
    supported = ((minimum_range >= 100.) & (distance <= 50000.) & (speed <= 50.)
                 & np.isfinite(orbit_velocity_km_s))
    direction = delta / np.where(supported, minimum_range, 1.)
    hz = REFERENCE_RF / LIGHT_KM_S * (speed * direction + orbit_velocity_km_s)
    up_angle = direction + observer.up_radius_rad + ANGLE_PAD_RAD
    return (np.where(supported, hz + FREQUENCY_PAD_HZ, np.inf),
            np.where(supported, np.rad2deg(up_angle), np.inf))


def phase_rates(bank):
    """Lipschitz rates of linear interpolation followed by inverse Earth rotation."""
    spacing = np.diff(bank["time_s"])
    if not np.isfinite(spacing).all() or not np.all(spacing > 0):
        raise ValueError("Ordered finite phase knots required")
    rates = []
    for key in ("position_km", "velocity_km_s"):
        states = bank[key]
        chord = np.linalg.norm(np.diff(states, axis=1), axis=2) / spacing
        rates.append(chord.max(axis=1) + EARTH_ROTATION_RAD_S
                     * np.linalg.norm(states, axis=2).max(axis=1))
    return tuple(rates)


def phase_exclusions(f, e, f_margin, e_margin, y, support_pairs, limit, *, rf,
                     receiver_contrast_hz=0.):
    """For each endpoint pair and phase, return horizon and hard RF exclusions.

    Track-constant receiver offsets, native alias integers, fitted RF terms,
    and the profiled bias cancel in the difference. Use the same alias at both
    endpoints of one support. Unknown or unbounded quantities keep the phase.
    """
    a, b = np.asarray(support_pairs, dtype=int).T
    difference = np.abs((y[a] - rf * f[..., a]) - (y[b] - rf * f[..., b]))
    allowance = (np.nextafter(limit[a] + limit[b], np.inf) + receiver_contrast_hz
                 + abs(rf) * (f_margin[..., a] + f_margin[..., b]) + FREQUENCY_PAD_HZ)
    invisible = (e[..., a] + e_margin[..., a] < 0.) | (e[..., b] + e_margin[..., b] < 0.)
    return invisible, difference > allowance


def contrast_census(scan, *, phase_limit_s, phase_tile_s, orbit_position_km, orbit_velocity_km_s):
    """Count conditional whole-track exclusions under explicit bounded nuisances."""
    from leo.analysis.research.orbit_phase_geometry import FrozenOrbitBank, phase_shifted_states

    region = scan.search_region
    observer = ObserverDisk.from_region(region, region.center)
    if observer is None:
        raise ValueError("The audit requires a finite offered regional square")
    p_rate, v_rate = phase_rates(scan.sky)
    bank = FrozenOrbitBank(scan.sky)
    boundaries = np.linspace(-phase_limit_s, phase_limit_s,
                             int(np.ceil(2 * phase_limit_s / phase_tile_s)) + 1)
    intervals = [(0., 0.)] if phase_limit_s == 0 else list(zip(boundaries[:-1], boundaries[1:], strict=True))
    knots = scan.sky["time_s"]
    count = len(scan.norads)
    viable_any_track = np.zeros(count, bool)
    work = Counter(tracks=len(scan.tracks), catalogue=count, edges=count * len(scan.tracks),
                   curved_tracks=len(scan.curved), curved_edges=count * len(scan.curved))
    curved = set(scan.curved)
    for i, track in enumerate(scan.tracks):
        times = track["times"][[0, -1]]
        measured = track["values"][[0, -1]]
        rf = track["rf_hz"] / REFERENCE_RF
        # Conservative bounds in the explicit anchored receiver box. They do
        # not impose a hard support on v3's later Gaussian nuisance terms.
        drift = 31.5 * np.ptp(times)
        smooth = abs(rf) * 2000. * np.sum(np.abs(scan.rx_basis[i][-1] - scan.rx_basis[i][0]))
        # If RMS <= 450, |epsilon_i - epsilon_j| <= 450 sqrt(2n).
        limit = np.full(2, 450. * np.sqrt(len(track["times"]) / 2.))
        impossible = np.ones(count, bool)
        invisible = np.ones(count, bool)
        for lo, hi in intervals:
            if times.min() + lo < knots[0] or times.max() + hi > knots[-1]:
                impossible[:] = invisible[:] = False
                work["edge_phase_tiles_uncovered"] += count
                continue
            midpoint, half = (lo + hi) / 2., (hi - lo) / 2.
            position, velocity = phase_shifted_states(bank, times, midpoint)
            f, e = phase_frequency_from_states(position, velocity, *region.center)
            f_margin, e_margin = projection_margins(
                position, velocity, observer, orbit_position_km=orbit_position_km + half * p_rate[:, None],
                orbit_velocity_km_s=orbit_velocity_km_s + half * v_rate[:, None],
            )
            below, outside = phase_exclusions(
                f, e, f_margin, e_margin, measured, [(0, 1)], limit, rf=rf,
                receiver_contrast_hz=drift + smooth,
            )
            invisible &= below[:, 0]
            impossible &= (below | outside)[:, 0]
        viable_any_track |= ~impossible
        work["reject_edges"] += int(impossible.sum())
        work["reject_only_horizon"] += int(invisible.sum())
        if i in curved:
            work["reject_curved_edges"] += int(impossible.sum())
    work["reject_trajectories"] = int((~viable_any_track).sum())
    return dict(work)


def regional_rejections(scan, j, times, supports, y, noise, rf, phases, coordinates, observer):
    """Return only complete supports eliminated across the original 121 phases."""
    if (observer is None or not supports or not np.isfinite(times).all() or not np.isfinite(y).all()
            or not np.isfinite(noise).all() or np.max(np.abs(y)) > 1e8
            or not np.isfinite(rf) or not 0.1 <= rf <= 10.
            or np.any(noise < 1e-3) or np.any(noise > 1e6)):
        return None
    pairs = np.asarray(supports, dtype=int) - [0, 1]
    endpoints = np.unique(pairs)
    t = times[endpoints]
    knots = scan.sky["time_s"]
    if (times[0] + phases[0] < knots[0] or times[-1] + phases[-1] > knots[-1]):
        return None
    # All phases share one bank row. A broadcasting view suffices for the
    # original paired interpolator and retains its numerical operation order.
    bank = {k: np.broadcast_to(scan.sky[k][j], (len(phases), *scan.sky[k][j].shape))
            for k in ("position_km", "velocity_km_s")}
    bank["time_s"] = knots
    labels = np.repeat(np.arange(len(phases)), len(t))
    pos, vel = paired_phase_states(bank, np.tile(t, len(phases)), labels, phases)
    f, e = (value.reshape(len(phases), len(t))
            for value in phase_frequency_from_states(pos, vel, *coordinates))
    pos, vel = (v.reshape(len(phases), len(t), 3) for v in (pos, vel))
    f_margin, e_margin = projection_margins(pos, vel, observer)
    pairs = np.searchsorted(endpoints, pairs)
    horizon, rf_outside = phase_exclusions(
        f, e, f_margin, e_margin, y[endpoints], pairs, raw_error_limit(noise[endpoints]), rf=rf,
    )
    rejected = np.all(horizon | rf_outside, axis=0)
    horizon_only = np.all(horizon, axis=0)
    return rejected, horizon_only


def _measure_guard(region_guard, scan, j, t, supports, y, noise, rf, grid, coordinates, observer, work):
    start = process_time()
    rejection = region_guard(scan, j, t, supports, y, noise, rf, grid, coordinates, observer)
    work["bound_cpu_s"] += process_time() - start
    if rejection is None:
        work["fallback_trajectories"] += 1
        return np.zeros(len(supports), bool)
    rejected, horizon = rejection
    work["reject_supports"] += int(rejected.sum())
    work["reject_only_horizon"] += int(horizon.sum())
    work["reject_trajectories"] += int(rejected.all())
    return rejected


def fine_alternatives(kernel, scan, track, y, noise, rf, shortlist, coordinates, *,
                      work, prune):
    """Scoped stock fine loop with an independently certified support guard."""
    t, values = track["times"], track["values"]
    grid = np.linspace(-15, 15, 121)
    supports = [(a, b) for a, b in kernel.selected_supports(len(t))
                if t[b - 1] - t[a] >= 20 and kernel.raw_curvature(dict(times=t[a:b], values=values[a:b]))]
    # A different frequency binding can carry different orbit authority.
    observer = (ObserverDisk.from_region(scan.search_region, coordinates)
                if kernel.paired_phase_frequency is paired_phase_frequency else None)
    alternatives = []
    for j in sorted(shortlist):
        work["trajectories"] += 1
        work["supports"] += len(supports)
        rejected = _measure_guard(regional_rejections, scan, j, t, supports, y, noise,
                                  rf, grid, coordinates, observer, work)
        if prune and rejected.all() and supports:
            continue
        bank = dict(
            time_s=scan.sky["time_s"],
            position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
            velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0),
        )
        f, e = kernel.paired_phase_frequency(
            bank, np.tile(t, len(grid)), np.repeat(np.arange(len(grid)), len(t)),
            grid, *coordinates,
        )
        f, e = f.reshape(len(grid), -1), e.reshape(len(grid), -1)
        for (a, b), impossible in zip(supports, rejected, strict=True):
            if prune and impossible:
                continue
            work["profile_calls"] += 1
            terms = kernel.profile(y[a:b], rf * f[:, a:b], np.diag(1 / noise[a:b]))
            cost = terms["cost"] + grid**2 / 9
            cost[e[:, a:b].min(axis=1) < 0] = np.inf
            best = int(np.argmin(cost))
            residual = terms["residual"][best]
            maximum = np.max(abs(residual) / noise[a:b])
            if defer_noise(residual, t[a:b], terms["rms"][best], terms["bias"][best], cost[best], maximum):
                continue
            screen = kernel.batch_noise_screen(residual[None], t[a:b])
            if (terms["rms"][best] > 450 or abs(terms["bias"][best]) > 3000
                    or not np.isfinite(cost[best]) or not screen["noise_screen_pass"][0] or maximum > 6):
                continue
            if impossible:
                raise ValueError("Regional support exclusion failed on the unpruned path")
            alternatives.append(dict(
                start_index=a, stop_index=b, points=b - a, candidate_index=j,
                norad=int(scan.norads[j]), phase_s=float(grid[best]), cost=float(cost[best]),
                alias=int(terms["alias"][best]), rms_hz=float(terms["rms"][best]),
                max_external_radio_sigma=float(maximum),
            ))
    alternatives.sort(key=lambda row: (-row["points"], row["cost"]))
    return alternatives[:5], len(supports)


@contextmanager
def regional_fine_salvage(*, prune, expected_source_sha256):
    """Enter inside the v3 publication's existing stable salvage scope."""
    from tools.pipeline_eval.variants import v5_tiled_salvage

    source = Path(v5_tiled_salvage.__file__)
    if sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
        raise ValueError("Unexpected fine salvage policy source")
    work = Counter()

    def measured(*args, **kwargs):
        start = process_time()
        try:
            alternatives, supports = fine_alternatives(*args, **kwargs, work=work, prune=prune)
            work["admitted_alternatives"] += len(alternatives)
            return alternatives, supports
        finally:
            work["fine_cpu_s"] += process_time() - start

    with patch.object(v5_tiled_salvage, "fine_alternatives", measured):
        yield work
