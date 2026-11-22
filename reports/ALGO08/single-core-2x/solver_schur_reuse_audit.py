"""Inspect exact Schur-input reuse along a stock captured likelihood trajectory."""

import argparse
import ctypes as ct
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_posterior_handoff import SOURCE_SHA256, replace

from .dense_likelihood_kernel_trial import equal, inputs

PRIME = 65521


def build(output):
    original = native_bound.SOURCE
    if native_bound.digest(original) != SOURCE_SHA256:
        raise ValueError("Expected the released native likelihood source")
    header = """
typedef void (*observer)(int,int,int,const double*,const double*,const double*,const double*);
static _Thread_local observer observe;
void nb_observe(observer callback) { observe=callback; }
"""
    source = replace(original.read_text(), "/* All work belongs", header + "\n/* All work belongs")
    marker = "        /* T=QF, with F supported only on each group's shared columns. */"
    source = replace(source, marker,
                     "        if(observe)observe(s,k,p,a,root,weight,precision);\n" + marker)
    generated = output.with_suffix(".c")
    with generated.open("x") as stream:
        stream.write(source)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                    str(generated), "-lm", "-o", str(output)], check=True, timeout=30)


def residues(array):
    """Reduce exact binary64 values in the prime field, including subnormals."""
    bits = np.ascontiguousarray(array, dtype=np.float64).view(np.uint64)
    exponent = ((bits >> 52) & 0x7ff).astype(np.int64)
    if np.any(exponent == 0x7ff):
        raise ValueError("The exact rank audit requires finite binary64 values")
    mantissa = (bits & ((1 << 52) - 1)) + np.where(exponent > 0, 1 << 52, 0).astype(np.uint64)
    # At exponent bits 0 and 1 the unit for the integer significand is 2^-1074.
    powers = np.array([pow(2, max(1, e) - 1075, PRIME) for e in range(2047)], dtype=np.int64)
    reduced = ((mantissa % PRIME).astype(np.int64) * powers[exponent]) % PRIME
    return np.where(bits >> 63, -reduced, reduced)


def rank_mod(matrix):
    """Return a lower bound on rational rank, exact when the matrix is full rank."""
    work = matrix.copy() % PRIME
    rank = 0
    for column in range(work.shape[1]):
        pivot_rows = np.flatnonzero(work[rank:, column])
        if len(pivot_rows) == 0:
            continue
        chosen = rank + pivot_rows[0]
        work[[rank, chosen]] = work[[chosen, rank]]
        inverse = pow(int(work[rank, column]), -1, PRIME)
        scale = work[rank + 1:, column] * inverse % PRIME
        tail = work[rank + 1:, column + 1:]
        tail[:] = (tail - scale[:, None] * work[rank, column + 1:]) % PRIME
        rank += 1
        if rank == len(work):
            break
    return rank


def unchanged_prefix(first, second):
    size = len(first)
    different = np.tril(first.view(np.uint64) != second.view(np.uint64))
    changed_rows = np.flatnonzero(different.any(axis=1))
    return int(changed_rows[0]) if len(changed_rows) else size


def summarize(trace, features, groups, powers):
    s = len(trace[0][0])
    lower = np.tril_indices(s)
    support = np.array([np.any(features[groups == group] != 0, axis=0)
                        for group in np.unique(groups)])
    shared = support.sum(axis=0) > 1
    private = support.sum(axis=0) == 1
    if shared.sum() != s:
        raise ValueError("Reconstructed support does not match the native shared block")

    whole_matrices, factored_inputs, factors = set(), set(), set()
    stats = Counter()
    ranges = {}
    last = None

    def record(name, value):
        stats[name] += int(value)
        lo, hi = ranges.get(name, (value, value))
        ranges[name] = int(min(lo, value)), int(max(hi, value))

    for matrix, factor, weight, precision in trace:
        for key, value, seen in (
            ("exact_full_schur_repeats", matrix, whole_matrices),
            ("exact_factor_input_repeats", matrix[lower], factored_inputs),
            ("exact_factor_repeats", factor[lower], factors),
        ):
            body = value.tobytes()
            stats[key] += body in seen
            seen.add(body)
        symmetric = np.tril(matrix) + np.tril(matrix, k=-1).T
        field = residues(symmetric)
        weighted = weight * powers
        if last is not None:
            old, old_symmetric, old_field, old_weight, old_precision = last
            changed_weights = weighted.view(np.uint64) != old_weight.view(np.uint64)
            changed_priors = precision.view(np.uint64) != old_precision.view(np.uint64)
            changed_groups = changed_weights | np.any(support[:, private & changed_priors], axis=1)
            touched = np.any(support[changed_groups][:, shared], axis=0) | changed_priors[shared]
            rank = rank_mod(field - old_field)
            record("changed_noise_group_precisions", changed_weights.sum())
            record("changed_prior_precisions", changed_priors.sum())
            record("shared_columns_touched", touched.sum())
            record("exact_changed_symmetric_rows",
                   np.count_nonzero(np.any(symmetric != old_symmetric, axis=1)))
            record("unchanged_leading_factor_input_width", unchanged_prefix(old, matrix))
            record("binary64_matrix_update_rank_lower_bound", rank)
            stats["certified_full_rank_updates"] += rank == s
        last = matrix, symmetric, field, weighted, precision
    return dict(shared_columns=s, observation_groups=len(trace[0][2]), factorizations=len(trace),
                counts=dict(stats), per_transition_ranges=ranges,
                rank_certificate_prime=PRIME)


def inspect(stock_library, audit_library, path):
    args, options = inputs(path)
    bound = native_bound.NativeBound(stock_library)
    reference = bound.run
    library = ct.CDLL(str(audit_library))
    audited = library.nb_run
    audited.argtypes, audited.restype = reference.argtypes, reference.restype
    double = ct.POINTER(ct.c_double)
    callback_type = ct.CFUNCTYPE(None, ct.c_int, ct.c_int, ct.c_int, double, double, double, double)
    library.nb_observe.argtypes, library.nb_observe.restype = [callback_type], None
    trace = []

    @callback_type
    def collect(s, k, p, matrix, factor, weights, precision):
        square = [np.ctypeslib.as_array(pointer, shape=(s*s,)).copy().reshape((s, s), order="F")
                  for pointer in (matrix, factor)]
        vectors = [np.ctypeslib.as_array(pointer, shape=(length,)).copy()
                   for pointer, length in ((weights, k), (precision, p))]
        trace.append((*square, *vectors))

    try:
        baseline = bound(*args, **options)
        if bound.counts["activated"] != 1:
            raise ValueError("Expected a supported reference kernel")
        library.nb_observe(collect)
        bound.run = audited
        result = bound(*args, **options)
        if not equal(baseline, result) or len(trace) != result["precision_iterations"] + 1:
            raise ValueError("Unexpected reference trace or changed likelihood fields")
        support = summarize(trace, args[1], args[3], options.get("powers", 1.))
        return dict(input_sha256=native_bound.digest(path), exact_likelihood_parity=True,
                    updates=result["precision_iterations"], **support)
    finally:
        library.nb_observe(callback_type())
        bound.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_library", type=Path)
    parser.add_argument("audit_library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("witnesses", type=Path, nargs="+")
    args = parser.parse_args()
    build(args.audit_library)
    result = {path.parent.name: inspect(args.stock_library, args.audit_library, path)
              for path in args.witnesses}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
