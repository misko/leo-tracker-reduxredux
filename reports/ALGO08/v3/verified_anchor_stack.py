"""Compare a causal local carrier stack to the complete receiver on sealed South I/Q."""

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from itertools import product
import json
from math import remainder
from pathlib import Path
from statistics import median
from time import process_time_ns

import numpy as np

from cyclic_carrier_trial import PINS, V3_RECEIVER, digest, pilot_lines
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastScanStore, FastSegmentSource
from reports.ALGO08.v3.directed_verifier_trial import Directed, seed
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_tracking import (
    ADC, TICKS_PER_FRAME, absolute_phase, agree, selected,
)
from track_before_detect import BIN_HZ, CFO_TOLERANCE, Surface, frequency_scores, load


DIRECTED_SHA = "d66ab774f8844fbaec21e28eb2c6ecf42e57152705ea5d4677ca8f032d52397d"
WINDOWS = 256
TRIGGER = 10.
ANCHOR_STRIDE = 8
ARMS = ("stock", "schedule", "latest", "stack")
STEPS = tuple(product((0., -150., 150.), (0., -500., 500.)))
BOUNDS = 800_000


@dataclass
class History:
    visits: int = 0
    anchors: deque = field(default_factory=lambda: deque(maxlen=2))
    surfaces: deque = field(default_factory=lambda: deque(maxlen=4))

    def force(self):
        if self.visits % ANCHOR_STRIDE == 0:
            return "scheduled"
        if len(self.anchors) == 1:
            return "confirmation"
        return None

    def observe(self, counter, factors):
        self.surfaces.clear()
        if len(factors) != 1:
            self.anchors.clear()
            return
        current = (counter, factors[0])
        if self.anchors and secant(self.anchors[-1], current) is None:
            self.anchors.clear()
        self.anchors.append(current)


def secant(previous, recent):
    old_t, first = previous
    last_t, last = recent
    dt = (last_t - old_t) / ADC
    if not 0 < dt <= 8.:
        return None
    f_slope = (last[3] - first[3]) / dt
    timing_slope = remainder(absolute_phase(last_t, last) - absolute_phase(old_t, first),
                             TICKS_PER_FRAME) / (3 * dt)
    if abs(f_slope) > 8000. or abs(timing_slope) > 1000.:
        return None
    return f_slope, timing_slope


def score_bank(history, counter, current, *, stack):
    if len(history.anchors) != 2:
        return None
    previous, anchor = history.anchors
    last_t, last = anchor
    dt = (counter - last_t) / ADC
    if not 0 < dt <= 16.:
        return None
    rates = secant(previous, anchor)
    if rates is None:
        return None
    slope, phase_slope = rates
    epoch = ((absolute_phase(last_t, last) - (3 * counter % TICKS_PER_FRAME) + 3 * phase_slope * dt)
             % TICKS_PER_FRAME) / 3
    history.surfaces.append((counter, current))
    support = tuple(history.surfaces) if stack else ((counter, current),)
    deltas = np.asarray(STEPS)
    score = np.zeros(len(STEPS))
    available = np.ones(len(STEPS), dtype=bool)
    for time, surface in support:
        seconds = (time - last_t) / ADC
        hz = last[3] + (slope + deltas[:, 0]) * seconds + deltas[:, 1]
        available &= (hz >= surface[0]) & (hz <= surface[1])
        if np.any(available):
            score[available] += frequency_scores(surface, hz[available])
    if not np.any(available):
        return None
    ranked = np.where(available, score, -np.inf)
    return epoch, float(hz[np.argmax(ranked)]), hz[available].tolist(), len(support)


def within_bank(peak_hz, projection):
    return projection is not None and any(abs(peak_hz - hz) <= CFO_TOLERANCE for hz in projection[2])


def checked(window, lane, field, start):
    a, t = window.acquisition, window.target
    if (field["visit_index"] != a["global_visit"] or field["receiver_id"] != lane
            or field["valid_start_counter"] != a["sample_start"] or field["edge"] != t["edge"]
            or field["channel"] != t["channel"]
            or field["actual_rf_hz"] != a["actual_if_center_hz"] + t["lnb_lo_hz"]
            or a["global_visit"] != start):
        raise ValueError("held capture and installed packet differ")


