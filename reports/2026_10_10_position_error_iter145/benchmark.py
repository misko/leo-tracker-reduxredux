"""Bounded synthetic timing comparison against the published scalar prototype."""

import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
from pair_likelihood import paired_likelihood

from leo.analysis.hard60_score import likelihood
from leo.application.hard60_runner import HARD60_SCORE

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("Single-thread benchmark required")
    original = subprocess.check_output(
        ["git", "show", "e79c71393:reports/2026_10_10_position_error_iter145/pair_likelihood.py"],
        cwd=ROOT,
    )
    namespace = {}
    exec(compile(original, "published145_scalar", "exec"), namespace)
    rng = np.random.default_rng(145)
    n, k = 3500, 30
    measured = rng.normal(0, 125, n)
    prediction = rng.normal(0, 500, (n, k))
    visible = np.ones((n, k), bool)
    pairs = np.arange(n).reshape(-1, 2)
    outputs, timings = {}, {}
    for name, function in (
        ("ordinary", likelihood),
        ("published_scalar", namespace["paired_likelihood"]),
        ("batched", paired_likelihood),
    ):
        args = (measured, prediction, visible, HARD60_SCORE)
        if name != "ordinary":
            args += (pairs,)
        function(*args)
        elapsed = []
        for _ in range(5):
            begun = time.perf_counter()
            outputs[name] = function(*args)
            elapsed.append(time.perf_counter() - begun)
        timings[name] = dict(seconds=elapsed, median_s=float(np.median(elapsed)))
    a, b = outputs["published_scalar"], outputs["batched"]
    np.testing.assert_allclose(a.nll, b.nll, atol=1e-8, rtol=0)
    for key in ("responsibilities", "clutter_probability", "prediction_gradient", "residual_hz"):
        np.testing.assert_allclose(getattr(a, key), getattr(b, key), atol=1e-14, rtol=1e-13)
    result = dict(
        scope="Synthetic emission kernel only; not end-to-end optimizer or embedded timing",
        rows=n,
        candidates=k,
        pairs=len(pairs),
        seed=145,
        repeats=5,
        python=platform.python_version(),
        numpy=np.__version__,
        scalar_source_sha256=hashlib.sha256(original).hexdigest(),
        batched_source_sha256=hashlib.sha256(
            (HERE / "pair_likelihood.py").read_bytes()
        ).hexdigest(),
        objective_difference=float(b.nll - a.nll),
        timings=timings,
    )
    (HERE / "synthetic_timing.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
