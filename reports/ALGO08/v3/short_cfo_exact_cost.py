"""Profile and compare exact operand preparation in fixed-epoch CFO refinement."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
from pathlib import Path
from struct import pack

import numpy as np

from . import short_cfo_refine as ref
from .directed_verifier_trial import replace_once


BASE = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
BASE_PIN = "fed887f464c78d9a547bd1d939dbb0a3987ab4babd3db8f0779928be5a6a1d4e"
EVIDENCE = ref.HERE / "measurements/short-cfo-refine.json.gz"
EVIDENCE_PIN = "038049b8750420ccfd08f7fd3113e8c41d45d62ae0108281348e1d1f9f07c906"
SOURCE = ref.HERE / "short_cfo_refine.inc"
SOURCE_PIN = "82a9900ad8b7f643d6305f64e2723c131078dbd9f77c0788b84f0e1fea6de5a2"
FRACTIONAL = ref.HERE.parents[2] / "tools/pipeline_eval/variants/experimental/receiver_fractional_exact.inc"
FRACTIONAL_PIN = "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b"
ARM = ("frozen", "gather", "gather_angles")
REPEATS = (ARM, ARM[::-1]) * 3
STAGES = ("frame_geometry", "loader", "rotation_and_taps", "correlation", "delay_and_scores")
BODY_MARK = "int short_cfo_refine("
OUTPUT_ARG = "double out[8])"
LOAD = "    if (!frames || portable_verifier_load(w, iq, lane)) return -1;"
GATHER = "    if (!frames || load_frame_support(w, iq, lane, starts, frames, offset, integer)) return -1;"
CORRELATION = "absolute_fractional_correlations(w, frames, starts, cfo, offset)"
CPU_CLOCK = """
#include <time.h>
#ifndef CLOCK_THREAD_CPUTIME_ID
/* The archived -std=c11 build hides the glibc POSIX declaration on Gauss. */
extern int clock_gettime(int, struct timespec *);
#define CLOCK_THREAD_CPUTIME_ID 3
#endif
static uint64_t cfo_stage_clock(void) {
    struct timespec t = {0};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
"""


def instruments(fragment, frac):
    scoped = replace_once(frac, "absolute_fractional_correlations", "profiled_fractional_correlations")
    scoped = replace_once(scoped, "double offset)", "double offset, uint64_t measures[5])")
    scoped = replace_once(scoped, "        for (int k = 0;", "        uint64_t tick = cfo_stage_clock();\n        for (int k = 0;")
    scoped = replace_once(scoped, "        correlated_fractional(",
                          "        measures[2] += cfo_stage_clock() - tick;\n        tick = cfo_stage_clock();\n        correlated_fractional(")
    scoped = replace_once(scoped, "w->correlations[1] + frame * 64);",
                          "w->correlations[1] + frame * 64);\n        measures[3] += cfo_stage_clock() - tick;")
    body = replace_once(fragment, BODY_MARK, "int short_cfo_profile(")
    body = replace_once(body, OUTPUT_ARG, "double out[8], uint64_t measures[5])")
    body = replace_once(body, "    const int integer =", "    uint64_t tick = cfo_stage_clock();\n    const int integer =")
    body = replace_once(body, LOAD, "    measures[0] += cfo_stage_clock() - tick;\n    tick = cfo_stage_clock();\n" + LOAD
                        + "\n    measures[1] += cfo_stage_clock() - tick;")
    body = replace_once(body, "        prepare_integer_rotation(w, cfo);",
                        "        tick = cfo_stage_clock();\n        prepare_integer_rotation(w, cfo);\n"
                        "        measures[2] += cfo_stage_clock() - tick;\n        tick = cfo_stage_clock();")
    body = replace_once(body, "w->glrt_control, w->correlations[0], w->correlations[1]);",
                        "w->glrt_control, w->correlations[0], w->correlations[1]);\n        measures[3] += cfo_stage_clock() - tick;")
    body = replace_once(body, CORRELATION, "profiled_fractional_correlations(w, frames, starts, cfo, offset, measures)")
    body = replace_once(body, "    DelayProduct all", "    tick = cfo_stage_clock();\n    DelayProduct all")
    body = replace_once(body, "    return 0;", "    measures[4] += cfo_stage_clock() - tick;\n    return 0;")
    return CPU_CLOCK + scoped + body


def build(work):
    source = ref.verified(SOURCE, SOURCE_PIN).decode()
    shared, body = source.split(BODY_MARK, maxsplit=1)
    body = BODY_MARK + body
    frac = ref.verified(FRACTIONAL, FRACTIONAL_PIN).decode()
    extra = (ref.HERE / "short_cfo_exact_cost.inc").read_text()
    prepared = replace_once(frac, "absolute_fractional_correlations", "precomputed_angle_correlations")
    prepared = replace_once(prepared, "    double old_fraction", "    double arguments[aperture];\n    double old_fraction")
    prepared = replace_once(prepared, "        for (int k = 0;", "        prepare_angles(arguments, starts[frame], offset, cfo);\n        for (int k = 0;")
    prepared = replace_once(prepared, "rotate(-tau * cfo * position / rate)", "rotate(arguments[k])")
    gathered = replace_once(replace_once(body, BODY_MARK, "int short_cfo_gather("), LOAD, GATHER)
    both = replace_once(gathered, "int short_cfo_gather(", "int short_cfo_gather_angles(")
    both = replace_once(both, CORRELATION, "(__builtin_cpu_supports(\"avx2\")\n"
                        "        ? precomputed_angle_correlations(w, frames, starts, cfo, offset)\n"
                        f"        : {CORRELATION})")
    extension = work / "exact-measurement.inc"
    extension.write_text(shared + extra + prepared + gathered + both + instruments(body, frac))
    return ref.build(work / "build", ref.PAYLOAD / "receiver.so", extension)


def diag_bytes(diag):
    return None if diag is None else pack("=8d", *diag)


class RefineEntry(ref.Refine):
    def __init__(self, path, name):
        self.library = ct.CDLL(str(path))
        fn = getattr(self.library, name)
        fn.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_uint, ct.c_double, ct.c_double, ct.POINTER(ct.c_double))
        fn.restype = ct.c_int
        self.call = fn


def profile(path, library, iq, lane, factor):
    observe = library.short_cfo_profile
    observe.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_uint, ct.c_double, ct.c_double,
                        ct.POINTER(ct.c_double), ct.POINTER(ct.c_uint64))
    observe.restype = ct.c_int
    values, parts = (ct.c_double*8)(), (ct.c_uint64*5)()
    verify = ct.cast(path.native.ctx, ct.POINTER(ct.c_void_p))[1]
    before = ref.clock()
    status = observe(verify, iq.ctypes.data, lane, *factor[1:4], values, parts)
    return status, tuple(values), dict(zip(STAGES, parts, strict=True)), ref.since(before)


def conditioned(row, detector, refinement):
    short, added, primary = (), [0, 0], [0, 0]
    if row["mode"] == "short_primary":
        short, primary = detector["short"].run(row["iq"], row["lane"], row["tune"])
    else:
        short, primary = detector["full"].run(row["iq"], row["lane"], row["tune"])
        return short, None, (ref.ordered(short), "anchor"), added, primary
    start = ref.clock()
    diag = refinement.diagnostics(detector["full"], row["iq"], row["lane"], short)
    result = ref.amend(short, diag, 1.0, row["tune"])
    return short, diag, result, ref.since(start), primary


def signature(current):
    short, diag, (result, flag) = current[:3]
    return ref.factor_bytes(short), diag_bytes(diag), ref.factor_bytes(result), flag


def operand_count(factor):
    epoch, offset = factor[1:3]
    # The archived geometry uses integer-start arithmetic before adding offset.
    integer = abs(offset-round(offset)) <= 1e-12
    total, frames = 0, 0
    for f in range(15):
        start = epoch + (40_000*f+1)//3
        lo = int(np.floor(start+88+offset)) - (0 if integer else 7)
        hi = int(np.floor(start+88+64*44-1+offset)) + (0 if integer else 8)
        if lo < 0 or hi >= 200_000:
            break
        total += (64*44 if integer else hi-lo+1)
        frames += 1
    return frames, total


def run(work):
    machine = ref.check_machine()
    if work.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs directory")
    work.mkdir()
    before = ref.clock()
    base = BASE
    if not base.is_file():
        ref.verified(SOURCE, SOURCE_PIN)
        base, _ = ref.build(work / "frozen", ref.PAYLOAD / "receiver.so", SOURCE)
    ref.verified(base, BASE_PIN)
    variant, build_receipt = build(work)
    compiled = ref.since(before)
    readers = dict(frozen=RefineEntry(base, "short_cfo_refine"), gather=RefineEntry(variant, "short_cfo_gather"),
                   gather_angles=RefineEntry(variant, "short_cfo_gather_angles"))
    before, blocks = ref.clock(), ref.input_bytes()
    rows, scope = ref.signed_rows("held-0169")
    intake = ref.since(before)
    if ref.input_bytes() != blocks:
        raise ValueError("Held lane intake must stay on tmpfs")
    archive = json.loads(gzip.decompress(ref.verified(EVIDENCE, EVIDENCE_PIN)))
    held = archive["held"] if "held" in archive else archive
    records = held["panels"]["held-0169"]["rows"]
    original = {(r["key"], r["lane"]): r for r in records}

    def asset(edge):
        return np.frombuffer(ref.verified(ref.RELEASE / "assets" / (edge+".f32"), ref.PILOT_SHA[edge]), dtype="<f4")

    with ExitStack() as stack:
        def receiver(data, mode):
            lib = ref.PAYLOAD / "receiver.so" if mode == "full" else ref.ORIGINAL / "short-primary.so"
            path = ref.NativePath(lib, data, mode)
            stack.callback(path.close)
            return path

        before = ref.clock()
        lower = asset("lower")
        paths = {k: dict(full=receiver(lower, "full"), short=receiver(lower, "short_primary")) for k in ARM}
        initialized = ref.since(before)
        paired = []
        ledger = {}
        for order in REPEATS:
            times = {}
            for arm in order:
                total = Counter()
                started = ref.clock()
                outputs = []
                for row in rows:
                    output = conditioned(row, paths[arm], readers[arm])
                    outputs.append(output)
                    total.update(added_cpu_ns=output[3][0], added_wall_ns=output[3][1],
                                 primary_cpu_ns=output[4][0], primary_wall_ns=output[4][1])
                outer = ref.since(started)
                times[arm] = dict(total, outer_cpu_ns=outer[0], outer_wall_ns=outer[1])
                for row, output in zip(rows, outputs, strict=True):
                    key = row["key"], row["lane"]
                    vector = signature(output)
                    if row["mode"] == "full":
                        if ref.factor_bytes(output[2][0]) != ref.factor_bytes(row["short"]):
                            raise ValueError("A scheduled signed full anchor changed")
                    else:
                        expected = original[key]
                        factor, flag = expected["choices"]["1.0"]
                        if vector != (ref.factor_bytes(row["short"]), diag_bytes(expected["diagnostics"]),
                                      ref.factor_bytes(factor), flag):
                            raise ValueError("The refined diagnostics, signed tuple or gate differs from the freeze")
                    prior = ledger.setdefault(key, vector)
                    if vector != prior:
                        raise ValueError("Work order changed native result bytes")
            paired.append(dict(order=order, arms=times))

        stages, profiled = Counter(), []
        for row in rows:
            if row["mode"] != "short_primary" or not row["short"]:
                continue
            factor, = row["short"]
            status, values, costs, clocks = profile(paths["frozen"]["full"], readers["gather"].library,
                                                    row["iq"], row["lane"], factor)
            if status or diag_bytes(values) != ledger[(row["key"], row["lane"])][1]:
                raise ValueError("The stage profiler changed the frozen native outputs")
            stages.update(costs)
            frames, gathered = operand_count(factor)
            profiled.append(dict(visit=row["key"], lane=row["lane"], signed_hz=factor[3], frames=frames,
                                 converted_samples=gathered, parts=costs, elapsed=clocks))

        # Both pilot edges and signed polarities, exact and near-integer aperture boundaries.
        rng = np.random.default_rng(653)
        iq = rng.integers(-32760, 32760, (200_000, 2, 2), dtype=np.int16)
        controls = []
        for edge, path in (("lower", paths["frozen"]["full"]), ("upper", receiver(asset("upper"), "full"))):
            for lane, offset in enumerate((0., 0.375, -0.9999999999995, -1.5, 1.5, 9.999e-12)):
                factor = (0, (13_332 if lane % 2 else 0), offset, (415_000. if lane % 2 else -360_125.), 0.3, 0.1)
                outputs = [readers[arm].diagnostics(path, iq, lane % 2, (factor,)) for arm in ARM]
                if any(d is None or diag_bytes(d) != diag_bytes(outputs[0]) for d in outputs):
                    raise ValueError("A signed/integer/fractional native boundary changed")
                controls.append(dict(edge=edge, lane=lane % 2, factor=factor, diagnostics=outputs[0]))
    build_receipt["frozen_library_sha256"] = BASE_PIN
    ref.save(work / "receipt.json", dict(machine=machine, build=build_receipt, compiled_ns=compiled, intake_ns=intake,
             initial_contexts_ns=initialized, scope=scope, reference_sha256=sha256(EVIDENCE.read_bytes()).hexdigest(),
             signed_lanes=len(rows), controls=controls, paired=paired, profile_total_cpu_ns=stages,
             profiled=profiled, exact_gate=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)
