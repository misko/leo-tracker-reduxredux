"""Measure disjoint C work on the captured native likelihood calls."""

import argparse
import ctypes as ct
import json
import subprocess
from pathlib import Path
from statistics import median
from time import process_time_ns

import numpy as np

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_posterior_handoff import SOURCE_SHA256, replace

LOCATIONS = (
    ("group_gram", "    /* Current group Gram/RHS"),
    ("prior_initialization", "    for(int g=0;g<k;g++)rate[g]=alpha[g];"),
    ("assemble", "        int final=(iteration==budget"),
    ("primal_condition_and_schur", "        /* Exact full-Gram 1-norm"),
    ("lapack", "        if(s) {"),
    ("cross_covariance_and_condition", "        /* T=QF"),
    ("mean_and_residual", "        for(int j=0;j<p;j++)if(l->shared[j]>=0)mean[j]"),
    ("variance_and_rate_update", "        if(final)break;"),
    ("finish", "    for(int j=0;j<p;j++)logdet-=log(precision[j]);"),
    ("exit", "done:\n    free(work);return code;"),
)
CLOCK = """
#include <time.h>
#include <stdint.h>
#include <string.h>

static _Thread_local uint64_t phase_ns[{width}];
static inline uint64_t cpu_ns(void) {{
    struct timespec ts;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return (uint64_t)ts.tv_sec*1000000000 + ts.tv_nsec;
}}
static inline void switch_phase(int next, int *phase, uint64_t *since) {{
    uint64_t now=cpu_ns();
    phase_ns[*phase] += now-*since;
    *since=now;
    *phase=next;
}}
void nb_read_profile(uint64_t *output) {{
    memcpy(output,phase_ns,sizeof(phase_ns));
}}
"""


def profile_build(output):
    if native_bound.digest(native_bound.SOURCE) != SOURCE_SHA256:
        raise ValueError("Expected the exact installed likelihood source")
    source = native_bound.SOURCE.read_text()
    source = replace(source, "    Layout *l=pointer;\n    if(!l || !pf",
                     "    memset(phase_ns,0,sizeof(phase_ns));\n"
                     "    int phase=0;uint64_t since=cpu_ns();\n"
                     "    Layout *l=pointer;\n    if(!l || !pf")
    for index, (_, anchor) in enumerate(LOCATIONS, start=1):
        timed = f"    switch_phase({index},&phase,&since);\n"
        if anchor.startswith("done:"):
            occurrence = anchor.replace("done:\n", "done:\n" + timed)
        else:
            occurrence = timed + anchor
        source = replace(source, anchor, occurrence)
    path = output.with_suffix(".c")
    path.write_text(CLOCK.format(width=len(LOCATIONS) + 1) + source)
    subprocess.run(["cc", "-D_POSIX_C_SOURCE=200809L", *native_bound.FLAGS, str(path),
                    "-lm", "-o", str(output)], check=True, timeout=30)


def inputs(path):
    with np.load(path) as data:
        args = [data[k] for k in ("raw", "features", "sigma", "groups")]
        kwargs = {k: data[k].item() if data[k].ndim == 0 else data[k]
                  for k in data.files if k not in ("raw", "features", "sigma", "groups")}
    return args, kwargs


def equal(left, right):
    return left.keys() == right.keys() and all(np.asarray(value).tobytes() ==
                                               np.asarray(right[key]).tobytes()
                                               for key, value in left.items())


def witnesses(captures):
    for capture in captures:
        samples = json.loads((capture / "capture.json").read_bytes())["samples"]
        for name, meta in samples.items():
            args, options = inputs(capture / name)
            yield f"{capture.name}/{name}", meta, args, options


def candidate_trial(stock_library, library, captures):
    from tools.pipeline_eval.variants.algo08_private_width import expand_unsupported_layout

    rows = {}
    for name, meta, args, options in witnesses(captures):
        stock = native_bound.NativeBound(stock_library)
        try:
            expected = stock(*args, **options)
            with expand_unsupported_layout(library) as counts:
                candidate = stock(*args, **options)
                actual_counts = dict(counts)
            before, after = [], []
            for _ in range(5):
                start = process_time_ns()
                stock(*args, **options)
                before.append(process_time_ns() - start)
                with expand_unsupported_layout(library):
                    start = process_time_ns()
                    stock(*args, **options)
                    after.append(process_time_ns() - start)
            rows[name] = dict(
                witness=meta, stock_ns=median(before), candidate_ns=median(after),
                extended_counts=actual_counts, bit_equal=equal(expected, candidate),
                updates=[item["precision_iterations"] for item in (expected, candidate)],
                absolute_deltas={key: float(np.max(np.abs(np.asarray(value) - candidate[key]),
                                                   initial=0.0))
                                 for key, value in expected.items()},
            )
        finally:
            stock.clear()
    return rows


def diagnostic_trial(stock_library, diagnostic_library, captures):
    profile_build(diagnostic_library)
    stock = native_bound.NativeBound(stock_library)
    diagnostic = native_bound.NativeBound(stock_library)
    binary = ct.CDLL(str(diagnostic_library))
    compiled = binary.nb_run
    compiled.argtypes, compiled.restype = stock.run.argtypes, stock.run.restype
    binary.nb_read_profile.argtypes = [ct.POINTER(ct.c_uint64)]
    binary.nb_read_profile.restype = None
    diagnostic.run = compiled
    rows = {}
    for name, meta, args, options in witnesses(captures):
        expected = stock(*args, **options)
        candidate = diagnostic(*args, **options)
        if not equal(expected, candidate):
            raise ValueError("Profiler changed binary64 output")
        baseline, measured, phases = [], [], []
        for _ in range(5):
            start = process_time_ns()
            stock(*args, **options)
            baseline.append(process_time_ns() - start)
            start = process_time_ns()
            diagnostic(*args, **options)
            measured.append(process_time_ns() - start)
            counters = (ct.c_uint64 * (len(LOCATIONS) + 1))()
            binary.nb_read_profile(counters)
            phases.append(counters[:])
        rows[name] = dict(
            input=meta, rows=len(args[0]), columns=args[1].shape[1],
            updates=expected["precision_iterations"], baseline_cpu_ns=median(baseline),
            profiled_cpu_ns=median(measured),
            phase_cpu_ns={key: median(column) for key, column in zip(
                ("setup", *(name for name, _ in LOCATIONS)),
                zip(*phases, strict=True), strict=True,
            )} if meta["outcome"] == "activated" else {},
        )
        stock.clear()
        diagnostic.clear()
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_library", type=Path)
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--wider", action="store_true")
    args = parser.parse_args()
    run = candidate_trial if args.wider else diagnostic_trial
    with args.output.open("x") as stream:
        json.dump(run(args.stock_library, args.library, args.captures), stream, indent=2,
                  sort_keys=True, allow_nan=False)
        stream.write("\n")
