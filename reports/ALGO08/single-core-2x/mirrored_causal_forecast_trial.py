"""Lock causal face predictions before accessing the later generator orbit."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from leo.analysis.localization_v3 import phase_prior, signed_phase
from leo.analysis.localization_v3.history_policy import validate_history
from leo.analysis.localization_v3.history_position import forecast_phase_mean
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application.localization_v3_engine import _json_value
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.localization_v3_inputs import prepare_phase_history
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km, julian_day_from_utc_ns
from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser


study = import_module("reports.ALGO08.single-core-2x.mirrored_ephemeris_trial")
MODES = ("nominal", "signed_phase", "rolling_state")


@dataclass(frozen=True)
class RollingState:
    nominal: object
    previous: object
    weight: float

    def sgp4_array(self, julian, fraction):
        error, position, velocity = self.nominal.sgp4_array(julian, fraction)
        old_error, old_position, old_velocity = self.previous.sgp4_array(julian, fraction)
        weight = np.where(old_error == 0, self.weight, 0.)[:, None]
        position_delta = np.where(old_error[:, None] == 0, position - old_position, 0.)
        velocity_delta = np.where(old_error[:, None] == 0, velocity - old_velocity, 0.)
        return error, position + weight * position_delta, velocity + weight * velocity_delta


def receipts(orbit, current_epoch, versions, origin):
    earlier = [row for row in versions if current_epoch - row["epoch"] >= 10**9]
    age = (origin - current_epoch) / 1e9
    report = dict(age_s=age, previous_epoch_gap_s=None, old_new_alignment_s=None, sigma_s=1.)
    if not earlier:
        return report, None, 0.
    last = earlier[-1]
    previous = Satrec.twoline2rv(*last["lines"])
    gap = (current_epoch - last["epoch"]) / 1e9
    jd, fr = julian_day_from_utc_ns(origin + np.array([0, 150, 300], dtype=np.int64) * 10**9)
    error, position, velocity = orbit.sgp4_array(jd, fr)
    old_error, old_position, _ = previous.sgp4_array(jd, fr)
    if np.any(error) or np.any(old_error):
        return report, None, 0.
    alignment = float(np.median(np.sum((old_position - position) * velocity, axis=1)
                                / np.sum(velocity * velocity, axis=1)))
    report.update(previous_epoch_gap_s=gap, old_new_alignment_s=alignment,
                  sigma_s=phase_prior.causal_phase_sigma(alignment, age, gap))
    return report, previous, float(np.clip((age + 150.) / gap, 0., 2.))


def public_inputs(site, native, configuration):
    pin = study.inputs.PINS[site][2]
    graph = prepare_tracks(study.inputs.verified(native, pin), configuration)
    anchor = study.arrival.pinned_packet("regional-reassignment.json.gz")[f"{site}-containing"]
    mirrors = study.arrival.pinned_packet("region-mirrors.json.gz")["sites"][site]
    if any(row["native_sha256"] != pin or row["snapshots"] != anchor["snapshots"]
           for row in (anchor, *mirrors.values())):
        raise ValueError("Offers do not bind one capture-time scientific input")
    owners = max((p for p in anchor["points"] if p["side"] == "inside"), key=lambda p: p["score"])
    offers = sorted((row["offer"] for row in mirrors.values()), key=lambda offer: offer["center"])
    faces = study.arrival.paired_faces(offers, owners["latlon"])
    return graph, owners["owners"], faces, pin


def frequency(orbit, origin, times, rf, observer):
    return (-rf / study.cold_scenes.LIGHT_KM_S) * study.cold_scenes._signal(orbit, origin, times, observer)[1]


def predict(north, south, archive, track_config):
    config = TrackConfig(**study.inputs.verified(track_config, study.arrival.TRACK_CONFIG)["config"])
    public = {site: public_inputs(site, path, config) for site, path in (("north", north), ("south", south))}
    pre_rf = min((data[0]["metadata"] for data in public.values()), key=lambda row: row["causal_cutoff_utc_ns"])
    cutoff = pre_rf["causal_cutoff_utc_ns"]
    parser = CausalPreparationParser()
    catalogue = causal_catalogue(archive, cutoff, element_parser=parser)
    causal = dict(zip(catalogue.catalogue.satellite_numbers, catalogue.catalogue.satellites, strict=True))
    epochs = {row["norad"]: row["element_epoch_utc_ns"] for row in catalogue.provenance}
    history = prepare_phase_history(archive, {str(number): None for number in causal}, pre_rf, element_parser=parser)
    forecast = phase_prior.forecast(history)
    history_hash = sha256((json.dumps(history, sort_keys=True) + "\n").encode()).hexdigest()
    forecast["history_sha256"] = history_hash
    model, qualified = validate_history(history, forecast, case="SCAN", origin_utc_ns=pre_rf["anchor_utc_ns"],
                                        cutoff_utc_ns=cutoff, raw_sha256=history_hash)
    signed = signed_phase.qualify(forecast["transitions"], forecast["temporal_split_boundary_ns"],
                                  forecast["prefix_distribution"], model)
    del parser
    rows = {}
    for site, (graph, owners, faces, native_sha256) in public.items():
        origin = graph["metadata"]["anchor_utc_ns"]
        locations = [faces[0], faces.mean(axis=0), faces[1]]
        observers = [geodetic_to_ecef_km(*location, 0.) for location in locations]
        modifiers = {}
        for number in sorted(set(owners.values()) - {None}):
            receipt, before, weight = receipts(causal[number], epochs[number], history["past_versions"][str(number)], origin)
            mean = forecast_phase_mean([receipt], model["shrinkage"])
            mean = float(signed_phase.adjust_means(mean, [receipt], model, signed)[0])
            modifiers[number] = mean, before, weight
        tracks = []
        for track in graph["tracks"]:
            number = owners[track["key"]]
            if number is None:
                continue
            nominal = causal[number]
            mean, before, weight = modifiers[number]
            orbits = (nominal, study.AlongOrbit(nominal, mean) if mean else nominal,
                      RollingState(nominal, before, weight) if before is not None else nominal)
            times, rf = np.asarray(track["times"]), track["rf_hz"]
            phase_step = study.PHASE_STEP_S
            tangent = (frequency(study.AlongOrbit(nominal, phase_step), origin, times, rf, observers[1])
                       - frequency(study.AlongOrbit(nominal, -phase_step), origin, times, rf, observers[1])) / (2 * phase_step)
            projections = {mode: np.stack([frequency(orbit, origin, times, rf, observer) for observer in observers],
                                          axis=1).tolist() for mode, orbit in zip(MODES, orbits, strict=True)}
            tracks.append(dict(norad=number, times=times.tolist(), receiver=track["receiver"], rf=rf,
                               tangent=tangent.tolist(), predictions=projections))
        rows[site] = dict(native_sha256=native_sha256, origin_utc_ns=origin, faces=faces.tolist(), tracks=tracks,
                          modifiers={n: dict(phase_s=mean, previous_available=old is not None, weight=weight)
                                     for n, (mean, old, weight) in modifiers.items()})
    validation = dict(distribution_qualified=qualified, forecast_model=model, signed=signed,
                      history_sha256=history_hash, historic_rows=len(forecast["transitions"]),
                      released_validation=forecast["distribution_validation"],
                      nominal_validation=forecast["original_distribution_validation"])
    return dict(causal_cutoff_utc_ns=cutoff, sites=rows, validation=validation)


def evaluate(locked, later):
    output = {}
    for site, row in locked["sites"].items():
        faces, origin, tracks = np.asarray(row["faces"]), row["origin_utc_ns"], row["tracks"]
        observers = [geodetic_to_ecef_km(*coords, 0.) for coords in (faces[0], faces.mean(axis=0), faces[1])]
        count = [len(track["times"]) for track in tracks]
        owners = np.repeat([track["norad"] for track in tracks], count)
        receivers = np.repeat([track["receiver"] for track in tracks], count)
        times = np.concatenate([track["times"] for track in tracks])
        tangent = np.concatenate([track["tangent"] for track in tracks])
        groups = np.repeat(np.eye(len(tracks)), count, axis=0)
        drift = np.equal.outer(receivers, np.unique(receivers)) * ((times - times.mean()) / 150.)[:, None]
        phase = np.equal.outer(owners, np.unique(owners)) * tangent[:, None]
        design = np.column_stack((groups, drift, phase))
        truth = np.concatenate([np.stack([frequency(later[track["norad"]], origin, np.asarray(track["times"]),
                                                      track["rf"], observer) for observer in observers], axis=1)
                                for track in tracks])
        modes = {}
        for mode in MODES:
            raw = np.concatenate([track["predictions"][mode] for track in tracks])

            def scores(keep):
                values, _ = study.project(design[keep], np.column_stack((raw[keep], truth[keep])))
                score = study.face_comparison(values[:, :3], values[:, 3:])
                pairs = score["noiseless_causal_hz"]
                matches = {label: pair[i] < pair[1 - i] for i, (label, pair) in enumerate(pairs.items())}
                return score, matches

            result, matches = scores(np.ones(len(owners), dtype=bool))
            leave_out = {int(n): scores(owners != n)[1] for n in np.unique(owners)}
            modes[mode] = dict(full_matches=matches, leave_satellite_out=leave_out, **result)
        output[site] = modes
    return output


def checked_lock(path, pin):
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != pin:
        raise ValueError("Causal forecasts differ from their pre-reveal lock")
    return json.loads(contents)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    lock = sub.add_parser("predict")
    for name in ("north", "south", "archive", "track_config", "output"):
        lock.add_argument(name, type=Path)
    score = sub.add_parser("score")
    score.add_argument("lock", type=Path)
    score.add_argument("sha256")
    args = parser.parse_args()
    if args.action == "predict":
        locked = predict(args.north, args.south, TleArchiveReader(args.archive), args.track_config)
        raw = json.dumps(locked, sort_keys=True, default=_json_value, allow_nan=False).encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        locked = checked_lock(args.lock, args.sha256)
        later, authority = study.later_elements()
        if authority["collection_utc_ns"] <= max(row["origin_utc_ns"] for row in locked["sites"].values()):
            raise ValueError("The evaluation revision does not follow both captures")
        result = dict(lock_sha256=args.sha256, later=authority, validation=locked["validation"],
                      modifiers={site: row["modifiers"] for site, row in locked["sites"].items()},
                      sites=evaluate(locked, later))
        print(json.dumps(result, default=_json_value, allow_nan=False, indent=2))
