"""Test the full-rate adjacent-symbol contrast as the primary two-scan scout."""

import argparse
import ctypes as ct
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns

import numpy as np

from ..differential_pilot import filters
from .receiver_aperture import compare
from .receiver_benchmark import Factor, Receiver, digest, read_archive, read_simulated_prefix


class AdjacentStats(ct.Structure):
    _fields_ = [("scouts", ct.c_uint), ("fallback", ct.c_uint * 2), ("confirmed", ct.c_uint * 2)]


class Adjacent(Receiver):
    def __init__(self, binary, asset, edge):
        super().__init__(binary, asset)
        references = filters(edge)
        self.reference_filters = np.stack([k for k, _ in references], dtype="<c8")
        self.reference_energy = np.stack([e for _, e in references], dtype="<f8")
        configure = self.lib.receiver_adjacent_configure
        configure.argtypes = [ct.c_void_p] * 3
        configure.restype = ct.c_int
        if configure(self.ctx, self.reference_filters.ctypes.data,
                     self.reference_energy.ctypes.data):
            self.close()
            raise ValueError("adjacent-symbol scout rejected its reference inputs")
        self.scout = self.lib.receiver_adjacent_factors
        self.scout.argtypes = self.run.argtypes[:-1] + [
            ct.c_int, ct.POINTER(AdjacentStats), ct.POINTER(Factor),
        ]
        self.scout.restype = ct.c_int

    def detect(self, samples, lane, center, fallback):
        out, trace = (Factor * 2)(), AdjacentStats()
        args = self.ctx, samples.ctypes.data, lane, center - 800000, center + 800000, fallback
        start = process_time_ns()
        count = self.scout(*args, ct.byref(trace), out)
        cpu = process_time_ns() - start
        if not 0 <= count <= 2:
            raise ValueError("invalid adjacent receiver factor count")
        factors = tuple(tuple(getattr(value, name) for name, _ in Factor._fields_)
                        for value in out[:count])
        stats = dict(first_fallback=trace.fallback[0], residual_fallback=trace.fallback[1],
                     first_confirmed=trace.confirmed[0], residual_confirmed=trace.confirmed[1],
                     residual_attempted=int(trace.scouts == 2))
        return factors, cpu, stats


def trial(rows, binaries, assets):
    with ExitStack() as stack:
        contexts = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            exact, alternate = Receiver(binaries[0], pilot), Adjacent(binaries[1], pilot, edge)
            stack.callback(exact.close)
            stack.callback(alternate.close)
            contexts[edge] = exact, alternate
        runs, changes = [], []
        modes = ("exact", "primary", "fallback")
        for repeat in range(2):
            cpu, outcomes = Counter(), [Counter(), Counter()]
            for index, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                exact, variant = contexts[row["edge"]]
                for lane in (0, 1):
                    offset = (index + lane + repeat) % len(modes)
                    evidence = {}
                    for mode in modes[offset:] + modes[:offset]:
                        if mode == "exact":
                            factors, elapsed, _ = exact.timed(samples, lane, center)
                            stats = {}
                        else:
                            factors, elapsed, stats = variant.detect(
                                samples, lane, center, mode == "fallback",
                            )
                        cpu[mode] += elapsed
                        evidence[mode] = factors, stats
                    expected = evidence["exact"][0]
                    for arm, mode in enumerate(modes[1:]):
                        returned, stats = evidence[mode]
                        compare(expected, returned, outcomes[arm])
                        outcomes[arm].update(stats)
                    if not repeat and any(evidence[m][0] != expected for m in modes[1:]):
                        changes.append(dict(key=row["key"], lane=lane,
                                            **{key: value[0] for key, value in evidence.items()}))
            runs.append(dict(cpu_s={key: value / 1e9 for key, value in cpu.items()},
                             outcomes=dict(zip(modes[1:], outcomes, strict=True))))
        if runs[0]["outcomes"] != runs[1]["outcomes"]:
            raise ValueError("adjacent scout decisions changed between repeats")
        return dict(lanes=2 * len(rows), runs=runs, changed=changes,
                    iq_sha256=digest(json.dumps([row["sha256"] for row, _ in rows]).encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exact", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("simulation_panel", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    inputs = {"prospective": list(read_archive(args.prospective, 16)),
              "weak": list(read_archive(args.weak, 18))}
    simulation = defaultdict(list)
    for row, samples in read_simulated_prefix(args.simulation_panel, 40):
        simulation[row["case"]].append((row, samples))
    inputs.update(simulation)
    bins = args.exact, args.candidate
    report = {key: trial(rows, bins, args.assets) for key, rows in inputs.items()}
    hashes = [digest(p.read_bytes()) for p in bins]
    print(json.dumps(dict(binaries=hashes, cohorts=report), indent=2))


if __name__ == "__main__":
    main()
