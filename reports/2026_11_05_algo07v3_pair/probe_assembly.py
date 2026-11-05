"""Screen exact scatter assembly of the existing posterior normal equations.

External experiment only. No solver, stopping rule, reduction order per matrix
entry or runtime implementation is changed. The native engine does not import it.
"""

import argparse
import hashlib
import inspect
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3 import hierarchical


def candidate_function():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    anchor = "    def posterior(weight, precision, covariance):"
    old = (
        "        for w, (cols, index, matrix, b) in zip(power * weight, blocks, strict=True):\n"
        "            gram[index] += w * matrix\n"
        "            rhs[cols] += w * b"
    )
    setup = (
        "    matrix_indices = np.concatenate([(c[:, None] * width + c).ravel() "
        "for c, _, _, _ in blocks])\n"
        "    matrix_groups = np.concatenate([np.full(m.size, k, dtype=int) "
        "for k, (_, _, m, _) in enumerate(blocks)])\n"
        "    matrices = np.concatenate([m.ravel() for _, _, m, _ in blocks])\n"
        "    rhs_indices = np.concatenate([c for c, _, _, _ in blocks])\n"
        "    rhs_groups = np.concatenate([np.full(len(c), k, dtype=int) "
        "for k, (c, _, _, _) in enumerate(blocks)])\n"
        "    right_sides = np.concatenate([b for _, _, _, b in blocks])\n\n"
    )
    new = (
        "        block_weight = power * weight\n"
        "        np.add.at(gram.ravel(), matrix_indices, block_weight[matrix_groups] * matrices)\n"
        "        np.add.at(rhs, rhs_indices, block_weight[rhs_groups] * right_sides)"
    )
    if source.count(anchor) != 1 or source.count(old) != 1:
        raise ValueError("Unexpected reference source")
    code = source.replace(anchor, setup + anchor).replace(old, new)
    namespace = dict(vars(hierarchical))
    exec(compile(code, "<scatter-assembly-experiment>", "exec"), namespace)
    return namespace["hierarchical_bound"], source, code


def measure(args):
    candidate, reference_code, candidate_code = candidate_function()
    manifest = json.loads((args.fixture / "capture.json").read_bytes())
    rows = []
    for item in manifest["calls"]:
        path = args.fixture / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Captured inputs changed")
        with np.load(path, allow_pickle=False) as saved:
            inputs = [saved[k] for k in ("raw", "features", "sigma", "groups")]
            kwargs = {k[3:]: saved[k] for k in saved.files if k.startswith("kw_")}
        expected = hierarchical.hierarchical_bound(*inputs, **kwargs)
        elapsed = {"reference": [], "scatter": []}
        differences = []
        for side in ("reference", "scatter", "scatter", "reference"):
            started = time.perf_counter()
            value = (candidate if side == "scatter" else hierarchical.hierarchical_bound)(
                *inputs, **kwargs
            )
            elapsed[side].append(time.perf_counter() - started)
            for key in expected:
                a, b = np.asarray(expected[key]), np.asarray(value[key])
                if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
                    differences.append(
                        dict(side=side, field=key, maximum_delta=float(np.max(abs(a - b))))
                    )
        rows.append(
            dict(
                input_sha256=item["sha256"],
                shape=list(inputs[1].shape),
                exact=not differences,
                differences=differences,
                seconds=elapsed,
            )
        )
    result = dict(
        scope="eight captured likelihood calls; not full localization or a runtime change",
        reference_sha256=hashlib.sha256(reference_code.encode()).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate_code.encode()).hexdigest(),
        fixture_sha256=hashlib.sha256((args.fixture / "capture.json").read_bytes()).hexdigest(),
        order=["reference", "scatter", "scatter", "reference"],
        rows=rows,
        exact=all(row["exact"] for row in rows),
        enabled_in_runtime=False,
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            dict(
                exact=result["exact"],
                calls=len(rows),
                mean_sum_seconds={
                    side: sum(sum(row["seconds"][side]) / 2 for row in rows)
                    for side in ("reference", "scatter")
                },
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    measure(parser.parse_args())
