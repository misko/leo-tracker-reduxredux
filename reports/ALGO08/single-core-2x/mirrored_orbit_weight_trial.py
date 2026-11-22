"""Lock historical satellite weights before comparing them to the later orbit."""

import argparse
import gzip
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.localization_v3_inputs import prepare_phase_history
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import range_epoch_model
from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser


causal_trial = import_module("reports.ALGO08.single-core-2x.mirrored_causal_forecast_trial")
study = causal_trial.study
CURVES_SHA256 = "75cecc2db2b605fce456ecf3094de8907a4f86d710d26199e81f97b75e18f3a5"


def curves():
    path = study.inputs.MEASUREMENTS / "mirrored-causal-prediction.json.gz"
    raw = gzip.decompress(path.read_bytes())
    if sha256(raw).hexdigest() != CURVES_SHA256:
        raise ValueError("The original causal curves differ from their lock")
    return json.loads(raw)


def support(tracks):
    count = [len(track["times"]) for track in tracks]
    owners = np.repeat([track["norad"] for track in tracks], count)
    receivers = np.repeat([track["receiver"] for track in tracks], count)
    times = np.concatenate([track["times"] for track in tracks])
    tangent = np.concatenate([track["tangent"] for track in tracks])
    groups = np.repeat(np.eye(len(tracks)), count, axis=0)
    drift = np.equal.outer(receivers, np.unique(receivers)) * ((times - times.mean()) / 150.)[:, None]
    phase = np.equal.outer(owners, np.unique(owners)) * tangent[:, None]
    return owners, receivers, times, np.column_stack((groups, drift, phase))


def masses(variance, stereo_mse):
    if not np.isfinite(stereo_mse) or stereo_mse <= 0:
        raise ValueError("Expected a measured positive stereo variance floor")
    inverse = {n: 1 / (v + stereo_mse) for n, v in variance.items()}
    total = sum(inverse.values())
    return {n: mass / total for n, mass in inverse.items()}


def weights(locked, native, archive, configuration):
    cutoff = locked["causal_cutoff_utc_ns"]
    parser = CausalPreparationParser()
    current = causal_catalogue(archive, cutoff, element_parser=parser)
    satellite = dict(zip(current.catalogue.satellite_numbers, current.catalogue.satellites, strict=True))
    epochs = {row["norad"]: row["element_epoch_utc_ns"] for row in current.provenance}
    selected = {str(track["norad"]): None for row in locked["sites"].values() for track in row["tracks"]}
    history = prepare_phase_history(archive, selected, dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff),
                                    element_parser=parser)["past_versions"]
    result = {}
    for site, row in locked["sites"].items():
        graph, associations, faces, pin = causal_trial.public_inputs(site, native[site], configuration)
        if faces.tolist() != row["faces"] or pin != row["native_sha256"]:
            raise ValueError("Graph science differs from the prediction lock")
        active = [track for track in graph["tracks"] if associations[track["key"]] is not None]
        owners, receivers, times, design = support(row["tracks"])
        now = row["origin_utc_ns"]
        midpoint = geodetic_to_ecef_km(*faces.mean(axis=0), 0.)
        previous = {}
        for number in np.unique(owners):
            receipt, old, _ = causal_trial.receipts(satellite[number], epochs[number], history[str(number)], now)
            if old is None:
                raise ValueError("The predicted satellite lacks a usable past revision")
            previous[number] = old, receipt["previous_epoch_gap_s"]
        historical, channels, observed = [], [], []
        for track, saved in zip(active, row["tracks"], strict=True):
            number = associations[track["key"]]
            t = np.asarray(saved["times"])
            if (number != saved["norad"] or track["rf_hz"] != saved["rf"] or track["receiver"] != saved["receiver"]
                    or not np.array_equal(track["times"], t)):
                raise ValueError("Graph track order differs from the prediction lock")
            old = causal_trial.frequency(previous[number][0], now, t, saved["rf"], midpoint)
            historical.extend(np.asarray(saved["predictions"]["nominal"])[:, 1] - old)
            observed.extend(track["values"])
            channels.extend([track["channel"]] * len(t))
        projected, _ = study.project(design, np.asarray(historical))
        variance = {int(number): float(np.mean(projected[owners == number] ** 2)) for number in previous}
        first, second = study.simultaneous_pairs(owners, channels, times, receivers)
        observed = np.asarray(observed)
        difference = range_epoch_model.wrap(observed[first] - observed[second], range_epoch_model.FOLD_HZ)
        paired, _ = study.project(design[first] - design[second], difference / np.sqrt(2.))
        stereo_mse = float(np.mean(paired ** 2))
        result[site] = dict(stereo_mse=stereo_mse, pairs=len(first), variance=variance,
                            epoch_gap_s={int(n): gap for n, (_, gap) in previous.items()},
                            orbit_masses=masses(variance, stereo_mse))
    return dict(curves_sha256=CURVES_SHA256, sites=result)


