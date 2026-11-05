"""External exact-call experiment: batch variance reductions of equal shape.

Each group retains the original contiguous multiplication and sum length.
Only independent groups of the same width share a NumPy invocation; ordering
is restored before any precision update. Runtime source remains unchanged.
"""

import argparse
import hashlib
import inspect
import json
import runpy
import sys
import time
from pathlib import Path

import algo07v3_prevariance_hierarchical_oracle as reference_kernel
from probe_algo07v3_factor_reuse import FactorProbe

from leo.analysis.localization_v3 import hierarchical


def candidate_function():
    source = inspect.getsource(reference_kernel.hierarchical_bound)
    setup = "    def posterior(weight, precision, covariance):"
    reduction = (
        "        variance = np.array(\n"
        "            [np.sum(covariance[index] * matrix.T) for _, index, matrix, _ in blocks]\n"
        "        )"
    )
    if source.count(setup) != 1 or source.count(reduction) != 1:
        raise ValueError("Review changed variance calculation before probing")
    code = source.replace(setup, """    by_width = {}
    for k, (columns, index, matrix, _) in enumerate(blocks):
        by_width.setdefault(len(columns), []).append((k, columns, index, matrix.T))
    variance_blocks, variance_individual = [], []
    for block_width, rows in by_width.items():
        if len(rows) > 1 and len(rows) * block_width**2 * 8 <= 1024**2:
            variance_blocks.append((
                np.array([r[0] for r in rows]), np.stack([r[1] for r in rows]),
                np.ascontiguousarray(np.stack([r[3] for r in rows]))))
        else:
            variance_individual.extend((r[0], r[2], r[3]) for r in rows)

""" + setup).replace(reduction, """        variance = np.empty(len(blocks))
        for group_indices, columns, variance_matrices in variance_blocks:
            products = covariance[columns[:, :, None], columns[:, None, :]] * variance_matrices
            variance[group_indices] = np.sum(products, axis=(1, 2))
        for group_index, covariance_index, variance_matrix in variance_individual:
            variance[group_index] = np.sum(covariance[covariance_index] * variance_matrix)""")
    namespace = dict(vars(reference_kernel))
    exec(compile(code, "<equal-width-variance-reductions>", "exec"), namespace)
    return namespace["hierarchical_bound"], source, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("engine_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Fresh receipt required")
    forwarded = args.engine_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Engine arguments required after --")
    candidate, source, code = candidate_function()
    original = reference_kernel.hierarchical_bound
    runtime_function = hierarchical.hierarchical_bound
    probe = FactorProbe(original, candidate)
    hierarchical.hierarchical_bound = probe
    tool = Path(__file__).with_name("check_algo07v3_engine.py")
    old_argv, began, complete = sys.argv, time.perf_counter(), False
    sys.argv = [str(tool), *forwarded]
    try:
        runpy.run_path(str(tool), run_name="__main__")
        complete = True
    finally:
        sys.argv = old_argv
        hierarchical.hierarchical_bound = runtime_function
        result = dict(
            complete=complete, calls=probe.calls, failures=probe.failures,
            exact=complete and probe.calls > 0 and not probe.failures,
            component_seconds=probe.seconds, shapes=probe.shapes,
            process_seconds=time.perf_counter()-began,
            reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
            candidate_sha256=hashlib.sha256(code.encode()).hexdigest(),
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            engine_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
            arguments=forwarded, enabled_in_runtime=False, qualified_speedup=None,
        )
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({k: v for k, v in result.items() if k != "shapes"}), flush=True)


if __name__ == "__main__":
    main()
