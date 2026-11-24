"""Test ordered AVX2 Jacobi rotations on one already resident signed member."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time_ns, perf_counter_ns

import numpy as np

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

from . import legacy_block_input as port, legacy_block_seek as core, sparse_cold_input as release
from .cross_lag_eight_ms import BUILD_SHA, EIGHT, EIGHT_SHA, SOURCE_SHA
from .future_capture_storage import qualified
from .legacy_fresh_0169 import admit
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, verified
from .scout_readout_trial import check_machine, factor_bytes
from .whole_group_receiver_bound import FULL_BUILD, FULL_BUILD_SHA, SOURCE_SHA as FULL_SOURCE_SHA

HERE = Path(__file__).resolve().parent
HELPER = HERE / "receiver_jacobi_columns.inc"
ORDERS = (("scalar", "vector", "shipped"), ("shipped", "vector", "scalar")) * 2


def overlay(source):
    entry = "static void principal_modes(TimingFirst *w, const Sample *low) {\n"
    before, after = source.split(entry)
    modes, rest = after.split("\n/* A constant carrier rotates each lag", 1)

    def change(old, new):
        nonlocal modes
        if modes.count(old) != 1:
            raise ValueError(f"Original Jacobi source anchor changed: {old}")
        modes = modes.replace(old, new, 1)

    modes = "    uint64_t begin_modes = jacobi_now();\n    if (begin_modes) ++jacobi_trace[2];\n" + modes
    change("    for (int sweep = 0; sweep < 20; ++sweep) {",
           "    uint64_t begin_jacobi = jacobi_now();\n"
           "    const int vector = jacobi_columns_eligible(covariance);\n"
           "    for (int sweep = 0; sweep < 20; ++sweep) {")
    start = "                for (int k = 0; k < count; ++k) {\n"
    stop = "                covariance[p][p] = a - t * r;\n"
    leading, inner = modes.split(start)
    body, tail = inner.split(stop)
    modes = (leading + "                if (vector) {\n"
             "                    jacobi_rotate_columns(covariance, axis, p, q, c, s);\n"
             "                } else {\n" + "".join("    " + line for line in (start + body).splitlines(keepends=True))
             + "                }\n" + stop + tail)
    change("    if (have_planes) {\n        project_frame_planes(w, covariance, axis);\n        return;\n",
           "    if (vector) jacobi_restore_axis(axis);\n"
           "    jacobi_add_time(1, begin_jacobi);\n"
           "    if (have_planes) {\n        project_frame_planes(w, covariance, axis);\n"
           "        jacobi_add_time(0, begin_modes);\n        return;\n")
    if not modes.rstrip().endswith("}"):
        raise ValueError("Could not isolate the ordered mode function")
    at = modes.rindex("}")
    modes = modes[:at] + "    jacobi_add_time(0, begin_modes);\n" + modes[at:]
    return before + f'#include "{HELPER.name}"\n\n' + entry + modes + "\n/* A constant carrier rotates each lag" + rest


def build(root):
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(EIGHT.with_name("build-receipt.json"), BUILD_SHA))
    installed = release.PAYLOAD / "receiver.so"
    flags = [*full["commands"][-2][:-4], "-D_POSIX_C_SOURCE=200809L", "-I", HERE]
    paths, outputs, commands = {}, {}, []

    def execute(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, cwd=full["cwd"], check=True)

    for mode, shipped, pin, link, source_pin in (
        ("full", installed, INSTALLED_SHA, full["commands"][-1], FULL_SOURCE_SHA["full"]),
        ("short_primary", EIGHT, EIGHT_SHA, short["relink"], SOURCE_SHA),
    ):
        verified(shipped, pin)
        directory = root / mode
        directory.mkdir()
        relinked = directory / "relinked.so"
        execute([*link[:-1], relinked])
        verified(relinked, pin)
        old, = (Path(part) for part in link if Path(part).name == "timing_first_receiver.o")
        source = directory / old.with_suffix(".c").name
        source.write_text(overlay(verified(old.with_suffix(".c"), source_pin).decode()))
        obj, altered = source.with_suffix(".o"), directory / "jacobi.so"
        execute([*flags, "-c", source, "-o", obj])
        execute([*(obj if part == str(old) else part for part in link[:-1]
                   if not part.startswith("-fprofile-use=") and part != "-fno-profile-values"), altered])
        paths[mode] = shipped, altered
        outputs[mode] = dict(original=pin, source=source_pin, alternative=sha256(altered.read_bytes()).hexdigest())
    return paths, dict(output=outputs, commands=commands, same_build="no profile feedback on modified object",
                       helper_sha256=sha256(HELPER.read_bytes()).hexdigest())


def set_switch(engine, arm, trace):
    function = engine.native.lib.receiver_jacobi_columns_mode
    function.argtypes, function.restype = (ct.c_int, ct.c_int), ct.c_int
    if function(int(arm == "vector"), int(trace)) != int(arm == "vector"):
        raise ValueError("The native proof requires its scalar and AVX2 modes")


def read_trace(engine):
    data = (ct.c_uint64 * 3)()
    fn = engine.native.lib.receiver_jacobi_columns_times
    fn.argtypes, fn.restype = (ct.POINTER(ct.c_uint64),), None
    fn(data)
    return dict(zip(("modes_ns", "jacobi_ns", "scouts"), tuple(data), strict=True))


def cases(reader, windows):
    targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
    selector = StereoSchedule(full_coverage=True)
    jobs = []
    for window in windows:
        row = window.index
        if qualified(row.acquisition):
            target = targets[row.target_id]
            _, mode = selector.visit(target["edge"], target, row.acquisition)
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - row.acquisition["actual_if_center_hz"]
            jobs.extend((row.sequence, mode, lane, center, window.samples) for lane in (0, 1))
    return jobs


def execute_scope(engines, jobs, arm, *, full_only, trace=False):
    if arm != "shipped":
        for engine in engines[1].values():
            set_switch(engine, arm, trace)
    active, results, clocks = engines[arm != "shipped"], [], Counter()
    start = process_time_ns(), perf_counter_ns()
    for sequence, mode, lane, center, samples in jobs:
        mode = "full" if full_only else mode
        factors, (cpu, wall) = active[mode].run(samples, lane, center)
        results.append((sequence, mode, lane, factor_bytes(factors).hex(), len(factors)))
        clocks.update({mode + "_cpu_ns": cpu, mode + "_wall_ns": wall, mode + "_calls": 1})
    finish = process_time_ns() - start[0], perf_counter_ns() - start[1]
    return results, dict(native=dict(clocks), batch_cpu_ns=finish[0], batch_wall_ns=finish[1],
                         trace=None if not trace else {name: read_trace(engine) for name, engine in active.items()})


def run(root):
    machine = check_machine()
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use fresh tmpfs output")
    source, chunk, expected, authority, residency = admit()
    root.mkdir(mode=0o700)
    paths, build_receipt = build(root)
    specification = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer")
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, specification["paired_sha256"]["sha256"])
    with core.one_member(source.reader.path, chunk), ingress(), paired_decoded_hashes(hasher):
        windows = tuple(port.stock_scope(source.reader, chunk))
    if [window.index.iq_sha256 for window in windows] != expected:
        raise ValueError("Authenticated original input differs from the frozen authority")
    jobs = cases(source.reader, windows)
    if (len(jobs), sum(mode == "full" for _, mode, _, _, _ in jobs)) != (102, 16):
        raise ValueError("Preserve all admitted stereo visits and original mixed anchor cadence")
    asset = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    scopes = {}
    with ExitStack() as stack:
        engines = [{mode: NativePath(paths[mode][choice], asset, mode) for mode in paths} for choice in (0, 1)]
        for engineset in engines:
            for engine in engineset.values():
                stack.callback(engine.close)
        for scope in ("full20", "mixed20_8"):
            reference, repeats = None, []
            for order in ORDERS:
                repeat = {}
                for arm in order:
                    factors, measured = execute_scope(engines, jobs, arm, full_only=scope == "full20")
                    if reference is None:
                        reference = factors
                    if factors != reference:
                        raise ValueError(f"Ordered native bytes changed for {scope} {arm}")
                    repeat[arm] = measured
                repeats.append(repeat)
            stages = {}
            for arm in ("scalar", "vector"):
                factors, stages[arm] = execute_scope(engines, jobs, arm, full_only=scope == "full20", trace=True)
                if factors != reference:
                    raise ValueError("Stage clock changed native bytes")
            scopes[scope] = dict(repeats=repeats, stages=stages, factors=canonical_digest(reference),
                                 emitted=sum(row[-1] for row in reference), lane_calls=len(reference))
    receipt = dict(machine=machine, original=port.member_identity(source.reader, chunk), raw_authority=authority,
                   cache=residency, native_build=build_receipt, scopes=scopes, orders=ORDERS)
    with (root / "result.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
