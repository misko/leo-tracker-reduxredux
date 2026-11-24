"""Measure which missing short lanes contribute to archived installed time support."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import pairwise
import json
from math import fsum, isfinite
from pathlib import Path
import sys

from .calibration_transport import FIELD, FIRST30, signed_attempt
from .capped_revisit import HERTZ, SAMPLE_RATE, STREAM, candidate_packet, owner_bounds, saved_only, signed
from .ds30_paired_inputs import digest
from .track_cfo_denoise import COHORTS, original_pairs
from satellite_set_transfer import named_rows
from signed_cfo_time import ARMS, MAX_GAP, difference, epoch


HERE = Path(__file__).resolve().parent
POSITIVE = ("missing", "common", "disagreeing", "full_anchor")


def classes(installed, candidate):
    groups, remaining = defaultdict(set), Counter()
    for oid, lane in installed.items():
        before, after = lane["factor"], candidate[oid]["factor"]
        if any(len(row["row"]["candidates"]) != int(row["factor"] is not None) for row in (lane, candidate[oid])):
            raise ValueError("The enrolled detector packet is no longer a unique selected factor per lane")
        if any(not (isfinite(x[HERTZ]) and isfinite(epoch(x))) for x in (before, after) if x is not None):
            raise ValueError("The enrolled factor contains nonfinite signed measurements")
        if before is None:
            scope = "short" if lane["short"] else "anchor"
            state = "candidate_only" if after else "both_empty"
            remaining[f"{scope}_{state}"] += 1
        elif not lane["short"]:
            groups["full_anchor"].add(oid)
        elif after is None:
            groups["missing"].add(oid)
        elif difference(before, after)[2]:
            groups["common"].add(oid)
        else:
            groups["disagreeing"].add(oid)
    result = {name: groups[name] for name in POSITIVE}
    if sum(map(len, result.values()))+sum(remaining.values()) != len(installed):
        raise ValueError("Some signed lanes were left without an accounting class")
    return result, dict(remaining)


def lane_key(row):
    return tuple(row["row"][field] for field in STREAM)


def candidate_neighbors(candidate):
    index = defaultdict(list)
    for lane in candidate.values():
        if lane["factor"] is not None:
            index[lane_key(lane)].append(lane["counter"])
    return {key: sorted(times) for key, times in index.items()}


def context_counts(ids, lanes, index):
    total = Counter()
    for oid in ids:
        lane = lanes[oid]
        times = index.get(lane_key(lane), [])
        counter = lane["counter"]
        left, right = bisect_left(times, counter)-1, bisect_right(times, counter)
        before = left >= 0 and 0 < counter-times[left] <= 2*SAMPLE_RATE
        after = right < len(times) and 0 < times[right]-counter <= 2*SAMPLE_RATE
        total[("neither", "before", "after", "both")[int(before)+2*int(after)]] += 1
    return {name: total[name] for name in ("before", "after", "both", "neither")}


def time_groups(owners, observations):
    streams = defaultdict(list)
    for oid, (norad, _) in owners.items():
        lane = observations[oid]
        streams[norad, lane_key(lane)].append(oid)
    for group in streams.values():
        ordered = sorted(group, key=lambda oid: observations[oid]["counter"])
        split = [0] + [i for i, (a,b) in enumerate(pairwise(ordered),1)
                       if observations[b]["counter"]-observations[a]["counter"] > MAX_GAP] + [len(ordered)]
        for first, last in pairwise(split):
            yield ordered[first:last]


def time_design(counters):
    if len(counters) < 2:
        return (0., 0.)
    times = [(t-counters[0])/SAMPLE_RATE for t in counters]
    mean = fsum(times)/len(times)
    x = [t-mean for t in times]
    linear = fsum(t*t for t in x)
    if len(x) < 3 or not linear:
        return linear, 0.
    constant = linear/len(x)
    slope = fsum(t**3 for t in x)/linear
    return linear, fsum((t*t-constant-slope*t)**2 for t in x)


def owner_times(owners, observed, classes_):
    all_ids = set(owners)
    available = {"original": all_ids, "without_missing_shorts": all_ids-classes_["missing"],
                 "strict_shorts_and_full_anchors": all_ids & (classes_["common"] | classes_["full_anchor"])}
    metrics = {name: Counter() for name in available}
    time_designs = {name: [] for name in available}
    placement = Counter()
    counts = Counter()
    for group in time_groups(owners, observed):
        counts["original_groups"] += 1
        common = [i for i, oid in enumerate(group) if oid in classes_["common"]]
        missing = [i for i, oid in enumerate(group) if oid in classes_["missing"]]
        counts["groups_with_missing_owners"] += bool(missing)
        for i in missing:
            if not common:
                where = "no_common_owned_short"
            elif i < common[0]:
                where = "before_common"
            elif i > common[-1]:
                where = "after_common"
            else:
                where = "between_common"
            placement[where] += 1
        for name, keep in available.items():
            selected = [oid for oid in group if oid in keep]
            measure = metrics[name]
            measure["owned_points"] += len(selected)
            measure["wholly_erased_groups"] += not selected
            measure["first_owner_lost_groups"] += group[0] not in keep
            measure["last_owner_lost_groups"] += group[-1] not in keep
            t = [observed[oid]["counter"] for oid in selected]
            measure["span_samples"] += t[-1]-t[0] if t else 0
            measure["gaps_over_8_s"] += sum(b-a > MAX_GAP for a,b in pairwise(t))
            time_designs[name].append(time_design(t))
    for name, sums in time_designs.items():
        measures = metrics[name]
        measures["span_s"] = measures.pop("span_samples")/SAMPLE_RATE
        measures["slope_design_s2"], measures["quadratic_design_s4"] = map(fsum, zip(*sums)) if sums else (0.,0.)
    return dict(metrics={k: dict(v) for k,v in metrics.items()}, group_counts=dict(counts),
                missing_owner_placement_vs_common=dict(placement),
                satellites_with_missing_owner=len({n for oid, (n, _) in owners.items() if oid in classes_["missing"]}))


def fit_manifest(pub, result, row, positive_count):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    evidence = result["evidence"]
    detail = FastStandardAnalysisStore(pub).detail(evidence["receipt"]["run_id"])
    if (detail["state"] != "complete" or detail["input_sha256"] != result["native_sha256"]
            or detail["terminal_sha256"] != row["terminal_sha256"]
            or detail["raw_authority"] != row["raw_authority_sha256"] or detail["glrt_points"] != positive_count
            or {arm: r["owner_sha256"] for arm,r in detail["arms"].items()} != evidence["owners"]):
        raise ValueError("The installed publication is detached from its selected native owner digest")
    return detail["arms"]


def exact_arm(owners, membership, installed, candidate_index):
    owner_ids = owners.keys()
    records = {}
    for name, all_ids in membership.items():
        yes, no = all_ids & owner_ids, all_ids-owner_ids
        side = records[name] = dict(installed_owner=len(yes), installed_nonowner=len(no),
                                    radio={str(rx): dict(owned=sum(installed[i]["radio"]==rx for i in yes),
                                                 nonowned=sum(installed[i]["radio"]==rx for i in no)) for rx in (0,1)})
        if name in ("missing", "common"):
            side["neighbor_context"] = dict(owned=context_counts(yes, installed, candidate_index),
                                            nonowned=context_counts(no, installed, candidate_index))
    return dict(class_counts=records, time=owner_times(owners, installed, membership))


def study(snapshot):
    results = {}
    for cohort, cases in COHORTS.items():
        pairs = original_pairs(snapshot, cohort)
        for case in cases:
            entry = pairs[case,"installed"]
            old = signed_attempt(FIELD, entry)
            pub = (FIELD / entry["attempt"]).parent / "publication"
            native = signed.read_native(pub, old["native_sha256"])
            new, sparse, candidate, _ = candidate_packet(pairs[case,"successor"])
            if old["raw_identity"] != new["raw_identity"] or native["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
                raise ValueError("The candidate and installed packets are from different signed inputs")
            installed = signed.opportunities(native)
            signed.bind_pair(native, sparse, installed, candidate)
            groups, remaining = classes(installed, candidate)
            positive = set.union(*groups.values())
            arms = fit_manifest(pub, old, entry, len(positive))
            exact = named_rows(case, old)
            result = results[case] = dict(cohort=cohort, opportunity_count=len(installed),
                                          installed_positive_count=len(positive), installed_classes={k:len(v) for k,v in groups.items()},
                                          no_installed_positive_accounting=remaining, installed_native_sha256=old["native_sha256"],
                                          mixed_native_sha256=new["native_sha256"], attempt=entry["attempt_result_sha256"],
                                          owner_source="saved digest-matched rows" if exact else "published totals only",
                                          installed_graph_alias_or_piece_rows_available=False, arms={})
            candidate_index = candidate_neighbors(candidate)
            result["unstratified_candidate_neighbor_context"] = {
                name: context_counts(groups[name], installed, candidate_index) for name in ("missing","common")}
            if exact:
                maps = signed.owners(exact, old["evidence"]["owners"])
                for arm in ARMS:
                    owners = maps[arm]
                    if (not owners.keys() <= positive or len(owners) != arms[arm]["associated_points"]
                            or len({n for n,_ in owners.values()}) != arms[arm]["satellites"]):
                        raise ValueError("A published installed owner differs from its native factor or manifest")
                    result["arms"][arm] = dict(exact_arm(owners, groups, installed, candidate_index),
                                               owner_sha256=arms[arm]["owner_sha256"], owner_count=len(owners))
            else:
                for arm in ARMS:
                    count = arms[arm]["associated_points"]
                    result["arms"][arm] = dict(owner_sha256=arms[arm]["owner_sha256"], owner_count=count,
                                               exact_owner_count_bounds={k:owner_bounds(count,len(positive),len(v))
                                                                         for k,v in groups.items()})
    return dict(ledger_sha256=FIRST30, protocol_sha256=digest((HERE/"missed-owner-support-protocol.md").read_bytes()), cases=results)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("export", type=Path)
    args = cli.parse_args()
    sys.addaudithook(saved_only)
    print(json.dumps(study(args.export), indent=2, sort_keys=True, allow_nan=False))
