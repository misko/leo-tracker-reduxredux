"""Rebuild the sky and the observations at distant, deliberately unseen regional centers."""

import argparse
from collections import defaultdict
import json

import numpy as np

from models import CONFIG, cold, identity, latlon, run_models, save, tile


def catalog(path, cutoff, causal):
    stamp, digest = path.stem.split("-")
    assert identity(path) == digest
    parsed = cold.parse_element_sets(path.read_text())
    clock = cutoff if causal else int(stamp)
    oldest = clock - 48 * 3600 * 10**9
    return {sat.satnum: sat for sat, name, epoch in zip(
        parsed.satellites, parsed.names, parsed.element_epoch_utc_ns(), strict=True)
        if "STARLINK" in name.upper() and oldest <= epoch <= clock}


def changed_elements(a, b):
    return (a.jdsatepoch, a.jdsatepochF, a.no_kozai) != (b.jdsatepoch, b.jdsatepochF, b.no_kozai)


def snapshots(case, cutoff, material=False):
    def stamp(path):
        return int(path.name.split("-")[0])
    local = sorted((cold.INPUT / case / "tle").rglob("*.tle"), key=stamp)
    limit = 3600 * 10**9
    before = max((p for p in local if cutoff - 48*limit <= stamp(p) <= cutoff), key=stamp)
    pool = {p.name: p for c in CONFIG["real_cases"] for p in (cold.INPUT/c/"tle").rglob("*.tle")}
    future = [p for p in pool.values() if 12*limit <= stamp(p)-cutoff <= 36*limit
              and p.stem.split("-")[1] != before.stem.split("-")[1]]
    if not material:
        return before, min(future, key=stamp)
    baseline = catalog(before, cutoff, True)
    seen = set()
    for path in sorted(future, key=stamp):
        fingerprint = path.stem.split("-")[1]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        later = catalog(path, cutoff, False)
        common = baseline.keys() & later.keys()
        if common and sum(changed_elements(baseline[k], later[k]) for k in common) >= .8*len(common):
            return before, path
    raise ValueError(f"No materially updated forecast in the declared window for {case}")


def orbit_pair(case, meta, material):
    cutoff = meta["causal_cutoff_utc_ns"]
    paths = snapshots(case, cutoff, material)
    maps = [catalog(p, cutoff, causal=(i == 0)) for i, p in enumerate(paths)]
    common = np.array(sorted(maps[0].keys() & maps[1].keys()), dtype=int)
    sats = [[mapping[int(i)] for i in common] for mapping in maps]
    times = np.arange(0., 316., 15.)
    states = [cold.state(group, meta["anchor_utc_ns"], times) for group in sats]
    valid = np.logical_and.reduce([(err == 0).all(axis=1) for err, _, _ in states])
    ids = common[valid]
    local_sats = [[sat for j, sat in enumerate(group) if valid[j]] for group in sats]
    changed = np.array([changed_elements(a,b) for a,b in zip(*local_sats, strict=True)])
    return dict(paths=[p.name for p in paths], ids=ids, sats=local_sats, changed=changed,
                coarse_times=times, coarse_positions=[p[valid] for _, p, _ in states])


def schedule(case):
    native = cold.read(cold.INPUT / case / "native.json")
    source = native["source"]
    zero = native["clock_anchor"]["sample_counter"]
    lanes = defaultdict(list)
    for p in source["probes"]:
        lane = (p["receiver_id"]+1, p["channel"], p["actual_rf_hz"])
        lanes[lane].append((p["valid_start_counter"]-zero)/source["sample_rate_hz"] + source["probe_ms"]/2000.)
    return [(key, np.array(sorted(set(slots)))) for key, slots in sorted(lanes.items())]


def line_of_sight(position, velocity, observer, carrier):
    delta = position - observer
    length = np.linalg.norm(delta, axis=-1)
    return -(carrier / 299792.458) * np.sum(velocity*delta, axis=-1)/length


def sky_mask(pair, observer, frame, west_only):
    eligible = []
    for points in pair["coarse_positions"]:
        delta = points - observer
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        valid = direction @ frame[2] > np.sin(np.deg2rad(12.))
        if west_only:
            valid &= direction @ frame[0] < 0.
        eligible.append(valid)
    return eligible[0] & eligible[1]


def add_track(document, lane, times, freq):
    y = freq - cold.PERIOD * np.rint(freq[0]/cold.PERIOD)
    n = len(document["tracks"])
    centered = times - times.mean()
    residual = y - y.mean() - centered*(centered @ (y-y.mean()) / (centered @ centered))
    if np.sqrt(np.mean(residual**2)) >= 250.:
        document["curved_indices"].append(n)
    document["tracks"].append(dict(receiver=lane[0], channel=lane[1], rf_hz=lane[2],
                                   times=times, values=y))


def station_geometry(position, height_km):
    return cold.geodetic_to_ecef_km(*position, altitude_m=1000. * height_km), cold.ecef_to_enu_matrix(*position)


