"""Compare blind full-duration joint stereo pilot timing to mismatched and marginal controls."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from itertools import permutations
import json
from math import remainder
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import V3_SHA

from .low_bit_pilot_screen import adc, carrier_wave
from .scout_readout_trial import ACQUISITION, ACQUISITION_SHA, PILOT_SHA, check_machine
from .short_signed_trial import factor_bytes, verified


CELLS, PERIOD, POINTS, KEEP = 3333, 13333, 200000, 4
METHODS = {"joint": (-1, 0), "mismatched": (-1, 1111), "rx0": (0, 0), "rx1": (1, 0)}
DIRECTED = Path(__file__).with_name("measurements") / "directed-verifier.json.gz"


class Epoch(ct.Structure):
    _fields_ = [("sample", ct.c_int), ("score", ct.c_float)]


class Envelope:
    def __init__(self, path, asset):
        self.native = ct.CDLL(str(path))
        self.native.joint_envelope_create.argtypes = [ct.c_void_p]
        self.native.joint_envelope_create.restype = ct.c_void_p
        self.native.joint_envelope_free.argtypes = [ct.c_void_p]
        self.native.joint_envelope_free.restype = None
        self.detect = self.native.joint_envelope_detect
        self.detect.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.POINTER(Epoch)]
        self.detect.restype = ct.c_int
        pattern = asset[4 * PERIOD + 81:].view(np.complex64)
        energy = abs(pattern[3*np.arange(4*CELLS)])**2
        cells = energy.reshape(CELLS, 4).sum(axis=1)
        self.context = self.native.joint_envelope_create(cells.ctypes.data)
        if not self.context:
            raise ValueError("Could not initialize pilot envelope FFTs")

    def close(self):
        self.native.joint_envelope_free(self.context)

    def measure(self, iq, method):
        rows = (Epoch * KEEP)()
        lane, shift = METHODS[method]
        start, wall = process_time_ns(), perf_counter_ns()
        count = self.detect(self.context, iq.ctypes.data, lane, shift, rows)
        elapsed, ticks = perf_counter_ns() - wall, process_time_ns() - start
        if not 0 <= count <= KEEP:
            raise ValueError("Unexpected timing proposal count")
        return [(item.sample, item.score) for item in rows[:count]], ticks, elapsed


def epoch(factor):
    return factor[1] + factor[2]


def distance(a, b):
    return abs(remainder(a-b, PERIOD))


def supports(phases, timing, tolerance):
    """Count one-to-one matches between lane factors and the common phase set."""
    assignments = []
    for permutation in permutations(range(len(timing)), min(len(timing), len(phases))):
        for left in permutations(range(len(phases)), len(permutation)):
            pairs = [(i, distance(phases[i], timing[j])) for i, j in zip(left, permutation, strict=True)]
            assignments.append(sorted((i, err) for i, err in pairs if err <= tolerance))
    return min(assignments, key=lambda pairs: (-len(pairs), sum(err for _, err in pairs), pairs))


def counterparts(stock, tolerance):
    left, right = stock
    matches = []
    for a in permutations(left):
        for b in permutations(right):
            pairs = [(distance(epoch(x), epoch(y)), y[3] - x[3], x[0], y[0])
                     for x, y in zip(a, b, strict=False) if distance(epoch(x), epoch(y)) <= tolerance]
            matches.append(pairs)
    return min(matches, key=lambda pairs: (-len(pairs), sum(item[0] for item in pairs)))


def tabulate(detail, tolerance):
    counts, times, common, residual = {}, Counter(), [], Counter()
    totals = Counter()
    for row in detail:
        stock = row["stock"]
        common.extend(counterparts(stock, tolerance))
        totals["stereo"] += 1
        totals["lanes"] += 2
        for lane, factors in enumerate(stock):
            times["available_stock_ns"] += sum(row["stock_cpu_ns"][lane])
            totals[f"positive_rx{lane}"] += bool(factors)
            for rank, *_ in factors:
                totals[f"rx{lane}_rank{rank}"] += 1
            for method in ("joint", "mismatched", "marginal"):
                scores = row["proposal"][method if method != "marginal" else f"rx{lane}"]
                timing = [value for value, _ in scores]
                hits = supports([epoch(item) for item in factors], timing, tolerance)
                count = counts.setdefault(method, Counter())
                for i, _ in hits:
                    count[f"rx{lane}_rank{factors[i][0]}"] += 1
                count["retry_lanes"] += len(hits) != len(factors)
                count["retry_positive_with_only_rank1_missing"] += (
                    bool(factors) and len(hits) < len(factors)
                    and {factors[i][0] for i, _ in hits} == {0}
                )
                if not factors:
                    count["proposals_on_empty_v3_lanes"] += len(timing)
                if method == "joint" and len(hits) != len(factors):
                    times["retry_stock_ns"] += sum(row["stock_cpu_ns"][lane])
                    residual["rank1_misses"] += sum(item[0] == 1 for item in factors) - sum(
                        factors[i][0] == 1 for i, _ in hits)
        times["joint_total_cpu_ns"] += sum(row["cpu_ns"]["joint"])
    return dict(factors=totals, methods=counts, cpu_ns=times, paired_common=common,
                joint_rank1_misses=residual["rank1_misses"])


def evaluate(stereo, assets, binary, installed, repeats=5):
    detail = []
    with ExitStack() as closer:
        finders = {}
        for edge, sha in PILOT_SHA.items():
            asset = np.frombuffer(verified(assets / f"{edge}.f32", sha), dtype="<f4")
            stock, sketch = Receiver(installed, asset), Envelope(binary, asset)
            closer.callback(stock.close)
            closer.callback(sketch.close)
            finders[edge] = stock, sketch
        for row, iq in stereo:
            if iq.shape != (POINTS, 2, 2) or iq.dtype != np.dtype("<i2") or not iq.flags.c_contiguous:
                raise ValueError(f"Invalid stereo geometry for {row['key']}")
            detail.append(dict(key=row["key"], iq_sha256=row["sha256"], edge=row["edge"],
                               channel=row["target"]["channel"], truth=row.get("truth"),
                               stock=[None, None], stock_cpu_ns=[[], []], stock_wall_ns=[[], []],
                               proposal={}, cpu_ns={key: [] for key in METHODS},
                               wall_ns={key: [] for key in METHODS}))
        for repeat in range(repeats):
            for index, ((row, iq), record) in enumerate(zip(stereo, detail, strict=True)):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                stock, sketch = finders[row["edge"]]
                for lane in (0, 1):
                    factors, cpu, wall = stock.timed(iq, lane, center)
                    if repeat and factor_bytes(factors) != factor_bytes(record["stock"][lane]):
                        raise ValueError("Stock ALGO08v3 results changed across repeated calls")
                    record["stock"][lane] = factors
                    record["stock_cpu_ns"][lane].append(cpu)
                    record["stock_wall_ns"][lane].append(wall)
                methods = list(METHODS)
                for i in range(len(methods)):
                    method = methods[(index+repeat+i) % len(methods)]
                    phases, cpu, wall = sketch.measure(iq, method)
                    if repeat and phases != record["proposal"][method]:
                        raise ValueError("Envelope proposals changed across repeated calls")
                    record["proposal"][method] = phases
                    record["cpu_ns"][method].append(cpu)
                    record["wall_ns"][method].append(wall)
    return dict(detail=detail, summary={tolerance: tabulate(detail, tolerance) for tolerance in (4, 7)},
                median_stereo_cpu_ms={method: median(t for row in detail for t in row["cpu_ns"][method])/1e6
                                      for method in METHODS})


def plant(assets):
    rng = np.random.default_rng(6314802)
    for edge, sha in PILOT_SHA.items():
        asset = np.frombuffer(verified(assets / f"{edge}.f32", sha), dtype="<f4")
        for label, epochs in (("shared", (3208, 3208)), ("split", (3208, 7251)),
                              ("one_lane", (3208, None)), ("noise", (None, None))):
            iq = np.empty((POINTS, 2, 2), dtype="<i2")
            for lane, (phase, hz) in enumerate(zip(epochs, (-647217, 498719), strict=True)):
                wave = 0 if phase is None else carrier_wave(asset, phase * 3, hz, rolled=False)
                noise = (rng.normal(size=POINTS) + 1j*rng.normal(size=POINTS)) / np.sqrt(2)
                values = adc((wave + 0.35*noise) * (3000 if lane == 0 else 1700))
                iq[:, lane, 0], iq[:, lane, 1] = values.real, values.imag
            yield (dict(key=f"{edge}:{label}", edge=edge, sha256=digest(iq.tobytes()), truth=epochs,
                        target=dict(channel=1, rf_center_hz=0, lnb_lo_hz=0),
                        acquisition=dict(actual_if_center_hz=0)), iq)


def projection(result):
    split = json.loads(verified(ACQUISITION, ACQUISITION_SHA))
    callbacks = sum(row["cpu_s"] for row in split["detector_groups"].values())
    outside = split["outside_detector_cpu_s"]
    costs = result["summary"][7]["cpu_ns"]
    timing_ratio = costs["joint_total_cpu_ns"] / costs["available_stock_ns"]
    retry_ratio = costs["retry_stock_ns"] / costs["available_stock_ns"]
    return dict(source_sha256=ACQUISITION_SHA, stock_native_s=callbacks, outside_s=outside,
                native_ratio_allowed_for_half=(callbacks-outside)/(2*callbacks),
                joint_only_native_ratio=timing_ratio, stock_retry_native_ratio=retry_ratio,
                projected_cpu_s_with_timing_and_oracle_stock_retries=outside + callbacks*(timing_ratio+retry_ratio),
                path_gives_carrier_confirmation_and_verification_zero_cost=True,
                directed_verification_receipt_sha256=digest(DIRECTED.read_bytes()),
                directed_verification_checks=list(json.loads(gzip.decompress(DIRECTED.read_bytes()))
                                                   ["groups"]["dense"]["checks"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "installed", "assets", "weak", "binding", "bulk"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    machine = check_machine()
    verified(args.installed, V3_SHA)
    source = Path(__file__).with_name("joint_envelope.c").resolve()
    args.work.mkdir()
    binary = args.work / "joint-envelope.so"
    compile_cmd = ["cc", "-O3", "-std=c11", "-march=x86-64-v3", "-ffp-contract=off", "-fPIC", "-shared",
                   "-Wall", "-Werror", str(source), "-lfftw3f", "-lm", "-o", str(binary)]
    subprocess.run(compile_cmd, check=True)
    groups = {label: evaluate(list(rows), args.assets, binary, args.installed) for label, rows in (
        ("weak", read_archive(args.weak, 18)),
        ("dense", read_physical(args.binding, args.bulk, 48)),
        ("plant", plant(args.assets)),
    )}
    print(json.dumps(dict(machine=machine, installed_sha256=V3_SHA, asset_sha256=PILOT_SHA,
                          binding_sha256=digest(args.binding.read_bytes()), groups=groups,
                          source_sha256=digest(source.read_bytes()), binary_sha256=digest(binary.read_bytes()),
                          compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
                          command=compile_cmd, projection=projection(groups["dense"])),
                     allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
