"""Audit timing and signed CFO interpolation between alternating full receiver visits."""

import argparse
import json
import math
from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

import numpy as np

from .receiver_benchmark import Receiver, digest, read_simulated_prefix
from .receiver_tracking import ADC, PERIOD, TICKS_PER_FRAME, absolute_phase, measured_epoch

REFINE = (4., 1250.)
CONFIRM = (5., 1600.)
EXACT_ENCLOSURE = (6., 2250.)


@dataclass
class Measurement:
    index: str
    counter: int
    center: float
    factors: tuple
    cpu_ns: int


def signed_link(left, left_counter, right, right_counter):
    elapsed = (right_counter - left_counter) / ADC
    hz = right[3] - left[3]
    phase = math.remainder(absolute_phase(right_counter, right)
                           - absolute_phase(left_counter, left), TICKS_PER_FRAME)
    if 0 < elapsed <= 4 and abs(hz) <= 8000 * elapsed and abs(phase) <= 3000 * elapsed:
        return hz, phase
    return None


def interpolate(before, after, *, counter, center):
    if not (0 < counter - before.counter <= 2 * ADC
            and 0 < after.counter - counter <= 2 * ADC):
        return "gap", ()
    first, last = before.factors, after.factors
    if not first and not last:
        return "silent_anchors", ()
    if len(first) != len(last):
        return "different_anchor_counts", ()

    feasible = []
    for order in permutations(last):
        links = [signed_link(a, before.counter, b, after.counter)
                 for a, b in zip(first, order, strict=True)]
        if all(link is not None for link in links):
            feasible.append(links)
    if len(feasible) != 1:
        return ("ambiguous_links" if feasible else "no_signed_link"), ()

    fraction = (counter - before.counter) / (after.counter - before.counter)
    hints = []
    for a, (hz, phase) in zip(first, feasible[0], strict=True):
        epoch = (absolute_phase(before.counter, a) + phase * fraction
                 - (3 * counter) % TICKS_PER_FRAME) % TICKS_PER_FRAME
        carrier = a[3] + hz * fraction
        if abs(carrier - center) > 800000:
            return "outside_signed_search_band", ()
        hints.append((round(epoch / 3) % PERIOD, carrier))
    return "proposed", tuple(hints)


def support_count(factors, hints, limits):
    """Match both directions without reusing a proposal or an observed factor."""
    samples, hertz = limits
    return max(
        (sum(abs(math.remainder(measured_epoch(factor) - epoch, PERIOD)) <= samples
             and abs(factor[3] - hz) <= hertz
             for factor, (epoch, hz) in zip(observed, proposed, strict=False))
         for observed in permutations(factors) for proposed in permutations(hints)),
    )


