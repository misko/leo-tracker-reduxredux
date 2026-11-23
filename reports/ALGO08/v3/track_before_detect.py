"""Measure an oracle trajectory against unthresholded spectral carrier evidence."""

import argparse
from collections import Counter, defaultdict
import ctypes as ct
import gzip
from hashlib import sha256
import json
from math import ceil, floor, sqrt
from pathlib import Path
from statistics import median
from time import process_time
from zipfile import ZipFile

import numpy as np

from aperture_trial import archive_identity
from cyclic_carrier_trial import PINS, Scout, build, digest, pilot_lines
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.contracts.digests import canonical_digest
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastScanStore, FastSegmentSource
from reports.ALGO08.v3.anchor_sky import ALIAS, lanes_for, projected_sky


SIZE = 16384
BIN_HZ = 5_000_000 / (2 * SIZE)
BLOCK = 256
MIN_POINTS = 6
MAX_GAP_S = 10.
OFFSET_HZ = 1000
CFO_TOLERANCE = 4550
SCOUT_BYTES = 4 * (int(1_600_000 / BIN_HZ) + 1)
OWNERS_SHA = "09ccc94a33cbe813a82333aaa26a3e1c8efdf86c04d264d4ffdfee1e6a7b0658"
ATTENUATED_DB = (-9, -12)


def load(path):
    return json.loads(path.read_bytes())


def lane_key(probe):
    return probe["receiver_id"], probe["channel"], probe["actual_rf_hz"], probe["edge"]


def obs_id(session, probe):
    key = f'{session}:{probe["receiver_id"]}:{probe["valid_start_counter"]}'
    return "sha256:" + sha256(key.encode()).hexdigest()


def owner_frequency(probe):
    winner = max((r for r in probe["candidates"] if r["passed_fractional_margin_gate"]),
                 key=lambda r: (r["fractional_margin"], -r["candidate_rank"]))
    return winner["fractional_tracking_cfo_hz"]


def owner_groups(probes, session, owners):
    groups = defaultdict(list)
    for probe in probes:
        owner = owners.get(obs_id(session, probe))
        if owner is not None:
            groups[(owner["norad"], *lane_key(probe))].append(probe)
    return groups


def split_gaps(points):
    group = []
    for point in points:
        if group and point["valid_start_counter"] - group[-1]["valid_start_counter"] > 1e7 * MAX_GAP_S:
            yield group
            group = []
        group.append(point)
    if group:
        yield group


def blocks(probes, session, owners, n_windows):
    selected = []
    for first in range(0, n_windows, BLOCK):
        end = min(n_windows, first + BLOCK)
        members = [p for p in probes if first <= p["visit_index"] < end]
        groups = owner_groups(members, session, owners)
        tracks = [(key, group) for key, rows in groups.items()
                  for group in split_gaps(rows) if len(group) >= MIN_POINTS]
        selected.append((first, end, members, tracks))
    return selected


def physical_census(clip_roster, selected_zips, dense_native):
    roster = load(clip_roster)["recorded"]
    staggered = {}
    for case in ("DS26-0197", "DS29-0316"):
        counts = Counter((row["segment"], row["center_hz"])
                         for row in roster[case] if row["status"] == "valid")
        staggered[case] = dict(windows=sum(counts.values()), clip_receiver_rf_groups=len(counts),
                               max_visits_per_clip_receiver_rf=max(counts.values()))
    isolated = {}
    for path in selected_zips:
        with ZipFile(path) as archive:
            probes = json.loads(archive.read("index.json"))["visits"]
        counts = Counter((r["case"], r["edge"], r["acquisition"]["actual_if_center_hz"]
                          + r["target"]["lnb_lo_hz"]) for r in probes)
        isolated[path.name] = dict(windows=len(probes), pooled_max_visits_per_receiver_rf=max(counts.values()),
                                   archive_file_sha256=digest(path))
    dense = load(dense_native)["source"]["probes"]
    first = [row for row in dense if row["visit_index"] < 24]
    counts = Counter(lane_key(row) for row in first)
    return dict(staggered=staggered, isolated=isolated, staggered_lock_sha256=digest(clip_roster),
                prior_dense_prefix=dict(lanes=len(first), max_visits_per_receiver_rf=max(counts.values()),
                                        native_sha256=digest(dense_native)))


def standardized(score):
    peak = score.max()
    if peak == 0:
        return score.copy()
    # Native scores can be large with full-scale CI16. Rescale before the
    # variance squares them in Float32.
    scaled = score / peak
    centered = scaled - scaled.mean()
    scale = scaled.std()
    return centered / scale if scale > 0 else centered


