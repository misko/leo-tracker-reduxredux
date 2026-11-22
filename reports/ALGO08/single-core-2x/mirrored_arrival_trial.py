"""Compare nominal causal range increments on held public pilot-arrival blocks."""

import argparse
from collections import defaultdict
import gzip
from hashlib import sha256
from importlib import import_module
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


arrival = import_module("reports.ALGO08.single-core-2x.arrival_observability_trial")
inputs = import_module("reports.ALGO08.single-core-2x.mirrored_height_trial")
PINS = {
    "regional-reassignment.json.gz": "735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a",
    "region-mirrors.json.gz": "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728",
}
TRACK_CONFIG = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
SEED = 750200
BLOCK_SECONDS = 8
HYPOTHESES = ("A", "B", "reflected_A", "reflected_B", "rate_only", "carrier", "reflected_carrier")


def pinned_packet(name):
    data = (inputs.MEASUREMENTS / name).read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError("Public orbit-owner or mirrored packet changed")
    return json.loads(gzip.decompress(data))


def assign_blocks(norad, occupied):
    rng = np.random.default_rng([SEED, norad])
    return {int(block): fold % 2 for fold, block in enumerate(rng.permutation(sorted(occupied)))}


def interval_blocks(times):
    time = np.asarray(times)
    block = np.floor(time / BLOCK_SECONDS).astype(int)
    dt = np.diff(time)
    return np.where((dt > 0) & (dt <= arrival.phase.GAP_S) & (block[:-1] == block[1:]), block[:-1], -1)


def held_residuals(code, models, dt, labels, period):
    results = []
    for fold in (0, 1):
        train, held = labels == 1 - fold, labels == fold
        if train.sum() < 4 or held.sum() < 2:
            continue
        residuals = {name: arrival.predict(code, model, dt[:, None], train,
                                           arrival.phase.EPOCH_UNIT, period)[held]
                     for name, model in models.items()}
        results.append((fold, held, residuals))
    return results


def paired_faces(offers, frequency_anchor):
    """Choose homologous faces in the direction of the fixed frequency-only anchor."""
    centres = np.asarray([offer["center"] for offer in offers])
    axis = int(np.argmax(np.abs(centres[1] - centres[0])))
    normal = np.zeros(2)
    normal[axis] = np.sign(frequency_anchor[axis] - centres[:, axis].mean())
    if not normal[axis]:
        raise ValueError("The frequency anchor cannot choose the challenged face")
    return np.asarray([arrival.face(offer, centre + normal)
                       for offer, centre in zip(offers, centres, strict=True)])


def summarize(held):
    per_satellite = {orbit: {model: float(np.mean(np.square(samples))) for model, samples in row.items()}
                     for orbit, row in sorted(held.items())}
    contrasts = np.array([row["B"] - row["A"] for row in per_satellite.values()])
    if len(contrasts) < 2:
        raise ValueError("At least two held NORAD groups are required")
    aggregate = {model: float(np.mean([row[model] for row in per_satellite.values()]))
                 for model in HYPOTHESES}
    leave_one = (np.sum(contrasts) - contrasts) / (len(contrasts) - 1)
    return dict(satellite_mse_samples2=per_satellite, aggregate_mse_samples2=aggregate,
                delta_B_minus_A_samples2=float(np.mean(contrasts)),
                satellite_votes=dict(A=int((contrasts > 0).sum()), B=int((contrasts < 0).sum()),
                                     tie=int((contrasts == 0).sum())),
                leave_one_satellite_out_samples2=[float(leave_one.min()), float(leave_one.max())])


