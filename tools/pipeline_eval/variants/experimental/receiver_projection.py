"""Compare a first/residual linear projection scout on small saved I/Q slices."""

import argparse
import ctypes as ct
import json
import math
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns

import numpy as np

from .receiver_benchmark import Factor, Receiver, digest, read_archive
from .receiver_tracking import agree, measured_epoch


class ProjectedSeed(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double)]


class ProjectionTrace(ct.Structure):
    _fields_ = [("seed_count", ct.c_uint), ("attempted", ct.c_uint), ("zero", ct.c_uint),
                ("seeds", ProjectedSeed * 4)]


class ProjectionVisit(ct.Structure):
    _fields_ = [("scan", ProjectionTrace * 2), ("fallback", ct.c_uint)]


def bind(receiver):
    call = receiver.lib.cancellation_factors_projection
    call.argtypes = receiver.run.argtypes[:-1] + [ct.c_int, ct.POINTER(ProjectionVisit), ct.POINTER(Factor)]
    call.restype = ct.c_int
    return call


def timed(receiver, samples, lane, center, mode):
    factors, trace = (Factor * 2)(), ProjectionVisit()
    arguments = receiver.ctx, samples.ctypes.data, lane, center - 800000, center + 800000
    start = process_time_ns()
    if mode == "exact":
        count = receiver.run(*arguments, factors)
    else:
        policy = {"projection": 0, "guarded": 1, "exact_first": 2}[mode]
        count = receiver.lib.cancellation_factors_projection(
            *arguments, policy, ct.byref(trace), factors)
    elapsed = process_time_ns() - start
    if not 0 <= count <= 2:
        raise ValueError("invalid projection factor count")
    result = tuple(tuple(getattr(row, field) for field, _ in Factor._fields_) for row in factors[:count])
    return result, trace, elapsed


def score(exact, probe, trace):
    counts = Counter(projection_factors=len(probe))
    remaining = list(probe)
    for idx, name in enumerate(("first", "residual")):
        counts[f"{name}_attempted"] += trace.scan[idx].attempted
        counts[f"{name}_zero_bound"] += trace.scan[idx].zero
    for factor in exact:
        rank = factor[0]
        arm = "residual" if rank else "first"
        by_pass = trace.scan[rank]
        counts[f"{arm}_verified_reference"] += 1
        counts[f"{arm}_shortlist_recall"] += any(
            abs(math.remainder(seed.epoch - measured_epoch(factor), 13333.)) <= 2. and
            abs(seed.hz - factor[3]) <= 1000. for seed in by_pass.seeds[:by_pass.seed_count])
        matched = next((f for f in remaining if agree(factor, f)), None)
        if matched is not None:
            counts[f"{arm}_finally_matched"] += 1
            remaining.remove(matched)
    counts["projection_extras"] += len(remaining)
    return counts


def replay(rows, binaries, assets):
    modes = ("exact", "projection", "guarded", "exact_first")
    timings, evidence, residual_diagnostic = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    with ExitStack() as stack:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            for name, path in zip(("exact", "projection"), binaries, strict=True):
                receiver = Receiver(path, asset)
                stack.callback(receiver.close)
                receivers[edge, name] = receiver
                if name == "projection":
                    bind(receiver)
        for repeat in range(2):
            for index, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for lane in (0, 1):
                    offset = (index + lane + repeat) % len(modes)
                    order = modes[offset:] + modes[:offset]
                    result = {}
                    for mode in order:
                        arm = "exact" if mode == "exact" else "projection"
                        factors, trace, cpu = timed(receivers[row["edge"], arm], samples, lane, center, mode)
                        timings[repeat][mode] += cpu
                        result[mode] = factors, trace
                    exact, speculative, guarded, exact_first = (result[mode] for mode in modes)
                    if exact[0] != guarded[0]:
                        raise ValueError(f"guarded projection changed exact factors on {row['key']} lane {lane}")
                    evidence[repeat].update(score(exact[0], *speculative))
                    evidence[repeat]["guarded_fallbacks"] += guarded[1].fallback
                    residual_diagnostic[repeat].update({key: value for key, value in score(exact[0], *exact_first).items()
                                                       if key.startswith("residual_")})
    if evidence[0] != evidence[1] or residual_diagnostic[0] != residual_diagnostic[1]:
        raise ValueError("projection outputs changed across repeats")
    return dict(visits=len(rows), lanes=2 * len(rows), counts=evidence[0],
                residual_using_exact_first=residual_diagnostic[0],
                total_cpu_s=[{key: p[key] / 1e9 for key in modes} for p in timings.values()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    binaries = args.oracle, args.candidate
    results = {}
    for key, archive, limit in (("prospective", args.prospective, 16), ("weak", args.weak, 18)):
        rows = list(read_archive(archive, limit))
        results[key] = replay(rows, binaries, args.assets)
        results[key]["source_sha256"] = digest(json.dumps([row["sha256"] for row, _ in rows]).encode())
    print(json.dumps(dict(binaries=[digest(p.read_bytes()) for p in binaries], cohorts=results), indent=2))


if __name__ == "__main__":
    main()
