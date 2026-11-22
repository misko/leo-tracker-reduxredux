"""Compare held interval phase closure and fixed-owner geometric separations."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import ElementSetCatalogue
from tools.pipeline_eval.qualification import range_epoch_model as phase
from tools.pipeline_eval.qualification.range_epoch_trial import native_winners
from tools.pipeline_eval.variants.code_carrier import carrier_samples, predict


def partition(times):
    """Use prior interval limits and no shared endpoints between training and test."""
    cut = times[0] + 2 * (times[-1] - times[0]) / 3
    dt = np.diff(times)
    valid = (dt > 0) & (dt <= phase.GAP_S)
    train = valid & (times[1:] < cut)
    held = valid & (times[:-1] >= cut)
    return train, held


def controls(epoch, frequency, times, rate, rf):
    train, held = partition(times)
    if train.sum() < 4 or held.sum() < 2:
        return None
    use = train | held
    dt = np.diff(times)[use]
    period = rate / phase.FRAME_HZ
    code = phase.wrap(np.diff(epoch)[use], period)
    carrier = carrier_samples(frequency, np.diff(times), rf, rate)[use]
    x = dt[:, None]

    def estimate(curve):
        return predict(code, curve, x, train[use], phase.EPOCH_UNIT, period)[held[use]]

    return dict(positive=estimate(carrier), reflected=estimate(-carrier),
                clock_only=estimate(np.zeros_like(carrier))), int(train.sum()), held


def face(offer, other_center):
    """Intersect the offer boundary in the direction of another supplied point."""
    center = np.asarray(offer["center"])
    offset = np.asarray(other_center) - center
    scales = np.array([111., 111.32 * np.cos(np.deg2rad(center[0]))])
    norm = np.max(abs(offset * scales))
    return center + offset * ((offer["width_km"] / 2) / norm)


def public_geometry(receipt, opposite, far):
    original = receipt["offer"]
    first = face(original, np.asarray(original["center"]) * 2 - opposite["center"])
    second = face(opposite, original["center"])
    points = [first, second, face(far, first)]
    owners = max((p for p in receipt["points"] if p["side"] == "inside"),
                 key=lambda p: p["score"])["owners"]
    return owners, np.asarray([geodetic_to_ecef_km(*p, 0) for p in points])


def geometric_controls(counter, times, train, held, rate, orbit, sites):
    p, _, good = ecef_states(orbit, counter, times)
    if not good.all():
        raise ValueError("A fixed causal owner cannot be propagated")
    ranges = np.linalg.norm(p[0][None, :, :] - sites[:, None, :], axis=-1)
    delay = np.diff(ranges, axis=1) * rate / phase.LIGHT_KM_S
    dt = np.diff(times)
    x = dt[:, None]
    signals = {}
    for label, delta in zip(("mirror", "far"), delay[1:] - delay[0], strict=True):
        projected = delta - x @ np.linalg.lstsq(x[train], delta[train], rcond=None)[0]
        signals[label + "_raw"] = delta[held]
        signals[label + "_profiled"] = projected[held]
    period = rate / phase.FRAME_HZ
    # Geometry is reported through the same short-gap interval domain as carrier closure.
    if np.any(abs(delay[:, held]) >= period / 2):
        raise ValueError("Use circular range hypotheses inside the original frame period")
    return signals


def measure(document, configuration, geometry=None):
    graph = prepare_tracks(document, configuration)
    winners = native_winners(document)
    rate = document["source"]["sample_rate_hz"]
    groups = defaultdict(lambda: defaultdict(list))
    support = defaultdict(lambda: dict(tracks=0, train_intervals=0, held_intervals=0))
    for track in graph["tracks"]:
        rows = [winners[i] for i in track["observation_ids"]]
        time, frequency = track["times"], track["values"]
        for row, t, f in zip(rows, time, frequency, strict=True):
            if (row["rx"] != track["receiver"] or row["channel"] != track["channel"]
                    or row["rf_hz"] != track["rf_hz"] or abs(row["time_s"] - t) > 1e-9
                    or abs(phase.wrap(row["folded_hz"] - f, phase.FOLD_HZ)) > 1e-5):
                raise ValueError("Mismatch between Graph and its exact native timing factor")
        epochs = np.array([row["phase"] for row in rows])
        result = controls(epochs, frequency, time, rate, track["rf_hz"])
        if result is None:
            continue
        metrics, training, held = result
        lane = track["receiver"]
        for group in ("all", str(lane)):
            support[group]["tracks"] += 1
            support[group]["train_intervals"] += training
            support[group]["held_intervals"] += int(held.sum())
        if geometry is not None:
            assignments, sites, orbits = geometry
            owner = assignments[track["key"]]
            if owner in orbits:
                train, _ = partition(time)
                metrics.update(geometric_controls(graph["metadata"]["anchor_utc_ns"], time, train,
                                                   held, rate, orbits[owner], sites))
        for name, values in metrics.items():
            for group in ("all", str(lane)):
                groups[group][name].extend(values)

    def describe(values):
        value = np.asarray(values)
        return dict(count=len(value), rms=float(np.sqrt(np.mean(value**2))),
                    abs_median=float(np.median(abs(value))), abs_max=float(np.max(abs(value))))

    return dict(graph_tracks=len(graph["tracks"]), original_observations=len(winners),
                sample_rate_hz=rate, support=support,
                groups={group: {key: describe(values) for key, values in row.items()}
                        for group, row in groups.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("track_config", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("--public-geometry", nargs=4, type=Path, metavar=("ASSIGNMENTS", "MIRROR", "FAR", "ARCHIVE"))
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.sha256.removeprefix("sha256:"):
        raise ValueError("Native detection digest mismatch")
    document = json.loads(raw)
    geometry = None
    if args.public_geometry:
        assignment, mirror, far, archive = args.public_geometry
        receipt = json.loads(assignment.read_bytes())
        if receipt["native_sha256"] != args.sha256.removeprefix("sha256:"):
            raise ValueError("The fixed assignment came from different detection bytes")
        owners, sites = public_geometry(receipt, json.loads(mirror.read_bytes()), json.loads(far.read_bytes()))
        cutoff = document["clock_anchor"]["before"]["realtime_ns"]
        source = causal_catalogue(TleArchiveReader(archive), cutoff).catalogue
        orbits = {j: ElementSetCatalogue((name,), (j,), (sat,)) for j, name, sat in zip(
            source.satellite_numbers, source.names, source.satellites, strict=True) if j in owners.values()}
        geometry = owners, sites, orbits
    config = TrackConfig(**json.loads(args.track_config.read_bytes())["config"])
    print(json.dumps(dict(measure(document, config, geometry), native_sha256=args.sha256), allow_nan=False))


if __name__ == "__main__":
    main()
