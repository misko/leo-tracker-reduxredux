"""Price a post-graph aperture recheck from sealed factors and signed indexes."""

import argparse
from collections import Counter
import gzip
from itertools import chain
import json
from math import floor
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import RELEASE, configuration, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from eight_ms_crossover import CASE_ROOTS, RAW_REPORT_PINS, originals, strata
from eight_ms_graph_subset import GraphBuild, lane_rows, observed, signature
from local_future_policy import TRACKS_SHA256


HERE = Path(__file__).resolve().parent
PIVOTAL_PIN = "dc94c78dc1afe2b6bfb1ee28fa0179ea7d1affe03997c05909554aeefe923020"
WEAK_MARGIN = .050


def membership(tracks):
    return {oid: (frozenset(group), curved) for curved, group in tracks for oid in group}


def other_impact(original, changed, removed):
    members = membership(signature(original, frozenset(membership(original)) - {removed}))
    alternative = membership(changed)
    before, after = members.keys(), alternative.keys()
    lost, gained = len(before-after), len(after-before)
    together = sum(members[x][0] != alternative[x][0] for x in before & after)
    curves = sum(members[x][1] != alternative[x][1] for x in before & after)
    return dict(other_assignment_removed=lost, other_assignment_gained=gained, other_regrouped=together,
                other_curvature_changed=curves, influence=lost+gained+together)


def inventory(case, packet):
    from first_third_ingress import chunk_rows
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource

    source = packet["source"]
    path = CASE_ROOTS[case] / "8ms/fast-scan-inputs" / (source["session_id"] + ".json")
    native_inventory = read(path)
    if canonical_digest(native_inventory) != source["input_manifest_sha256"]:
        raise ValueError("Original signed input inventory changed")
    output, seen = [], set()
    for entry in native_inventory["segments"]:
        source_reader = FastSegmentSource(entry)
        for chunk in source_reader.reader.manifest.chunks:
            sizes = {row.acquisition["global_visit"]: row.payload_bytes for row in chunk_rows(source_reader, chunk)}
            if seen & sizes.keys() or len(sizes) != chunk.window_count:
                raise ValueError("Original signed visit inventory contains duplicate IDs")
            seen.update(sizes)
            output.append((chunk.compressed_bytes, chunk.index_bytes, sizes))
    if seen != set(range(native_inventory["window_count"])):
        raise ValueError("Signed visit inventory is incomplete")
    return output


def storage_footprint(members, visits):
    size = Counter()
    matched = set()
    for compressed, index, rows in members:
        requested = visits & rows.keys()
        if requested:
            if requested & matched:
                raise ValueError("A targeted visit occurs in multiple members")
            matched.update(requested)
            size.update(members=1, compressed_bytes=compressed, index_bytes=index, decoded_bytes=sum(rows.values()),
                        requested_stereo_bytes=sum(rows[x] for x in requested))
    if visits != matched:
        raise ValueError("Staged requests did not match the signed recording inventory")
    return dict(visits=len(visits), **{name: size[name] for name in
                ("members", "compressed_bytes", "index_bytes", "decoded_bytes", "requested_stereo_bytes")})


def prices(archived):
    eight, twelve = (archived["runs"][name] for name in ("8ms", "12ms"))
    short_s, full_s = (twelve["native"]["native_cpu_ns"][key]/1e9 for key in ("short_primary", "full"))
    spent = {name: sum(row["native"]["native_cpu_ns"].values())/1e9 for name, row in (("8ms", eight), ("12ms", twelve))}
    return dict(mixed_saving_s=spent["12ms"]-spent["8ms"],
                restart_12s=short_s/twelve["native"]["native_calls"]["short_primary"],
                restart_20s=full_s/twelve["native"]["native_calls"]["full"],
                existing_12ms_nonnative_acquire_s=twelve["acquisition"]["cpu_ns"]/1e9-spent["12ms"],
                existing_8ms_nonnative_acquire_s=eight["acquisition"]["cpu_ns"]/1e9-spent["8ms"])


def rate_report(candidates, members, price):
    storage = storage_footprint(members, {row["visit"] for row in candidates})
    lanes = len(candidates)
    arms = {}
    for label, rate in (("12ms", price["restart_12s"]), ("20ms", price["restart_20s"])):
        native = lanes * rate
        left = price["mixed_saving_s"] - native
        arms[label] = dict(estimated_native_cpu_s=native, cpu_left_after_estimated_native_s=left,
                           required_compressed_bytes_per_s=storage["compressed_bytes"]/left if left > 0 else None,
                           required_decoded_bytes_per_s=storage["decoded_bytes"]/left if left > 0 else None)
    return dict(lanes=lanes, storage=storage, restarts=arms)


