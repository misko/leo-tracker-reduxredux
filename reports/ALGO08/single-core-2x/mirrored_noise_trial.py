"""Compare conditional face errors under two frozen stereo-noise controls."""

import argparse
import json
from hashlib import sha256
from math import erfc, sqrt
from pathlib import Path

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import range_epoch_model

from . import mirrored_causal_forecast_trial as causal
from .mirrored_orbit_weight_trial import CURVES_SHA256, curves, support

study = causal.study
SITES = ("north", "south")


def selected_tracks(site, row, native, config):
    graph, association, faces, pin = causal.public_inputs(site, native, config)
    if (faces.tolist() != row["faces"] or pin != row["native_sha256"]
            or graph["metadata"]["anchor_utc_ns"] != row["origin_utc_ns"]):
        raise ValueError("Saved detections do not match the sealed orbit predictions")
    selected = [track for track in graph["tracks"] if association[track["key"]] is not None]
    for track, frozen in zip(selected, row["tracks"], strict=True):
        if (association[track["key"]] != frozen["norad"]
                or track["receiver"] != frozen["receiver"] or track["rf_hz"] != frozen["rf"]
                or not np.array_equal(track["times"], frozen["times"])):
            raise ValueError("Saved signal rows differ from the sealed orbit support")
    return selected


def noise_inputs(prediction, native, track_config):
    settings = study.inputs.verified(track_config, study.arrival.TRACK_CONFIG)
    config = TrackConfig(**settings["config"])
    frozen = {}
    for site in SITES:
        row = prediction["sites"][site]
        selected = selected_tracks(site, row, native[site], config)
        owners, receivers, times, design = support(row["tracks"])
        channel = np.repeat([t["channel"] for t in selected], [len(t["times"]) for t in selected])
        values = np.concatenate([t["values"] for t in selected])
        first, second = study.simultaneous_pairs(owners, channel, times, receivers)
        difference = range_epoch_model.wrap(
            values[first] - values[second], range_epoch_model.FOLD_HZ,
        )
        noise, rank = study.project(design[first] - design[second], difference / 2)
        frozen[site] = dict(
            native_sha256=row["native_sha256"], first=first.tolist(), second=second.tolist(),
            stereo_difference_rank=rank, noise_proxy_hz=noise.tolist(),
        )
    return dict(curves_sha256=CURVES_SHA256, track_config_sha256=study.arrival.TRACK_CONFIG,
                sites=frozen)


def satellite_sign_distribution(noise, owners, axis):
    amplitudes = [float(noise[owners == satellite] @ axis[owners == satellite])
                  for satellite in np.unique(owners)]
    if len(amplitudes) > 20:
        raise ValueError("Too many independent signs for exact enumeration")
    scores = np.zeros(1)
    for amplitude in amplitudes:
        scores = np.concatenate((scores - amplitude, scores + amplitude))
    return scores


def template_risk(templates, source, noise, owners):
    """Compute the score and both conditional class risks for fixed templates."""
    direction = templates[:, 1] - templates[:, 0]
    distance = np.linalg.norm(direction)
    sigma = study.rms(noise)
    if not (np.isfinite(distance) and distance > 0 and np.isfinite(sigma) and sigma > 0):
        raise ValueError("Expected distinct finite prediction templates and measured noise")
    axis = direction / distance
    margin_hz = (source - templates.mean(axis=1)[:, None]).T @ axis
    signs = np.array([-1., 1.])  # Positive score denotes B.
    signed_margin = margin_hz * signs
    iid_error = [erfc(float(margin) / (sigma * sqrt(2.))) / 2. for margin in signed_margin]
    noise_scores = satellite_sign_distribution(noise, owners, axis)
    block_error = []
    for margin, sign in zip(margin_hz, signs, strict=True):
        trial = sign * (margin + noise_scores)
        block_error.append(float(np.mean(trial < 0) + .5 * np.mean(trial == 0)))
    return dict(
        template_separation_rms_hz=float(distance / sqrt(len(noise))),
        template_separation_over_iid_noise=float(distance / sigma),
        score_margin_hz=margin_hz.tolist(),
        margin_equivalent_m=(200. * margin_hz / distance).tolist(),
        noiseless_class=["A" if x < 0 else "B" if x > 0 else "tie" for x in margin_hz],
        iid_class_error=iid_error, iid_worst_error=max(iid_error),
        satellite_sign_class_error=block_error, satellite_sign_worst_error=max(block_error),
        satellite_sign_cases=len(noise_scores), satellite_sign_score_rms_hz=study.rms(noise_scores),
    )


