"""External exactness screen for sharing the posterior root solve.

This changes no runtime code. Combining right-hand sides is mathematically valid
but must pass exact outputs before it could be considered for the owned engine.
"""

import argparse
import hashlib
import inspect
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3 import hierarchical


def run(fixture):
    original = inspect.getsource(hierarchical.hierarchical_bound)
    old_mean = "mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs))"
    old_inverse = "inv_root = np.linalg.solve(root, identity)"
    assert original.count(old_mean) == original.count(old_inverse) == 1
    code = original.replace(
        old_mean,
        "solved = np.linalg.solve(root, np.column_stack((rhs, identity))) if covariance else None\n"
        "        mean = np.linalg.solve(root.T, solved[:, 0] if covariance "
        "else np.linalg.solve(root, rhs))",
    ).replace(old_inverse, "inv_root = solved[:, 1:]")
    namespace = dict(vars(hierarchical))
    exec(compile(code, "<combined-rhs-experiment>", "exec"), namespace)
    candidate = namespace["hierarchical_bound"]
    manifest = json.loads((fixture / "capture.json").read_bytes())
    rows = []
    for item in manifest["calls"]:
        path = fixture / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        with np.load(path, allow_pickle=False) as saved:
            args = [saved[k] for k in ("raw", "features", "sigma", "groups")]
            kwargs = {k[3:]: saved[k] for k in saved.files if k.startswith("kw_")}
        times = {"reference": [], "combined": []}
        values = {}
        for side in ("reference", "combined", "combined", "reference"):
            start = time.perf_counter()
            values[side] = (hierarchical.hierarchical_bound if side == "reference" else candidate)(
                *args, **kwargs
            )
            times[side].append(time.perf_counter() - start)
        differences = []
        for key, expected in values["reference"].items():
            result = values["combined"][key]
            if not np.array_equal(expected, result):
                differences.append(
                    dict(
                        field=key,
                        maximum_delta=float(
                            np.max(np.abs(np.asarray(expected) - np.asarray(result)))
                        ),
                    )
                )
        rows.append(
            dict(
                input_sha256=item["sha256"],
                shape=list(args[1].shape),
                exact=not differences,
                differences=differences,
                seconds=times,
            )
        )
    return dict(
        scope="component exactness screen; not full optimization or position accuracy",
        source_sha256=hashlib.sha256(original.encode()).hexdigest(),
        experiment_sha256=hashlib.sha256(code.encode()).hexdigest(),
        fixture_sha256=hashlib.sha256((fixture / "capture.json").read_bytes()).hexdigest(),
        order=["reference", "combined", "combined", "reference"],
        exact=all(row["exact"] for row in rows),
        rows=rows,
        enabled_in_runtime=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.fixture)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(exact=result["exact"], calls=len(result["rows"]))))
