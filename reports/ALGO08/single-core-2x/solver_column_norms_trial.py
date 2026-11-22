"""Compare the released and contiguous likelihood kernels on saved inputs."""

import argparse
import ctypes
import json
import runpy
from pathlib import Path
from statistics import median
from time import process_time_ns


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock_binary", "candidate_binary", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("captures", type=Path, nargs="+")
    args = parser.parse_args()
    result = kernel(args.stock_binary, args.candidate_binary, args.captures)
    with args.output.open("x") as stream:
        print(json.dumps(result, indent=2, allow_nan=False), file=stream)