def measure(site, native_path, archive, track_config):
    native_hash = inputs.PINS[site][2]
    native = inputs.verified(native_path, native_hash)
    config = TrackConfig(**inputs.verified(track_config, TRACK_CONFIG)["config"])
    graph = prepare_tracks(native, config)
    winners = arrival.native_winners(native)
    rate = native["source"]["sample_rate_hz"]
    period = rate / arrival.phase.FRAME_HZ
    anchor = pinned_packet("regional-reassignment.json.gz")[f"{site}-containing"]
    mirrored = pinned_packet("region-mirrors.json.gz")["sites"][site]
    if any(row["native_sha256"] != native_hash or row["snapshots"] != anchor["snapshots"]
           for row in (anchor, *mirrored.values())):
        raise ValueError("Public offers do not share timing and orbit authority")
    frozen = max((p for p in anchor["points"] if p["side"] == "inside"), key=lambda p: p["score"])
    ordered = sorted(mirrored.items(), key=lambda item: item[1]["offer"]["center"])
    coordinates = paired_faces([row["offer"] for _, row in ordered], frozen["latlon"])
    sites = np.asarray([geodetic_to_ecef_km(*point, 0.) for point in coordinates])
    # Labels join only after timing comparison. Restrict geometry to the same causal records.
    prepared = causal_catalogue(TleArchiveReader(archive), graph["metadata"]["causal_cutoff_utc_ns"])
    if sorted({row["snapshot_digest"] for row in prepared.provenance}) != anchor["snapshots"]:
        raise ValueError("The capture-time TLE authority differs from the earlier score")
    catalogue = prepared.catalogue
    orbit_index = dict(zip(catalogue.satellite_numbers, range(len(catalogue)), strict=True))

    tracks = defaultdict(list)
    for track in graph["tracks"]:
        orbit = frozen["owners"][track["key"]]
        if orbit is None:
            continue
        times, frequency = np.asarray(track["times"]), np.asarray(track["values"])
        rows = [winners[key] for key in track["observation_ids"]]
        for row, t, f in zip(rows, times, frequency, strict=True):
            if (row["rx"] != track["receiver"] or row["channel"] != track["channel"]
                    or row["rf_hz"] != track["rf_hz"] or abs(row["time_s"] - t) > 1e-9
                    or abs(arrival.phase.wrap(row["folded_hz"] - f, arrival.phase.FOLD_HZ)) > 1e-5):
                raise ValueError("Graph timing does not match the exact native winner")
        code = arrival.phase.wrap(np.diff([row["phase"] for row in rows]), period)
        carrier = arrival.carrier_samples(frequency, np.diff(times), track["rf_hz"], rate)
        tracks[orbit].append((track["key"], times, code, carrier, interval_blocks(times)))

    all_held, block_receipt = defaultdict(lambda: defaultdict(list)), {}
    support_tracks, held_blocks = set(), set()
    interval_count = 0
    for orbit, entries in sorted(tracks.items()):
        occupied = set(np.concatenate([entry[-1] for entry in entries])) - {-1}
        assignments = assign_blocks(orbit, occupied)
        block_receipt[orbit] = assignments
        j = orbit_index[orbit]
        one = ElementSetCatalogue((catalogue.names[j],), (orbit,), (catalogue.satellites[j],))
        times = np.unique(np.concatenate([entry[1] for entry in entries]))
        position, _, good = ecef_states(one, graph["metadata"]["anchor_utc_ns"], times)
        if not good.all():
            raise ValueError("Causal timing orbit was unavailable")
        ranges = np.linalg.norm(position[0][None, :, :] - sites[:, None, :], axis=-1)
        for key, t, code, carrier, blocks in entries:
            use = blocks >= 0
            delays = np.diff(ranges[:, np.searchsorted(times, t)], axis=1)[:, use] * rate / arrival.phase.LIGHT_KM_S
            if np.any(np.abs(delays) >= period / 2):
                raise ValueError("Range increment left the original frame interval")
            a, b = delays
            models = dict(zip(HYPOTHESES, (a, b, -a, -b, np.zeros_like(a), carrier[use], -carrier[use]), strict=True))
            labels = np.array([assignments[value] for value in blocks[use]], dtype=int)
            for _, held, residuals in held_residuals(code[use], models, np.diff(t)[use], labels, period):
                support_tracks.add(key)
                interval_count += int(held.sum())
                held_blocks.update((orbit, int(value)) for value in blocks[use][held])
                for name, residual in residuals.items():
                    all_held[orbit][name].extend(residual)

    summary = summarize(all_held)
    mse = summary["aggregate_mse_samples2"]
    contrast = summary["delta_B_minus_A_samples2"]
    preferred = "A" if contrast > 0 else "B" if contrast < 0 else None
    lo, hi = summary["leave_one_satellite_out_samples2"]
    stable = (lo > 0 if preferred == "A" else hi < 0) if preferred else False
    beats_controls = preferred is not None and mse[preferred] < min(mse[k] for k in ("rate_only", "reflected_A", "reflected_B"))
    public_labels = dict(zip(("A", "B"), (label for label, _ in ordered), strict=True))
    return dict(site=site, native_sha256=native_hash, seed=SEED, block_seconds=BLOCK_SECONDS,
                block_assignments=block_receipt, tracks_scored=len(support_tracks), block_groups_scored=len(held_blocks),
                intervals_scored=interval_count, satellite_groups_scored=len(all_held), coordinates=coordinates.tolist(),
                public_labels=public_labels, preferred=preferred, stable=stable, beats_controls=beats_controls,
                correctly_prefers_containing=public_labels.get(preferred) == "inside", **summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", choices=inputs.PINS)
    for name in ("native", "archive", "track_config"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.site, args.native, args.archive, args.track_config), allow_nan=False, indent=2))