class Surface(Scout):
    def __init__(self, owned_library):
        super().__init__(owned_library, SIZE)
        export = ct.CDLL(str(owned_library.resolve())).cyclic_carrier_surface
        export.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, *([ct.c_void_p] * 4)]
        export.restype = ct.c_int
        self.export = export
        self.values = np.empty(SIZE, dtype=np.float32)
        self.first = ct.c_int()

    def get(self, iq, lane, center, lines, weights, *, repeats=3):
        callback = (self.work, iq.ctypes.data, lane, center, lines.ctypes.data,
                    weights.ctypes.data, self.values.ctypes.data, ct.byref(self.first))
        clocks = []
        for _ in range(repeats):
            start = process_time()
            count = self.export(*callback)
            if count <= 0 or count > len(self.values):
                raise ValueError("invalid native surface size")
            values = standardized(self.values[:count])
            clocks.append(process_time() - start)
        first = self.first.value * BIN_HZ
        return first, first + (count - 1) * BIN_HZ, values, median(clocks)


def frequency_scores(surface, hz):
    low, high, values, _ = surface
    frequencies = np.asarray(hz)
    if np.any(frequencies < low - 1e-6) or np.any(frequencies > high + 1e-6):
        raise ValueError("trajectory leaves the common signed interval")
    index = np.clip((frequencies - low) / BIN_HZ, 0, len(values) - 1)
    whole = index.astype(np.intp)
    fraction = index - whole
    return (1. - fraction) * values[whole] + fraction * values[np.minimum(whole + 1, len(values) - 1)]


def aligned_scores(surfaces, cfo):
    low = max(s[0] - carrier for s, carrier in zip(surfaces, cfo, strict=True))
    high = min(s[1] - carrier for s, carrier in zip(surfaces, cfo, strict=True))
    offsets = np.arange(ceil(low / OFFSET_HZ), floor(high / OFFSET_HZ) + 1) * OFFSET_HZ
    if 0 not in offsets:
        raise ValueError("oracle frequency was outside the signed surface")
    readings = np.asarray([frequency_scores(surface, carrier + offsets)
                           for surface, carrier in zip(surfaces, cfo, strict=True)])
    return offsets, readings


def ranks(offsets, readings):
    score = readings.sum(axis=0) / sqrt(len(readings))
    aligned = abs(offsets) <= CFO_TOLERANCE
    center = float(score[offsets == 0][0])
    best_near = float(np.max(score[aligned]))
    false = score[~aligned]
    false_best = float(np.max(false))
    p95 = float(np.percentile(false, 95))
    order = np.argsort(-score, kind="stable")
    shortlist = []
    for index in order:
        shift = int(offsets[index])
        if all(abs(shift - other) >= 10000 for other in shortlist):
            shortlist.append(shift)
        if len(shortlist) == 4:
            break
    return dict(visits=len(readings), shifted_cells=len(false), true_score=center, best_near=best_near,
                false_median=float(np.median(false)), false_p95=p95, false_max=false_best,
                equal_false_cells=int(np.count_nonzero(false == center)),
                exact_rank=int(1 + np.count_nonzero(false > center)),
                optimistic_rank=int(1 + np.count_nonzero(false > best_near)),
                top4_in_band=any(abs(hz) <= CFO_TOLERANCE for hz in shortlist), shortlist_hz=shortlist)


def collect(scene, start, end, probes, scouts, assets):
    manifest = scene / "manifest.json"
    capture = FastSegmentSource(dict(path=scene, manifest_digest="sha256:" + digest(manifest)),
                                start_sequence=start, stop_sequence=end)
    if tuple(capture.receiver_ids) != (0, 1):
        raise ValueError("unexpected simulation receivers")
    expected = {(p["visit_index"], p["receiver_id"]): p for p in probes}
    policy = FastScanPolicyV2()
    scores, sources = {}, []
    weakened = {db: {} for db in ATTENUATED_DB}
    clipped = Counter()
    rng = np.random.default_rng(20261124)
    mixed = np.zeros((2 * SIZE, 2, 2), dtype="<i2")
    for window in capture.windows():
        a, t = window.acquisition, window.target
        if not valid_window_support(a, window.sample_rate_hz, window.samples.shape, capture.receiver_ids, policy):
            continue
        visit = a["global_visit"]
        sources.append((visit, window.iq_sha256))
        for lane in (0, 1):
            probe = expected[visit, lane]
            if (probe["valid_start_counter"] != a["sample_start"] or probe["edge"] != t["edge"]
                    or probe["channel"] != t["channel"]
                    or probe["actual_rf_hz"] != a["actual_if_center_hz"] + t["lnb_lo_hz"]):
                raise ValueError("waveform/detection metadata mismatch")
            center = t["rf_center_hz"] - probe["actual_rf_hz"]
            scores[visit, lane] = scouts.get(window.samples, lane, center, *assets[t["edge"]])
            signal = window.samples[:2 * SIZE, lane].astype(np.float32)
            noise = rng.standard_normal(signal.shape, dtype=np.float32)
            rms = np.sqrt(np.mean(signal**2))
            for db in ATTENUATED_DB:
                amplitude = rms * 10 ** (-db / 20)
                components = np.rint(signal + amplitude * noise)
                clipped[str(db)] += int(np.count_nonzero((components < -32768) | (components > 32767)))
                mixed[:, lane] = np.clip(components, -32768, 32767)
                weakened[db][visit, lane] = scouts.get(mixed, lane, center, *assets[t["edge"]], repeats=1)
    if scores.keys() != expected.keys():
        raise ValueError("sealed capture left probe opportunities unmatched")
    return scores, weakened, dict(manifest_sha256=digest(manifest), inputs=sources,
                                   weakened_saturated_components=dict(clipped),
                                   weakened_components_per_level=len(scores) * 4 * SIZE)


