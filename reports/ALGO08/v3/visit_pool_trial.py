"""Measure causal marginal pilot-score pooling before any expensive detector."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import ExitStack
import ctypes as ct
from itertools import permutations
import json
from pathlib import Path
from statistics import mean
from time import process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import V3_SHA
from tools.pipeline_eval.variants.experimental.receiver_differential_fold import (
    CFO_HZ, PERIOD, ROTATION, ROW_INDICES, folded_correlations, pilot_filters,
)

from .scout_readout_trial import PILOT_SHA, check_machine


RATES = (-8000., -4000., -2000., 0., 2000., 4000., 8000.)
FRAMES = ROW_INDICES[[0, 2, 4, 7, 10, 13]]
ARMS = ("latest", "flat_pool", "drift_pool", "mismatched_channel", "current")
CAP = 4
MAX_SECONDS = 2.


class Sketch:
    def __init__(self, lib, asset):
        self.fir = asset[4*PERIOD:4*PERIOD+81].copy()
        self.filters = pilot_filters(asset)
        self.low = np.empty(100000, dtype=np.float32)
        self.decimate = lib.delay_decimate
        self.decimate.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        self.decimate.restype = ct.c_int

    def score(self, iq, lane, center):
        stereo = iq[:, lane].astype(np.float32)
        if center:
            rotor = np.exp(-2j*np.pi*center/1e7 * np.arange(len(stereo)))
            stereo.view(np.complex64)[:, 0] *= rotor
        if self.decimate(stereo.ctypes.data, self.fir.ctypes.data, 81, 4, self.low.ctypes.data):
            raise ValueError("Released decimator rejected the pinned waveform")
        correlation = folded_correlations(self.low.view(np.complex64), self.filters, FRAMES)
        power = np.sum(abs(correlation)**2, axis=0)
        support = []
        for _ in range(8):
            epoch = int(np.argmax(power))
            support.append(epoch)
            power[(epoch + np.arange(-2, 3)) % len(power)] = -1.
        marginal = np.real(ROTATION @ correlation[:, support]).max(axis=1)
        baseline = float(np.median(marginal))
        scale = max(float(np.quantile(marginal, .90)) - baseline, 1e-9)
        return np.maximum(marginal - baseline, 0.)/scale


def age(current_counter, previous):
    return (current_counter - previous[0]) / 1e7


def aligned(counter, center, items, rates=(0.,), *, mismatch=False):
    """Align phase-free per-visit spectra at the trial carrier in the future."""
    elapsed = np.asarray([age(counter, item) for item in items])
    if not np.all((elapsed > 0) & (elapsed <= MAX_SECONDS)):
        raise ValueError("Carrier prior must be causal and local")
    weights = np.exp(-elapsed / 1.2)
    scale = weights.sum()
    choices = []
    for rate in rates:
        combined = np.zeros(len(CFO_HZ))
        for seconds, weight, (_, mixer, power) in zip(elapsed, weights, items, strict=True):
            offset = 0. if mismatch else center - mixer
            combined += weight * np.interp(CFO_HZ + offset - rate*seconds, CFO_HZ, power, left=0., right=0.)
        choices.append(combined / scale)
    return np.max(choices, axis=0)


def shortlist(spectrum, center):
    available = np.asarray(spectrum, dtype=float).copy()
    result = []
    for _ in range(CAP):
        i = int(np.argmax(available))
        result.append(float(CFO_HZ[i] + center))
        available[abs(CFO_HZ - CFO_HZ[i]) < 10000.] = -np.inf
    return result


class PriorBank:
    def __init__(self):
        self.histories = defaultdict(lambda: deque(maxlen=4))

    def latest(self, key, counter):
        return [item for item in self.histories.get(key, ()) if 0 < age(counter, item) <= MAX_SECONDS]

    def donors(self, key, counter):
        lane, generation, edge, channel, _ = key
        paired = ((channel - 1) ^ 1) + 1
        available = [self.latest(source, counter) for source in self.histories
                     if source[:4] == (lane, generation, edge, paired)]
        foreign = max((items for items in available if len(items) >= 3), default=[], key=lambda items: items[-1][0])
        same = self.latest(key, counter)
        n = min(len(same), len(foreign))
        return (same[-n:], foreign[-n:]) if n >= 3 else (None, None)

    def push(self, key, counter, center, values):
        if self.histories[key] and self.histories[key][-1][0] >= counter:
            raise ValueError("Non-increasing same-lane observations")
        self.histories[key].append((counter, center, values))


def proposals(counter, center, same, foreign, current):
    compute = {
        "latest": lambda: aligned(counter, center, same[-1:]),
        "flat_pool": lambda: aligned(counter, center, same),
        "drift_pool": lambda: aligned(counter, center, same, RATES),
        "mismatched_channel": lambda: aligned(counter, center, foreign, RATES, mismatch=True),
        "current": lambda: current,
    }
    picks, clocks = {}, {}
    for name, score in compute.items():
        start = process_time_ns()
        picks[name] = shortlist(score(), center)
        clocks[name] = process_time_ns() - start
    return picks, clocks


def matched(factors, picks, tolerance):
    if not factors or not picks:
        return []
    rows = []
    for order in permutations(picks, len(factors)):
        delta = [abs(factor[3] - seed) for factor, seed in zip(factors, order, strict=True)]
        hits = [i for i, error in enumerate(delta) if error <= tolerance]
        rows.append((-len(hits), sum(delta[i] for i in hits), hits))
    return min(rows)[2]


def summary(rows):
    installed_cpu = sum(r["installed_cpu_ns"] for r in rows)
    sketch_cpu = sum(r["sketch_cpu_ns"] for r in rows)
    all_factors = Counter(factor[0] for row in rows for factor in row["factors"])
    supported = [row for row in rows if row["picks"]]
    held_factors = Counter(factor[0] for row in supported for factor in row["factors"])
    by_arm = {}
    for arm in ARMS:
        results = {}
        for tolerance in (400, 4550):
            matches, counts = Counter(), Counter()
            retry_cpu = 0
            for row in rows:
                factors, cpu = row["factors"], row["installed_cpu_ns"]
                if not row["picks"]:
                    counts["cold_start_lanes"] += 1
                    retry_cpu += cpu
                    continue
                picks = row["picks"][arm]
                found = matched(factors, picks, tolerance)
                matches.update(factors[i][0] for i in found)
                counts["proposals"] += len(picks)
                counts["unsupported_slots"] += len(picks) - len(found)
                if not factors:
                    counts["empty_lanes_with_proposals"] += 1
                elif len(found) != len(factors):
                    counts["positive_fallback_lanes"] += 1
                    retry_cpu += cpu
                else:
                    counts["covered_positive_lanes"] += 1
                    counts["covered_positive_cpu_ns"] += cpu
            ranking = sum(r["proposal_cpu_ns"].get(arm, 0) for r in rows)
            results[str(tolerance)] = dict(matches_by_rank=dict(matches), counts=dict(counts),
                                           fallback_cpu_ns=retry_cpu, ranking_cpu_ns=ranking,
                                           oracle_floor_cpu_ns=sketch_cpu + ranking + retry_cpu)
        by_arm[arm] = results
    return dict(lanes=len(rows), eligible=len(supported), source_factors_by_rank=dict(all_factors),
                eligible_factors_by_rank=dict(held_factors), by_arm=by_arm, installed_cpu_ns=installed_cpu,
                sketch_cpu_ns=sketch_cpu)


def measure(rows, installed, assets):
    packed, bank = [], PriorBank()
    last = -1
    with ExitStack() as stack:
        hardware = {}
        for edge in set(row["edge"] for row, _ in rows):
            payload = (assets / f"{edge}.f32").read_bytes()
            if digest(payload) != PILOT_SHA[edge]:
                raise ValueError("Pinned receiver asset changed")
            asset = np.frombuffer(payload, dtype="<f4")
            radio = Receiver(installed, asset)
            stack.callback(radio.close)
            hardware[edge] = radio, Sketch(radio.lib, asset)
        for row, samples in rows:
            t, a = row["target"], row["acquisition"]
            current = a["sample_start"]
            if current <= last:
                raise ValueError("Input is not in original acquisition order")
            last = current
            rf = t["lnb_lo_hz"] + a["actual_if_center_hz"]
            center = t["rf_center_hz"] - rf
            radio, sketch = hardware[row["edge"]]
            for lane in (0, 1):
                key = lane, a["generation"], row["edge"], int(t["channel"]), rf
                calculate = []
                for _ in range(2):
                    start = process_time_ns()
                    vector = sketch.score(samples, lane, center)
                    calculate.append(process_time_ns() - start)
                same, foreign = bank.donors(key, current)
                picks, clocks = ({}, {}) if same is None else proposals(current, center, same, foreign, vector)
                bank.push(key, current, center, vector)
                # Score only after the causal proposals are fixed and the
                # original waveform score is committed for subsequent visits.
                attestation = [radio.timed(samples, lane, center) for _ in range(2)]
                if attestation[0][0] != attestation[1][0]:
                    raise ValueError("Repeated installed receiver changed factors")
                packed.append(dict(visit=row["key"], lane=lane, center_hz=center, actual_rf_hz=rf,
                                   channel=key[3], counter=current, iq_sha256=row["sha256"],
                                   installed_cpu_ns=round(mean(entry[1] for entry in attestation)),
                                   sketch_cpu_ns=round(mean(calculate)), picks=picks, proposal_cpu_ns=clocks,
                                   prior_counters=[] if same is None else [item[0] for item in same],
                                   null_counters=[] if foreign is None else [item[0] for item in foreign],
                                   factors=attestation[0][0]))
    return dict(summary=summary(packed), rows=packed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("installed", "assets", "dense_binding", "transfer_binding", "bulk"):
        parser.add_argument(key, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    machine = check_machine()
    if digest(args.installed.read_bytes()) != V3_SHA:
        raise ValueError("Installed detector differs")
    groups = {name: measure(list(read_physical(binding, args.bulk, cap)), args.installed, args.assets)
              for name, binding, cap in (("DS30-0008", args.dense_binding, 128),
                                         ("DS30-0016", args.transfer_binding, 64))}
    print(json.dumps(dict(machine=machine, installed_sha256=V3_SHA, pilot_sha256=PILOT_SHA,
                          protocol_sha256=digest(Path(__file__).with_name("visit-pool-protocol.md").read_bytes()),
                          bindings={path.name: digest(path.read_bytes())
                                    for path in (args.dense_binding, args.transfer_binding)}, groups=groups),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
