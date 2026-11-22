"""Audit the frozen first-pass nonlinear scout against its verified residual targets."""

import argparse
import ctypes as ct
import json
import math
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns

import numpy as np

from .receiver_benchmark import Factor, Receiver, digest, read_archive
from .receiver_tracking import agree, measured_epoch


class AuditPeak(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("rank", ct.c_int), ("confirmed", ct.c_int)]


RANKS = ("timing_cell_rank", "timing_seed_rank", "frequency_cell_rank", "coarse_rank",
         "refined_rank", "confirmed_rank", "verified_rank")


class ShortlistAudit(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double)] + [(name, ct.c_int) for name in (
        *RANKS[:3], "seeds_used", *RANKS[3:], "candidates", "first_confirmed",
    )] + [("peaks", AuditPeak * 24)]


class ShortlistFast(ct.Structure):
    _fields_ = [(name, ct.c_uint) for name in (
        "first_confirmed", "narrow_trials", "local_confirmed", "full_residual", "full_retry",
    )]


def call_fast(audit, samples, lane, center):
    out, stats = (Factor * 2)(), ShortlistFast()
    fn = audit.lib.receiver_shortlist_fast
    args = audit.ctx, samples.ctypes.data, lane, center - 800000, center + 800000, ct.byref(stats), out
    start = process_time_ns()
    count = fn(*args)
    elapsed = process_time_ns() - start
    if not 0 <= count <= 2:
        raise ValueError("conservative shortlist returned an invalid count")
    factors = tuple(tuple(getattr(row, name) for name, _ in Factor._fields_) for row in out[:count])
    return factors, elapsed, {name: getattr(stats, name) for name, _ in ShortlistFast._fields_}


def compare_factors(exact, fast, counts):
    counts["changed_factor_lanes"] += exact != fast
    remaining = list(fast)
    for target in exact:
        match = next((f for f in remaining if agree(target, f)), None)
        if match is None:
            counts["missing_exact_factors"] += 1
        else:
            remaining.remove(match)
    counts["extra_factors"] += len(remaining)


def ranks_summary(rows):
    summary = dict(lanes=len(rows), first_confirmed=sum(row["first_confirmed"] for row in rows))
    selected = [row for row in rows if row["residual"] is not None]
    summary["verified_residual_targets"] = len(selected)
    summary["coverage"] = {rank: sum(bool(row[rank]) for row in selected) for rank in RANKS}
    summary["raw_candidate_rank_histograms"] = {
        rank: dict(Counter(row[rank] for row in selected)) for rank in RANKS[3:]}
    summary["verified_rank_at_most_four"] = sum(0 < row["verified_rank"] <= 4 for row in selected)
    return summary


def run(rows, binaries, assets):
    with ExitStack() as stack:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            pair = [Receiver(path, asset) for path in binaries]
            for receiver in pair:
                stack.callback(receiver.close)
            oracle, audit = pair
            fn = audit.lib.receiver_audit_shortlist
            fn.argtypes = audit.run.argtypes[:-1] + [ct.c_double, ct.c_double, ct.POINTER(ShortlistAudit)]
            fn.restype = ct.c_int
            fast = audit.lib.receiver_shortlist_fast
            fast.argtypes = audit.run.argtypes[:-1] + [ct.POINTER(ShortlistFast), ct.POINTER(Factor)]
            fast.restype = ct.c_int
            receivers[edge] = oracle, audit, fn
        evidence = []
        for row, samples in rows:
            target, acq = row["target"], row["acquisition"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            oracle, audit, fn = receivers[row["edge"]]
            for lane in (0, 1):
                factors = oracle.timed(samples, lane, center)[0]
                if audit.timed(samples, lane, center)[0] != factors:
                    raise ValueError("audit-enabled receiver changed uninstrumented factors")
                secondary = next((factor for factor in factors if factor[0] == 1), None)
                epoch, hz = (math.nan, math.nan) if secondary is None else (measured_epoch(secondary), secondary[3])
                trace = ShortlistAudit()
                if fn(audit.ctx, samples.ctypes.data, lane, center - 800000, center + 800000,
                      epoch, hz, ct.byref(trace)):
                    raise ValueError("first-scout instrumentation failed")
                row_data = {rank: getattr(trace, rank) for rank in RANKS}
                evidence.append(dict(key=row["key"], lane=lane, residual=secondary, seeds=trace.seeds_used,
                                     first_confirmed=trace.first_confirmed, **row_data))
        repeats = []
        changed = []
        for repeat in range(2):
            cpu = [0, 0]
            counts = Counter()
            for i, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                oracle, audit, _ = receivers[row["edge"]]
                for lane in (0, 1):
                    if (i + lane + repeat) % 2:
                        actual, candidate_cpu, stats = call_fast(audit, samples, lane, center)
                        baseline, baseline_cpu, _ = oracle.timed(samples, lane, center)
                    else:
                        baseline, baseline_cpu, _ = oracle.timed(samples, lane, center)
                        actual, candidate_cpu, stats = call_fast(audit, samples, lane, center)
                    counts.update(stats)
                    compare_factors(baseline, actual, counts)
                    if not repeat and baseline != actual:
                        changed.append(dict(key=row["key"], lane=lane, exact=baseline, shortcut=actual, routing=stats))
                    cpu[0] += baseline_cpu
                    cpu[1] += candidate_cpu
            repeats.append(dict(oracle_cpu_s=cpu[0] / 1e9, shortcut_cpu_s=cpu[1] / 1e9, counts=counts))
    return dict(summary=ranks_summary(evidence), rows=evidence, shortcut=repeats, changed=changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    binaries = args.oracle, args.audit
    cohorts = {}
    for key, archive, limit in (("prospective", args.prospective, 16), ("weak", args.weak, 18)):
        rows = list(read_archive(archive, limit))
        cohorts[key] = run(rows, binaries, args.assets)
        cohorts[key]["source_sha256"] = digest(json.dumps([row["sha256"] for row, _ in rows]).encode())
    print(json.dumps(dict(binaries=[digest(p.read_bytes()) for p in binaries], cohorts=cohorts), indent=2))


if __name__ == "__main__":
    main()