def load_windows(scene, pair, native):
    document = load(native)
    archived = load(pair)
    run = archived["runs"]["candidate"]
    session, inventory, inventory_doc = FastScanStore(scene.parent).inventory(scene, verify_windows=False)
    terminal = load(native.parents[1] / run["receipt"]["run_id"] / "terminal.json")
    if (str(scene) != archived["recording"] or session != document["source"]["session_id"]
            or inventory != document["source"]["input_manifest_sha256"]
            or canonical_digest(document) != terminal["native_sha256"]
            or canonical_digest(terminal) != run["receipt"]["terminal_sha256"]
            or run["raw_authority"] != document["source"]["raw_recording_authority_digest"]
            or document["provenance"]["detector_sha256"] != "sha256:" + V3_RECEIVER):
        raise ValueError("invalid sealed South acquisition binding")
    segment, = inventory_doc["segments"]
    start = process_time_ns()
    source = FastSegmentSource(segment, stop_sequence=WINDOWS)
    if tuple(source.receiver_ids) != (0, 1):
        raise ValueError("expected both original antennas")
    policy = FastScanPolicyV2()
    rows = [w for w in source.windows()
            if valid_window_support(w.acquisition, w.sample_rate_hz, w.samples.shape, source.receiver_ids, policy)]
    if len(rows) != WINDOWS:
        raise ValueError("sealed prefix admissions changed")
    input_cpu = process_time_ns() - start
    probes = document["source"]["probes"][:2 * WINDOWS]
    for position, window in enumerate(rows):
        for lane in (0, 1):
            checked(window, lane, probes[position * 2 + lane], position)
    return rows, probes, dict(inventory_sha256=inventory, native_sha256=digest(native), pair_sha256=digest(pair),
                              window_sha256=[row.iq_sha256 for row in rows], input_cpu_ns=input_cpu,
                              retained_ci16_bytes=sum(row.samples.nbytes for row in rows))


def open_libraries(args, asset):
    if digest(args.installed) != V3_RECEIVER or digest(args.directed) != DIRECTED_SHA:
        raise ValueError("unexpected receiver binary")
    stock = Receiver(args.installed, asset)
    helper = Receiver(args.directed, asset)
    return stock, helper, Directed(helper, asset), Surface(args.surface)


def measure_arm(name, windows, stock, verify, scout, lines, weights):
    data = []
    histories, continuation = defaultdict(History), Continuation()
    elapsed = 0
    for window in windows:
        acq, target = window.acquisition, window.target
        counter = acq["sample_start"]
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
        rf = target["rf_center_hz"] - center
        for lane in (0, 1):
            start = process_time_ns()
            factors, projection, peak = (), None, None
            clocks = Counter()
            history = histories[lane, target["channel"], rf, target["edge"]]
            route = "stock" if name == "stock" else history.force()
            history.visits += 1
            if route is None:
                before = process_time_ns()
                surface = scout.get(window.samples, lane, center, lines, weights, repeats=1)
                top = int(np.argmax(surface[2]))
                peak = float(surface[2][top]), surface[0] + top * BIN_HZ
                clocks["surface"] += process_time_ns() - before
                before = process_time_ns()
                if name != "schedule":
                    projection = score_bank(history, counter, surface, stack=name == "stack")
                expected = within_bank(peak[1], projection)
                clocks["bank"] += process_time_ns() - before
                if peak[0] >= TRIGGER and not expected:
                    route = "discovery"
                elif projection is not None:
                    before = process_time_ns()
                    factors, _, _, _ = verify.timed(window.samples, lane, center, [seed(*projection[:2])], "refine")
                    clocks["verify"] += process_time_ns() - before
                    if not factors and peak[0] >= TRIGGER:
                        route = "rejected_retry"
            if route is not None:
                before = process_time_ns()
                factors, _, _ = stock.timed(window.samples, lane, center)
                history.observe(counter, factors)
                clocks["full"] += process_time_ns() - before
            serial = selected(continuation, window, lane, factors)
            duration = process_time_ns() - start
            elapsed += duration
            data.append(dict(visit=acq["global_visit"], lane=lane, key=[lane, target["channel"], rf, target["edge"]],
                             route=route or ("verified" if factors else "no_detection"),
                             factors=factors, selected=serial, peak=peak, projection=projection,
                             clocks=dict(clocks), duration=duration))
    return data, elapsed


def factor_match(want, received):
    return any(want[0] == other[0] and agree(want, other) for other in received)


def score(reference, trial):
    counts, stage, routes = Counter(), Counter(), Counter()
    misses, arrivals = [], []
    histories = {}
    missed_stock_ns = mandatory_stock_ns = 0
    for before, now in zip(reference, trial, strict=True):
        if (before["visit"], before["key"]) != (now["visit"], now["key"]):
            raise ValueError("receiver lanes were not paired")
        key = tuple(before["key"])
        original, predicted = before["factors"], now["factors"]
        paid = now["route"] in ("scheduled", "confirmation", "discovery", "rejected_retry")
        arrival = bool(original and not histories.get(key))
        routes[now["route"]] += 1
        if now["route"] in ("scheduled", "confirmation") or arrival:
            # Give hindsight the true waking lanes. Existing-track propagation,
            # independent verification and all unrelated searches are free.
            mandatory_stock_ns += before["clocks"]["full"]
        if now["route"] == "discovery" and not original:
            counts["strong_discovery_without_factor"] += 1
        stage.update(now["clocks"])
        counts["factors"] += len(original)
        counts["empty_lanes"] += not original
        counts["added_factors"] += sum(not factor_match(factor, original) for factor in predicted)
        if not paid:
            counts["held_factors"] += len(original)
            counts["held_lanes"] += 1
        missed = [factor for factor in original if not factor_match(factor, predicted)]
        if missed:
            misses.append(dict(visit=now["visit"], lane=now["lane"], missing=missed, route=now["route"]))
            missed_stock_ns += before["clocks"]["full"]
        counts["matched_factors"] += len(original) - len(missed)
        if not paid:
            counts["matched_held_factors"] += len(original) - len(missed)
        if before["selected"] is not None:
            counts["selected"] += 1
            counts["matched_selected"] += (now["selected"] is not None
                                           and factor_match(before["selected"], [now["selected"]]))
        if now["selected"] is not None:
            counts["added_selected"] += (before["selected"] is None
                                         or not factor_match(now["selected"], [before["selected"]]))
        if now["clocks"].get("verify"):
            counts["verified_queries"] += 1
            counts["empty_lanes_queried"] += not original
            epoch, cfo, _, used = now["projection"]
            counts["queries_stack_size_" + str(used)] += 1
            counts["queries_with_cfo_4550"] += any(abs(cfo - f[3]) <= CFO_TOLERANCE for f in original)
            counts["queries_with_phase_4"] += any(abs(remainder(epoch - f[1] - f[2], TICKS_PER_FRAME / 3)) <= 4
                                                  for f in original)
        if arrival:
            counts["new_arrivals"] += 1
            counts["new_arrivals_matched"] += not missed
            arrivals.append(dict(visit=now["visit"], lane=now["lane"], status=now["route"], matched=not missed))
        histories[key] = original
    return dict(counts=dict(counts), arrivals=arrivals, misses=misses, calls=dict(routes), stage_ns=dict(stage),
                oracle_extra_full_retry_ns=missed_stock_ns, hindsight_mandatory_waveform_search_ns=mandatory_stock_ns)