def coverage(groups):
    counts, cpu, detail = Counter(), Counter(), []
    for key, measurements in groups.items():
        for index, current in enumerate(measurements):
            counts["lanes"] += 1
            counts["factors"] += len(current.factors)
            counts["residuals"] += sum(factor[0] == 1 for factor in current.factors)
            cpu["all"] += current.cpu_ns
            if index % 2 == 0:
                counts["anchor"] += 1
                continue
            if index + 1 == len(measurements):
                counts["tail_without_lookahead"] += 1
                continue
            left, right = measurements[index - 1], measurements[index + 1]
            counts["bracketed"] += 1
            cpu["all_bracketed"] += current.cpu_ns
            counts["bracketed_factors"] += len(current.factors)
            counts["bracketed_residuals"] += sum(factor[0] == 1 for factor in current.factors)
            reason, hints = interpolate(left, right, counter=current.counter, center=current.center)
            counts[reason] += 1
            if not hints:
                counts["fallback_with_factors"] += bool(current.factors)
                cpu["preflight_fallback"] += current.cpu_ns
            else:
                cpu["with_proposal"] += current.cpu_ns
            audit = dict(key=list(key), visit=current.index, anchors=[left.index, right.index],
                         reason=reason, hints=hints, factors=current.factors,
                         neighbor_factors=[left.factors, right.factors],
                         lookback_s=(current.counter - left.counter) / ADC,
                         lookahead_s=(right.counter - current.counter) / ADC)
            if hints:
                counts["missing_expected_in_middle"] += len(current.factors) < len(hints)
                counts["other_factors_in_middle"] += len(current.factors) > len(hints)
                for label, limits in (
                    ("nominal", REFINE), ("confirmation", CONFIRM), ("outer", EXACT_ENCLOSURE),
                ):
                    matched = support_count(current.factors, hints, limits)
                    residuals = tuple(factor for factor in current.factors if factor[0] == 1)
                    supported_residuals = support_count(residuals, hints, limits)
                    counts[label + "_factors"] += matched
                    counts[label + "_residuals"] += supported_residuals
                    full = matched == len(hints) == len(current.factors)
                    counts[label + "_whole_lane"] += full
                    if full:
                        cpu[label + "_whole_lane"] += current.cpu_ns
                    audit[label] = [matched, len(current.factors), supported_residuals]
            middle_only = [
                cur for cur in current.factors
                if not any(signed_link(f, left.counter, cur, current.counter) is not None
                           for f in left.factors)
                and not any(signed_link(cur, current.counter, f, right.counter) is not None
                            for f in right.factors)
            ]
            counts["middle_only_factors"] += len(middle_only)
            counts["middle_only_residuals"] += sum(cur[0] == 1 for cur in middle_only)
            audit["middle_only_factors"] = middle_only
            detail.append(audit)
    return dict(counts=counts, cpu_s={key: value / 1e9 for key, value in cpu.items()},
                detail=detail)


def measure(rows, binary, assets):
    groups = defaultdict(list)
    with ExitStack() as closer:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            receiver = Receiver(binary, np.fromfile(assets / f"{edge}.f32", dtype="<f4"))
            closer.callback(receiver.close)
            receivers[edge] = receiver
        for row, raw in rows:
            acq, target = row["acquisition"], row["target"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                key = (row["case"], lane, acq["generation"], row["edge"], target["channel"],
                       acq["actual_if_center_hz"], target["lnb_lo_hz"])
                factors, elapsed, _ = receivers[row["edge"]].timed(raw, lane, center)
                groups[key].append(Measurement(row["key"], acq["sample_start"], center,
                                               factors, elapsed))
    return coverage(groups) | {
        "input_sha256": digest(json.dumps([row for row, _ in rows], sort_keys=True).encode()),
    }


def read_physical(binding, bulk, visits):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    case = json.loads(binding.read_bytes())["case"]
    entry = case["recording"]["segments"][0]
    source = FastSegmentSource(dict(path=(bulk / entry["path"]).parent,
                                    manifest_digest="sha256:" + entry["sha256"]),
                               stop_sequence=visits)
    policy = FastScanPolicyV2()
    receivers = tuple(source.receiver_ids)
    if receivers != (0, 1):
        raise ValueError("expected two ordered independent receiver lanes")
    for window in source.windows():
        a, t = window.acquisition, window.target
        if valid_window_support(a, window.sample_rate_hz, window.samples.shape, receivers, policy):
            row = dict(case=case["id"], key=f'{case["id"]}:{a["global_visit"]}',
                       edge=t["edge"], acquisition=a, target=t, sha256=window.iq_sha256)
            yield row, window.samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("--physical-binding", type=Path)
    parser.add_argument("--simulated-panel", type=Path)
    parser.add_argument("--bulk", type=Path, default=Path("/srv/bulk"))
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    cohorts = defaultdict(list)
    if args.physical_binding:
        for row, raw in read_physical(args.physical_binding, args.bulk, 128):
            cohorts[row["case"]].append((row, raw))
    if args.simulated_panel:
        for row, raw in read_simulated_prefix(args.simulated_panel, 40):
            cohorts[row["case"]].append((row, raw))
    if not cohorts:
        parser.error("specify at least one bounded input")
    evidence = {key: measure(rows, args.oracle, args.assets) for key, rows in cohorts.items()}
    result = dict(binary_sha256=digest(args.oracle.read_bytes()), cohorts=evidence)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