def scenes(pair, lanes, anchor, position, height, west_only, seed):
    rng = np.random.default_rng(seed)
    observer, frame = station_geometry(position, height)
    visible = sky_mask(pair, observer, frame, west_only)
    lane_offsets = rng.uniform(-16000., 16000., 4)
    lane_rates = rng.uniform(-2., 2., 4)
    tx_offsets = rng.normal(0., 180., len(pair["ids"]))
    phase = rng.normal(0., .7, len(pair["ids"]))
    c = rng.uniform(-24000., 24000.)
    docs = [dict(tracks=[], curved_indices=[]) for _ in range(2)]
    owners, updated, comparisons = [], [], []
    for attempt in range(48*6):
        if len(owners) == 48:
            break
        lane, available = lanes[attempt % len(lanes)]
        width = rng.uniform(28., 85.)
        start = rng.uniform(.1, 299.-width)
        times = available[(available >= start) & (available <= start+width)]
        if len(times) < 28:
            continue
        size = min(len(times), int(rng.integers(28, 75)))
        times = np.sort(rng.choice(times, size=size, replace=False))
        ix = np.clip(np.rint(np.array([times[0], times.mean(), times[-1]])/15).astype(int),
                     0, visible.shape[1]-1)
        possible = np.flatnonzero(visible[:, ix].all(axis=1))
        if not len(possible):
            continue
        choice = int(rng.choice(possible))
        row = 2*(lane[0]-1) + int(lane[1] > 4)
        unit_t = (times-times.mean())/np.ptp(times)
        disturbance = (lane_offsets[row] + lane_rates[row]*(times-150.) + c*(lane[2]/1e9-11.5)
                       + tx_offsets[choice] + rng.normal(0., 85., size) + rng.normal(0., 180.)*unit_t**2)
        corrupt = len(owners) % 8 == 7
        if corrupt:
            disturbance += rng.choice((-1., 1.))*7000. + rng.uniform(-10000., 10000.)*unit_t**2
        owners.append(None if corrupt else int(pair["ids"][choice]))
        updated.append(bool(pair["changed"][choice]))
        signal = []
        for doc, satrows in zip(docs, pair["sats"], strict=True):
            err, p, v = cold.state([satrows[choice]], anchor, times+phase[choice])
            if np.any(err):
                raise RuntimeError("Unpropagatable orbit after the coarse screen")
            ideal = line_of_sight(p[0], v[0], observer, lane[2])
            signal.append(ideal)
            add_track(doc, lane, times, ideal + disturbance)
        comparisons.extend(np.abs(signal[0]-signal[1]).tolist())
    return docs, owners, dict(generated=len(owners), updated_elements=sum(updated),
                              median_paired_orbit_difference_hz=float(np.median(comparisons)) if comparisons else None,
                              injected_c_hz_per_ghz=float(c))


def main(material, confirmation=False):
    rows = []
    cases = CONFIG["confirmation_cases"] if confirmation else CONFIG["synthetic_cases"]
    centers = CONFIG["confirmation_centers_latlon"] if confirmation else CONFIG["synthetic_centers_latlon"]
    for epoch, case in enumerate(cases):
        graph_path = cold.GRAPHS / f"{case}.json"
        # The generator takes only the public time, duration and visits from the archive.
        # It never takes a measured frequency, detected track, or satellite identity from DS26.
        meta = json.loads(graph_path.read_bytes())["metadata"]
        pair = orbit_pair(case, meta, material)
        visits = schedule(case)
        for region_index, (region, center) in enumerate(centers.items()):
            with tile(center):
                bank, receipt = cold.build_bank(case, meta, check_approximation=False)
            assert pair["paths"][0] == receipt["snapshot"]
            for index, offset in enumerate(CONFIG["synthetic_offsets_east_north_km"]):
                seed = CONFIG["seed"] + 100*epoch + index
                if confirmation:
                    seed += 91000 + 1000*region_index
                    jitter = np.random.default_rng(seed+22000).uniform(1.,11.5,2)
                    offset = (np.sign(offset)*jitter).tolist()
                truth = latlon(center, offset)
                height = 1.2 if (epoch + index) % 2 else 0.
                west_only = bool((epoch + index//2) % 2)
                docs, owners, simulation = scenes(pair, visits, meta["anchor_utc_ns"],
                                                  truth, height, west_only, seed)
                for mode, doc in zip(CONFIG["synthetic_orbits"], docs, strict=True):
                    methods = run_models(doc, bank, center, owners=owners, refine=confirmation)
                    rows.append(dict(case=case, region=region, orbit_mode=mode, offset=offset, seed=seed,
                                     truth=truth, center=center, altitude_km=height, west_only=west_only,
                                     solver_snapshot=pair["paths"][0], generator_snapshot=pair["paths"][int(mode=="later")],
                                     regional_candidates=receipt["regional"], clean_owners=sum(i is not None for i in owners),
                                     curved=len(doc["curved_indices"]), simulation=simulation, methods=methods))
            print(case, region, flush=True)
    filename = "confirmation-predictions.json" if confirmation else (
        "updated-orbit-predictions.json" if material else "synthetic-predictions.json")
    save(filename, rows)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--updated-catalogues", action="store_true")
    cli.add_argument("--confirmation", action="store_true")
    args = cli.parse_args()
    main(args.updated_catalogues or args.confirmation, args.confirmation)
