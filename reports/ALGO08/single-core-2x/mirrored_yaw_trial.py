"""Estimate shared orbit yaw after removing individual along-orbit shifts."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

import numpy as np
from sgp4.api import SatrecArray

from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km, julian_day_from_utc_ns
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

from . import mirrored_causal_forecast_trial as causal
from .mirrored_orbit_weight_trial import CURVES_SHA256, curves, study, support

NS = 10**9
STATE_TIMES_NS = np.array([0, 150, 300], dtype=np.int64) * NS
PHASE_STEP_NS = 50_000_000
MIN_LEVERAGE = .01
ARCSECONDS = 180. * 3600. / np.pi


def row_dot(left, right):
    return np.einsum("ij,ij->i", left, right)


def profiled_yaw(base, new, phase):
    """One state angle per orbit after projecting its own time direction."""
    yaw = np.stack((-base[..., 1], base[..., 0], np.zeros_like(base[..., 0])), axis=-1)
    yaw, difference, phase = (a.reshape(len(base), -1) for a in (yaw, new - base, phase))
    phase_norm = np.sqrt(row_dot(phase, phase))
    unit = phase / phase_norm[:, None]
    after = yaw - unit * row_dot(yaw, unit)[:, None]
    adjusted = difference - unit * row_dot(difference, unit)[:, None]
    energy = row_dot(after, after)
    leverage = np.sqrt(energy / row_dot(yaw, yaw))
    angles = np.divide(row_dot(after, adjusted), energy,
                       out=np.full_like(energy, np.nan), where=leverage >= MIN_LEVERAGE)
    return angles, leverage, energy, row_dot(adjusted, adjusted)


def plane_yaw(base, new):
    p, q = (np.cross(a[:, :, 0], a[:, :, 1])[..., :2] for a in (base, new))
    sine = p[..., 0] * q[..., 1] - p[..., 1] * q[..., 0]
    cosine = np.sum(p * q, axis=-1)
    return np.median(np.arctan2(sine, cosine), axis=1)


def states(bank, epochs):
    julian, fraction = julian_day_from_utc_ns(epochs)
    error, position, velocity = SatrecArray(bank).sgp4(julian, fraction)
    return (error == 0).all(axis=1), np.stack((position, velocity), axis=2)


def fitted_rows(base, new, observed_at, *, strictly_newer):
    base_rows, new_rows = (dict(zip(cat.satellite_numbers, cat.satellites, strict=True))
                           for cat in (base, new))
    epochs = [{n: epoch for n, epoch in zip(cat.satellite_numbers,
                                           cat.element_epoch_utc_ns(), strict=True)}
              for cat in (base, new)]
    numbers = sorted(n for n in base_rows.keys() & new_rows.keys()
                     if not strictly_newer or epochs[1][n] > epochs[0][n])
    base_orbits, new_orbits = ([rows[n] for n in numbers] for rows in (base_rows, new_rows))
    times = observed_at + STATE_TIMES_NS
    good_base, a = states(base_orbits, times)
    good_new, b = states(new_orbits, times)
    good_early, early = states(base_orbits, times - PHASE_STEP_NS)
    good_late, late = states(base_orbits, times + PHASE_STEP_NS)
    good = good_base & good_new & good_early & good_late
    a, b, early, late = (v[good] for v in (a, b, early, late))
    norm = np.linalg.norm(a, axis=-1).mean(axis=1)[:, None, :, None]
    phase = (late - early) / (2 * PHASE_STEP_NS / NS)
    angles, leverage, energy, residual = profiled_yaw(a / norm, b / norm, phase / norm)
    usable = np.isfinite(angles)
    array = dict(
        norad=np.asarray(numbers)[good][usable], radians=angles[usable],
        updated=np.asarray([epochs[1][n] > epochs[0][n] for n in numbers])[good][usable],
        inclination=np.rad2deg([orb.inclo for orb in base_orbits])[good][usable],
        plane_radians=plane_yaw(a, b)[usable], leverage=leverage[usable],
        energy=energy[usable], residual=residual[usable],
    )
    return array, dict(common_norads=len(numbers), propagated=int(good.sum()),
                       identifiable=int(usable.sum()))


def summarize(rows, keep):
    subset = {name: values[keep] for name, values in rows.items()}
    angles = subset["radians"]
    if not len(angles):
        raise ValueError("No identifiable common orbit states")
    theta = float(np.median(angles))
    groups = np.floor(subset["inclination"] / 5).astype(int)
    group_fit = {}
    for group in np.unique(groups):
        mask = groups == group
        if mask.sum() >= 32:
            group_fit[str(5 * group)] = dict(
                satellites=int(mask.sum()), arcsec=float(np.median(angles[mask]) * ARCSECONDS),
            )
    correction = np.sum(subset["energy"] * (2 * theta * angles - theta**2))
    return dict(
        count=len(angles), common_yaw_arcsec=theta * ARCSECONDS,
        yaw_p05_p95_arcsec=(np.quantile(angles, [.05, .95]) * ARCSECONDS).tolist(),
        yaw_mad_arcsec=float(np.median(np.abs(angles - theta)) * ARCSECONDS),
        median_orbit_plane_yaw_arcsec=float(np.median(subset["plane_radians"]) * ARCSECONDS),
        yaw_leverage_p05_median=np.quantile(subset["leverage"], [.05, .5]).tolist(),
        fraction_state_residual_energy_removed=float(correction / np.sum(subset["residual"])),
        inclination_groups_deg=group_fit,
    )


def past_snapshots(reader, cutoff):
    distinct = {}
    for snapshot in reader.list_snapshots("space-track"):
        if snapshot.collected_utc_ns <= cutoff:
            distinct.setdefault(snapshot.sha256, snapshot)
    snapshots = list(distinct.values())[-5:]
    if len(snapshots) != 5:
        raise ValueError("Expected five distinct capture-causal snapshots")
    return snapshots


def bank_before(reader, snapshot):
    catalogue = parse_element_sets(reader.read(snapshot))
    items = [(name, number, satellite) for name, number, satellite, epoch in zip(
        catalogue.names, catalogue.satellite_numbers, catalogue.satellites,
        catalogue.element_epoch_utc_ns(), strict=True,
    ) if "STARLINK" in name.upper() and epoch <= snapshot.collected_utc_ns]
    return ElementSetCatalogue(*(tuple(column) for column in zip(*items, strict=True)))


def rate_forecast(transitions):
    if len(transitions) != 4:
        raise ValueError("Expected two training and two held orbit revisions")
    training = [row["common_yaw_arcsec"] / row["elapsed_hours"] for row in transitions[:2]]
    rate = float(np.median(training))
    held = []
    for row in transitions[2:]:
        measured = row["common_yaw_arcsec"]
        forecast = rate * row["elapsed_hours"]
        improved = measured * forecast > 0 and abs(forecast - measured) < abs(measured)
        held.append(dict(measured_arcsec=measured, predicted_arcsec=forecast, passed=improved))
    return dict(training_rate_arcsec_per_hour=rate, held=held,
                qualified=all(row["passed"] for row in held))


def required_yaw(latitude):
    x, y, _ = geodetic_to_ecef_km(latitude, 0., 0.)
    return .2 / np.hypot(x, y) * ARCSECONDS


def predict(reader, prediction):
    cutoff = prediction["causal_cutoff_utc_ns"]
    snapshots = past_snapshots(reader, cutoff)
    banks = [bank_before(reader, snapshot) for snapshot in snapshots]
    transitions = []
    for index in range(1, len(banks)):
        old, new = snapshots[index - 1:index + 1]
        rows, counts = fitted_rows(banks[index - 1], banks[index], new.collected_utc_ns,
                                  strictly_newer=True)
        elapsed = (new.collected_utc_ns - old.collected_utc_ns) / (3600 * NS)
        transitions.append(summarize(rows, slice(None)) | counts | {
            "from": old.digest, "to": new.digest, "elapsed_hours": elapsed,
        })
    forecast = rate_forecast(transitions)
    rate = forecast["training_rate_arcsec_per_hour"] if forecast["qualified"] else 0.
    last = snapshots[-1].collected_utc_ns
    sites = {}
    for name, row in prediction["sites"].items():
        age = (row["origin_utc_ns"] - last) / (3600 * NS)
        lat = row["faces"][0][0]
        sites[name] = dict(yaw_200m_arcsec=required_yaw(lat), prediction_arcsec=rate * age,
                           nominal_collection_age_hours=age, faces=row["faces"])
    nominal = causal_catalogue(reader, cutoff)
    pins = sorted({r["snapshot_digest"] for r in nominal.provenance})
    return dict(curves_sha256=CURVES_SHA256, cutoff_utc_ns=cutoff, nominal_snapshots=pins,
                history=[dict(digest=s.digest, collected_utc_ns=s.collected_utc_ns)
                         for s in snapshots],
                pre_capture_transitions=transitions, forecast=forecast, sites=sites)


def face_curves(bank, row, angle_arcsec):
    # A spin rotation of the satellite states is equivalent to evaluating the
    # original bank at the observer shifted by the opposite longitude.
    angle_deg = angle_arcsec / 3600.
    sites = [geodetic_to_ecef_km(lat, lon - angle_deg, 0.) for lat, lon in row["faces"]]
    return np.concatenate([
        np.column_stack([causal.frequency(
            bank[track["norad"]], row["origin_utc_ns"], np.asarray(track["times"]),
            track["rf"], site,
        ) for site in sites])
        for track in row["tracks"]
    ])


def face_comparison(row, nominal, later, angles):
    _, _, _, design = support(row["tracks"])
    truth, _ = study.project(design, face_curves(later, row, 0.))
    saved = np.concatenate([track["predictions"]["nominal"] for track in row["tracks"]])[:, [0, 2]]
    if not np.allclose(face_curves(nominal, row, 0.), saved, rtol=0, atol=1e-8):
        raise ValueError("Unrotated predictions differ from the earlier causal lock")
    output = {}
    for name, angle in angles.items():
        forecast, _ = study.project(design, face_curves(nominal, row, angle))
        losses = [[study.rms(y - x) for x in forecast.T] for y in truth.T]
        output[name] = dict(
            yaw_arcsec=angle, rms_hz=losses,
            chosen=["A" if a < b else "B" if b < a else "tie" for a, b in losses],
        )
    return output


def score(reader, prediction, locked):
    cutoff = prediction["causal_cutoff_utc_ns"]
    causal_bank = causal_catalogue(reader, cutoff)
    if (locked["curves_sha256"] != CURVES_SHA256 or locked["cutoff_utc_ns"] != cutoff
            or sorted({r["snapshot_digest"] for r in causal_bank.provenance})
            != locked["nominal_snapshots"]):
        raise ValueError("The causal bank changed after the yaw lock")
    nominal = causal_bank.catalogue
    bank = dict(zip(nominal.satellite_numbers, nominal.satellites, strict=True))
    later, authority = study.later_elements()
    starts = [row["origin_utc_ns"] for row in prediction["sites"].values()]
    if authority["collection_utc_ns"] <= max(starts) + STATE_TIMES_NS[-1]:
        raise ValueError("Expected the scoring-only after-capture generator orbit")
    later_catalogue = ElementSetCatalogue(
        tuple(map(str, later)), tuple(later), tuple(later.values()),
    )
    rows, counts = fitted_rows(nominal, later_catalogue, min(starts), strictly_newer=False)
    oracle = summarize(rows, slice(None))
    revised = summarize(rows, rows["updated"])
    results = {}
    for site, row in prediction["sites"].items():
        proposed, scale = (locked["sites"][site][name]
                           for name in ("prediction_arcsec", "yaw_200m_arcsec"))
        local = summarize(rows, np.isin(rows["norad"], [t["norad"] for t in row["tracks"]]))
        angles = dict(nominal=0., causal=proposed, reversed_causal=-proposed,
                      oracle_fleet=oracle["common_yaw_arcsec"],
                      oracle_updated_fleet=revised["common_yaw_arcsec"],
                      plus_200m=scale, minus_200m=-scale)
        results[site] = dict(
            faces=row["faces"], yaw_200m_arcsec=scale, selected_orbit_yaw=local,
            predictions=face_comparison(row, bank, later, angles),
        )
    return dict(later=authority, orbit_fit_counts=counts, oracle_fleet=oracle,
                oracle_revised_fleet=revised, sites=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="stage", required=True)
    for stage in ("predict", "score"):
        command = commands.add_parser(stage)
        command.add_argument("archive", type=Path)
        command.add_argument("lock", type=Path)
        if stage == "score":
            command.add_argument("sha256")
    args = parser.parse_args()
    reader, prediction = TleArchiveReader(args.archive), curves()
    if args.stage == "predict":
        output = predict(reader, prediction)
        raw = json.dumps(output, sort_keys=True, allow_nan=False).encode()
        with args.lock.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        locked = causal.checked_lock(args.lock, args.sha256)
        result = score(reader, prediction, locked)
        print(json.dumps(dict(lock_sha256=args.sha256, **result), allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
