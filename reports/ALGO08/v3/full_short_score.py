"""Score sealed prefix factors, inherited owner support and 55-file clock scenarios."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
from statistics import median, quantiles

from acquisition_throughput import gates, minimum_rate
from survey_owner_diagnostic import exact_owners

from .full_short_cold import MEASURED, ORDERS, freeze
from .sparse_cold_input import ARCHIVED_DETECTION_SHA, WINDOWS, verified


INVENTORY_SHA = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"
OWNER_SHA = "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"
SCENARIOS = {"23.482/60.966": 23.482/60.966, "11.680/21.383": 11.680/21.383}
PERIOD_SAMPLES = 13333


def selected(probe):
    saved = probe["candidates"]
    if len(saved) > 1 or any(candidate["passed_fractional_margin_gate"] is not True for candidate in saved):
        raise ValueError("Expected at most one individually verified selected factor per antenna/visit")
    return saved[0] if saved else None


def changes(original, current):
    epoch = lambda factor: factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]
    return dict(
        wrapped_timing_samples=remainder(epoch(current)-epoch(original), PERIOD_SAMPLES),
        signed_cfo_change_hz=current["fractional_tracking_cfo_hz"]-original["fractional_tracking_cfo_hz"],
        rank_equal=current["candidate_rank"] == original["candidate_rank"],
    )


def distance_stats(samples):
    if not samples:
        return dict(count=0)
    absolute = sorted(map(abs, samples))
    return dict(count=len(samples), median_signed=median(samples), median_absolute=median(absolute),
                p95_absolute=quantiles(absolute, n=20, method="inclusive")[18] if len(absolute) > 1 else absolute[0],
                max_absolute=absolute[-1])


def compare_lanes(original, candidate):
    before, after = (doc["source"]["probes"] for doc in (original, candidate))
    visits, lanes = Counter(), {}
    session = original["source"]["session_id"]
    for index, (left, right) in enumerate(zip(before, after, strict=True)):
        metadata = dict(left, candidates=[])
        if metadata != dict(right, candidates=[]):
            raise ValueError("The receiver arms share no one-to-one lane binding")
        stream = tuple(left[key] for key in ("channel", "actual_rf_hz", "edge"))
        if index % 2 == 0:
            slot = "full" if visits[stream] % 8 == 0 else "short_primary"
            visits[stream] += 1
        a, b = selected(left), selected(right)
        delta = None if a is None or b is None else changes(a, b)
        matched = delta is not None and abs(delta["wrapped_timing_samples"]) <= 2 and abs(delta["signed_cfo_change_hz"]) <= 250
        token = f"{session}:{left['receiver_id']}:{left['valid_start_counter']}"
        identity = "sha256:" + sha256(token.encode()).hexdigest()
        if identity in lanes:
            raise ValueError("Duplicate original observation ID")
        lanes[identity] = dict(visit=left["visit_index"], rx=left["receiver_id"], channel=left["channel"], slot=slot,
                               stock_rank=None if a is None else a["candidate_rank"],
                               candidate_rank=None if b is None else b["candidate_rank"], delta=delta,
                               matched=matched, matched_same_rank=matched and delta["rank_equal"])
    return lanes


def counts(lanes):
    available_before = [row for row in lanes if row["stock_rank"] is not None]
    available_after = [row for row in lanes if row["candidate_rank"] is not None]
    both = [row for row in available_after if row["delta"] is not None]
    matched = [row for row in both if row["matched"]]
    return dict(lanes=len(lanes), stock_selected=len(available_before), candidate_selected=len(available_after),
                both_selected=len(both), matched=len(matched), matched_same_rank=sum(row["matched_same_rank"] for row in both),
                stock_only=len(available_before)-len(both), candidate_only=len(available_after)-len(both),
                candidate_extra_vs_tolerance=len(available_after)-len(matched),
                rank_changed=sum(not row["delta"]["rank_equal"] for row in both),
                errors={kind: {key: distance_stats([row["delta"][key] for row in selected_rows])
                               for key in ("wrapped_timing_samples", "signed_cfo_change_hz")}
                        for kind, selected_rows in (("colocated", both), ("tolerance_matched", matched))})


def owner_score(lanes):
    source = gzip.decompress(verified(MEASURED / "track-quadrature.json.gz", OWNER_SHA))
    original = json.loads(source)["runs"]["DS30-0008"]["stock"]
    if original["identity"]["native_sha256"] != "sha256:" + ARCHIVED_DETECTION_SHA:
        raise ValueError("Published full-stock owners refer to another native measurement")
    owners = exact_owners(original["selected_rows"], original)
    scores = {}
    for arm, published in owners.items():
        held = {oid: label for oid, label in published.items() if oid in lanes}
        support = [lanes[oid] for oid in held]
        if any(row["stock_rank"] is None for row in support):
            raise ValueError("Published owners reference an empty installed prefix lane")
        scores[arm] = dict(full_published=len(published), prefix=counts(support),
                          by_role={role: counts([lanes[oid] for oid, (_, held_role) in held.items() if held_role == role])
                                   for role in sorted({role for _, role in held.values()})},
                          by_slot={slot: counts([row for row in support if row["slot"] == slot])
                                   for slot in ("full", "short_primary")},
                          published_owner_sha256=original["owners"][arm], prefix_sats=len({sat for sat, _ in held.values()}))
    return scores


def project(repeats, inventory):
    groups = {"all": inventory, "warm": [r for r in inventory if (r["initial_residency"] or 0) > .95],
              "cold": [r for r in inventory if r["initial_residency"] is not None and r["initial_residency"] < .2]}
    result = {}
    for name, group in groups.items():
        cases = {}
        for scenario, fraction in SCENARIOS.items():
            clocks = []
            for repeat, pair in enumerate(repeats):
                for row in pair:
                    rate = row["effective_compressed_MB_per_s"]
                    omitted = row["omitted_subprocess_wall_ns"] / 1e9
                    gauss = gates(group, rate, fraction)
                    full = gates(group, rate, fraction, startup_s=omitted)
                    clocks.append(dict(arm=row["arm"], pair=repeat, rate=rate, omitted_worker_s=omitted,
                                       median_and_sum_ratio=gauss, median_and_sum_with_worker_ratio=full,
                                       passes_both_gates=max(gauss) <= .5,
                                       passes_both_with_worker_gates=max(full) <= .5))
            cases[scenario] = dict(solve_fraction=fraction, predictions=clocks,
                                   minimum_rates_MB_s=[minimum_rate(group, fraction, gate) for gate in (0, 1)])
        result[name] = dict(inventories=len(group), median_MB=median(r["compressed_MB"] for r in group),
                            member_count_range=[min(r["members"] for r in group), max(r["members"] for r in group)],
                            scenarios=cases)
    return result


def score(directory, summary, full):
    receipt = directory / "acquisition.json"
    acquisition = json.loads(receipt.read_bytes())
    if (acquisition["orders"] != [list(pair) for pair in ORDERS] or acquisition["compressed_bytes"] != 232083693
            or acquisition["archived_stock_sha256"] != ARCHIVED_DETECTION_SHA):
        raise ValueError("Expected four acquisition receipts from the signed three-member prefix")
    decoded = {}
    for pair in acquisition["repeats"]:
        for row in pair:
            body = json.loads(verified(directory / row["detection_file"], row["sealed_detection_sha256"]))
            if row["arm"] in decoded and body != decoded[row["arm"]]:
                raise ValueError("Repeated acquisition changed sealed evidence")
            decoded[row["arm"]] = body
    if {doc["provenance"]["window_count"] for doc in decoded.values()} != {WINDOWS}:
        raise ValueError("The scored control is limited to the frozen prefix")
    lanes = compare_lanes(decoded["stock"], decoded["full-short"])
    if 2 * WINDOWS != len(lanes):
        raise ValueError("The scored prefix changed exact lane support")
    for pair in acquisition["repeats"]:
        measured, = [row["native"]["native_calls"] for row in pair if row["arm"] == "full-short"]
        if Counter(row["slot"] for row in lanes.values()) != measured:
            raise ValueError("The scored anchor sites differ from the actual paid call schedule")
    selection = counts(list(lanes.values()))
    owners = owner_score(lanes)
    inventory = json.loads(verified(MEASURED / "acquisition-throughput.json", INVENTORY_SHA))["rows"]
    if len(inventory) != 55:
        raise ValueError("The timing transfer requires all frozen published records")
    transfer = project(acquisition["repeats"], inventory)
    result = dict(acquisition_sha256=sha256(receipt.read_bytes()).hexdigest(), inventory_sha256=INVENTORY_SHA,
                  owner_archive_sha256=OWNER_SHA, selection=selection, owners=owners, projections=transfer,
                  selected_by_slot={slot: counts([row for row in lanes.values() if row["slot"] == slot])
                                    for slot in ("full", "short_primary")})
    freeze(summary, result)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(acquisition=acquisition, detection_documents=decoded, scores=result, lanes=lanes),
                                             sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "summary", "full"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
