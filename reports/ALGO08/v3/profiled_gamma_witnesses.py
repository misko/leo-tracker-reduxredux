"""Compare a Gamma overlay on previously captured native likelihood inputs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import process_time_ns

import numpy as np

from leo.analysis.localization_v4.native_bound import NativeBound
from tools.pipeline_eval.variants.algo08_profiled_gamma import operations


INPUTS = ("raw", "features", "sigma", "groups")


def compare(stock_library, variant_library, captures):
    wrap, counts = operations(variant_library)
    stock, candidate = NativeBound(stock_library), wrap(NativeBound(stock_library))
    result = {}
    try:
        for capture in captures:
            samples = json.loads((capture / "capture.json").read_bytes())["samples"]
            for name, meta in samples.items():
                path = capture / name
                with np.load(path) as data:
                    args = [data[key] for key in INPUTS]
                    options = {key: data[key].item() if not data[key].ndim else data[key]
                               for key in data.files if key not in INPUTS}
                medians = [[], []]
                before = counts()
                for _ in range(5):
                    start = process_time_ns()
                    baseline = stock(*args, **options)
                    medians[0].append(process_time_ns() - start)
                    start = process_time_ns()
                    variant = candidate(*args, **options)
                    medians[1].append(process_time_ns() - start)
                result[str(Path(capture.name) / name)] = dict(
                    input=meta, sha256=sha256(path.read_bytes()).hexdigest(), shape=list(args[1].shape),
                    stock_cpu_ns=median(medians[0]), profiled_cpu_ns=median(medians[1]),
                    updates=[item["precision_iterations"] for item in (baseline, variant)],
                    final_change=[item["final_log_precision_change"] for item in (baseline, variant)],
                    elbo_delta=variant["negative_twice_elbo"] - baseline["negative_twice_elbo"],
                    residual_max_hz=float(np.max(np.abs(
                        baseline["conditional_residual_hz"] - variant["conditional_residual_hz"]))),
                    five_call_counters={key: value - before[key] for key, value in counts().items()},
                )
    finally:
        stock.clear()
        candidate.clear()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_library", type=Path)
    parser.add_argument("variant_library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("captures", type=Path, nargs="+")
    args = parser.parse_args()
    result = compare(args.stock_library, args.variant_library, args.captures)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
