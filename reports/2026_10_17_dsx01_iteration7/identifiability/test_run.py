import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from numpy.testing import assert_allclose

SPEC = importlib.util.spec_from_file_location(
    "identifiability_run", Path(__file__).with_name("run.py")
)
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


def test_actual_clock_scale_recovered_from_full_precision_not_default():
    nodes = np.arange(6, dtype=float)
    gauge = np.stack((np.ones(6), nodes - nodes.mean()))
    null = np.linalg.svd(gauge, full_matrices=True)[2][2:].T
    second = np.diff(np.eye(6), n=2, axis=0) @ null
    precision = np.kron(np.eye(2), np.eye(4) / 200.0**2 + second.T @ second / 100.0**2)
    raw = SimpleNamespace(base=SimpleNamespace(nodes=nodes, null=null, precision=precision))
    actual = run.clock_metadata(raw)
    assert_allclose(actual["inferred_prior_scale"], 4.0)
    assert_allclose(actual["amplitude_sigma_hz"], 200.0)
    assert_allclose(actual["second_difference_sigma_hz"], 100.0)
    assert_allclose(actual["exact_precision"], precision)
