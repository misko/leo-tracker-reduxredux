"""Compare the predeclared precision iteration on existing captured kernels."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import process_time_ns

import numpy as np

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_anderson import accelerated, build

from .dense_likelihood_kernel_trial import witnesses

EXACT = ("normalization_constant", "effective_observations")
ABSOLUTE = dict(
    negative_twice_elbo=1e-5, quadratic=1e-5, logvolume=1e-5, noise_gamma_cost=1e-5,
    prior_gamma_cost=1e-5, gamma_cost=1e-5, conditional_residual_hz=1e-3, residual=1e-5,
)
SCALED = ("coefficient", "noise_precision", "coefficient_prior_precision", "prior_group_precision")


def compare(stock, variant):
    if stock.keys() != variant.keys():
        raise ValueError("Mismatched likelihood result fields")
    differences, gates = {}, {}
    for key, value in stock.items():
        first, second = np.asarray(value), np.asarray(variant[key])
        if (first.shape != second.shape
                or not np.isfinite(first).all() or not np.isfinite(second).all()):
            raise ValueError(f"Mismatched or nonfinite likelihood field {key}")
        difference = abs(second - first)
        if key in SCALED:
            difference = difference / np.maximum(1., abs(first))
        maximum = float(np.max(difference, initial=0.))
        differences[key] = maximum
        if key in EXACT:
            gates[key] = first.tobytes() == second.tobytes()
        elif key in ABSOLUTE:
            gates[key] = maximum <= ABSOLUTE[key]
        elif key in SCALED:
            gates[key] = maximum <= 1e-5
    return differences, gates


def measure(owner, args, options):
    before = owner.counts["activated"]
    start = process_time_ns()
    result = owner(*args, **options)
    return result, process_time_ns() - start, owner.counts["activated"] > before


def run(stock_library, library, captures):
    build(library)
    rows = {}
    for name, meta, args, options in witnesses(captures):
        owner = native_bound.NativeBound(stock_library)

        try:
            stock, _, stock_native = measure(owner, args, options)
            with accelerated(owner, library) as diagnostic:
                variant, _, variant_native = measure(owner, args, options)
            baseline_times, accelerated_times = [], []
            for _ in range(5):
                baseline_times.append(measure(owner, args, options)[1])
                with accelerated(owner, library):
                    accelerated_times.append(measure(owner, args, options)[1])
            differences, gates = compare(stock, variant)
            gates["same_native_outcome"] = stock_native == variant_native
            control_cpu, variant_cpu = median(baseline_times), median(accelerated_times)
            if (name.startswith("dense-likelihood-capture-0008/")
                    and meta["caller"] == "position" and stock_native):
                gates["dense_native_cpu"] = variant_cpu <= 0.65 * control_cpu
            if name.startswith("dense-likelihood-capture-south/") and stock_native:
                gates["southern_native_cpu"] = variant_cpu <= 1.15 * control_cpu
            rows[name] = dict(
                input=meta, shape=list(args[1].shape),
                stock_cpu_ns=control_cpu, accelerated_cpu_ns=variant_cpu,
                updates=[stock["precision_iterations"], variant["precision_iterations"]],
                final_log_precision_change=[stock["final_log_precision_change"],
                                            variant["final_log_precision_change"]],
                difference=differences, gates=gates, acceleration=dict(diagnostic),
            )
        finally:
            owner.clear()
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_library", type=Path)
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("captures", nargs="+", type=Path)
    args = parser.parse_args()
    result = run(args.stock_library, args.library, args.captures)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