def blank_control(opportunities, band, surfaces):
    groups, current = [], []
    for probe in opportunities:
        if probe["candidates"]:
            if current:
                groups.append(current)
                current = []
        else:
            current.append(probe)
    if current:
        groups.append(current)
    for blank in sorted(groups, key=lambda g: -len(g)):
        length = min(len(blank), len(band))
        while length >= MIN_POINTS:
            for first in range(len(blank) - length + 1):
                candidates = blank[first:first + length]
                before = np.diff([p["valid_start_counter"] for p in band[:length]])
                after = np.diff([p["valid_start_counter"] for p in candidates])
                if np.array_equal(before, after):
                    keys = [(p["visit_index"], p["receiver_id"]) for p in candidates]
                    support = [surfaces[key] for key in keys]
                    hz = [owner_frequency(p) for p in band[:length]]
                    score = ranks(*aligned_scores(support, hz))
                    return dict(score, first_visit=candidates[0]["visit_index"],
                                last_visit=candidates[-1]["visit_index"], span_s=float(sum(after) / 1e7))
            length -= 1
    return None


def evaluate(tracks, probes, surfaces, noise, zero, weakened):
    by_lane = defaultdict(list)
    for p in probes:
        by_lane[lane_key(p)].append(p)
    details = []
    for key, band in tracks:
        support = [p for p in by_lane[key[1:]]
                   if band[0]["valid_start_counter"] <= p["valid_start_counter"] <= band[-1]["valid_start_counter"]]
        times = [p["valid_start_counter"] for p in band]
        known = [owner_frequency(p) for p in band]
        span_hz = np.interp([p["valid_start_counter"] for p in support], times, known)
        span_index = [(p["visit_index"], p["receiver_id"]) for p in support]
        span_scores = [surfaces[index] for index in span_index]
        offsets, readings = aligned_scores(span_scores, span_hz)
        owned_mask = np.isin([p["valid_start_counter"] for p in support], times)
        empty_mask = np.asarray([not p["candidates"] for p in support])
        independent = [noise[index] for index in span_index]
        null_offsets, null = aligned_scores(independent, span_hz)
        zeros = [zero for _ in support]
        zero_offset, blank = aligned_scores(zeros, span_hz)
        stress = {}
        for db, by_slot in weakened.items():
            shifted, weaker = aligned_scores([by_slot[index] for index in span_index], span_hz)
            stress[str(db)] = dict(full_span=ranks(shifted, weaker),
                                   single_owned=[ranks(shifted, row[None, :]) for row in weaker[owned_mask]])
        details.append(dict(key=key, start_visit=band[0]["visit_index"], stop_visit=band[-1]["visit_index"],
                            span_s=(times[-1] - times[0]) / 1e7,
                            owned=ranks(offsets, readings[owned_mask]), full_span=ranks(offsets, readings),
                            native_empty_only=ranks(offsets, readings[empty_mask]) if np.any(empty_mask) else None,
                            matched_blank_control=blank_control(by_lane[key[1:]], band, surfaces),
                            white_noise=ranks(null_offsets, null), zero=ranks(zero_offset, blank),
                            attenuated=stress,
                            single_owned=[ranks(offsets, r[None, :]) for r in readings[owned_mask]]))
    return details


