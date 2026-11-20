"""Center the joint orbit phase on a signed, site-free causal TLE forecast."""

from time import perf_counter
from unittest.mock import patch

import numpy as np
from sgp4.api import Satrec, SatrecArray

from leo.sky.frames import julian_day_from_utc_ns

from . import joint_orbits as joint
from . import phase_capture as gauge

METHOD = "native_phase_forecast"
BOUNDARY = "Anonymous native GLRT Graph and causal TLEs through signed orbit phase and joint fit"
SECOND = 1_000_000_000
HOUR = 3600 * SECOND
MAX_HOURS = 72
MAX_PHASE = 15.0


def phase_delta(reference, velocity, target):
    """Seconds to advance reference along its velocity towards the target TEME position."""
    displacement = target - reference
    speed2 = np.sum(velocity * velocity, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        seconds = np.sum(displacement * velocity, axis=-1) / speed2
    return seconds, np.linalg.norm(displacement - seconds[..., None] * velocity, axis=-1)


def physical_mean(previous, current, velocity, age_h, gap_h):
    """Continue the signed prior→current innovation with fixed shrinkage and leverage."""
    seconds, transverse = phase_delta(previous, velocity, current)
    along = abs(seconds) * np.linalg.norm(velocity, axis=-1)
    age, gap = np.asarray(age_h), np.asarray(gap_h)
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = 0.5 * seconds * np.clip(age / gap, 0, 2) * np.clip((gap - 2) / 4, 0, 1)
    keep = (
        np.isfinite(raw)
        & (age >= 0)
        & (age <= 48)
        & (gap >= 2)
        & (gap <= 48)
        & (transverse <= np.maximum(1.0, 1.5 * along))
    )
    return np.where(keep, np.clip(raw, -MAX_PHASE, MAX_PHASE), 0.0)


def mean_forecast(satellites, previous, document):
    """One mean per current SGP4 object; previous inputs carry authenticated epochs."""
    anchor, cutoff, collection = (
        document[k] for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns")
    )
    if not collection <= cutoff <= anchor:
        raise ValueError("noncausal TLE collection or capture time")
    output = np.zeros(len(satellites))
    available, old, epoch, old_epoch = [], [], [], []
    for j, sat in enumerate(satellites):
        element_epoch = epoch_ns(sat)
        if element_epoch > collection:
            raise ValueError("current element postdates its collection")
        record = previous.get(sat.satnum)
        if record is None:
            continue
        prior, prior_epoch, prior_collection = record[:3]
        if not (
            sat.satnum == prior.satnum
            and epoch_ns(prior) == prior_epoch
            and cutoff - MAX_HOURS * HOUR <= prior_epoch < element_epoch
            and prior_epoch <= prior_collection < collection
        ):
            raise ValueError("invalid or noncausal predecessor")
        available.append(j)
        old.append(prior)
        epoch.append(element_epoch)
        old_epoch.append(prior_epoch)
    if available:
        jd, fr = julian_day_from_utc_ns(np.asarray([anchor], dtype=np.int64))
        err0, r0, _ = SatrecArray(old).sgp4(jd, fr)
        err1, r1, v1 = SatrecArray([satellites[i] for i in available]).sgp4(jd, fr)
        age = (anchor - np.asarray(epoch)) / HOUR
        gap = (np.asarray(epoch) - np.asarray(old_epoch)) / HOUR
        values = physical_mean(r0[:, 0], r1[:, 0], v1[:, 0], age, gap)
        output[available] = np.where((err0[:, 0] == 0) & (err1[:, 0] == 0), values, 0)
    return output


def epoch_ns(sat):
    return round(((sat.jdsatepoch - 2440587.5) + sat.jdsatepochF) * (86400 * SECOND))


def as_satellite(first, second):
    return Satrec.twoline2rv(first.decode("ascii"), second.decode("ascii"))


def infer(document, offer, catalogue, past):
    detail = {}
    make = gauge.grid.make_tile

    def prepare(sky, center):
        start = perf_counter()
        nominal = make(sky, center)
        wide, order, ids = gauge._shift_bank(sky, nominal)
        current = {sat.satnum: sat for sat in sky.satellites}
        satellites = [current[i] for i in ids]
        predecessor = past(satellites, document, detail)
        mean = mean_forecast(satellites, predecessor, document)
        detail.update(
            bank_orbits=len(ids),
            signed_prior_orbits=int(np.count_nonzero(mean)),
            max_abs_prior_s=float(np.max(abs(mean), initial=0)),
            prior_setup_s=perf_counter() - start,
            phase_mean_s=dict(zip(ids, mean.tolist(), strict=True)),
        )
        picked = {i: float(value) for i, value in enumerate(mean) if value != 0}
        return gauge._shifted(nominal, wide, order, picked)

    with patch.object(gauge.grid, "make_tile", prepare):
        result = joint.infer(document, offer, catalogue)
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        {k: v for k, v in detail.items() if k != "phase_mean_s" and k != "history_sources"}
    )
    return result, detail
