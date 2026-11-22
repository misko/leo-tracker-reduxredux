"""Splice a tiled FIR into d97b and compare complete native receiver calls."""

import argparse
import ctypes as ct
import json
from pathlib import Path
from statistics import median
import subprocess
from time import process_time_ns

import numpy as np

from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import exports, run
from .receiver_refine_parity_trial import austin_windows
from .receiver_resident_cancel_trial import austin, paired
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_archive


WRAPPED_SHA = "d97b603faaf3eb63b246706cfa8dfeca0b7e329b0cc23b227e7de946de48b0e3"
WEAK_SHA = "d3005a6496d2ca650ad9853bd5f307332ec79b53f976193a5efec9f31ca106e5"
SOURCE = restore.HERE / "receiver_fir_tile.c"


def build(work, bench):
    work.mkdir()
    wrapped = bench / "receiver-cfo-wrap-fix"
    archive = bench / "site-free-mode-pair-pgo/candidate/objects"
    cancellation = bench / "c803-packed-cancel-trial-v2/candidate"
    identity = json.loads((wrapped / "build.json").read_bytes())
    restore.digest(wrapped / "wrapped.so", WRAPPED_SHA)
    recipe_file = restore.PINNED / "build.json"
    restore.digest(recipe_file, restore.RECIPE_SHA)
    recipe = json.loads(recipe_file.read_bytes())
    flags, base = restore.compiler_inputs(recipe, archive, cancellation)
    delays = tuple(wrapped / name for name in ("delay_pgo.o", "delay_reference.o", "delay_dispatch.o"))
    for name, path in base.items():
        restore.digest(path, identity["original_objects"][name])
    for path in delays:
        restore.digest(path, identity["linked_delay_objects"][path.name])
    compiler = recipe["cc"]

    def link(output, objects, extra=()):
        return run([compiler, "-shared", "-Wl,--gc-sections", *objects.values(), *delays[1:], *extra,
                    "-lfftw3f", "-pthread", "-lm", "-o", output], cwd=restore.PINNED)

    reference = work / "reference.so"
    base[restore.DELAY] = delays[0]
    commands = [link(reference, base)]
    restore.digest(reference, WRAPPED_SHA)
    delay_copy, tile = work / "delay_pgo.o", work / "tile.o"
    commands.append(run(["objcopy", "--redefine-sym=delay_decimate=leo_pgo_delay_decimate",
                         delays[0], delay_copy]))
    commands.append(run([compiler, *flags, "-Wall", "-Wextra", "-Werror", "-c", SOURCE, "-o", tile],
                        cwd=restore.PINNED))
    candidate = work / "tile.so"
    commands.append(link(candidate, base | {restore.DELAY: delay_copy}, (tile,)))
    if exports(reference) != exports(candidate):
        raise ValueError("The tiled FIR changed the receiver's exports")
    for section in (".text.refine_batch", ".text.delay_refine_bank", ".text.unlikely.delay_refine"):
        command = ["readelf", "--hex-dump", section]
        if subprocess.check_output([*command, delays[0]]) != subprocess.check_output([*command, delay_copy]):
            raise ValueError(f"The object rename changed archived instructions in {section}")
    return dict(reference_sha256=WRAPPED_SHA, candidate_sha256=restore.digest(candidate),
                tile_source_sha256=restore.digest(SOURCE), commands=commands)


def synthetic_fir(binaries, assets):
    operators = []
    for path in binaries:
        kernel = ct.CDLL(str(path)).delay_decimate
        kernel.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        kernel.restype = ct.c_int
        operators.append(kernel)
    rng = np.random.default_rng(392403)
    integral = rng.integers(-32768, 32768, size=400000, dtype=np.int16).astype(np.float32)
    fractional = (integral * np.float32(1.0 / 117)).astype(np.float32)
    output = [np.empty(100000, dtype=np.float32) for _ in binaries]
    results = {}
    for edge in ("lower", "upper"):
        asset = assets / f"{edge}.f32"
        restore.digest(asset, PINS[asset.name])
        coeff = np.fromfile(asset, dtype="<f4")[4 * 13333:4 * 13333 + 81]
        for label, samples in (("ci16-float", integral), ("fractional-float", fractional)):
            times = []
            for repeat in range(60):
                row = [0, 0]
                for index in (repeat % 2, 1 - repeat % 2):
                    begin = process_time_ns()
                    status = operators[index](samples.ctypes.data, coeff.ctypes.data, 81, 4,
                                              output[index].ctypes.data)
                    row[index] = process_time_ns() - begin
                    if status != 0:
                        raise ValueError("The fixture FIR call failed")
                times.append(row)
            if output[0].tobytes() != output[1].tobytes():
                raise ValueError(f"FIR output differs on {edge} {label}")
            results[f"{edge}-{label}"] = dict(
                native_cpu_ns=times, median_cpu_ns=[median(col) for col in zip(*times, strict=True)],
                paired_change=median(b / a - 1 for a, b in times), output_sha256=digest(output[0].tobytes()),
            )
    return results


def trial(work, bench, assets, weak, archive, source_audit, wide_reference):
    manifest = build(work, bench)
    binaries = work / "reference.so", work / "tile.so"
    rows = list(read_archive(weak, 18))
    expected = digest(json.dumps([row["sha256"] for row, _ in rows]).encode())
    if len(rows) != 18 or expected != WEAK_SHA:
        raise ValueError("Expected the pinned weak-carrier archive")
    return dict(
        build=manifest, solo=synthetic_fir(binaries, assets),
        weak=paired(rows, assets, binaries, repeats=9),
        Austin=austin(list(austin_windows(archive, source_audit, wide_reference)), assets, binaries),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("work", "bench", "assets", "weak", "archive", "source_audit", "wide_reference"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    print(json.dumps(trial(**vars(parser.parse_args())), indent=2, allow_nan=False))
