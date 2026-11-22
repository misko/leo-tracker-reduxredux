"""Measure reusable support after the frozen signed CI16 cancellation."""

import argparse
import ctypes as ct
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns

import numpy as np

from .receiver_benchmark import Receiver, digest, read_archive, read_simulated_prefix

SAMPLES = 200_000
PILOT_LENGTH = 13_333
STRIDE = 4
FIR_HALF = 40
PERIOD_THIRDS = 40_000
FIR_COUNT = SAMPLES // STRIDE
FRAME_WIDTH = 3333 + 128 * 44 // STRIDE - 1
FRAME_STARTS = tuple(round(f * 10_000_000 / (750 * STRIDE)) + 88 // STRIDE for f in range(14))
FRAME_END = FRAME_STARTS[-1] + FRAME_WIDTH


class Coarse(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("score", ct.c_double),
                ("confirmation", ct.c_int)]


def guaranteed_clean_runs(epoch):
    """Return the gaps in the nominal pilot loop, before quantization."""
    safe, previous = [], 0
    begin = round(3 * epoch) - PERIOD_THIRDS
    for start in range(begin, 3 * SAMPLES, PERIOD_THIRDS):
        lo = max(0, min(SAMPLES, (start + 2 * 132 + 2) // 3))
        hi = max(0, min(SAMPLES, (start + 302 * 132 + 2) // 3))
        if lo > previous:
            safe.append((previous, lo))
        previous = hi
    if previous < SAMPLES:
        safe.append((previous, SAMPLES))
    return safe


def fir_extent(begin, end):
    """Map a clean native run to fully supported quarter-rate FIR outputs."""
    start = 0 if not begin else (begin + FIR_HALF + STRIDE - 1) // STRIDE
    stop = FIR_COUNT if end == SAMPLES else (end - FIR_HALF + STRIDE - 1) // STRIDE
    return start, max(start, stop)


def count_support(runs):
    native, fir, used, rows, longest = 0, 0, 0, 0, 0
    for begin, end in runs:
        native += end - begin
        longest = max(longest, end - begin)
        lo, hi = fir_extent(begin, end)
        fir += hi - lo
        used += max(0, min(FRAME_END, hi) - max(FRAME_STARTS[0], lo))
        rows += sum(lo <= start and start + FRAME_WIDTH <= hi for start in FRAME_STARTS)
    return dict(native_clean=int(native), fir_clean=int(fir), used_fir_clean=int(used),
                clean_modes_rows=int(rows), longest_clean_run=int(longest))


class SupportProbe:
    def __init__(self, library):
        audit = ct.CDLL(str(library.resolve()))
        self.equal_runs = audit.equal_iq_runs
        self.equal_runs.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        self.equal_runs.restype = ct.c_int
        self.copy = audit.copy_retained_input
        self.copy.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t]
        self.copy.restype = None
        self.runs = np.empty((SAMPLES // 2 + 1, 2), dtype="<i4")
        self.residual = np.empty((SAMPLES, 2, 2), dtype="<i2")
        self.rotated = np.empty(80000, dtype="<f4")
        self.retained = np.empty((SAMPLES, 2, 2), dtype="<i2")

    def measure(self, receiver, timing, asset, raw, lane, center):
        raw_address, residual_address = raw.ctypes.data, self.residual.ctypes.data
        coarse = Coarse()
        success = receiver.lib.timing_first_detect(
            timing, raw_address, lane, center - 800000, center + 800000, ct.byref(coarse),
        )
        if success:
            raise ValueError("unexpected failure from the frozen timing scout")
        if not coarse.confirmation:
            return None
        synthesis = asset.ctypes.data + asset.itemsize * (4 * PILOT_LENGTH + 2 * FIR_HALF + 1)
        if receiver.lib.pilot_cancel(raw_address, residual_address, lane,
                                     synthesis, self.rotated.ctypes.data, coarse.epoch, coarse.hz):
            raise ValueError("unexpected failure from frozen cancellation")
        if not np.array_equal(raw[:, 1 - lane], self.residual[:, 1 - lane]):
            raise ValueError("cancellation changed the other physical lane")
        started = process_time_ns()
        count = self.equal_runs(raw_address, residual_address, SAMPLES, lane, self.runs.ctypes.data)
        readback_ns = process_time_ns() - started
        start_copy = process_time_ns()
        self.copy(self.retained.ctypes.data, raw_address, raw.nbytes)
        copy_ns = process_time_ns() - start_copy
        actual = count_support(self.runs[:count].tolist())
        guaranteed = count_support(guaranteed_clean_runs(coarse.epoch))
        if any(actual[key] < guaranteed[key] for key in actual):
            raise ValueError("cancellation escaped the prescribed pilot support")
        return dict(epoch=coarse.epoch, hz=coarse.hz, center=center, clean_runs=count,
                    readback_ns=readback_ns, copy_ns=copy_ns, actual=actual, guaranteed=guaranteed)


def timing_context(receiver, asset):
    lib = receiver.lib
    lib.timing_first_create.argtypes = [ct.c_int, ct.c_void_p, ct.c_void_p]
    lib.timing_first_create.restype = ct.c_void_p
    lib.timing_first_free.argtypes = [ct.c_void_p]
    lib.timing_first_free.restype = None
    lib.timing_first_detect.argtypes = [*receiver.run.argtypes[:-1], ct.POINTER(Coarse)]
    lib.timing_first_detect.restype = ct.c_int
    lib.pilot_cancel.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_void_p,
                                ct.c_double, ct.c_double]
    lib.pilot_cancel.restype = ct.c_int
    fir = asset.ctypes.data + asset.itemsize * 4 * PILOT_LENGTH
    timing = lib.timing_first_create(STRIDE, asset.ctypes.data, fir)
    if not timing:
        raise ValueError("frozen timing scout creation failed")
    return timing


def study(rows, binary, assets, audit):
    data, counts, comp = [], Counter(), Counter()
    with ExitStack() as resources:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            receiver = Receiver(binary, asset)
            resources.callback(receiver.close)
            timing = timing_context(receiver, asset)
            resources.callback(receiver.lib.timing_first_free, timing)
            receivers[edge] = receiver, timing, asset
        for row, raw in rows:
            acq, target = row["acquisition"], row["target"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            receiver, timing, asset = receivers[row["edge"]]
            for lane in (0, 1):
                factors, cpu, _ = receiver.timed(raw, lane, center)
                counts["lanes"] += 1
                comp["whole_receiver_ns"] += cpu
                entry = audit.measure(receiver, timing, asset, raw, lane, center)
                if entry is None:
                    if factors:
                        raise ValueError("a factor was exported without coarse confirmation")
                    continue
                counts["residual_scans"] += 1
                rank1 = any(f[0] == 1 for f in factors)
                counts["exported_second_factor"] += rank1
                counts["nonzero_mixing_center"] += bool(center)
                data.append(dict(key=row["key"], edge=row["edge"], lane=lane, second_factor=rank1,
                                 factors=factors, **entry))
    return dict(counts=counts, timings_ns=comp, cases=data,
                iq_sha256=digest(json.dumps([row["sha256"] for row, _ in rows]).encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receiver", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("simulation_panel", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    inputs = {"prospective": list(read_archive(args.prospective, 16)),
              "weak": list(read_archive(args.weak, 18))}
    sims = defaultdict(list)
    for row, samples in read_simulated_prefix(args.simulation_panel, 40):
        sims[row["case"]].append((row, samples))
    inputs.update(sims)
    probe = SupportProbe(args.audit)
    cohorts = {key: study(rows, args.receiver, args.assets, probe) for key, rows in inputs.items()}
    receipt = dict(receiver_sha256=digest(args.receiver.read_bytes()),
                   audit_sha256=digest(args.audit.read_bytes()), cohorts=cohorts)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
