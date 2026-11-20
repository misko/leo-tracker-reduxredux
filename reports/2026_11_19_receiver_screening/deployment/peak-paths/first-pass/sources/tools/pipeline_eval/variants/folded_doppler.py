"""Track-free positioning by backprojecting anonymous GLRT CFO detections."""

from __future__ import annotations

import ctypes as ct
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

PERIOD_HZ = 1 / 4.4e-6
KNOT_STEP_S = 2.0
BIN_S = 4.0
TILE_RADIUS_KM = 12.5
GLOBAL_CELLS = 768
SEEDS = 6
MAX_ARCS = 4
BOUNDARY = "Anonymous GLRT carrier peaks plus causal TLE to held-out folded Doppler position"
KERNEL = Path(__file__).with_suffix(".c")


class _Point(ct.Structure):
    _fields_ = [
        ("t", ct.c_double),
        ("rf", ct.c_double),
        ("cfo", ct.c_double),
        ("group", ct.c_int),
        ("bin", ct.c_int),
    ]


class _Match(ct.Structure):
    _fields_ = [(name, ct.c_int) for name in ("orbit", "group", "train", "held")] + [
        (name, ct.c_double) for name in ("offset_hz", "train_score", "held_score", "held_expected")
    ]


@dataclass(frozen=True)
class Observations:
    points: np.ndarray
    groups: tuple[tuple[int, float, int], ...]
    bin_count: int


@dataclass(frozen=True)
class Orbits:
    states: np.ndarray
    caps: np.ndarray
    norads: np.ndarray


@dataclass(frozen=True)
class SiteScore:
    point: tuple[float, float]
    profiles: tuple[dict, ...]

    @property
    def training(self):
        return sum(profile["train_score"] for profile in self.profiles)

    @property
    def validation(self):
        return sum(max(profile["held_score"], 0.0) for profile in self.profiles)


def _wrap(value, period=PERIOD_HZ):
    return (value + period / 2) % period - period / 2


