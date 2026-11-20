"""Generate and seal an independent SGP4 holdout. Run from the repository venv."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import secrets
import tempfile

import numpy as np
from sgp4.api import Satrec, SatrecArray, WGS72


PRIVATE = Path(__file__).resolve().parent
ROOT = PRIVATE.parent
PUBLIC = ROOT / "public_synthetic"
RECEIPT = ROOT / "holdout-receipt.json"
PROTOCOL = PRIVATE / "protocol.json"
CONFIG = json.loads(PROTOCOL.read_bytes())
ARCHIVE = Path(CONFIG["archive_tle"])
NATIVE = Path(CONFIG["archive_native"])
NS = 10**9
HOUR = 3600 * NS
DAY = 24 * HOUR
DURATION = CONFIG["capture_duration_s"]
EARTH_KM = 6371.0088
C_KM_S = 299792.458
OMEGA = 7.29211514670698e-5
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def packed(document):
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(path, data):
    with path.open("xb") as dst:
        dst.write(data)


def timestamp(value):
    elapsed = datetime.fromisoformat(value) - EPOCH
    return (elapsed.days * 86400 + elapsed.seconds) * NS + 1000 * elapsed.microseconds


def identifier(rng):
    return rng.bytes(16).hex()


def move(center, bearing, km):
    lat, lon = np.deg2rad(center)
    arc = km / EARTH_KM
    next_lat = np.arcsin(np.sin(lat)*np.cos(arc) + np.cos(lat)*np.sin(arc)*np.cos(bearing))
    next_lon = lon + np.arctan2(np.sin(bearing)*np.sin(arc)*np.cos(lat),
                               np.cos(arc) - np.sin(lat)*np.sin(next_lat))
    return [float(np.rad2deg(next_lat)), float((np.rad2deg(next_lon)+180) % 360-180)]


def station(latlon, height):
    lat, lon = np.deg2rad(latlon)
    sin_lat, cos_lat = np.sin(lat), np.cos(lat)
    sin_lon, cos_lon = np.sin(lon), np.cos(lon)
    e2 = 0.0066943799901413165
    n = 6378.137 / np.sqrt(1-e2*sin_lat**2)
    obs = np.array([(n+height)*cos_lat*cos_lon, (n+height)*cos_lat*sin_lon,
                    (n*(1-e2)+height)*sin_lat])
    frame = np.array([[-sin_lon, cos_lon, 0.],
                      [-sin_lat*cos_lon, -sin_lat*sin_lon, cos_lat],
                      [cos_lat*cos_lon, cos_lat*sin_lon, sin_lat]])
    return obs, frame


def contains(center, truth):
    origin, frame = station(center, 0.)
    target, _ = station(truth, 0.)
    return bool(np.max(np.abs(frame[:2] @ (target-origin))) <= 12.5)


def distance(a, b):
    a, b = np.deg2rad(a), np.deg2rad(b)
    h = np.sin((a[0]-b[0])/2)**2 + np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(2*EARTH_KM*np.arcsin(np.sqrt(np.clip(h, 0., 1.))))


def orbit_state(sats, anchor, seconds):
    days, remainder = divmod(anchor, DAY)
    jd = np.full(len(seconds), 2440587.5+days)
    fr = remainder / DAY + np.asarray(seconds)/86400.
    errors, p, v = SatrecArray(sats).sgp4(jd, fr)
    century = ((jd - 2451545.) + fr) / 36525.
    gmst = (67310.54841 + ((876600.*3600. + 8640184.812866)
            + (.093104 - 6.2e-6*century)*century)*century) * (np.pi/43200.)
    cs, sn = np.cos(gmst), np.sin(gmst)
    xyz = np.stack((cs*p[..., 0]+sn*p[..., 1], -sn*p[..., 0]+cs*p[..., 1], p[..., 2]), axis=-1)
    uvw = np.stack((cs*v[..., 0]+sn*v[..., 1]+OMEGA*xyz[..., 1],
                    -sn*v[..., 0]+cs*v[..., 1]-OMEGA*xyz[..., 0], v[..., 2]), axis=-1)
    return errors, xyz, uvw


def projection(p, v, observer, carrier):
    delta = p-observer
    return -(carrier/C_KM_S)*np.sum(v*delta, axis=-1)/np.linalg.norm(delta, axis=-1)


@dataclass(frozen=True)
class Snapshot:
    retrieved: int
    last_epoch: int
    digest: str
    path: Path


def inventory():
    snapshots = []
    directory = ARCHIVE / "snapshots/space-track/starlink" / CONFIG["archive_month"]
    for path in directory.glob("*/*.json"):
        document = json.loads(path.read_bytes())
        raw = ARCHIVE / document["raw_object"]
        assert raw.is_file()
        snapshots.append(Snapshot(timestamp(document["retrieved_at"]),
                                  timestamp(document["tle_epoch_max"]),
                                  document["raw_sha256"], raw))
    return sorted(snapshots, key=lambda snap: snap.retrieved)


def new_capture_times(snapshots, disallowed_dates, disallowed_hashes, rng):
    options = []
    month = CONFIG["archive_month"].replace("/", "-")
    for date in CONFIG["archive_days"]:
        start = timestamp(f"{month}-{date:02d}T00:00:00+00:00")
        assert start//DAY not in disallowed_dates
        available = []
        for a, b in zip(snapshots, snapshots[1:]):
            latest = min(b.retrieved-360*NS, start+DAY-360*NS)
            if (start <= a.retrieved < start+DAY and a.digest not in disallowed_hashes
                    and a.last_epoch <= a.retrieved and latest > a.retrieved+120*NS):
                available.append((a, latest))
        for _ in range(4):
            order = rng.permutation(len(available))
            options.append([available[i] for i in order])
    occupied = {}

    def reserve(slot, seen):
        for snap, latest in options[slot]:
            if snap.digest in seen:
                continue
            seen.add(snap.digest)
            if snap.digest not in occupied or reserve(occupied[snap.digest][0], seen):
                occupied[snap.digest] = (slot, snap, latest)
                return True
        return False

    required = [i for i in range(len(options)) if i%4 != 3]
    for slot in sorted(required, key=lambda i: len(options[i])):
        if not reserve(slot, set()):
            raise RuntimeError("Too few independent causal catalogs to cover the planned dates")
    target = len(CONFIG["region_seeds_latlon"])*CONFIG["sites_per_group"]
    for slot in rng.permutation(np.arange(3, len(options), 4)):
        if len(occupied) == target:
            break
        reserve(slot, set())
    assert len(occupied) == target
    captures = [(snap, int(rng.integers(snap.retrieved+120*NS, latest)))
                for _, snap, latest in occupied.values()]
    rng.shuffle(captures)
    return captures


def catalog_bytes(snap):
    data = snap.path.read_bytes()
    assert sha(data) == snap.digest
    return data


@lru_cache(maxsize=4)
def parse_catalog(snap):
    lines = catalog_bytes(snap).decode("ascii").splitlines()
    satellites = {}
    for name, line1, line2 in zip(lines, lines[1:], lines[2:]):
        if "STARLINK" not in name or not line1.startswith("1 ") or not line2.startswith("2 "):
            continue
        sat = Satrec.twoline2rv(line1, line2, WGS72)
        epoch = round((sat.jdsatepoch - 2440587.5)*DAY) + round(sat.jdsatepochF*DAY)
        assert sat.satnum not in satellites
        satellites[sat.satnum] = (sat, epoch, line2)
    assert len(satellites) > 10000
    return satellites


def updated_orbits(before, capture_end, snapshots, disallowed_hashes):
    baseline = parse_catalog(before)
    lead_min, lead_max = CONFIG["generation_archive_lookahead_hours"]
    for snap in snapshots:
        if not (capture_end+lead_min*HOUR <= snap.retrieved <= capture_end+lead_max*HOUR):
            continue
        if snap.digest in disallowed_hashes or snap.digest == before.digest:
            continue
        later = parse_catalog(snap)
        common = baseline.keys() & later.keys()
        rows = []
        for key in sorted(common):
            sat, epoch, line2 = later[key]
            _, causal_epoch, causal_line2 = baseline[key]
            if capture_end < epoch <= snap.retrieved and epoch > causal_epoch and line2 != causal_line2:
                rows.append((sat, epoch, causal_epoch))
        if common and len(rows) >= CONFIG["generation_minimum_updated_common_fraction"]*len(common):
            return snap, rows, len(common)
    raise RuntimeError("No eligible materially updated orbit snapshot")


def transfer_exclusions():
    folder = ROOT.parent / "2026_11_18_location_transfer"
    protocol = json.loads((folder / "protocol.json").read_bytes())
    cases = set(protocol["real_cases"] + protocol["synthetic_cases"] + protocol["confirmation_cases"])
    dates, hashes = set(), set()
    for case in cases:
        graph = Path(CONFIG["archive_graphs"]) / f"{case}.json"
        dates.add(json.loads(graph.read_bytes())["metadata"]["anchor_utc_ns"]//DAY)
        hashes.update(p.stem.split("-")[1] for p in (NATIVE/case/"tle").rglob("*.tle"))
    old_centers = [(37.906, -122.545), *protocol["synthetic_centers_latlon"].values(),
                   *protocol["confirmation_centers_latlon"].values()]
    assert cases.isdisjoint(CONFIG["independent_visit_schedule_cases"])
    return dates, hashes, old_centers


def lane_template(case):
    data = (NATIVE / case / "native.json").read_bytes()
    native = json.loads(data)
    source = native["source"]
    zero = native["clock_anchor"]["sample_counter"]
    lanes = defaultdict(list)
    for visit in source["probes"]:
        lane = (visit["receiver_id"]+1, visit["channel"], visit["actual_rf_hz"])
        t = ((visit["valid_start_counter"]-zero)/source["sample_rate_hz"]
             + source["probe_ms"]/2000.)
        if 0. <= t <= DURATION:
            lanes[lane].append(t)
    result = [(key, np.unique(times)) for key, times in sorted(lanes.items())]
    assert len(result) == 16 and min(len(times) for _, times in result) >= 740
    return result, sha(data)


def compact_offer(origin, rng):
    angle = rng.uniform(0., 2*np.pi)
    return [move(origin, angle + i*np.pi/2 + rng.uniform(-.075, .075), rng.uniform(31., 38.))
            for i in range(4)]


def geography(group, layout, rng):
    groups = CONFIG["region_seeds_latlon"]
    if layout == "neighboring":
        angle, offset = rng.uniform(0., 2*np.pi), rng.uniform(59., 72.)
        origins = [move(groups[group], angle, offset), move(groups[group], angle+np.pi, offset)]
        rng.shuffle(origins)
        offered = compact_offer(origins[0], rng)
        absent = compact_offer(origins[1], rng)
        selected = int(rng.integers(4))
    else:
        others = rng.permutation([i for i in range(len(groups)) if i != group])
        offered = [move(groups[i], rng.uniform(0., 2*np.pi), rng.uniform(15., 90.))
                   for i in [group, *others[:3]]]
        absent = [move(groups[i], rng.uniform(0., 2*np.pi), rng.uniform(15., 90.))
                  for i in others[:4]]
        selected = 0
    inset = np.sqrt(rng.uniform(2.25**2, 11.5**2))
    truth = move(offered[selected], rng.uniform(0., 2*np.pi), inset)
    return truth, offered, absent, selected


def angular_difference(angle, reference):
    return (angle-reference+np.pi) % (2*np.pi)-np.pi


def visibility(positions, errors, observer, frame, orientation, width, floor):
    direction = positions-observer
    local = np.einsum("...j,ij->...i", direction, frame)
    azimuth = np.arctan2(local[..., 0], local[..., 1])
    threshold = np.sin(floor + np.deg2rad(4.)*np.cos(azimuth-orientation)**2)
    radii = np.linalg.norm(positions, axis=-1)
    return ((errors == 0) & (radii >= 6660.) & (radii <= 7100.)
            & (local[..., 2] > threshold*np.linalg.norm(direction, axis=-1))
            & (np.abs(angular_difference(azimuth, orientation)) < width/2))


def scene(anchor, updated, lanes, truth, rig, rng):
    sparse = rig == "sparse"
    height = rng.uniform(*{"open": (0.025, 0.45), "masked": (0.2, 1.8),
                           "sparse": (0.55, 2.1)}[rig])
    observer, frame = station(truth, height)
    orientation = rng.uniform(0., 2*np.pi)
    width = np.deg2rad(rng.uniform(*{"open": (315., 360.), "masked": (190., 275.),
                                     "sparse": (145., 215.)}[rig]))
    floor = np.deg2rad(rng.uniform(*{"open": (11., 17.), "masked": (15., 23.),
                                     "sparse": (22., 31.)}[rig]))
    step = 7.5
    coarse = np.arange(0., DURATION+step, step)
    sats, epochs, causal_epochs = zip(*updated, strict=True)
    errors, pos, _ = orbit_state(sats, anchor, coarse)
    visible = visibility(pos, errors, observer, frame, orientation, width, floor)
    rx_bias = rng.uniform(-14000., 14000., size=(2, 2))
    rx_rate = rng.normal(0., 2.8, size=(2, 2))
    rx_quad = rng.normal(0., 95., size=(2, 2))
    c = float(rng.choice([0., rng.uniform(-24000., -4000.), rng.uniform(4000., 24000.)],
                         p=[.125, .4375, .4375]))
    static = rng.normal(0., 140., size=len(sats))
    phase = rng.normal(0., .9, size=len(sats))
    phase = np.clip(phase, -3., 3.)
    tracks, provenance = [], []
    completed = Counter()
    counts = (int(rng.integers(5, 9)), int(rng.integers(5, 9)), 3) if sparse else (
        int(rng.integers(12, 19)), int(rng.integers(12, 19)), int(rng.integers(4, 9)))
    plan = [(block, k in bad) for block, count in enumerate(counts)
            for bad in [set(rng.choice(count, size=max(1, round(.15*count)), replace=False))]
            for k in range(count)]
    lane_order = rng.permutation(len(lanes))
    for i, (block, corrupt) in enumerate(plan):
        (rx, channel, rf), visits = lanes[lane_order[i % len(lanes)]]
        for _ in range(30):
            duration = rng.uniform(25., 76. if sparse else 83.)
            limits = [(2., 146.-duration), (154., 298.-duration),
                      (152.-.7*duration, 148.-.3*duration)]
            start = rng.uniform(*limits[block])
            t = visits[(start <= visits) & (visits <= start+duration)]
            if rng.random() < .55:
                blank = rng.uniform(start, start+duration-3.)
                t = t[(t < blank) | (t > blank+rng.uniform(3., min(15., .3*duration)))]
            n = min(len(t), int(rng.integers(20, 47) if sparse else rng.integers(29, 66)))
            if n < 20 or t[-1]-t[0] < 18.:
                continue
            t = np.sort(np.r_[t[0], rng.choice(t[1:-1], n-2, replace=False), t[-1]])
            a, b = int(t[0]//step), int(np.ceil(t[-1]/step))
            possible = np.flatnonzero(visible[:, a:b+1].all(axis=1))
            if not len(possible):
                continue
            choice = int(rng.choice(possible))
            err, p, v = orbit_state([sats[choice]], anchor, t+phase[choice])
            if not visibility(p, err, observer, frame, orientation, width, floor).all():
                continue
            break
        else:
            continue
        u = (t-t.mean())/np.ptp(t)
        band = (rx-1, int(channel > 4))
        f = (projection(p[0], v[0], observer, rf) + static[choice] + rx_bias[band]
             + rx_rate[band]*(t-150.) + rx_quad[band]*((t-150.)/150.)**2
             + c*(rf/1e9-11.5) + rng.normal(0., rng.uniform(40., 165.), n)
             + rng.normal(0., 260.)*u**2 + rng.normal(0., 75.)*np.sin(u*np.pi))
        if corrupt:
            split = rng.uniform(-.17, .17)
            f += (rng.choice((-1., 1.))*rng.uniform(2700., 11500.)
                  + rng.uniform(-13500., 13500.)*np.maximum(0., u-split)
                  + rng.choice((-1., 1.))*rng.uniform(2300., 8700.)*u**2)
        tracks.append({"times": np.round(t, 8).tolist(), "values": np.round(f, 3).tolist(),
                       "rf_hz": rf, "receiver": rx, "channel": channel})
        provenance.append({"norad": sats[choice].satnum, "epoch_utc_ns": epochs[choice],
                           "causal_epoch_utc_ns": causal_epochs[choice],
                           "timing_s": float(phase[choice]), "corrupt": corrupt})
        completed[block, corrupt] += 1
    order = rng.permutation(len(tracks))
    info = {"height_km": float(height), "mask_azimuth_deg": float(np.rad2deg(orientation)),
            "mask_width_deg": float(np.rad2deg(width)), "elevation_floor_deg": float(np.rad2deg(floor)),
            "rig": rig, "c_hz_per_ghz": c, "planned_block_counts": counts,
            "clean_early_late": [completed[i, False] for i in (0, 1)],
            "tracks": [provenance[i] for i in order]}
    return [tracks[i] for i in order], info


def public_commitment(directory):
    return {str(path.relative_to(directory)): sha(path.read_bytes())
            for path in sorted(directory.rglob("*")) if path.is_file()}


def check_public(stage, queries, documents, cases, old_centers):
    by_id = {row["id"]: row for row in cases}
    assert len(queries) == len(by_id) == 80 and queries.keys() == by_id.keys()
    assert len(documents) == 40
    groups, pairs, hidden = set(), defaultdict(list), set()
    for qid, query in queries.items():
        truth = by_id[qid]
        pairs[truth["pair"]].append(query)
        groups.add(truth["site_group"])
        hidden.add(tuple(truth["latlon"]))
        assert min(distance(truth["latlon"], p) for p in old_centers) > 550.
        containing = [region["id"] for region in query["regions"]
                      if contains(region["center"], truth["latlon"])]
        assert len(query["regions"]) == 4
        for region in query["regions"]:
            dist = distance(region["center"], truth["latlon"])
            if region["id"] != truth["true_region"]:
                assert dist > 25.
            else:
                assert 2. < dist < 11.6
        expected = [truth["true_region"]] if truth["condition"] == "present" else []
        assert containing == expected
        assert sha((stage/"queries"/f"{qid}.json").read_bytes()) == sha(packed(query))
        document = documents[query["observation"]]
        assert document["catalog_timestamp_ns"] <= document["cutoff_utc_ns"] <= document["anchor_utc_ns"]
        for track in document["tracks"]:
            times = np.asarray(track["times"])
            assert len(times) >= 20 and len(times) == len(track["values"])
            assert ((0. <= times) & (times <= document["duration_s"])).all()
            assert (np.diff(times) > 0.).all()
            assert np.isfinite(track["values"]).all()
    assert len({r["id"] for q in queries.values() for r in q["regions"]}) == 320
    assert len(groups) == 8 and len(hidden) == 40 and len(pairs) == 40
    for pair in pairs.values():
        a, b = pair
        assert a["observation"] == b["observation"] and a["catalog"] == b["catalog"]
        assert {by_id[r["id"]]["condition"] for r in pair} == {"present", "missing"}
        assert by_id[a["id"]]["latlon"] == by_id[b["id"]]["latlon"]


def draft(stage, rng):
    for name in ("orbits", "observations", "queries"):
        (stage/name).mkdir()
    dates, excluded_catalogs, old_centers = transfer_exclusions()
    snapshots = inventory()
    captures = iter(new_capture_times(snapshots, dates, excluded_catalogs, rng))
    lane_templates = [lane_template(case) for case in CONFIG["independent_visit_schedule_cases"]]
    queries, documents, cases, provenance = {}, {}, [], {}
    for index in range(len(CONFIG["region_seeds_latlon"])):
        site_group = identifier(rng)
        layouts = ["neighboring"]*(2+index%2) + ["dispersed"]*(3-index%2)
        rng.shuffle(layouts)
        rigs = ["open", "open", "masked", "masked", "sparse"]
        rng.shuffle(rigs)
        for layout, rig in zip(layouts, rigs, strict=True):
            pair = identifier(rng)
            truth, present, missing, selected = geography(index, layout, rng)
            causal, anchor = next(captures)
            capture_end = anchor+DURATION*NS
            later, updated, common = updated_orbits(causal, capture_end, snapshots, excluded_catalogs)
            slot = int(rng.integers(len(lane_templates)))
            lanes, native_sha = lane_templates[slot]
            tracks, scene_info = scene(anchor, updated, lanes, truth, rig, rng)
            put(stage/"orbits"/f"{causal.digest}.tle", catalog_bytes(causal))
            observation = {"anchor_utc_ns": anchor, "cutoff_utc_ns": anchor, "duration_s": float(DURATION),
                           "catalog_timestamp_ns": causal.retrieved, "tracks": tracks}
            obs_bytes = packed(observation)
            obs_hash = sha(obs_bytes)
            documents[obs_hash] = observation
            put(stage/"observations"/f"{obs_hash}.json", obs_bytes)
            for condition, centers in (("present", present), ("missing", missing)):
                regions = [{"id": identifier(rng), "center": center} for center in centers]
                true_region = regions[selected]["id"] if condition == "present" else None
                rng.shuffle(regions)
                qid = identifier(rng)
                query = {"id": qid, "observation": obs_hash, "catalog": causal.digest, "regions": regions}
                queries[qid] = query
                put(stage/"queries"/f"{qid}.json", packed(query))
                cases.append({"id": qid, "pair": pair, "site_group": site_group, "source": "synthetic",
                              "condition": condition, "true_region": true_region, "latlon": truth,
                              "difficulty": f"{layout}_{rig}"})
            future_epoch_leads = [t["epoch_utc_ns"]-capture_end for t in scene_info["tracks"]]
            causal_epoch_ages = [anchor-t["causal_epoch_utc_ns"] for t in scene_info["tracks"]]
            provenance[pair] = {"visit_case": CONFIG["independent_visit_schedule_cases"][slot],
                                "visit_template_sha256": native_sha, "observation": obs_hash,
                                "causal_sha256": causal.digest, "latest_causal_epoch_ns": causal.last_epoch,
                                "causal_archive_utc_ns": causal.retrieved, "later_sha256": later.digest,
                                "later_archive_utc_ns": later.retrieved,
                                "later_archive_lookahead_ns": later.retrieved-capture_end,
                                "updated_common_elements": len(updated),
                                "common_elements": common,
                                "updated_common_fraction": len(updated)/common,
                                "eligible_element_epoch_lead_ns": [
                                    min(t[1] for t in updated)-capture_end,
                                    max(t[1] for t in updated)-capture_end],
                                "used_element_epoch_lead_ns": [
                                    min(future_epoch_leads), max(future_epoch_leads)] if tracks else None,
                                "used_causal_element_age_ns": [
                                    min(causal_epoch_ages), max(causal_epoch_ages)] if tracks else None,
                                "end_utc_ns": capture_end, **scene_info}
    check_public(stage, queries, documents, cases, old_centers)
    ids = list(queries)
    rng.shuffle(ids)
    rng.shuffle(cases)
    put(stage/"manifest.json", packed({"queries": ids}))
    return cases, provenance


def publish():
    assert not RECEIPT.exists() and not PUBLIC.exists()
    seed_path = PRIVATE/"seed.bin"
    if not seed_path.exists():
        put(seed_path, secrets.token_bytes(32))
    seed = seed_path.read_bytes()
    assert len(seed) == 32
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temp:
        staged = Path(temp)/"public_synthetic"
        staged.mkdir()
        cases, provenance = draft(staged, rng)
        tree = public_commitment(staged)
        put(PRIVATE/"truth.json", packed({"cases": cases}))
        put(PRIVATE/"provenance.json", packed(provenance))
        put(PRIVATE/"public-byte-index.json", packed(tree))
        captured = list(provenance.values())
        normal = [x for x in captured if x["rig"] != "sparse"]
        assert all(r["latest_causal_epoch_ns"] <= r["causal_archive_utc_ns"] for r in captured)
        assert all(t["epoch_utc_ns"] > r["end_utc_ns"] for r in captured for t in r["tracks"])
        private_files = ["publish.py", "protocol.json", "seed.bin", "truth.json",
                         "provenance.json", "public-byte-index.json", "test_publish.py"]
        receipt = {
            "schema": "blind-regional-receiver-synthetic-receipt/v1",
            "sealed_at_utc": datetime.now(UTC).isoformat(),
            "counts": {"queries": len(cases), "paired_observations": len(provenance),
                       "regional_groups": len({x["site_group"] for x in cases}),
                       "distinct_sites": len({tuple(x["latlon"]) for x in cases}),
                       "capture_days": len({x["end_utc_ns"]//DAY for x in captured}),
                       "present": sum(x["condition"] == "present" for x in cases),
                       "missing": sum(x["condition"] == "missing" for x in cases),
                       "causal_catalogs": len({x["causal_sha256"] for x in captured}),
                       "later_catalogs": len({x["later_sha256"] for x in captured}),
                       "public_files": len(tree),
                       "total_tracks": sum(len(x["tracks"]) for x in captured),
                       "contaminated_tracks": sum(t["corrupt"] for x in captured for t in x["tracks"]),
                       "normal_scenes_with_9_clean_tracks_per_half":
                           sum(min(x["clean_early_late"]) >= 9 for x in normal),
                       "normal_scenes": len(normal)},
            "validation": {"prior_protocol_site_case_and_catalog_exclusions": True,
                           "causal_catalog_byte_identical_to_archived_source": True,
                           "used_later_epochs_after_capture": True,
                           "square_containment_and_matched_public_inputs": True,
                           "minimum_updated_common_element_fraction":
                               min(x["updated_common_fraction"] for x in captured)},
            "sha256": {name: sha((PRIVATE/name).read_bytes()) for name in private_files}
                      | {"public_manifest": tree["manifest.json"], "public_tree": sha(packed(tree))},
        }
        put(RECEIPT, packed(receipt))
        staged.rename(PUBLIC)
    print("Synthetic holdout published and sealed")


def verify():
    receipt = json.loads(RECEIPT.read_bytes())
    for name, digest in receipt["sha256"].items():
        if name not in ("public_manifest", "public_tree"):
            assert sha((PRIVATE/name).read_bytes()) == digest
    tree = public_commitment(PUBLIC)
    assert packed(tree) == (PRIVATE/"public-byte-index.json").read_bytes()
    assert tree["manifest.json"] == receipt["sha256"]["public_manifest"]
    assert sha(packed(tree)) == receipt["sha256"]["public_tree"]
    assert len(tree) == receipt["counts"]["public_files"]
    for path, digest in tree.items():
        if path.startswith(("observations/", "orbits/")):
            assert Path(path).stem == digest
    manifest = json.loads((PUBLIC/"manifest.json").read_bytes())
    assert len(manifest["queries"]) == receipt["counts"]["queries"]
    assert len(set(manifest["queries"])) == len(manifest["queries"])
    assert {f"queries/{i}.json" for i in manifest["queries"]} == {
        path for path in tree if path.startswith("queries/")}
    print("Synthetic holdout commitments verified")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--verify", action="store_true")
    (verify if cli.parse_args().verify else publish)()