def null_surfaces(probes, scout, asset, surfaces):
    rng = np.random.default_rng(7701)
    iq = np.zeros((2 * SIZE, 2, 2), dtype="<i2")
    zero = scout.get(iq, 0, 0, *asset, repeats=1)
    noise = {}
    for p in probes:
        slot = p["visit_index"], p["receiver_id"]
        left, right, _, _ = surfaces[slot]
        center = (left + right) / 2
        iq[:, 0] = np.rint(rng.normal(0, 1000, size=(len(iq), 2))).astype(np.int16)
        noise[slot] = scout.get(iq, 0, center, *asset, repeats=1)
    return noise, zero


def native_accumulator(library):
    use = ct.CDLL(str(library.resolve())).cyclic_carrier_accumulate
    use.argtypes = [ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.c_void_p, ct.c_int,
                    ct.c_void_p, ct.c_int, ct.c_void_p]
    use.restype = ct.c_int
    return use


def bank(native, probes, surfaces, archive_path, region, library):
    before, after = [native["clock_anchor"][k]["realtime_ns"] for k in ("before", "after")]
    lanes = lanes_for(probes, native["clock_anchor"], native["source"]["probe_ms"])
    started = process_time()
    catalogue = causal_catalogue(TleArchiveReader(archive_path), before)
    parsed = process_time()
    cfo, _, numbers, support = projected_sky(catalogue.catalogue, (before + after) // 2, lanes, region,
                                            include_visibility=True)
    online = support.pop("above_horizon")
    projected = process_time()
    offsets = np.arange(0., ALIAS, OFFSET_HZ)
    queries = 0
    band_lower = min(value[0] for value in surfaces.values())
    band_upper = max(value[1] for value in surfaces.values())
    shifts = range(floor((band_lower - np.max(cfo) - offsets[-1]) / ALIAS),
                   ceil((band_upper - np.min(cfo)) / ALIAS) + 1)
    offsets = np.concatenate([offsets + branch * ALIAS for branch in shifts])
    use = native_accumulator(library)
    scenarios = {}
    for name, mask in (("broad", np.ones_like(online)), ("horizon", online)):
        started_lookup = process_time()
        scores_by_track = np.zeros((len(numbers), len(offsets)))
        input_frequency = np.ascontiguousarray(np.where(mask, cfo, np.inf).T)
        queries = 0
        # Charge one interpolation per in-band offset. This does not track
        # visibility turnover or calibrate distinct families' fitted scores.
        for lane, lane_hz in zip(lanes, input_frequency, strict=True):
            low, _, values, _ = surfaces[lane.visit, lane.rx]
            queries += use(values.ctypes.data, len(values), low, BIN_HZ, lane_hz.ctypes.data, len(lane_hz),
                           offsets.ctypes.data, len(offsets), scores_by_track.ctypes.data)
        duration = process_time() - started_lookup
        scenarios[name] = dict(mean_visible_satellites=float(mask.sum() / len(lanes)),
                               signed_cell_reads=queries, signed_cells_checked=int(mask.sum()) * len(offsets),
                               query_cpu_s=duration, checksum=float(np.sum(scores_by_track)),
                               dense_projection_scaling=dict(lanes=13530, signed_cell_reads=queries / len(lanes) * 13530,
                                                             cpu_s=duration / len(lanes) * 13530))
    return dict(causal_catalogue_cpu_s=parsed - started, projection_cpu_s=projected - parsed,
                visible_satellites=len(numbers), center_screen=support,
                offsets_per_alias=len(offsets) // len(shifts), **scenarios, lanes=len(lanes),
                dense_surface_bytes=SCOUT_BYTES * 13530)


