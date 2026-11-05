"""External exact-call probe for root factorization reuse on the owned kernel.

This changes no installed/runtime source. Every likelihood call executes the
frozen pre-solver implementation and the candidate with alternating order. A scientific
difference aborts the diagnostic instead of becoming an ordinary fit rejection.
"""

import argparse
import hashlib
import inspect
import json
import runpy
import sys
import time
from pathlib import Path

import algo07v3_presolver_hierarchical_oracle as reference_kernel
import numpy as np
from probe_algo07v3_assembly import AssemblyProbe
from scipy.linalg.lapack import dgetrf, dgetrs

from leo.analysis.localization_v3 import hierarchical


def solve_factor(lu, pivots, rhs):
    result, info = dgetrs(lu, pivots, rhs)
    if info:
        raise np.linalg.LinAlgError(f"DGETRS failed: {info}")
    return result


def candidate_function():
    source = inspect.getsource(reference_kernel.hierarchical_bound)
    mean = "mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs))"
    inverse = "inv_root = np.linalg.solve(root, identity)"
    if source.count(mean) != 1 or source.count(inverse) != 1:
        raise ValueError("Unexpected owned kernel; review the candidate explicitly")
    code = source.replace(
        mean,
        "lu, pivots, info = dgetrf(root) if width else (root, None, 0)\n"
        "        if info != 0:\n"
        "            raise np.linalg.LinAlgError('DGETRF failed')\n"
        "        mean = np.linalg.solve(root.T, solve_factor(lu, pivots, rhs)) "
        "if width else rhs.copy()",
    ).replace(
        inverse, "inv_root = solve_factor(lu, pivots, identity) if width else identity.copy()"
    )
    namespace = dict(vars(reference_kernel), dgetrf=dgetrf, solve_factor=solve_factor)
    exec(compile(code, "<owned-kernel-factor-reuse>", "exec"), namespace)
    return namespace["hierarchical_bound"], source, code


class FactorMismatch(BaseException):
    """A probe mismatch must not be caught as a scientific rejection."""


class FactorProbe(AssemblyProbe):
    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except ValueError as error:
            if self.failures:
                raise FactorMismatch(str(error)) from error
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("engine_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Fresh output receipt required")
    forwarded = args.engine_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Native qualification arguments required after --")
    candidate, old_source, new_source = candidate_function()
    original = reference_kernel.hierarchical_bound
    runtime_function = hierarchical.hierarchical_bound
    probe = FactorProbe(original, candidate)
    hierarchical.hierarchical_bound = probe
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    original_argv = sys.argv
    sys.argv = [str(tool), *forwarded]
    began = time.perf_counter()
    complete = False
    try:
        runpy.run_path(str(tool), run_name="__main__")
        complete = True
    finally:
        sys.argv = original_argv
        hierarchical.hierarchical_bound = runtime_function
        result = dict(
            complete=complete,
            calls=probe.calls,
            failures=probe.failures,
            exact=complete and probe.calls > 0 and not probe.failures,
            shapes=probe.shapes,
            component_seconds=probe.seconds,
            process_seconds=time.perf_counter() - began,
            reference_sha256=hashlib.sha256(old_source.encode()).hexdigest(),
            candidate_sha256=hashlib.sha256(new_source.encode()).hexdigest(),
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
            arguments=forwarded,
            enabled_in_runtime=False,
            qualified_speedup=None,
        )
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
