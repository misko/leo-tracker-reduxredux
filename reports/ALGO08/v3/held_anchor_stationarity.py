"""Measure independent full-anchor support without using held measurements to form tracks."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from math import remainder
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import RELEASE, configuration, read, write
from anchor_exposure import enroll
from dense_full_short_raw import checked
from dense_geographic_trial import host
from discovery_margin import factor_weights
from discovery_margin_trial import verified_input
from full_short_run import checked_recipe
from local_future_policy import TRACKS_SHA256
from north_factor_swap import PINS as NORTH_PINS, rebound


NORTH = Path("/var/tmp/leo-north-short-regional-nov23")
SOUTH = Path("/var/tmp/leo-full-short-south-transfer-final/containing")
SOUTH_PIN = "sha256:a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"
CFO_HZ = "fractional_tracking_cfo_hz"
MATCH_HZ = 250.
GROUPS = ("all", "some", "none")


def signed_inputs():
    from leo.contracts.digests import canonical_digest
    from short_primary_epoch_audit import STOCK

    _, _, north = verified_input("north", "12ms")
    _, _, weak = verified_input("physical", "12ms")
    (south_path,) = (SOUTH / "fast-scan-automatic-work").glob("*/detections.json")
    (full_path,) = (NORTH / "stock/fast-scan-automatic-work").glob("*/detections.json")
    (full_terminal,) = full_path.parent.parent.glob("*/terminal.json")
    south, full = read(south_path), read(full_path)
    seal = read(SOUTH / "full-short-recipe.json")
    if (canonical_digest(south) != SOUTH_PIN or not south["source"]["qualified"]
            or seal["recipe"] != checked_recipe() or seal["saved_digest"] is not None
            or seal["receiver_audit"]["selected"] != sum(factor_weights(south, unit=True)[1].values())):
        raise ValueError("The South input differs from the original unfiltered short receiver")
    if (canonical_digest(full) != NORTH_PINS["stock"] or read(full_terminal)["native_sha256"] != NORTH_PINS["stock"]
            or full["provenance"]["detector_sha256"] != STOCK or not full["source"]["qualified"]):
        raise ValueError("The North full packet differs from the original v3 receiver")
    return {"north": north, "DS30-0016": weak, "south": south}, full


def counterpart_census(full, short):
    from short_primary_epoch_audit import FRAME_SAMPLES, epoch, good_match, paired_probes, stats

    counts = Counter()
    signed, phase = [], []
    for _, _, left, right, short_slot in paired_probes(full, short):
        kind = "short_slot" if short_slot else "anchor"
        both = left is not None and right is not None
        label = ("matched" if good_match(left, right) else "mismatch") if both else (
            "full_only" if left is not None else "short_only" if right is not None else "empty")
        counts[kind, label] += 1
        if both:
            counts[kind, "identical_factors"] += left == right
            counts[kind, "identical_cfo"] += left[CFO_HZ] == right[CFO_HZ]
        if label == "matched":
            signed.append(right[CFO_HZ] - left[CFO_HZ])
            phase.append(remainder(epoch(right) - epoch(left), FRAME_SAMPLES))
    return dict(lanes={kind: {name: count for (k, name), count in counts.items() if k == kind}
                       for kind in ("anchor", "short_slot")}, signed_hz=stats(signed), wrapped_samples=stats(phase))


def erase(document):
    """Keep the opportunity holes. Their original measurements never enter history."""
    probes = document["source"]["probes"]
    held = [index for index, opportunity in enumerate(enroll(document)) if opportunity[4] == "anchor"]
    masked = list(probes)
    for index in held:
        masked[index] = dict(probes[index], candidates=[])
    return rebound(document, masked, ["diagnostic all full anchors erased before preparation v1"]), held


def history_only(masked):
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    history, rows = Continuation(), []
    for row in masked["source"]["probes"]:
        _, keep, _ = history.select(row)
        rows.append(dict(row, candidates=[] if keep is None else [row["candidates"][keep]]))
    return rebound(masked, rows, ["diagnostic strictly erased carrier history v1"])


def lane(probe):
    return probe["receiver_id"], probe["channel"], probe["actual_rf_hz"], probe["edge"]


def nominate(track, raw, at, branch_period, gap):
    from numpy.polynomial.legendre import legval

    times = track["times"]
    right = times.searchsorted(at)
    if (right == 0 or right == len(times) or times[right] <= at
            or max(at - times[right - 1], times[right] - at) > gap):
        return None
    piece = next((piece for piece in track["pieces"]
                  if piece["start_s"] <= times[right - 1] < at < times[right] <= piece["end_s"]), None)
    if piece is None:
        return None
    predicted = float(legval((at - piece["reference_time_s"]) / piece["time_scale_s"], piece["coefficients_hz"]))
    branches = [round((lifted - measured) / branch_period)
                for lifted, measured in zip(track["values"][right - 1:right + 1], raw[right - 1:right + 1], strict=True)]
    signed = predicted - branches[0] * branch_period if branches[0] == branches[1] else None
    return predicted, signed


def predictions(graph, masked, held, evidence, ids, selection, config):
    by_lane, roster = defaultdict(list), {}
    observed = {point["observation_id"]: point["measured_cfo_hz"] for point in graph["observations"]}
    probes = masked["source"]["probes"]
    lookup = dict(zip(ids, probes, strict=True))
    for track in graph["tracks"]:
        members = track["observation_ids"]
        (group,) = {lane(lookup[oid]) for oid in members}
        raw = [observed[oid] for oid in members]
        survives = sum(oid in selection for oid in members)
        kind = "all" if survives == len(members) else "some" if survives else "none"
        roster[track["key"]] = dict(group=kind, lane=group, rows=len(members), survives=survives, members=members)
        by_lane[group].append((track, raw))
    result = []
    for index in held:
        proposals = []
        for track, raw in by_lane[lane(probes[index])]:
            candidate = nominate(track, raw, evidence.time_s[index], config.alias_spacing_hz, config.max_join_gap_s)
            if candidate is not None:
                proposals.append((track["key"], *candidate))
        result.append(proposals)
    return roster, result


def score(held, probes, predicted, roster, config):
    from short_primary_epoch_audit import selected, stats

    lanes, tracks, errors = Counter(), defaultdict(Counter), []
    serialized = []
    margin = config.association_sigma * config.noise_sigma_hz
    for index, candidates in zip(held, predicted, strict=True):
        probe = probes[index]
        factor = selected(probe)
        actual = factor[CFO_HZ] if factor is not None else None
        matches, signed, folded = [], [], []
        for key, lift, cf in candidates:
            row = tracks[key]
            row["opportunities"] += 1
            row["signed_opportunities"] += cf is not None
            if actual is None:
                row["empty"] += 1
                continue
            row["positive"] += 1
            row["signed_positive"] += cf is not None
            folded.append(remainder(lift - actual, config.alias_spacing_hz))
            row["folded_matches"] += abs(folded[-1]) <= MATCH_HZ
            if cf is not None:
                signed.append(cf - actual)
                if abs(signed[-1]) <= MATCH_HZ:
                    matches.append(key)
                    row["signed_matches"] += 1
        if len(matches) == 1:
            tracks[matches[0]]["unique_matches"] += 1
        if signed:
            errors.append(min(signed, key=abs))
        label = "positive" if actual is not None else "empty"
        lanes[label] += 1
        lanes[label + "_covered"] += bool(candidates)
        lanes[label + "_signed_covered"] += any(cf is not None for _, _, cf in candidates)
        lanes[label + "_proposals"] += len(candidates)
        lanes[label + "_signed_proposals"] += sum(cf is not None for _, _, cf in candidates)
        lanes["positive_signed_matches"] += bool(matches)
        lanes["positive_signed_unique"] += len(matches) == 1
        lanes["positive_signed_ambiguous"] += len(matches) > 1
        lanes["positive_signed_graph_gate"] += any(abs(diff) <= margin for diff in signed)
        lanes["positive_folded_oracle_matches"] += any(abs(diff) <= MATCH_HZ for diff in folded)
        serialized.append(dict(index=index, visit=probe["visit_index"], lane=lane(probe), actual=actual, predictions=candidates))
    groups = {}
    detail = {key: dict(row, counts=dict(tracks[key])) for key, row in roster.items()}
    for group in GROUPS:
        entries = [row for row in detail.values() if row["group"] == group]
        coverage = Counter()
        for row in entries:
            coverage["rows"] += row["rows"]
            counts = row["counts"]
            coverage["tracks_with_ge2_positive"] += counts.get("positive", 0) >= 2
            coverage["tracks_with_ge2_signed_positive"] += counts.get("signed_positive", 0) >= 2
            coverage["tracks_with_ge2_unique_matches"] += counts.get("unique_matches", 0) >= 2
            coverage.update(counts)
        groups[group] = dict(track_count=len(entries), coverage=dict(coverage))
    return dict(lanes=dict(lanes), groups=groups, tracks=detail, closest_signed_error=stats(errors), rows=serialized)


def audit(document, config, native_library):
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection

    cpu0, wall0 = process_time(), perf_counter()
    masked, held = erase(document)
    historical = history_only(masked)
    evidence, _, _ = frequency_evidence(masked)
    ids = ["sha256:" + sha256(value.encode()).hexdigest() for value in evidence.ids]
    start_graph = process_time()
    graph, routes, timings = {}, {}, {}
    prepare = defer_collection(prepare_tracks)
    for name, native in (("unfiltered", masked), ("history", historical)):
        begin = process_time()
        with native_paths(native_library, required=True) as path_counts:
            graph[name] = prepare(native, config)
        routes[name] = dict(path_counts)
        timings[name] = process_time() - begin
    census, digest = {}, {}
    started_predictions = process_time()
    accepted = {point["observation_id"] for point in graph["history"]["observations"]}
    for name, value in graph.items():
        roster, predicted = predictions(value, masked, held, evidence, ids, accepted, config)
        digest[name] = canonical_digest([roster, predicted])
        census[name] = (roster, predicted)
    ready = process_time()
    outcomes = {name: score(held, document["source"]["probes"], predicted, roster, config)
                for name, (roster, predicted) in census.items()}
    return dict(
        input=canonical_digest(document), training=canonical_digest(masked), history=canonical_digest(historical),
        predictions_before_scoring=digest, anchor_visits=len(held) // 2, outcomes=outcomes, graph_paths=routes,
        clocks=dict(mask_history_cpu_s=start_graph-cpu0, graph_cpu_s=timings,
                    proposal_cpu_s=ready-started_predictions, score_cpu_s=process_time()-ready,
                    total_cpu_s=process_time()-cpu0, elapsed_s=perf_counter()-wall0),
    )


def north_attribution(result, full, short):
    """Join archived owners only after the predictor and all its scores are complete."""
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from short_primary_epoch_audit import good_match, paired_probes

    path = NORTH / "containing"
    proof = read(path / "joint-research-receipt.json")
    receipt = proof["receipt"]
    if read(path / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")["native_sha256"] != result["input"]:
        raise ValueError("Original North owners correspond to a different receiver packet")
    manifest = read(FastStandardAnalysisStore(path).folder(receipt["run_id"]) / "manifest.json")
    paired = {oid: ("matched" if good_match(left, right) else "short_only" if left is None else "mismatch",
                    "short" if slot else "anchor")
              for oid, _, left, right, slot in paired_probes(full, short) if right is not None}
    tracks = {oid: row for row in result["outcomes"]["unfiltered"]["tracks"].values() for oid in row["members"]}
    comparison = {}
    for arm, selected in proof["selected_rows"].items():
        owners = {oid: satellite for oid, satellite, _ in selected}
        if len(owners) != len(selected) or owner_digest(owners) != manifest["arms"][arm]["owner_sha256"]:
            raise ValueError("The scored North owners disagree with the official publication")
        counts = defaultdict(Counter)
        for oid in owners:
            counterpart, slot = paired[oid]
            row = tracks.get(oid)
            counts[counterpart]["total"] += 1
            if slot == "anchor":
                counts[counterpart]["held_anchor"] += 1
            elif row is None:
                counts[counterpart]["no_training_track"] += 1
            else:
                counts[counterpart]["training_track"] += 1
                counts[counterpart]["repeatedly_supported_track"] += row["counts"].get("unique_matches", 0) >= 2
        comparison[arm] = {label: dict(count) for label, count in counts.items()}
    return comparison


def run(output):
    system = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    from leo.analysis.polynomial_tracklets import TrackConfig

    config = TrackConfig(**read(checked(RELEASE / "assets/tracks.json", TRACKS_SHA256))["config"])
    docs, full = signed_inputs()
    north = counterpart_census(full, docs["north"])
    results = {case: audit(document, config, Path(spec["graph_path"]["library"])) for case, document in docs.items()}
    attribution = north_attribution(results["north"], full, docs["north"])
    write(output, dict(machine=system, graph=spec["graph_path"], north_counterparts=north,
                      cases=results, north_postfit_attribution=attribution))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