def evaluate(prediction, noise_lock, later):
    results = {}
    for site in SITES:
        row, locked = prediction["sites"][site], noise_lock["sites"][site]
        if row["native_sha256"] != locked["native_sha256"]:
            raise ValueError("The noise input has a different saved waveform")
        tracks = row["tracks"]
        observers = [geodetic_to_ecef_km(*coords, 0.) for coords in row["faces"]]
        truth = np.concatenate([
            np.column_stack([causal.frequency(
                later[track["norad"]], row["origin_utc_ns"], np.asarray(track["times"]),
                track["rf"], observer,
            ) for observer in observers])
            for track in tracks
        ])
        owners, _, _, design = support(tracks)
        first, second = (np.asarray(locked[key]) for key in ("first", "second"))
        if not np.array_equal(owners[first], owners[second]):
            raise ValueError("Frozen stereo pairs have different satellite owners")
        nominal = np.concatenate([track["predictions"]["nominal"] for track in tracks])[:, [0, 2]]
        all_models = np.column_stack((nominal, truth))
        mean_design = (design[first] + design[second]) / 2
        mean_predictions = (all_models[first] + all_models[second]) / 2
        rf = np.repeat([track["rf"] for track in tracks], [len(track["times"]) for track in tracks])
        calibration = (rf[first] + rf[second]) / 2e9 - 11.5
        inputs = np.column_stack((mean_predictions, calibration))
        projected, rank = study.project(mean_design, inputs)
        calibration_residual = float(np.max(abs(projected[:, -1])))
        if calibration_residual > 1e-9:
            raise ValueError("Track offsets did not absorb the fitted calibration column")
        projected = projected[:, :-1]
        noise = np.asarray(locked["noise_proxy_hz"])
        measured, matched_owners = len(noise), owners[first]
        results[site] = dict(
            faces=row["faces"], simultaneous_pairs=measured, nuisance_rank=rank,
            satellites=len(np.unique(matched_owners)),
            stereo_average_noise_proxy_rms_hz=study.rms(noise),
            calibration_projection_max=calibration_residual,
            nominal=template_risk(projected[:, :2], projected[:, 2:], noise, matched_owners),
            oracle=template_risk(projected[:, 2:], projected[:, 2:], noise, matched_owners),
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    freeze = sub.add_parser("freeze")
    for name in (*SITES, "track_config", "output"):
        freeze.add_argument(name, type=Path)
    score = sub.add_parser("score")
    score.add_argument("lock", type=Path)
    score.add_argument("sha256")
    args = parser.parse_args()
    prediction = curves()
    if args.stage == "freeze":
        native = {site: getattr(args, site) for site in SITES}
        locked = noise_inputs(prediction, native, args.track_config)
        raw = json.dumps(locked, sort_keys=True, allow_nan=False).encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        locked = causal.checked_lock(args.lock, args.sha256)
        if locked["curves_sha256"] != CURVES_SHA256:
            raise ValueError("Noise was locked against a different orbit model")
        later, authority = study.later_elements()
        if authority["collection_utc_ns"] <= max(v["origin_utc_ns"]
                                                 for v in prediction["sites"].values()):
            raise ValueError("The scoring-only generator orbit does not follow both captures")
        print(json.dumps(dict(noise_sha256=args.sha256, curves_sha256=CURVES_SHA256,
                              later=authority, sites=evaluate(prediction, locked, later)),
                         indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
