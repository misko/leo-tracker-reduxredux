"""External screen: reuse root LU, keeping vector and matrix solves separate."""

import argparse
import hashlib
import inspect
import json
import time
from pathlib import Path

import algo07v3_hierarchical_oracle as hierarchical
import numpy as np
from scipy.linalg.lapack import dgetrf, dgetrs


def solve_factor(lu, pivots, rhs):
    result, info = dgetrs(lu, pivots, rhs)
    if info != 0:
        raise np.linalg.LinAlgError(f"DGETRS failed: {info}")
    return result


def candidate_function():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    mean = "mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs))"
    inverse = "inv_root = np.linalg.solve(root, identity)"
    if source.count(mean) != 1 or source.count(inverse) != 1:
        raise ValueError("Unexpected reference implementation")
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
    namespace = dict(vars(hierarchical), dgetrf=dgetrf, solve_factor=solve_factor)
    exec(compile(code, "<separate-rhs-factor-reuse>", "exec"), namespace)
    return namespace["hierarchical_bound"], source, code


def run(args):
    from probe_algo07v3_assembly import exact_result

    candidate, source, code = candidate_function()
    raw_manifest = (args.fixture / "capture.json").read_bytes()
    manifest = json.loads(raw_manifest)
    rows = []
    for item in manifest["calls"]:
        path = args.fixture / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Captured input changed")
        with np.load(path, allow_pickle=False) as saved:
            inputs = [saved[k] for k in ("raw", "features", "sigma", "groups")]
            kwargs = {k[3:]: saved[k] for k in saved.files if k.startswith("kw_")}
        baseline = hierarchical.hierarchical_bound(*inputs, **kwargs)
        timings = dict(reference=[], factor_reuse=[])
        failures = []
        for side in ("reference", "factor_reuse", "factor_reuse", "reference") * args.repeats:
            function = hierarchical.hierarchical_bound if side == "reference" else candidate
            began = time.perf_counter()
            actual = function(*inputs, **kwargs)
            timings[side].append(time.perf_counter() - began)
            try:
                exact_result(baseline, actual)
            except ValueError as error:
                failures.append(dict(side=side, error=str(error)))
        rows.append(dict(input_sha256=item["sha256"], seconds=timings, failures=failures))
    result = dict(
        exact=all(not row["failures"] for row in rows),
        rows=rows,
        mean_sum_seconds={
            side: sum(sum(row["seconds"][side]) / len(row["seconds"][side]) for row in rows)
            for side in ("reference", "factor_reuse")
        },
        reference_sha256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_sha256=hashlib.sha256(code.encode()).hexdigest(),
        fixture_sha256=hashlib.sha256(raw_manifest).hexdigest(),
        experiment_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope="Eight captured calls; no runtime change or complete-path speed claim",
        enabled_in_runtime=False,
        repeats=args.repeats,
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=10, choices=range(1, 51))
    run(parser.parse_args())