def projection_cost(acq, oracle):
    anchor = acq["detector_groups"]["anchors"]["cpu_s"]
    positive_factors = acq["detector_groups"]["nonanchors"]["selections"]
    callback = sum(group["cpu_s"] for group in acq["detector_groups"].values())
    controls = oracle["groups"]["dense"]["checks"]
    strict = controls["strict_fixed_guard"]
    cost = strict["cpu_ms"]["mean"] * strict["counts"]["lanes"] / strict["counts"]["total_returned"]
    verify = cost * positive_factors / 1000
    cold_allowance = acq["in_process_to_solver_cpu_s"] / 2 - acq["outside_detector_cpu_s"]
    warm_allowance = (52.69852971 - 3.3423025956425363) / 2 - (52.69852971 - callback)
    return dict(scheduled_anchor_cpu_s=anchor, nonanchor_factors=positive_factors,
                waived_false_proposals_strict_oracle_ms_per_factor=cost, verify_cpu_s=verify,
                optimistic_anchors_verification_cpu_s=anchor + verify,
                cold_callback_allowance_s=cold_allowance, warm_callback_allowance_s=warm_allowance,
                remaining_for_all_reacquisition_and_prediction_cold_cpu_s=cold_allowance - anchor - verify,
                remaining_for_all_reacquisition_and_prediction_warm_model_s=warm_allowance - anchor - verify)


def trial(args):
    windows, probes, identity = load_windows(args.scene, args.pair, args.native)
    asset_path = args.assets / "upper.f32"
    if digest(asset_path) != PINS["upper"]:
        raise ValueError("upper pilot does not match prior trial")
    asset = np.fromfile(asset_path, dtype="<f4")
    lines, weights, _ = pilot_lines(asset)
    stock, helper, verify, scout = open_libraries(args, asset)
    runs, clocks = {}, defaultdict(list)
    try:
        for order in (ARMS, ARMS[::-1], ARMS[1:] + ARMS[:1]):
            for name in order:
                rows, cpu = measure_arm(name, windows, stock, verify, scout, lines, weights)
                clocks[name].append(cpu)
                if name in runs and any(a["factors"] != b["factors"] or a["route"] != b["route"]
                                        for a, b in zip(runs[name], rows, strict=True)):
                    raise ValueError("rerun changed the held acquisition")
                runs[name] = rows
    finally:
        for context in (scout, verify, helper, stock):
            context.close()
    for probe, row in zip(probes, runs["stock"], strict=True):
        expected = probe["candidates"]
        factor = row["selected"]
        if bool(expected) != (factor is not None) or (factor is not None and (
                len(expected) != 1 or factor[0] != expected[0]["candidate_rank"]
                or factor[3] != expected[0]["fractional_tracking_cfo_hz"])):
            raise ValueError("fresh stock digest differs at signed selection")
    measured = {arm: dict(cpu_ns=clocks[arm], median_cpu_ms_per_lane=median(clocks[arm]) / len(probes) / 1e6,
                          **score(runs["stock"], rows)) for arm, rows in runs.items()}
    dense = projection_cost(load(args.dense_split), load(args.oracle))
    data = dict(inputs=identity | {key: digest(getattr(args, key)) for key in
                                  ("surface", "installed", "directed", "dense_split", "oracle")},
                lanes=len(probes), measurements=measured, dense_optimistic=dense, rows=runs,
                runner_sha256=digest(Path(__file__)))
    with args.output.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scene", "pair", "native", "assets", "surface", "installed", "directed",
                 "dense_split", "oracle", "output"):
        parser.add_argument(name, type=Path)
    trial(parser.parse_args())
