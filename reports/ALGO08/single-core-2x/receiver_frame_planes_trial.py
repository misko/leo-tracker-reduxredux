"""Compare exact shared frame planes with the d97b receiver."""

import argparse
import ctypes as ct
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import process_time_ns

import numpy as np

import receiver_mixer_profile_trial as mixer_profile
from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import exports, run
from .receiver_fir_tile_trial import WEAK_SHA, WRAPPED_SHA
from .receiver_refine_parity_trial import austin_windows
from .receiver_resident_cancel_trial import austin, paired
from tools.pipeline_eval.variants.experimental import receiver_frame_planes, receiver_mode_pair_build
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_archive


TIMING_SOURCE = "timing_first_receiver.c"


def build(work, bench, assets):
    wrapped = bench / "receiver-cfo-wrap-fix"
    identity = json.loads((wrapped / "build.json").read_bytes())
    commands = []
    reference = wrapped / "wrapped.so"
    restore.digest(reference, WRAPPED_SHA)
    link = identity["commands"][-1]
    index, = [i for i, part in enumerate(link) if Path(part).name == "timing_first_receiver.o"]
    original = Path(link[index])
    restore.digest(original, identity["original_objects"][original.name])
    old_source = original.with_suffix(".c")
    source = work / TIMING_SOURCE
    source.write_text(receiver_frame_planes.overlay(old_source.read_text()))
    baseline = work / "reference.so"
    commands.append(run([*link[:-1], baseline], cwd=identity["cwd"]))
    restore.digest(baseline, WRAPPED_SHA)
    staged = source.with_suffix(".o")
    link[index] = str(staged)
    profiles = work / "profiles"
    profiles.mkdir()
    flags, _ = restore.compiler_inputs(
        json.loads((restore.PINNED / "build.json").read_bytes()),
        original.parent, bench / "c803-packed-cancel-trial-v2/candidate",
    )
    compiler = link[0]
    for mode in ("generate", "use"):
        output = work / f"{mode}.so"
        feedback = [f"-fprofile-{mode}={profiles}", "-fno-profile-values"]
        if mode == "use":
            feedback += ["-Werror=missing-profile", "-Werror=coverage-mismatch"]
        commands.append(run([
            compiler, *feedback, *flags, "-I", restore.PINNED / "tools/pipeline_eval/variants",
            "-I", restore.HERE, "-c", source, "-o", staged,
        ], cwd=restore.PINNED))
        commands.append(run([compiler, *feedback, *link[1:-1], output], cwd=identity["cwd"]))
        if mode == "generate":
            training = subprocess.run([sys.executable, mixer_profile.__file__, "train", output, assets],
                                      check=True, text=True, stdout=subprocess.PIPE)
    if exports(output) != exports(baseline):
        raise ValueError("The frame layout changed the exported receiver ABI")
    return dict(
        reference_sha256=WRAPPED_SHA, candidate_sha256=restore.digest(output),
        reference_source_sha256=restore.digest(old_source), generated_source_sha256=restore.digest(source),
        frame_planes_sha256=restore.digest(restore.HERE / "receiver_frame_planes.inc"),
        commands=commands, training=json.loads(training.stdout),
    )


def mode_fixture(work):
    native = restore.PINNED / "tools/pipeline_eval/variants" / TIMING_SOURCE
    source = receiver_mode_pair_build.timing(native.read_text())

    def mode_body(text):
        start = text.index("static void principal_modes(")
        return text[start:text.index("/* A constant carrier", start)]

    common = """
#include <complex.h>
#include <math.h>
#include <string.h>
enum { first = 88, count = 14 };
typedef struct { float re, im; } Sample;
typedef struct { int stride, width; Sample *frames, *modes; } TimingFirst;
"""
    fixture = work / "mode_fixture.c"
    # d97b emits covariance_dot separately. Inlining it into this small
    # fixture lets GCC specialize the diagonal to a different reduction.
    pair_kernel = (restore.HERE / "receiver_mode_pair.inc").read_text().replace(
        "static inline Sample covariance_dot",
        "__attribute__((noinline)) static Sample covariance_dot",
    )
    fixture.write_text(common + source[source.index("static Sample multiply("):
                                       source.index("static void *reserve(")]
                       + pair_kernel + '\n#include "receiver_frame_planes.inc"\n'
                       + mode_body(source)
                       + mode_body(receiver_frame_planes.overlay(source)).replace(
                           "principal_modes", "principal_modes_planes", 1,
                       )
                       + """
void exercise_modes(const Sample *low, int stride, int width, Sample *frames, Sample *modes, int packed) {
    TimingFirst w = {stride, width, frames, modes};
    if (packed) principal_modes_planes(&w, low);
    else principal_modes(&w, low);
}
int have_avx2(void) { return __builtin_cpu_supports("avx2"); }
""")
    output = work / "mode_fixture.so"
    run(["cc", "-O3", "-fPIC", "-shared", "-fopenmp-simd", "-ffp-contract=off",
         "-fno-strict-aliasing", "-I", restore.HERE, fixture, "-lm", "-o", output])
    library = ct.CDLL(str(output))
    library.exercise_modes.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int]
    library.exercise_modes.restype = None
    return library


def run_modes(library, samples, stride, width, repeats):
    scratch = [np.empty(28 * width, dtype=np.float32) for _ in range(2)]
    output = [np.empty(4 * width, dtype=np.float32) for _ in range(2)]
    elapsed = []
    for repeat in range(repeats):
        row = [0, 0]
        for arm in (repeat % 2, 1 - repeat % 2):
            begin = process_time_ns()
            library.exercise_modes(samples.ctypes.data, stride, width, scratch[arm].ctypes.data,
                                   output[arm].ctypes.data, arm)
            row[arm] = process_time_ns() - begin
        elapsed.append(row)
    if output[0].tobytes() != output[1].tobytes():
        raise ValueError("The complete ordered mode arrays changed")
    return dict(
        ns=elapsed, median_cpu_ns=[median(col) for col in zip(*elapsed, strict=True)],
        paired_change=median(b / a - 1 for a, b in elapsed), output_sha256=digest(output[0].tobytes()),
    )


def trial(work, bench, assets, weak, archive, source_audit, wide_reference):
    work.mkdir()
    fixture = mode_fixture(work)
    rng = np.random.default_rng(512175)
    low = rng.standard_normal(100_000, dtype=np.float32)
    stage = run_modes(fixture, low, 4, 4740, 60)
    manifest = build(work, bench, assets)
    binaries = work / "reference.so", work / "use.so"
    rows = list(read_archive(weak, 18))
    authority = digest(json.dumps([row["sha256"] for row, _ in rows]).encode())
    if len(rows) != 18 or authority != WEAK_SHA:
        raise ValueError("Expected the pinned saved weak-carrier archive")
    return dict(
        build=manifest, synthetic_modes=stage,
        weak=paired(rows, assets, binaries, repeats=9),
        Austin=austin(list(austin_windows(archive, source_audit, wide_reference)), assets, binaries),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("work", "bench", "assets", "weak", "archive", "source_audit", "wide_reference"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    print(json.dumps(trial(**vars(parser.parse_args())), indent=2, allow_nan=False))
