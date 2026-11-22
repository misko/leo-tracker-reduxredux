"""Compare one causal and one later orbit model on fixed public face pairs."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
import json
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import cold_scenes, range_epoch_model
from tools.pipeline_eval.qualification.waveform_site_trial import revised


arrival = import_module("reports.ALGO08.single-core-2x.mirrored_arrival_trial")
inputs = arrival.inputs
FACE_STEP_KM = .2
PHASE_STEP_S = .05


@dataclass(frozen=True)
class AlongOrbit:
    satellite: object
    phase_s: float

    def sgp4_array(self, julian, fraction):
        return self.satellite.sgp4_array(julian, fraction + self.phase_s / 86400.)


def project(design, values):
    fitted, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ fitted, int(rank)


def rms(values):
    return float(np.sqrt(np.mean(np.square(values))))


def face_comparison(causal, later):
    """Compare four noiseless oracle/causal alternatives in one projected space."""
    shift = later[:, 2] - later[:, 0]
    mismatch = later[:, 1] - causal[:, 1]
    information = shift @ shift
    return dict(
        signature_hz={"causal": rms(causal[:, 2] - causal[:, 0]), "later": rms(shift)},
        orbit_update_hz={label: rms(later[:, i] - causal[:, i])
                         for i, label in enumerate(("A", "midpoint", "B"))},
        midpoint_error_along_later_signature_m=float(1000 * FACE_STEP_KM * (mismatch @ shift) / information)
        if information else None,
        noiseless_control_hz={label: [rms(later[:, i] - later[:, j]) for j in (0, 2)]
                              for i, label in ((0, "A"), (2, "B"))},
        noiseless_causal_hz={label: [rms(later[:, i] - causal[:, j]) for j in (0, 2)]
                             for i, label in ((0, "A"), (2, "B"))},
    )


def simultaneous_pairs(owners, channels, times, receivers):
    groups = defaultdict(dict)
    for index, (owner, channel, time, receiver) in enumerate(zip(owners, channels, times, receivers, strict=True)):
        key = (owner, channel, time)
        if receiver in groups[key]:
            raise ValueError("Duplicate same-receiver observation at a paired epoch")
        groups[key][receiver] = index
    pairs = [(row[1], row[2]) for row in groups.values() if row.keys() == {1, 2}]
    if not pairs:
        raise ValueError("No simultaneous same-orbit and same-channel observations")
    return np.asarray(pairs).T


def later_elements():
    original = json.loads(cold_scenes.SNAPSHOT.read_bytes())
    received = cold_scenes._stamp(datetime.fromisoformat(original["retrieved_at"]))
    later, collected, authority = revised(received, cold_scenes.CATALOG_SHA256)
    elements = {sat.satnum: sat for sat in cold_scenes._constellation(later, collected)}
    return elements, authority


def measure(site, native, archive, track_config):
    pin = inputs.PINS[site][2]
    configuration = TrackConfig(**inputs.verified(track_config, arrival.TRACK_CONFIG)["config"])
    graph = prepare_tracks(inputs.verified(native, pin), configuration)
    anchor = arrival.pinned_packet("regional-reassignment.json.gz")[f"{site}-containing"]
    mirrors = arrival.pinned_packet("region-mirrors.json.gz")["sites"][site]
    if any(row["native_sha256"] != pin or row["snapshots"] != anchor["snapshots"]
           for row in (anchor, *mirrors.values())):
        raise ValueError("Offers do not bind the same capture-time scientific inputs")
    frozen = max((p for p in anchor["points"] if p["side"] == "inside"), key=lambda p: p["score"])
    offers = sorted((row["offer"] for row in mirrors.values()), key=lambda offer: offer["center"])
    faces = arrival.paired_faces(offers, frozen["latlon"])
    locations = np.asarray([faces[0], faces.mean(axis=0), faces[1]])
    observers = [geodetic_to_ecef_km(*location, 0.) for location in locations]
    cutoff = graph["metadata"]["causal_cutoff_utc_ns"]
    utc = graph["metadata"]["anchor_utc_ns"]
    prepared = causal_catalogue(TleArchiveReader(archive), cutoff)
    snapshots = sorted({row["snapshot_digest"] for row in prepared.provenance})
    if snapshots != anchor["snapshots"]:
        raise ValueError("Capture-time TLE authority differs from the earlier score")
    catalogue = prepared.catalogue
    causal = dict(zip(catalogue.satellite_numbers, catalogue.satellites, strict=True))
    later, authority = later_elements()
    if authority["collection_utc_ns"] <= cutoff:
        raise ValueError("The later scoring control unexpectedly meets the causal cutoff")
    selected = set(frozen["owners"].values()) - {None}
    unavailable = selected - (causal.keys() & later.keys())

    parts, track_ids, owners, times, receivers, channels, rf, observations = [], [], [], [], [], [], [], []
    for track in graph["tracks"]:
        norad = frozen["owners"][track["key"]]
        if norad is None or norad in unavailable:
            continue
        t = np.asarray(track["times"])
        frequency_scale = -track["rf_hz"] / cold_scenes.LIGHT_KM_S

        def prediction(orbit, observer):
            return frequency_scale * cold_scenes._signal(orbit, utc, t, observer)[1]

        orbit = causal[norad]
        tangent = (prediction(AlongOrbit(orbit, PHASE_STEP_S), observers[1])
                   - prediction(AlongOrbit(orbit, -PHASE_STEP_S), observers[1])) / (2 * PHASE_STEP_S)
        parts.append(np.column_stack((*(prediction(orbit, p) for p in observers),
                                      *(prediction(later[norad], p) for p in observers), tangent)))
        track_ids.extend([track["key"]] * len(t))
        owners.extend([norad] * len(t))
        times.extend(t)
        channels.extend([track["channel"]] * len(t))
        receivers.extend([track["receiver"]] * len(t))
        rf.extend([track["rf_hz"]] * len(t))
        observations.extend(track["values"])

    geometry = np.concatenate(parts)
    time = np.asarray(times)
    groups = np.equal.outer(track_ids, np.unique(track_ids)).astype(float)
    drift = np.equal.outer(receivers, np.unique(receivers)) * ((time - time.mean()) / 150.)[:, None]
    tangent = np.equal.outer(owners, np.unique(owners)) * geometry[:, -1, None]
    design = np.column_stack((groups, drift, tangent))
    lifted = range_epoch_model.wrap(np.asarray(observations) - geometry[:, 1], range_epoch_model.FOLD_HZ)
    lifted += geometry[:, 1]
    projected, rank = project(design, np.column_stack((geometry[:, :6], lifted)))
    stats = face_comparison(projected[:, :3], projected[:, 3:6])
    stats["conditional_measured_midpoint_rms_hz"] = [rms(projected[:, -1] - projected[:, i]) for i in (1, 4)]

    first, second = simultaneous_pairs(owners, channels, times, receivers)
    difference = range_epoch_model.wrap(np.asarray(observations)[first] - np.asarray(observations)[second],
                                        range_epoch_model.FOLD_HZ)
    paired, paired_rank = project(design[first] - design[second], difference / np.sqrt(2))
    calibration, _ = project(design, np.asarray(rf) / 1e9 - 11.5)
    if np.max(np.abs(calibration)) > 1e-9:
        raise ValueError("Track offsets did not absorb the fitted calibration column")
    return dict(site=site, faces=faces.tolist(), native_sha256=pin, causal_snapshots=snapshots,
                later_orbit=authority, unavailable_norads=sorted(unavailable),
                observations=len(time), tracks=groups.shape[1], satellites=tangent.shape[1],
                nuisance_rank=rank, simultaneous_pairs=len(first), differential_nuisance_rank=paired_rank,
                paired_receiver_proxy_rms_hz=rms(paired), calibration_projection_max=float(np.max(abs(calibration))),
                **stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", choices=inputs.PINS)
    for name in ("native", "archive", "track_config"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.site, args.native, args.archive, args.track_config), allow_nan=False, indent=2))
