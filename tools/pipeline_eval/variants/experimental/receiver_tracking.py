"""Run a cold causal waveform replay on one bounded chronological saved slice."""

import argparse
import ctypes as ct
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Factor, Receiver, digest


ADC = 10_000_000
TICKS_PER_FRAME = 40_000
PERIOD = 13333


class TimingHint(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("hz", ct.c_double)]


class TrackingStats(ct.Structure):
    _fields_ = [(key, ct.c_uint) for key in (
        "global_first", "global_residual", "short_first", "short_residual", "narrow_first", "reacquire",
    )]


def measured_epoch(factor):
    return (factor[1] + factor[2]) % PERIOD


def absolute_phase(counter, factor):
    return (3 * counter % TICKS_PER_FRAME + 3 * measured_epoch(factor)) % TICKS_PER_FRAME


class History:
    """Use the last two measured visits on an unchanged RF lane."""

    def __init__(self):
        self.visits = 0
        self.rows = deque(maxlen=2)

    def update(self, counter, factors):
        if self.rows and self.rows[-1][0] >= counter:
            raise ValueError("phase forecast requires increasing hardware counters")
        self.rows.append((counter, factors))
        self.visits += 1

    def force_full(self):
        return self.visits < 2 or self.visits % 4 == 3

    def predict(self, now):
        if len(self.rows) != 2:
            return []
        (old_t, earlier), (last_t, recent) = self.rows
        interval = (last_t - old_t) / ADC
        gap = (now - last_t) / ADC
        if not (0 < interval <= 2 and 0 < gap <= 2):
            return []
        links = []
        for j, last in enumerate(recent):
            for i, old in enumerate(earlier):
                f_slope = (last[3] - old[3]) / interval
                phase = math.remainder(absolute_phase(last_t, last) - absolute_phase(old_t, old),
                                       TICKS_PER_FRAME)
                phase_slope = phase / interval
                if abs(f_slope) <= 8000 and abs(phase_slope) <= 3000:
                    links.append((abs(last[3] - old[3]), i, j, f_slope, phase_slope))
        proposals, used_old, used_new = [], set(), set()
        for _, i, j, f_slope, phase_slope in sorted(links):
            if i in used_old or j in used_new:
                continue
            last = recent[j]
            epoch_ticks = (absolute_phase(last_t, last) + phase_slope * gap -
                           (3 * now % TICKS_PER_FRAME)) % TICKS_PER_FRAME
            proposals.append((round(epoch_ticks / 3) % PERIOD, last[3] + f_slope * gap))
            used_old.add(i)
            used_new.add(j)
        return proposals


def lane_key(window, lane):
    target, acq = window.target, window.acquisition
    return lane, acq["generation"], target["edge"], target["channel"], acq["actual_if_center_hz"], target["lnb_lo_hz"]


def selected(continuation, window, lane, factors):
    target, acq = window.target, window.acquisition
    _, index, _ = continuation.select(dict(
        receiver_id=lane, channel=target["channel"],
        actual_rf_hz=acq["actual_if_center_hz"] + target["lnb_lo_hz"],
        valid_start_counter=acq["sample_start"], candidates=[Receiver.criteria(*p) for p in factors],
    ))
    return factors[index] if index is not None else None


def run(binary, asset, windows, *, tracking):
    receiver = Receiver(binary, asset)
    if tracking:
        detector = receiver.lib.cancellation_factors_tracking
        detector.argtypes = receiver.run.argtypes[:-1] + [ct.POINTER(TimingHint), ct.c_uint, ct.c_int,
                                                         ct.POINTER(TrackingStats), ct.POINTER(Factor)]
        detector.restype = ct.c_int
    history, continuation = defaultdict(History), Continuation()
    outputs, stats = [], TrackingStats()
    cpu = wall = 0
    try:
        for window in windows:
            acq, target = window.acquisition, window.target
            mid = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                start_wall, start_cpu = perf_counter_ns(), process_time_ns()
                counter = acq["sample_start"]
                past = history[lane_key(window, lane)]
                proposed = past.predict(counter) if tracking else None
                factors = (Factor * 2)()
                args = receiver.ctx, window.samples.ctypes.data, lane, mid - 800000, mid + 800000
                if tracking:
                    hints = (TimingHint * len(proposed))(*(TimingHint(*item) for item in proposed))
                    count = detector(*args, hints, len(hints), past.force_full(), ct.byref(stats), factors)
                else:
                    count = receiver.run(*args, factors)
                if not 0 <= count <= 2:
                    raise ValueError("invalid factor count")
                factors = tuple(tuple(getattr(p, name) for name, _ in Factor._fields_) for p in factors[:count])
                keep = selected(continuation, window, lane, factors)
                if tracking:
                    past.update(counter, factors)
                cpu += process_time_ns() - start_cpu
                wall += perf_counter_ns() - start_wall
                if not tracking:
                    proposed = past.predict(counter)
                    past.update(counter, factors)
                outputs.append((acq["global_visit"], lane, factors, keep, proposed))
    finally:
        receiver.close()
    return outputs, dict(cpu_s=cpu / 1e9, wall_s=wall / 1e9,
                         scans={key: getattr(stats, key) for key, _ in TrackingStats._fields_})


