"""Run the frozen saved curvature filter and score the sealed orders separately."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DENSE = Path("/dev/shm/leo-v3-mixed-final-0008-01")
SOUTH = Path("/dev/shm/leo-v3-south-omitted-raw01")
SOUTH_RAW = SOUTH/"near-omitted"
CONTROLS = {
    "dense": (DENSE/"candidate/joint-research-receipt.json", "dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a"),
    "south": (SOUTH_RAW/"joint-research-receipt.json", "da3f455ffd311564b4a6a201fa8cad0606608a6a5267baa415ff09f40f0aafed"),
}
DENSE_COLD = "d5caefcf59182ded8f26176b2548e03a6d814d89dca98f081bc57e765600757d"
DENSE_PAIR = (
    (Path("/dev/shm/leo-exact-solver-0008-result01/candidate/joint-research-receipt.json"),
     "c1f7486fb931e782049f6191d6751354cbb908cc739a05248c058e5ef2e9ac3a"),
    (Path("/dev/shm/leo-dense-8ms-prefix-fit01/candidate/joint-research-receipt.json"),
     "f70566671491da7eb1b5b572e60ffd5eb5ab65c398757de9e1e40137d2784c95"),
)
SOURCES = (Path(__file__), HERE/"curvature_filter.py", HERE/"curvature-filter-protocol.md")


def clocks(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def now():
    return process_time(), perf_counter()


def pins():
    return {p.name: sha256(p.read_bytes()).hexdigest() for p in SOURCES}


def write_seal(output, document, checked_sources):
    release_pins = {name: sha256(data).hexdigest() for name, data in checked_sources.items()}
    serial = json.dumps(dict(document, release_sources=release_pins), sort_keys=True, allow_nan=False)
    with output.open("xb") as file:
        file.write(gzip.compress(serial.encode(), mtime=0))


def inputs(case):
    from empty_bootstrap import bind_native, checked
    from held_spatial_start_trial import inputs as original_inputs, json_pin
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    if case == "dense":
        native, reader, offer, projection, identity = original_inputs(case)
        checked(projection, "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee")
        return native, reader, offer, projection, identity
    job = json_pin(SOUTH/"binding.json", "c3176d130ab5de1b1420593871b3c642b9bc61f0ce2e76c0e575a172bee99bc6")
    raw = json_pin(SOUTH_RAW/"unified-short-bootstrap.json", "a6c23fcc4a0aadafff77744fc1c2284513c2c3a3b1f43be62411952b31d7173c")
    request = job["request"]
    matches = tuple(SOUTH_RAW.glob("fast-scan-automatic-work/*/detections.json"))
    packet_path, = matches
    native = json_pin(packet_path, raw["native_sha256"])
    bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=raw["native_sha256"])
    cutoff = request["cutoff_utc_ns"]
    authority = native["source"]["raw_recording_authority_digest"]
    if authority != request["authority"] or native["clock_anchor"]["before"]["realtime_ns"] != cutoff:
        raise ValueError("South raw authority or cutoff changed")
    region_pin = request["offer_sha256"]["near-omitted"]
    offer = Algo08Region.parse(json_pin(request["offers"]["near-omitted"], region_pin))
    projector = job["libraries"]["--geographic-library"]
    projection = Path(projector["path"])
    checked(projection, projector["sha256"])
    path, archive_pin = Path(request["archive"]["root"]), request["archive"]["snapshots_sha256"]
    reader = TleArchiveReader(path)
    snapshots = reader.list_snapshots("space-track")
    if canonical_digest({s.path.name: s.sha256 for s in snapshots}) != archive_pin:
        raise ValueError("South causal snapshot manifest changed")
    identity = dict(detector=raw["native_sha256"], archive=archive_pin, cutoff_utc_ns=cutoff, identity=authority)
    return native, reader, offer, projection, identity


def run(case, output):
    from empty_bootstrap import RELEASE, checked, load_runtime

    _, spec, release_sources, _, release_clock = load_runtime()
    from curvature_filter import eligibility, sampled_ordering
    from dense_geographic_trial import host
    from exact_graph_execution import graph_execution
    from full_short_run import geographic_projection
    from historical_orbit_index import TRACK_PIN
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import TrackConfig
    from leo.application.localization_v3 import prepare_native_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    machine = host()
    start = now()
    native, reader, operator, projection, identity = inputs(case)
    source_checks = clocks(start)
    tracks = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", TRACK_PIN))["config"])
    parser = Path(spec["tle_parser"]["library"])
    checked(parser, spec["tle_parser"]["sha256"])
    region = SearchRegion(operator.center, width_km=operator.width_km)
    started = now()
    with (batch_records(parser) as parsed, causal_table(canonical_exports=True, previous_catalogues=True),
          graph_execution(enabled=True)):
        prepared = defer_collection(prepare_native_scan)(native, reader, tracks, element_parser=CausalPreparationParser(),
                    screen_latitude_deg=operator.screen_center[0], screen_longitude_deg=operator.screen_center[1])
    preparation = clocks(started)
    if parsed["fallback"] or prepared["status"] != "inputs_prepared":
        raise ValueError("Expected fully prepared signed factors on the strict parser")
    with geographic_projection(projection):
        started = now()
        # This diagnostic does not create a terminal. The prepared noise
        # model itself is retained by the installed context.
        scan = v5_core.scan_context(prepared, region, None, None, "previous")
        context = clocks(started)
        started = now()
        evidence, decision = eligibility(scan)
        filter_clock = clocks(started)
        started = now()
        ordered = sampled_ordering(scan, region, evidence)
        scout_clock = clocks(started)
    packed = dict(case=case, input=identity, sources=pins(), machine=machine, region=operator.document(),
                  bank=scan.norads.tolist(), prepared=dict(observations=len(prepared["tracks"]["observations"]),
                  tracks=len(scan.tracks), active_tracks=len(scan.curved), parser=parsed),
                  clocks=dict(release=release_clock, input_checks=source_checks, preparation=preparation,
                              context=context, filter=filter_clock, scout=scout_clock, local_total=clocks(start)),
                  original_waveform_reads=0, complete_solves=0, lookahead=False, filter=decision, sampled=ordered)
    write_seal(output, packed, release_sources)


def histogram(ranks):
    return dict(pairs=len(ranks), top8=sum(i <= 8 for i in ranks), top32=sum(i <= 32 for i in ranks),
                best=min(ranks, default=None), worst=max(ranks, default=None))


def score_owners(selected, track_by_obs, ranks):
    pairs = Counter((track_by_obs[oid], norad) for oid, norad, _ in selected if oid in track_by_obs)
    positions = {pair: ranks[pair[0]].get(pair[1]) for pair in pairs}
    return dict(archived_rows=len(selected), joined_rows=sum(pairs.values()),
                rows_no_bank=sum(n for p, n in pairs.items() if positions[p] is None),
                rows_top8=sum(n for p, n in pairs.items() if positions[p] is not None and positions[p] <= 8),
                rows_top32=sum(n for p, n in pairs.items() if positions[p] is not None and positions[p] <= 32),
                track_satellite_pairs=histogram([r for r in positions.values() if r is not None]))


def score_case(path, case):
    from held_spatial_start_trial import json_pin

    data = path.read_bytes()
    packet = json.loads(gzip.decompress(data))
    if packet["case"] != case or packet["sources"] != pins():
        raise ValueError("Sealed ordering or frozen source changed")
    trial, bank = packet["sampled"], packet["bank"]
    allowed = set(bank)
    if (len(allowed) != len(bank) or packet["filter"]["slots"] != packet["filter"]["survivors"]
            or any(len(row["order"]) != len(bank) or set(row["order"]) != allowed for row in trial["tracks"])):
        raise ValueError("The fallback lost or duplicated original catalogue entries")
    ranks = {row["key"]: {norad: j for j, norad in enumerate(row["order"], start=1)} for row in trial["tracks"]}
    track_by_obs = {oid: row["key"] for row in trial["tracks"] for oid in row["observation_ids"]}
    if len(track_by_obs) != sum(len(row["observation_ids"]) for row in trial["tracks"]):
        raise ValueError("A prepared observation occurs in more than one active curve")
    control = json_pin(*CONTROLS[case])
    cold = control["route_details"]["cold"]
    if len(bank) != cold["catalogue"]:
        raise ValueError("Reference did not use the same sized causal regional bank")
    owners = {arm: score_owners(rows, track_by_obs, ranks) for arm, rows in control["selected_rows"].items()}
    results = {k: v for k, v in packet.items() if k not in ("sampled", "bank")}
    results.update(scored_archive=CONTROLS[case][1], measured_seal_sha256=sha256(data).hexdigest(), owners=owners,
                   stock_cold=control["route_details"]["cold_clocks"], numerical_rejections=0,
                   sampled={k: v for k, v in trial.items() if k != "tracks"},
                   catalogue_rows=len(bank), fallback_fraction=1., credited_gross_cpu_s=0.)
    results["sampled"].update(visible_slots=sum(row["visible"] for row in trial["tracks"]),
                              sign_compatible_slots=sum(row["sign_compatible"] for row in trial["tracks"]))
    if case == "dense":
        prior = gzip.decompress((HERE/"measurements/cold-exact-budget-dense-control.json.gz").read_bytes())
        if sha256(prior).hexdigest() != DENSE_COLD:
            raise ValueError("Signed independent dense work ledger changed")
        work = json.loads(prior)["stages"]["work"]
        stock = work["ordered"]
        first = stock[work["selected"]["branch"]-1]
        if any(norad not in allowed or key not in ranks for proposal in stock for key, _, norad, _ in proposal):
            raise ValueError("The dense originals did not survive the complete bank fallback")
        pair = [json_pin(*paths)["selected_rows"] for paths in DENSE_PAIR]
        switches = {}
        for arm in pair[0]:
            old, new = [{oid: norad for oid, norad, _ in run[arm]} for run in pair]
            moved = {oid for oid in old.keys() & new.keys() if (old[oid], new[oid]) == (67511, 63478)}
            if len(moved) != 222 or not {67511, 63478} <= allowed:
                raise ValueError("The prespecified dense ambiguity does not match the sealed regression")
            used = {track_by_obs[oid] for oid in moved if oid in track_by_obs}
            switches[arm] = dict(shared_moved=len(moved), joined_curves=len(used),
                                 joined_rows=sum(oid in track_by_obs for oid in moved),
                                 original={key: ranks[key][67511] for key in sorted(used)},
                                 alternative={key: ranks[key][63478] for key in sorted(used)},
                                 both_catalogue_rows_survive=True)
        results.update(proposals=dict(archived=len(stock), retained=len(stock),
                                     winning_branch=work["selected"]["branch"],
                                     winner=histogram([ranks[key][norad] for key, _, norad, _ in first]),
                                     archived_finalist_prefixes=len(work["selected"]["prefix"]),
                                     rank_cpu_s=work["ranks"][0]["cpu_ns"]/1e9,
                                     cold_cpu_s=work["scopes"][0]["cpu_ns"]/1e9), competition=switches)
    else:
        winner, = [item for item in cold["completed"] if item["branch"] == cold["branch"]]
        labels = [bank[i] for i in winner["labels"]]
        results["proposals"] = dict(archived_prefixes=len(cold["prefix"]), retained_prefixes=len(cold["prefix"]),
                                    winning_branch=cold["branch"], winning_labels=len(labels),
                                    winner_all_labels_in_bank=True,
                                    sampled_top8_any_track=sum(any(r[n] <= 8 for r in ranks.values()) for n in labels),
                                    sampled_top32_any_track=sum(any(r[n] <= 32 for r in ranks.values()) for n in labels))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dense", "south", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a direct tmpfs results directory")
    if args.mode == "score":
        result = {case: score_case(args.root/f"{case}.json.gz", case) for case in ("dense", "south")}
        with (args.root/"result.json").open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    else:
        run(args.mode, args.root/f"{args.mode}.json.gz")