def observations(capture):
    """Use the entire visit stream with a local two-peak cap per group and second."""
    groups = set()
    buckets = defaultdict(list)
    passing = 0
    for probe in capture.probes:
        t = (probe["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz + (
            probe["probe_start_ms"] + capture.probe_ms / 2
        ) / 1000
        if not 0 <= t <= capture.duration_s:
            raise ValueError("GLRT peak lies outside the authorized capture")
        rf = float(probe["actual_rf_hz"])
        if not np.isfinite(rf) or rf <= 0:
            raise ValueError("GLRT peak requires a finite positive tuned RF")
        group = int(probe["channel"]), rf, int(probe["receiver_id"])
        for candidate in probe["candidates"]:
            if not candidate["passed_fractional_margin_gate"]:
                continue
            margin = candidate["fractional_margin"]
            cfo = candidate["fractional_tracking_cfo_hz"]
            if not np.isfinite((margin, cfo)).all():
                raise ValueError("GLRT peak requires finite frequency and evidence")
            passing += 1
            groups.add(group)
            buckets[int(t), group].append((-margin, t, _wrap(cfo)))

    groups = tuple(sorted(groups))
    group_ids = {group: i for i, group in enumerate(groups)}
    points = []
    for (_, group), bucket in buckets.items():
        chosen = []
        for _, t, cfo in sorted(bucket):
            if all(abs(_wrap(cfo - other)) >= 1000 for other in chosen):
                chosen.append(cfo)
                points.append((t, group[1], cfo, group_ids[group], int(t / BIN_S)))
                if len(chosen) == 2:
                    break
    dtype = np.dtype([("t", "f8"), ("rf", "f8"), ("cfo", "f8"), ("group", "i4"), ("bin", "i4")])
    result = Observations(
        np.array(sorted(points), dtype=dtype), groups, int(capture.duration_s / BIN_S) + 1
    )
    return result, dict(
        probe_rows=len(capture.probes),
        accepted_glrt_peaks=passing,
        retained_unlinked_peaks=len(points),
        rf_receiver_groups=len(groups),
    )


def orbit_bank(states, norads):
    """Build a conservative cap covering every knot plus the 20 degree footprint."""
    positions = states[..., :3]
    radius = np.linalg.norm(positions, axis=-1)
    unit = positions / radius[..., None]
    middle = unit[:, unit.shape[1] // 2].copy()
    excursion = np.arccos(np.clip(np.einsum("ski,si->sk", unit, middle), -1, 1)).max(axis=1)
    elevation = np.deg2rad(20)
    horizon = np.arccos(np.clip(6356.0 * np.cos(elevation) / radius.max(axis=1), 0, 1)) - elevation
    threshold = np.cos(excursion + horizon + np.deg2rad(1))
    return Orbits(np.ascontiguousarray(states), np.column_stack((middle, threshold)), norads)


def orbital_states(capture):
    catalogue = parse_element_sets(capture.catalog.decode("ascii"))
    satrecs = [
        sat
        for name, sat in zip(catalogue.names, catalogue.satellites, strict=True)
        if name.startswith("STARLINK")
    ]
    if not satrecs:
        raise ValueError("causal catalogue contains no Starlink element sets")
    knots = np.arange(0, capture.duration_s + 2 * KNOT_STEP_S, KNOT_STEP_S)
    jd, fraction = julian_day_from_utc_ns(capture.anchor_utc_ns + np.rint(knots * 1e9).astype("i8"))
    errors, position, velocity = SatrecArray(satrecs).sgp4(jd, fraction)
    valid = (errors == 0).all(axis=1) & np.isfinite(position).all(axis=(1, 2))
    valid &= np.isfinite(velocity).all(axis=(1, 2))
    valid &= (np.linalg.norm(position, axis=-1) > 6378).all(axis=1)
    if not valid.any():
        raise ValueError("causal catalogue contains no complete physical ephemerides")
    angle = greenwich_mean_sidereal_time_rad(jd, fraction)
    position, velocity = teme_to_ecef(position[valid], velocity[valid], angle)
    norads = np.array([sat.satnum for sat in satrecs])[valid]
    orbits = orbit_bank(np.concatenate((position, velocity), axis=-1), norads)
    return orbits, dict(
        catalogue_satellites=len(satrecs),
        usable_satellites=len(norads),
        sgp4_evaluations=len(satrecs) * len(knots),
        orbit_knots=len(knots),
        orbit_bank_bytes=orbits.states.nbytes + orbits.caps.nbytes,
    )


@cache
def _site_kernel():
    with TemporaryDirectory(prefix="leo-folded-doppler-") as directory:
        library = Path(directory) / "folded_doppler.so"
        subprocess.run(
            ["cc", "-std=c11", "-O3", "-fPIC", "-shared", str(KERNEL), "-lm", "-o", str(library)],
            check=True,
            timeout=30,
        )
        call = ct.CDLL(str(library)).folded_doppler_site
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    call.argtypes = [
        real,
        real,
        ct.c_size_t,
        ct.c_size_t,
        ct.c_double,
        ct.POINTER(_Point),
        ct.c_size_t,
        ct.c_size_t,
        ct.c_size_t,
        ct.c_int,
        real,
        real,
        ct.POINTER(_Match),
    ]
    call.restype = ct.c_int
    return call


class Accumulator:
    def __init__(self, data, orbits):
        self.data, self.orbits = data, orbits
        self.call = _site_kernel()
        self.calls = 0
        if data.points.itemsize != ct.sizeof(_Point):
            raise ValueError("folded Doppler point layout differs from the native kernel")
        self.points = data.points.ctypes.data_as(ct.POINTER(_Point))

    def __call__(self, point, bins):
        self.calls += 1
        site = geodetic_to_ecef_km(*point, 0)
        up = ecef_to_enu_matrix(*point)[2]
        states = self.orbits.states
        matches = (_Match * 64)()
        count = self.call(
            states,
            self.orbits.caps,
            *states.shape[:2],
            KNOT_STEP_S,
            self.points,
            len(self.data.points),
            len(self.data.groups),
            self.data.bin_count,
            bins,
            site,
            up,
            matches,
        )
        if count < 0:
            raise MemoryError("could not allocate folded Doppler workspace")
        profiles, seen_satellites, seen_channels = [], set(), set()
        for match in matches[:count]:
            norad = int(self.orbits.norads[match.orbit])
            channel, rf, receiver = self.data.groups[match.group]
            if norad in seen_satellites or channel in seen_channels:
                continue
            profiles.append(
                dict(
                    norad=norad,
                    channel=channel,
                    rf_hz=rf,
                    receiver=receiver,
                    train_bins=match.train,
                    held_bins=match.held,
                    train_score=match.train_score,
                    held_score=match.held_score,
                    held_expected=match.held_expected,
                    offset_hz=match.offset_hz,
                )
            )
            seen_satellites.add(norad)
            seen_channels.add(channel)
            if len(profiles) == MAX_ARCS:
                break
        return SiteScore(tuple(map(float, point)), tuple(profiles))


def earth_mesh(size=GLOBAL_CELLS):
    i = np.arange(size)
    z = 1 - (2 * i + 1) / size
    return np.column_stack((np.rad2deg(np.arcsin(z)), _wrap(i * 137.50776405003785, 360)))


def _offset(center, east, north):
    lat, lon = np.deg2rad(center)
    distance = np.hypot(east, north) / 6371.0
    azimuth = np.arctan2(east, north)
    lat2 = np.arcsin(
        np.clip(
            np.sin(lat) * np.cos(distance) + np.cos(lat) * np.sin(distance) * np.cos(azimuth), -1, 1
        )
    )
    lon2 = lon + np.arctan2(
        np.sin(azimuth) * np.sin(distance) * np.cos(lat),
        np.cos(distance) - np.sin(lat) * np.sin(lat2),
    )
    return float(np.rad2deg(lat2)), float(_wrap(np.rad2deg(lon2), 360))


def _neighborhood(center, step, radius):
    offsets = range(-radius, radius + 1)
    return (_offset(center, step * e, step * n) for e, n in product(offsets, offsets))


def _spaced(best, count, separation):
    chosen = []
    xyz = []
    for row in sorted(best, key=lambda s: -s.training):
        position = geodetic_to_ecef_km(*row.point, 0)
        if all(np.linalg.norm(position - previous) >= separation for previous in xyz):
            chosen.append(row)
            xyz.append(position)
            if len(chosen) == count:
                break
    return chosen


def search(accumulate, tile):
    if tile is None:
        coarse = [accumulate(p, 16) for p in earth_mesh()]
        seeds = _spaced(coarse, SEEDS, 450)
        stages = ((240, 2, 32), (70, 2, 64), (22, 1, 128), (7, 1, 256), (2, 1, 512), (0.6, 1, 1024))
    else:
        center = np.asarray(tile, dtype=float)
        if center.shape != (2,) or not np.isfinite(center).all() or np.any(abs(center) > (90, 180)):
            raise ValueError("tile requires one finite latitude and longitude center")
        center_xyz = geodetic_to_ecef_km(*center, 0)

        def inside(point):
            return np.linalg.norm(geodetic_to_ecef_km(*point, 0) - center_xyz) <= TILE_RADIUS_KM

        coarse = [accumulate(p, 256) for p in _neighborhood(center, 4, 3) if inside(p)]
        seeds = _spaced(coarse, 4, 4)
        stages = ((2, 1, 512), (0.6, 1, 1024))
    for step, radius, bins in stages:
        seeds = [
            max(
                (
                    accumulate(p, bins)
                    for p in _neighborhood(seed.point, step, radius)
                    if tile is None or inside(p)
                ),
                key=lambda s: s.training,
            )
            for seed in seeds
        ]
    return sorted(seeds, key=lambda s: -s.training)


def _decision(finalists, tile):
    winner = finalists[0]
    if not winner.profiles:
        return False, dict(reason="no recurring training offset at the final scale")
    xyz = geodetic_to_ecef_km(*winner.point, 0)
    separation = 250 if tile is None else 6
    rivals = [
        p.validation
        for p in finalists[1:]
        if np.linalg.norm(geodetic_to_ecef_km(*p.point, 0) - xyz) >= separation
    ]
    lead = winner.validation - max(rivals, default=0.0)
    confirmed = sum(p["held_bins"] >= 4 and p["held_score"] >= 3.0 for p in winner.profiles)
    passed = bool(confirmed >= 3 and lead >= 3.0)
    return passed, dict(
        reason="independent held bins confirm the winning site"
        if passed
        else "insufficient diverse held-bin support or lead over a separated trained rival",
        winning_train_score=winner.training,
        winning_held_score=winner.validation,
        confirmed_independent_profiles=confirmed,
        held_lead=lead,
        profiles=winner.profiles,
        finalists=[
            dict(latlon=p.point, train_score=p.training, held_score=p.validation) for p in finalists
        ],
    )


def solve(capture, *, tile=None):
    started = perf_counter()
    data, metrics = observations(capture)
    metrics.update(
        policy_mode="global" if tile is None else "supplied_tile",
        c_identifiable=False,
        c_cancels_exactly=True,
        independent_bin_s=BIN_S,
        confirmation_width_hz=PERIOD_HZ / 1024,
    )
    point = None
    passed = False
    reason = "insufficient unlinked GLRT peak support"
    if len(data.points) >= 30 and len({group[0] for group in data.groups}) >= 3:
        orbits, geometry = orbital_states(capture)
        accumulator = Accumulator(data, orbits)
        finalists = search(accumulator, tile)
        passed, decision = _decision(finalists, tile)
        reason = decision.pop("reason")
        if finalists[0].profiles:
            point = finalists[0].point
        metrics.update(geometry, **decision, evaluated_locations=accumulator.calls)
    metrics["algorithm_wall_s"] = perf_counter() - started
    arm = dict(latlon=point if passed else None, forced_latlon=point, rf_rms_hz=None)
    return dict(
        status="ok" if passed else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms={"c0": arm, "fitted_c": dict(arm)},
    )
