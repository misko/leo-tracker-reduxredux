"""Associate and locate anonymous Doppler traces on a fixed board of regions."""

from dataclasses import dataclass
from itertools import product
from time import process_time

import numpy as np
from sgp4.api import Satrec

from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)

METHODS = ("orbcomm_blind_held", "orbcomm_blind_ungated", "orbcomm_blind_reversed")
WIDTH = 12.5
LIGHT_KM_S = 299_792.458
RESIDUAL_CAP_HZ = 75.0
MIN_ORBIT_MARGIN_HZ = 5.0
MAX_PREDICTION_ERROR_HZ = 20.0
MIN_RIVAL_MARGIN_HZ = 0.5
MIN_FACE_KM = 0.02


def geographic(center, offset):
    lat, lon = center
    east, north = offset
    return [float(lat + north / 111), float(lon + east / (111.32 * np.cos(np.deg2rad(lat))))]


@dataclass(frozen=True)
class Bank:
    xyz: np.ndarray
    velocity: np.ndarray
    valid: np.ndarray
    norads: np.ndarray
    cfo: np.ndarray
    rf: np.ndarray


def orbit_bank(tracks, catalogue, cutoff):
    if not tracks or len(catalogue) < 3:
        raise ValueError("need anonymous tracks and a multi-object historical catalogue")
    allowed = {"id", "rf_hz", "times_ns", "cfo_hz"}
    if any(set(track) != allowed for track in tracks):
        raise ValueError("unexpected field in anonymous detector handoff")
    times = np.asarray([r["times_ns"] for r in tracks], dtype=np.int64)
    values = np.asarray([r["cfo_hz"] for r in tracks], dtype=float)
    carriers = np.asarray([r["rf_hz"] for r in tracks], dtype=float)
    if (
        times.ndim != 2
        or times.shape[1] < 12
        or times.shape != values.shape
        or np.any(times < cutoff)
        or np.any(np.diff(times, axis=1) <= 0)
        or np.any(~np.isfinite(values))
        or np.any(~np.isfinite(carriers) | (carriers < 137.2e6) | (carriers > 137.8e6))
    ):
        raise ValueError("invalid anonymous VHF trace geometry")
    dates, fractions = julian_day_from_utc_ns(times.ravel())
    sidereal = greenwich_mean_sidereal_time_rad(dates, fractions)
    xyz, velocity, valid, norads = [], [], [], []
    for orbit in catalogue:
        sat = Satrec.twoline2rv(*orbit["tle"])
        if max(orbit["epoch_ns"], orbit["collected_ns"]) >= cutoff or sat.satnum != orbit["norad"]:
            raise ValueError("ephemeris identity or causal authority is invalid")
        status, pos, vel = sat.sgp4_array(dates, fractions)
        pos, vel = teme_to_ecef(pos, vel, sidereal)
        xyz.append(pos.reshape(*times.shape, 3))
        velocity.append(vel.reshape(*times.shape, 3))
        valid.append(np.all(status.reshape(times.shape) == 0, axis=-1))
        norads.append(sat.satnum)
    if len(set(norads)) != len(norads):
        raise ValueError("duplicate causal orbit identifier")
    return Bank(*(np.asarray(items) for items in (xyz, velocity, valid, norads)), values, carriers)


def score_point(bank, point, cfo):
    receiver = geodetic_to_ecef_km(*point, 0.0)
    line = bank.xyz - receiver
    ranges = np.linalg.norm(line, axis=-1)
    radial = np.einsum("otnc,otnc->otn", line, bank.velocity) / ranges
    up = receiver / np.linalg.norm(receiver)
    elevation = np.einsum("otnc,c->otn", line, up) / ranges
    visible = bank.valid & (np.mean(elevation > -0.035, axis=-1) >= 0.9)
    residual = cfo[np.newaxis] + (bank.rf[np.newaxis, :, np.newaxis] / LIGHT_KM_S) * radial
    split = cfo.shape[1] * 3 // 5
    offset = np.mean(residual[..., :split], axis=-1)
    adjusted = residual - offset[..., np.newaxis]
    rms = np.sqrt(np.mean(adjusted[..., :split] ** 2, axis=-1))
    ranked = np.where(visible, rms, np.inf)
    order = np.argsort(ranked, axis=0, kind="stable")
    first, second = order[:2]
    arc = np.arange(len(first))
    train = ranked[first, arc]
    held = np.sqrt(np.mean(adjusted[first, arc, split:] ** 2, axis=-1))
    held = np.where(np.isfinite(train), held, np.inf)
    return (
        train,
        held,
        bank.norads[first],
        np.minimum(ranked[second, arc], 1e6) - np.minimum(train, 1e6),
        np.sum(visible, axis=0),
    )