def agree(a, b):
    return (abs(math.remainder(measured_epoch(a) - measured_epoch(b), PERIOD)) <= 2 and
            abs(a[3] - b[3]) <= 250)


def compare(reference, proposed):
    counts, loss = Counter(), []
    max_deltas = [0., 0.]
    for old, new in zip(reference, proposed, strict=True):
        visit, lane, left, chosen, prior = old
        if old[:2] != new[:2]:
            raise ValueError("different chronological receiver supports")
        right, replacement = new[2:4]
        counts["same_factor_tuple_lanes"] += left == right
        counts["tracking_lanes_with_forecast"] += bool(new[4])
        counts["exact_factors"] += len(left)
        counts["tracking_factors"] += len(right)
        counts["exact_selected"] += chosen is not None
        counts["tracking_selected"] += replacement is not None
        counts["selected_loss"] += chosen is not None and (replacement is None or not agree(chosen, replacement))
        counts["selected_addition"] += chosen is None and replacement is not None
        remaining = list(right)
        for f in left:
            tags = ["all"]
            if f[0] == 1:
                tags.append("second_scan")
            if len(left) == 2 and f == left[1]:
                tags.append("lower_margin")
            if not any(abs(hz - f[3]) <= 1600 and
                       abs(math.remainder(epoch - measured_epoch(f), PERIOD)) <= 5
                       for epoch, hz in prior):
                tags.append("no_signed_history_proposal")
            counts.update("exact_" + tag for tag in tags)
            match = next((p for p in remaining if agree(f, p)), None)
            if match is None:
                counts.update("lost_" + tag for tag in tags)
                offsets = [p[3] - f[3] for p in right
                           if abs(math.remainder(measured_epoch(f) - measured_epoch(p), PERIOD)) <= 2]
                codes = []
                for delta in offsets:
                    if 500 < abs(delta) <= 2500 and abs(math.remainder(delta, 750.)) <= 150.:
                        codes.append("750_hz_alias")
                    if abs(delta) > 100_000 and abs(math.remainder(delta, ADC / 44)) <= 1000.:
                        codes.append("227_khz_alias")
                counts.update("lost_" + code for code in set(codes))
                loss.append(dict(visit=visit, lane=lane, rank=f[0], hz=f[3], margin=f[4]-f[5],
                                 alternatives=[p[3] for p in right], tags=tags + codes))
                continue
            remaining.remove(match)
            max_deltas[0] = max(max_deltas[0], abs(math.remainder(measured_epoch(f) - measured_epoch(match), PERIOD)))
            max_deltas[1] = max(max_deltas[1], abs(f[3] - match[3]))
        counts["tracking_extra_factors"] += len(remaining)
    return dict(counts=counts, lost=loss, maximum_matched_epoch_and_cfo_difference=max_deltas)


def main():
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("binding", type=Path)
    parser.add_argument("--bulk", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--visits", type=int, default=128)
    args = parser.parse_args()
    if not 32 <= args.visits <= 128:
        parser.error("use 32 to 128 scheduled visits from one saved recording")
    case = json.loads(args.binding.read_bytes())["case"]
    entry = case["recording"]["segments"][0]
    source = FastSegmentSource(dict(path=(args.bulk / entry["path"]).parent,
                                    manifest_digest="sha256:" + entry["sha256"]), stop_sequence=args.visits)
    policy = FastScanPolicyV2()
    visits = [w for w in source.windows() if valid_window_support(
        w.acquisition, w.sample_rate_hz, w.samples.shape, tuple(source.receiver_ids), policy)]
    edges = {w.target["edge"] for w in visits}
    if len(edges) != 1 or tuple(source.receiver_ids) != (0, 1):
        raise ValueError("require one edge and two independent receiver lanes")
    asset = np.fromfile(args.assets / (edges.pop() + ".f32"), dtype="<f4")
    repeats, quality = [], None
    for order in ((False, True), (True, False)):
        result = {arm: run(args.candidate if arm else args.oracle, asset, visits, tracking=arm) for arm in order}
        metrics = compare(result[False][0], result[True][0])
        if quality is not None and quality != metrics:
            raise ValueError("tracking replay yielded inconsistent decisions")
        quality = metrics
        repeats.append(dict(oracle=result[False][1], tracking=result[True][1]))
    print(json.dumps(dict(case=case["id"], scheduled_visits=args.visits, eligible=len(visits),
                          binaries=[digest(p.read_bytes()) for p in (args.oracle, args.candidate)],
                          raw_manifest=entry["sha256"], iq_digest=digest(json.dumps([w.iq_sha256 for w in visits]).encode()),
                          repeats=repeats, evaluation=quality), indent=2))


if __name__ == "__main__":
    main()