def score_by_satellite(errors, owners, weight):
    satellites = np.unique(owners)
    scores = [np.mean(errors[owners == n] ** 2, axis=0) for n in satellites]
    return np.sqrt(np.average(scores, axis=0, weights=[weight[int(n)] for n in satellites])).tolist()


def compare(geometry, weight_lock, later):
    output = {}
    for site, row in geometry["sites"].items():
        tracks, now = row["tracks"], row["origin_utc_ns"]
        observers = [geodetic_to_ecef_km(*face, 0.) for face in row["faces"]]
        owners, _, _, design = support(tracks)
        truth = np.concatenate([np.stack([causal_trial.frequency(later[track["norad"]], now,
                                        np.asarray(track["times"]), track["rf"], observer)
                                        for observer in observers], axis=1) for track in tracks])
        predictions = np.concatenate([np.asarray(track["predictions"]["nominal"])[:, [0, 2]] for track in tracks])
        matrices = np.column_stack((predictions, truth))
        masses_by_mode = dict(equal={int(n): 1. for n in np.unique(owners)},
                              historical={int(n): w for n, w in weight_lock["sites"][site]["orbit_masses"].items()})
        results = {}
        for mode, weight in masses_by_mode.items():
            def score(keep):
                projected, _ = study.project(design[keep], matrices[keep])
                return {label: score_by_satellite(projected[:, :2] - projected[:, i+2:i+3], owners[keep], weight)
                        for i, label in enumerate(("A", "B"))}

            fitted = score(np.ones(len(owners), dtype=bool))
            held = {int(n): score(owners != n) for n in np.unique(owners)}
            results[mode] = dict(scores_hz=fitted, held_satellite_scores_hz=held)
        output[site] = results
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    lock = sub.add_parser("weights")
    for name in ("north", "south", "archive", "track_config", "output"):
        lock.add_argument(name, type=Path)
    score = sub.add_parser("score")
    score.add_argument("lock", type=Path)
    score.add_argument("sha256")
    args = parser.parse_args()
    predictions = curves()
    if args.action == "weights":
        config = TrackConfig(**study.inputs.verified(args.track_config, study.arrival.TRACK_CONFIG)["config"])
        result = weights(predictions, dict(north=args.north, south=args.south), TleArchiveReader(args.archive), config)
        raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        frozen = causal_trial.checked_lock(args.lock, args.sha256)
        if frozen["curves_sha256"] != CURVES_SHA256:
            raise ValueError("Satellite weights were computed on different curves")
        later, authority = study.later_elements()
        if authority["collection_utc_ns"] <= max(row["origin_utc_ns"] for row in predictions["sites"].values()):
            raise ValueError("The evaluation revision does not follow both captures")
        print(json.dumps(dict(weights_sha256=args.sha256, later=authority,
                              sites=compare(predictions, frozen, later)), allow_nan=False, indent=2))