def trial(args):
    scene = args.scene
    pair = load(args.pair)
    native = load(args.native)
    installed = load(args.installed)
    native_sha = digest(args.native)
    if digest(args.owners) != OWNERS_SHA:
        raise ValueError("unexpected scoped owner witness")
    witness = json.loads(json.loads(gzip.decompress(args.owners.read_bytes()))["south-containing"])
    source = witness["captures"]["complete"]
    authority = source["identity"]["source"]
    run = pair["runs"]["candidate"]
    installed_pair_path = args.installed.parents[3] / "pair.json"
    installed_pair = load(installed_pair_path)
    archive = archive_identity(Path(authority["archive"]))
    terminal = load(args.native.parents[1] / run["receipt"]["run_id"] / "terminal.json")
    installed_receipt = installed_pair["runs"]["candidate"]["receipt"]
    installed_terminal = load(args.installed.parents[1] / installed_receipt["run_id"] / "terminal.json")
    source_id, inventory_sha, _ = FastScanStore(scene.parent).inventory(scene, verify_windows=False)
    if (authority["pair_sha256"] != digest(args.pair)
            or authority["native_sha256"] != "sha256:" + native_sha
            or canonical_digest(native) != terminal["native_sha256"]
            or canonical_digest(terminal) != run["receipt"]["terminal_sha256"]
            or canonical_digest(installed_terminal) != installed_receipt["terminal_sha256"]
            or canonical_digest(installed) != installed_terminal["native_sha256"]
            or authority["session_id"] != native["source"]["session_id"]
            or source_id != native["source"]["session_id"]
            or inventory_sha != native["source"]["input_manifest_sha256"]
            or authority["raw_authority"] != native["source"]["raw_recording_authority_digest"]
            or authority["raw_authority"] != installed["source"]["raw_recording_authority_digest"]
            or authority["terminal_sha256"] != run["receipt"]["terminal_sha256"]
            or str(scene) != pair["recording"]
            or str(scene) != installed_pair["recording"]
            or digest(installed_pair_path) != authority["archive_authority_sha256"]
            or archive != installed_pair["archive"]
            or archive["snapshots_sha256"] != authority["snapshots_sha256"]):
        raise ValueError("archived native ownership source changed")
    probes = native["source"]["probes"]
    fields = ("clock_anchor", "delivery_clocks", "last_sample_counter", "schema_version")
    if any(native[key] != installed[key] for key in fields):
        raise ValueError("installed and owner source clocks differ")
    for a, b in zip(probes, installed["source"]["probes"], strict=True):
        if any(a[k] != b[k] for k in a if k != "candidates") or (
            bool(a["candidates"]) != bool(b["candidates"]) or (
                bool(a["candidates"]) and owner_frequency(a) != owner_frequency(b)
            )
        ):
            raise ValueError("installed and owner source are not signed equivalents")
    owners = source["witness"]["labels"]
    session = native["source"]["session_id"]
    if not owners.keys() <= {obs_id(session, p) for p in probes if p["candidates"]}:
        raise ValueError("unmatched archived owners")
    options = blocks(probes, session, owners, native["provenance"]["window_count"])
    start, end, members, tracks = max(options, key=lambda row: len({item[0] for item in row[3]}))
    if not tracks:
        raise ValueError("no simulation span supports six aligned visits")
    edges = {p["edge"] for p in members}
    if len(edges) != 1:
        raise ValueError("the bounded independent control expects one pilot edge")
    edge, = edges
    asset = args.assets / f"{edge}.f32"
    if digest(asset) != PINS[edge]:
        raise ValueError("installed asset mismatch")
    lines, weights, _ = pilot_lines(np.fromfile(asset, dtype="<f4"))
    scout = Surface(args.library)
    try:
        data, weaker, bindings = collect(scene, start, end, members, scout, {edge: (lines, weights)})
        noise, zero = null_surfaces(members, scout, (lines, weights), data)
    finally:
        scout.close()
    details = evaluate(tracks, members, data, noise, zero, weaker)
    causal = bank(native, members, data, Path(authority["archive"]), Algo08Region.parse(source["identity"]["offer"]),
                  args.library)
    sketch_cpu = sum(item[-1] for item in data.values())
    result = dict(source=dict(pair_sha256=digest(args.pair), installed_doc_sha256=digest(args.installed),
                              native_doc_sha256=native_sha, owner_witness_sha256=digest(args.owners),
                              asset_sha256=digest(asset), library_sha256=digest(args.library),
                              runner_sha256=digest(Path(__file__)), archive=archive, **bindings),
                  physical=physical_census(args.staggered, args.zip, args.dense_native),
                  blocks=[dict(start=row[0], stop=row[1], qualifying_segments=len(row[3]),
                               distinct_satellites=len({item[0][0] for item in row[3]})) for row in options],
                  simulation=dict(start=start, stop=end, lanes=len(members), edge=edge,
                                  indigenous_blanks=sum(not p["candidates"] for p in members), tracks=details,
                                  surface_cpu_s=sketch_cpu, surface_cpu_ms_per_lane=1000 * sketch_cpu / len(members),
                                  surface_bytes=sum(item[2].nbytes for item in data.values()), causal_bank=causal))
    with args.output.open("x") as output:
        json.dump(result, output, allow_nan=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("library", type=Path)
    scout = commands.add_parser("trial")
    for field in ("library", "assets", "scene", "pair", "native", "installed", "owners", "staggered",
                  "dense_native", "output"):
        scout.add_argument(field, type=Path)
    scout.add_argument("--zip", type=Path, action="append", required=True)
    args = parser.parse_args()
    if args.command == "build":
        print(json.dumps(build(args.library), indent=2))
    else:
        trial(args)