def audit(case, crossover, output):
    system = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.analysis.polynomial_tracklets import TrackConfig
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths

    _, _, (measured,) = originals(case, ("8ms",))
    opportunities = strata(measured, measured)
    metadata = {oid: dict(order=order, visit=row["visit_index"], receiver=row["receiver_id"],
                          anchor=kind == "anchor", margin=None if factor is None else factor["fractional_exact_score"]-
                          factor["fractional_control_score"])
                for order, (oid, kind, row, _, factor) in enumerate(opportunities)}
    by_lane = lane_rows(winning_observations(measured)[0])
    config = TrackConfig(**read(checked(RELEASE / "assets/tracks.json", TRACKS_SHA256))["config"])
    build = GraphBuild(config, max_fits=600)
    scored = []
    with native_paths(Path(spec["graph_path"]["library"]), required=True) as native:
        first = {key: build(rows) for key, rows in by_lane.items()}
        if tuple(sorted(chain.from_iterable(first.values()))) != observed(crossover, "111"):
            raise ValueError("Actual 8 ms preliminary Graph topology changed")
        initial = build.clocks()
        cpu, start = process_time(), perf_counter()
        for key, base in first.items():
            for removed in membership(base):
                meta = metadata[removed]
                if not meta["anchor"]:
                    rest = build([row for row in by_lane[key] if row["observation_id"] != removed])
                    scored.append(dict(oid=removed, **meta, **other_impact(base, rest, removed)))
        leave_one_out = dict(lane_fits=build.fits-initial["fits"], cpu_s=process_time()-cpu, elapsed_s=perf_counter()-start)
    ranking = sorted(scored, key=lambda row: (-row["influence"], row["margin"], row["order"]))
    prepared = membership(tuple(chain.from_iterable(first.values())))
    for row in ranking:
        row["high_influence"] = row["influence"] >= config.min_points
        row["weak_margin"] = row["margin"] < WEAK_MARGIN
    archived = read(checked(HERE / f"measurements/eight-ms-{case}.json", RAW_REPORT_PINS[case]))
    price = prices(archived)
    cheap = floor(price["mixed_saving_s"]/price["restart_12s"])
    rules = {"weak_margin": [row for row in ranking if row["weak_margin"]],
             "high_influence": [row for row in ranking if row["high_influence"]],
             "union": [row for row in ranking if row["weak_margin"] or row["high_influence"]],
             "intersection": [row for row in ranking if row["weak_margin"] and row["high_influence"]],
             "free_storage_12ms_cap": ranking[:cheap]}
    members = inventory(case, measured)
    retention = storage_footprint(members, {row["visit"] for row in metadata.values()
                                           if not row["anchor"] and row["margin"] is not None})
    costs = {name: rate_report(rows, members, price) for name, rows in rules.items()}
    reference = json.loads(gzip.decompress(checked(HERE / "measurements/eight-ms-graph-subset.json.gz", PIVOTAL_PIN).read_bytes()))
    factors = {row["oid"] for lane in reference[case]["changed_lanes"] for row in lane["reduced"]}
    ranks = {row["oid"]: rank for rank, row in enumerate(ranking, start=1)}
    coverage = {oid: dict(in_actual_8ms_graph=oid in prepared, rank=ranks.get(oid),
                          features=next((row for row in ranking if row["oid"] == oid), None),
                          rules={name: any(row["oid"] == oid for row in rows) for name, rows in rules.items()})
                for oid in sorted(factors)}
    write(output, dict(case=case, machine=system, graph_path_sha256=spec["graph_path"]["sha256"],
                       graph_assets=TRACKS_SHA256, staged_path_pin=PIVOTAL_PIN, native=dict(native),
                       pilot_threshold=WEAK_MARGIN, high_influence_other_rows=config.min_points,
                       prepared_rows=len(prepared), eligible_nonanchors=len(ranking), initial_graph=initial,
                       leave_one_out=leave_one_out, inherited_native_prices=price,
                       short_native_free_storage_cap=cheap, retention_upper_from_first_positive=retention,
                       whole_recording=storage_footprint(members, set(chain.from_iterable(row.keys() for _, _, row in members))),
                       first_look_index_payload_verified_only=True, costs=costs, pivotal_coverage=coverage, ranking=ranking))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_ROOTS)
    parser.add_argument("crossover", type=Path)
    parser.add_argument("output", type=Path)
    audit(**vars(parser.parse_args()))