def robust_rms(values):
    return float(np.sqrt(np.mean(np.minimum(values, RESIDUAL_CAP_HZ) ** 2)))


def locate(bank, tiles, *, reverse):
    cfo = bank.cfo[:, ::-1] if reverse else bank.cfo

    def evaluate(center, local):
        point = geographic(center, local)
        evidence = score_point(bank, point, cfo)
        return robust_rms(evidence[0]), local, point, evidence

    def fit(center):
        grid = tuple(product(np.linspace(-WIDTH, WIDTH, 7), repeat=2))
        best = min((evaluate(center, xy) for xy in grid), key=lambda row: row[0])
        for spacing in (2.0, 0.5):
            local = best[1]
            nearby = {
                tuple(np.clip(np.asarray(local) + shift, -WIDTH, WIDTH))
                for shift in product((-spacing, 0.0, spacing), repeat=2)
            }
            best = min((evaluate(center, xy) for xy in sorted(nearby)), key=lambda row: row[0])
        return best

    ranked = sorted(((key, fit(center)) for key, center in tiles.items()), key=lambda x: x[1][0])
    win, (train_rms, local, point, (train, held, norad, margin, visible)) = ranked[0]
    held_rms = robust_rms(held)
    rival = min(robust_rms(item[1][3][1]) for item in ranked[1:]) - held_rms
    selected = (train <= MAX_PREDICTION_ERROR_HZ) & (held <= MAX_PREDICTION_ERROR_HZ)
    selected &= margin >= MIN_ORBIT_MARGIN_HZ
    assigned = [int(x) if good else None for x, good in zip(norad, selected, strict=True)]
    n_orbits = len({x for x in assigned if x is not None})
    face = WIDTH - max(abs(x) for x in local)
    if n_orbits < 3 or np.count_nonzero(selected) < 6:
        reason = "insufficient_independent_held_orbit_support"
    elif rival < MIN_RIVAL_MARGIN_HZ:
        reason = "insufficient_held_tile_margin"
    elif face <= MIN_FACE_KM:
        reason = "fit_at_region_face"
    else:
        reason = None
    metrics = dict(
        tiles=len(tiles),
        tile=win,
        training_robust_rms_hz=train_rms,
        held_robust_rms_hz=held_rms,
        held_nearest_rival_gain_hz=rival,
        face_km=face,
        tracks=len(assigned),
        tracks_with_genuine_alternative=int(np.count_nonzero(visible > 1)),
        held_orbit_count=n_orbits,
        held_tracks=int(np.count_nonzero(selected)),
        accepted_chain_norad=assigned,
        relief_height_model_m=0,
        rf_slope_identifiable=False,
        projected_rf_rank=0,
        profiled_per_track_intercepts=True,
        tile_scores=[
            dict(id=key, training_rms_hz=fit[0], held_rms_hz=robust_rms(fit[3][1]))
            for key, fit in ranked
        ],
    )
    return point, reason, metrics


def outcome(point, reason, metrics):
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary="Anonymous measured Bellaterra VHF traces and causal OG2 catalogue",
        metrics=metrics,
        arms=dict(
            c0=dict(
                latlon=None if reason else point,
                forced_latlon=point if reason else None,
                rf_rms_hz=metrics["held_robust_rms_hz"],
            ),
            fitted_c=dict(
                latlon=None, status="unavailable", reason="per_track_offsets_span_rf_term"
            ),
        ),
    )


def infer(request):
    if set(request) != {"tracks", "catalogue", "cutoff_ns", "tiles"} or len(request["tiles"]) < 2:
        raise ValueError("need anonymous measurements and multiple independently offered tiles")
    start = process_time()
    bank = orbit_bank(request["tracks"], request["catalogue"], request["cutoff_ns"])
    normal = locate(bank, request["tiles"], reverse=False)
    reverse = locate(bank, request["tiles"], reverse=True)
    return dict(
        results=dict(
            zip(
                METHODS,
                (outcome(*normal), outcome(normal[0], None, normal[2]), outcome(*reverse)),
                strict=True,
            )
        ),
        cpu_s=process_time() - start,
    )


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(infer(json.load(sys.stdin)), allow_nan=False))
