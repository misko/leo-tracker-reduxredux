"""Compare the likelihood kernel or replay one frozen ALGO08v3 saved solve."""

import argparse
import ctypes
import json
import runpy
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import process_time_ns
from unittest.mock import patch


def kernel(stock_binary, candidate_binary, captures):
    from leo.analysis.localization_v4 import native_bound

    helpers = runpy.run_path(str(Path(__file__).with_name("dense_likelihood_kernel_trial.py")))
    results = {}
    library = ctypes.CDLL(str(candidate_binary))
    for name, witness, args, options in helpers["witnesses"](captures):
        control = native_bound.NativeBound(stock_binary)
        candidate = native_bound.NativeBound(stock_binary)
        operation = library.nb_run
        operation.argtypes, operation.restype = control.run.argtypes, control.run.restype
        candidate.run = operation
        timings = ([], [])
        try:
            expected, actual = (port(*args, **options) for port in (control, candidate))
            if not helpers["equal"](expected, actual) or control.counts != candidate.counts:
                raise ValueError(f"Native likelihood changed on {name}")
            for repetition in range(12):
                for side in (repetition % 2, 1 - repetition % 2):
                    port = (control, candidate)[side]
                    start = process_time_ns()
                    port(*args, **options)
                    timings[side].append(process_time_ns() - start)
            results[name] = dict(
                witness=witness, precision_iterations=actual["precision_iterations"],
                control_cpu_ns=median(timings[0]), candidate_cpu_ns=median(timings[1]),
                binary64_equal=True,
            )
        finally:
            control.clear()
            candidate.clear()
    return results


def saved(native, spec, archive, offer, output, build):
    from tools.pipeline_eval.variants.experimental import lean_startup

    source = Path(__file__).resolve()
    variant = source.parents[3] / "tools/pipeline_eval/variants/algo08_column_norms.py"
    helpers = runpy.run_path(str(source.with_name("residual_attribution_trial.py")))
    if helpers["read"](spec).get("startup") != "lazy-exports":
        raise ValueError("Expected the frozen ALGO08v3 startup")
    install = lean_startup.install
    with ExitStack() as stack:
        def install_with_overlay():
            install()
            if build is not None:
                column_norms = runpy.run_path(str(variant))["column_norms"]
                stack.enter_context(column_norms(
                    build / "column-norms-bound.so", build / "column-norms-grid.so",
                ))

        stack.enter_context(patch.object(lean_startup, "install", install_with_overlay))
        helpers["worker"](native, spec, archive, offer, output, include_evidence=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(required=True, dest="mode")
    comparison = subparsers.add_parser("kernel")
    for name in ("stock_binary", "candidate_binary", "output"):
        comparison.add_argument(name, type=Path)
    comparison.add_argument("captures", type=Path, nargs="+")
    comparison = subparsers.add_parser("saved")
    for name in ("native", "spec", "archive", "offer", "output"):
        comparison.add_argument(name, type=Path)
    comparison.add_argument("--build", type=Path)
    arguments = vars(parser.parse_args())
    mode = arguments.pop("mode")
    if mode == "kernel":
        output = arguments.pop("output")
        result = kernel(**arguments)
        with output.open("x") as stream:
            print(json.dumps(result, indent=2, allow_nan=False), file=stream)
    else:
        saved(**arguments)
