"""Evaluate an optimistic two-sided anchor envelope on saved factor ledgers."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from random import Random

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.carrier_continuation import Continuation


SEED = 8011
STRIDE = 8
ADC = 10_000_000
PERIOD = 40_000 / 3
GAP = 8 * ADC
WINDOW_BYTES = 1_600_000
V3 = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"


def digest(blob):
    return sha256(blob).hexdigest()


def channel(row):
    return row["channel"], row["actual_rf_hz"], row["edge"]


def lane(row):
    return row["receiver_id"], channel(row)


def choose_anchors(rows):
    by_channel = defaultdict(list)
    for first, second in zip(rows[::2], rows[1::2], strict=True):
        if (first["receiver_id"], second["receiver_id"]) != (0, 1) or any(
            first[key] != second[key]
            for key in ("visit_index", "valid_start_counter", "channel", "actual_rf_hz", "edge")
        ):
            raise ValueError("expected paired stereo rows")
        by_channel[channel(first)].append(first["visit_index"])
    rng = Random(SEED)
    return {rng.choice(visits[i:i + STRIDE]) for _, visits in sorted(by_channel.items())
            for i in range(0, len(visits), STRIDE)}


def factor_values(counter, candidate):
    # Reduce the large integer counter before adding the fractional sample.
    epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
    phase = (counter * 3 % 40_000) / 3 + epoch
    return candidate["fractional_tracking_cfo_hz"], phase


def projected_cells(left, right, target):
    ta, a = left
    tb, b = right
    before, after = (target - ta) / ADC, (tb - target) / ADC
    if not (0 < before <= GAP / ADC and 0 < after <= GAP / ADC):
        raise ValueError("an envelope needs bounded strictly two-sided support")
    dt = before + after
    ha, pa = a
    hb, pb = b
    if abs(hb - ha) > 8000 * dt:
        return None
    midpoint = ha + (hb - ha) * before / dt
    hz_radius = 2250 + 500 * before * after
    phase_radius = 6 + 10 * before * after
    diff = math.remainder(pb - pa, PERIOD)
    lower = math.ceil((-1000 * dt - diff) / PERIOD)
    upper = math.floor((1000 * dt - diff) / PERIOD)
    phases = [pa + (diff + branch * PERIOD) * before / dt for branch in range(lower, upper + 1)]
    return midpoint, hz_radius, phases, phase_radius


def ordered_rows(data):
    rows = data["source"]["probes"]
    if any(a["valid_start_counter"] >= b["valid_start_counter"] for a, b in zip(rows[::2], rows[2::2])):
        raise ValueError("requires chronological hardware counters")
    return rows


def selected(rows, admissible):
    history = Continuation()
    result = []
    for row, candidates in zip(rows, admissible, strict=True):
        _, choice, _ = history.select(dict(row, candidates=candidates))
        result.append(candidates[choice:choice + 1] if choice is not None else [])
    return result


def holding(rows, anchors):
    """Minimum local-lookahead ring capacity through the next scheduled same-RF anchor."""
    stereo = rows[::2]
    next_anchor = {}
    deltas = [0] * (len(stereo) + 1)
    delay = 0
    for index in reversed(range(len(stereo))):
        row = stereo[index]
        key = channel(row)
        if row["visit_index"] in anchors:
            next_anchor[key] = index
        elif key in next_anchor:
            end = next_anchor[key]
            delta = stereo[end]["valid_start_counter"] - row["valid_start_counter"]
            if delta <= GAP:
                delay = max(delay, delta)
                deltas[index] += 1
                deltas[end] -= 1
    peak, occupancy = 0, 0
    for delta in deltas:
        occupancy += delta
        peak = max(peak, occupancy)
    return dict(whole_record_pending_stereo_bytes=(len(stereo) - len(anchors)) * WINDOW_BYTES,
                next_same_rf_anchor_peak_stereo_windows=peak,
                next_same_rf_anchor_peak_stereo_bytes=peak * WINDOW_BYTES,
                next_same_rf_anchor_max_lookahead_s=delay / ADC)


def summarize(rows, original, observed, supported, anchors, cpu):
    counts = Counter()
    original_witnesses = Counter()
    candidate_witnesses = Counter()
    for i, (row, ref, found, choice) in enumerate(zip(rows, original, supported, observed, strict=True)):
        on_anchor = row["visit_index"] in anchors
        origin = row["candidates"]
        counts["reference_factors"] += len(origin)
        counts["supported_factors"] += len(found)
        counts["reference_residuals"] += sum(f["candidate_rank"] == 1 for f in origin)
        counts["supported_residuals"] += sum(f["candidate_rank"] == 1 for f in found)
        counts["reference_continuations"] += bool(ref)
        counts["kept_continuations"] += bool(choice)
        counts["anchor_continuations"] += on_anchor and bool(ref)
        counts["same_continuations"] += bool(ref) and ref == choice
        counts["new_or_changed_continuations"] += bool(choice) and ref != choice
        counts["nonanchor_reference_factors"] += 0 if on_anchor else len(origin)
        counts["nonanchor_supported_factors"] += 0 if on_anchor else len(found)
        counts["nonanchor_reference_residuals"] += sum(f["candidate_rank"] == 1 for f in origin if not on_anchor)
        counts["nonanchor_supported_residuals"] += sum(f["candidate_rank"] == 1 for f in found if not on_anchor)
        if ref:
            original_witnesses[channel(row)] += 1
        if ref and ref == choice:
            candidate_witnesses[channel(row)] += 1
        if on_anchor or len(origin) != len(found):
            counts["oracle_full_lanes"] += 1
            if cpu is not None:
                counts["oracle_full_lane_cpu_ns"] += cpu[i]
    return dict(counts=counts, same_continuations_by_channel=[
        [*key, value, candidate_witnesses[key]] for key, value in sorted(original_witnesses.items())
    ])


def screen(rows, anchors, original, cpu=None):
    anchor_points = defaultdict(list)
    for row in rows:
        t = row["valid_start_counter"]
        if row["visit_index"] in anchors:
            anchor_points[lane(row)].extend((t, factor_values(t, f)) for f in row["candidates"])
    anchor_times = {key: [point[0] for point in points] for key, points in anchor_points.items()}
    both, cfo_only = [], []
    proposal_pairs = []
    for row in rows:
        factors = row["candidates"]
        if row["visit_index"] in anchors:
            both.append(factors)
            cfo_only.append(factors)
            continue
        t, key = row["valid_start_counter"], lane(row)
        points, times = anchor_points.get(key, ()), anchor_times.get(key, ())
        before = points[bisect_left(times, t - GAP):bisect_left(times, t)]
        after = points[bisect_right(times, t):bisect_right(times, t + GAP)]
        cells = [cell for left in before for right in after
                 if (cell := projected_cells(left, right, t)) is not None]
        proposal_pairs.append(len(cells))
        covering_cfo, covering_both = [], []
        for factor in factors:
            hz, phase = factor_values(t, factor)
            near_cfo = [cell for cell in cells if abs(hz - cell[0]) <= cell[1]]
            if near_cfo:
                covering_cfo.append(factor)
            if any(abs(math.remainder(phase - p, PERIOD)) <= pad
                   for _, _, phases, pad in near_cfo for p in phases):
                covering_both.append(factor)
        both.append(covering_both)
        cfo_only.append(covering_cfo)
    return dict(
        evidence={name: summarize(rows, original, selected(rows, factors), factors, anchors, cpu)
                  for name, factors in (("two_sided_cfo_and_phase", both), ("two_sided_cfo_only_oracle", cfo_only),
                                        ("anchors_only", [row["candidates"] if row["visit_index"] in anchors else []
                                                          for row in rows]))},
        proposed_pairs=dict(maximum=max(proposal_pairs, default=0),
                            with_at_least_one=sum(n > 0 for n in proposal_pairs),
                            with_more_than_two=sum(n > 2 for n in proposal_pairs)),
    )


def saved_ledger(path, saved_path):
    blob = path.read_bytes()
    saved = saved_path.read_bytes()
    ledger = json.loads(gzip.decompress(blob))
    if ledger["saved_detections_sha256"] != digest(saved):
        raise ValueError("detector packet differs from ledger binding")
    reference = json.loads(saved)
    probes = ordered_rows(reference)
    rows, cpu = ledger["rows"], ledger["native_cpu_ns"]
    if (len(rows) != len(probes) or len(cpu) != len(rows)
            or ledger["ordered_selected_sha256"] != canonical_digest(probes)
            or ledger["raw_authority"] != reference["source"]["raw_recording_authority_digest"]):
        raise ValueError("incomplete ledger or reference")
    if any({**row, "candidates": ref["candidates"]} != ref for row, ref in zip(rows, probes, strict=True)):
        raise ValueError("ledger and native probe metadata differ")
    original = [row["candidates"] for row in probes]
    if selected(rows, [row["candidates"] for row in rows]) != original:
        raise ValueError("ledger does not reproduce the normal continuation")
    return rows, original, cpu, dict(ledger_sha256=digest(blob), detections_sha256=digest(saved),
                                     detector_sha256=ledger["detector_sha256"],
                                     acquisition_cpu_s=ledger["acquisition_cpu_ns"] / 1e9,
                                     acquisition_elapsed_s=ledger["acquisition_wall_ns"] / 1e9)


def census(rows, original, cpu=None):
    anchors = choose_anchors(rows)
    result = screen(rows, anchors, original, cpu)
    result.update(lanes=len(rows), anchors=sorted(anchors), storage=holding(rows, anchors))
    if cpu is not None:
        result["native_cpu_s"] = sum(cpu) / 1e9
        result["anchor_cpu_s"] = sum(t for row, t in zip(rows, cpu, strict=True)
                                      if row["visit_index"] in anchors) / 1e9
    return result


def publication_budget(rows, anchors, clocks, estimate_native_s):
    target = float(clocks["elapsed_s"]) / 2 - float(clocks["detections_to_terminal_s"]) / 2
    target -= float(clocks["terminal_to_exit_s"])
    residual = float(clocks["launch_to_detections_s"]) - estimate_native_s
    anchor_cpu = estimate_native_s * len(anchors) / (len(rows) / 2)
    remaining = target - residual - anchor_cpu
    unprocessed_selected = sum(bool(row["candidates"]) for row in rows if row["visit_index"] not in anchors)
    return dict(warm_acquisition_s=float(clocks["launch_to_detections_s"]), target_acquisition_s=target,
                estimate_native_s=estimate_native_s, estimate_nonreceiver_elapsed_s=residual,
                estimate_anchor_native_s=anchor_cpu, all_other_native_and_model_budget_s=remaining,
                nonanchor_installed_selections=unprocessed_selected,
                max_ms_per_nonanchor_installed_selection=1000 * remaining / unprocessed_selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", nargs=3, action="append", required=True,
                        metavar=("CASE", "GZIP_LEDGER", "DETECTIONS"))
    parser.add_argument("--selected", nargs=2, action="append", required=True,
                        metavar=("CASE", "DETECTIONS"))
    parser.add_argument("--clocks", type=Path, required=True)
    args = parser.parse_args()
    result = dict(seed=SEED, anchor_stride=STRIDE, maximum_side_gap_s=GAP / ADC,
                  hypotheses_per_nonanchor_lane=2, factor_ledgers={}, selected_stream_oracles={})
    with args.clocks.open() as source:
        clocks = {row["recording"]: row for row in csv.DictReader(source)}
    for label, ledger, saved in args.ledger:
        rows, original, cpu, binding = saved_ledger(Path(ledger), Path(saved))
        result["factor_ledgers"][label] = dict(binding=binding, **census(rows, original, cpu))
    for label, saved in args.selected:
        blob = Path(saved).read_bytes()
        data = json.loads(blob)
        if data["provenance"]["detector_sha256"] != V3:
            raise ValueError("expected installed ALGO08v3 selected stream")
        rows = ordered_rows(data)
        if any(len(row["candidates"]) > 1 for row in rows):
            raise ValueError("expected post-continuation native document")
        task = census(rows, [row["candidates"] for row in rows])
        if label == "DS30-0008":
            task["perfect_proposals_budget"] = publication_budget(rows, set(task["anchors"]), clocks[label], 36.5)
        result["selected_stream_oracles"][label] = dict(detections_sha256=digest(blob), **task)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
