"""Validate the scoped arithmetic swap and compare native CPU on the saved DS26 slice."""

import argparse
import ctypes as ct
import json
from pathlib import Path
from statistics import median

import numpy as np

from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    benchmark,
    digest,
    read_archive,
)

from . import receiver_cfo_lineage_trial as lineage
from . import receiver_cfo_restore_object as restore
from . import receiver_cfo_wrap_build as build

WEAK_SHA = "d3005a6496d2ca650ad9853bd5f307332ec79b53f976193a5efec9f31ca106e5"
RESULT = ct.c_double * 4
REQUESTS = (
    ((0, -421_875.), (4, 773_438.), (13328, -789_062.5), (13332, 781_250.)),
    ((13331, 351_562.5), (13329, -0.), (13328, 0.), (8400, -400_390.625), (1, -791_016.)),
    ((3, 0.), (4, 799_900.), (4, -780_000.), (13330, 175_781.25)),
    ((2, -721_679.6875),),
)


def synthesize(paths):
    rng = np.random.default_rng(3549)
    samples = rng.normal(size=400_000).astype(np.float32)
    pilot = rng.normal(size=2 * 2816).astype(np.float32)
    ptr = ct.c_void_p
    functions = {}
    banks = {}
    for name, path in paths.items():
        lib = ct.CDLL(str(path.resolve()))
        functions[name] = lineage.bind(lib, "delay_refine", ct.c_int, ptr, ptr, ct.c_int,
                                       ct.c_double, ct.c_double, ct.c_double,
                                       ct.POINTER(ct.c_double))
        banks[name] = lineage.bind(lib, "delay_refine_bank", ct.c_int, ptr, ptr,
                                   ct.POINTER(lineage.Request), ct.c_int, ct.c_double, ct.c_double,
                                   ct.POINTER(RESULT))
    data = samples.ctypes.data, pilot.ctypes.data
    limits = (-800_000., 800_000.)
    receipts = []
    for group in REQUESTS:
        count = len(group)
        requests = (lineage.Request * count)(*(lineage.Request(*seed) for seed in group))
        records = {name: (RESULT * count)() for name in banks}
        for name, bank in banks.items():
            if bank(*data, requests, count, *limits, records[name]):
                raise ValueError(f"Refinement bank rejected a valid synthetic request on {name}")
        for index, (epoch, hz) in enumerate(group):
            geometry = "restored" if epoch < 4 or epoch >= 13329 else "packed"
            if bytes(records["wrapped"][index]) != bytes(records[geometry][index]):
                raise ValueError("Wrapped bank changed a synthetic result outside its routing rule")
            left, right = RESULT(), RESULT()
            if (functions["wrapped"](*data, epoch, hz, *limits, left)
                    or functions[geometry](*data, epoch, hz, *limits, right)
                    or bytes(left) != bytes(right)):
                raise ValueError("Wrapped direct call changed a synthetic result outside its rule")
            receipts.append(dict(count=count, epoch=epoch, hz=hz, expected_arm=geometry,
                                 direct=list(left), bank={name: list(rows[index])
                                                         for name, rows in records.items()}))
    return receipts


def trial(wrapped, restoration, assets, weak):
    receipt = json.loads((wrapped / "build.json").read_bytes())
    paths = dict(packed=wrapped / "packed.so", restored=restoration / "restored.so",
                 wrapped=wrapped / "wrapped.so")
    expected = dict(packed=restore.INPUT_SHA, restored=build.FULL_RESTORATION_SHA,
                    wrapped=receipt["library_sha256"])
    for name, path in paths.items():
        restore.digest(path, expected[name])
    rows = list(read_archive(weak, 18))
    authority = digest(json.dumps([row["sha256"] for row, _ in rows]).encode())
    if len(rows) != 18 or authority != WEAK_SHA:
        raise ValueError("Expected the frozen 18-window DS26 weak archive")
    for edge in {row["edge"] for row, _ in rows}:
        asset = assets / f"{edge}.f32"
        restore.digest(asset, PINS[asset.name])
    synthetic = synthesize(paths)
    timing = benchmark((paths["restored"], paths["wrapped"]), rows, assets, repeats=8)
    repeats = timing["total_cpu_s"]
    return dict(build=receipt, native_binaries=expected, weak_iq_sha256=authority,
                synthetic=synthetic, measured=timing,
                median_cpu_s=[median(values) for values in zip(*repeats, strict=True)],
                paired_cpu_saving_fraction=median(1 - trial / full for full, trial in repeats))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wrapped", "restoration", "assets", "weak"):
        parser.add_argument(name, type=Path)
    print(json.dumps(trial(**vars(parser.parse_args())), allow_nan=False, indent=2))
