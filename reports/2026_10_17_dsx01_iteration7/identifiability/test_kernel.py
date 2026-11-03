import importlib.util
from pathlib import Path

import numpy as np
import pytest
from numpy.testing import assert_allclose

SPEC = importlib.util.spec_from_file_location(
    "information_kernel", Path(__file__).with_name("kernel.py")
)
kernel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kernel)


def test_block_statistics_equal_explicit_small_design_and_projection():
    rng = np.random.default_rng(181)
    n, k, d = 7, 3, 4
    s, t, c = rng.normal(size=(n, k, 2)), rng.normal(size=(n, k)), rng.normal(size=(n, d))
    w = rng.random((n, k))
    blocks = kernel.gram_blocks(s, t, c, w)
    timing = np.zeros((n, k, k))
    for j in range(k):
        timing[:, j, j] = t[:, j]
    nuisance = np.concatenate((np.broadcast_to(c[:, None, :], (n, k, d)), timing), axis=2).reshape(
        n * k, d + k
    )
    root = np.sqrt(w.ravel())
    a = s.reshape(n * k, 2) * root[:, None]
    z = nuisance * root[:, None]
    projected = a - z @ np.linalg.lstsq(z, a, rcond=1e-12)[0]
    actual = kernel.compare(blocks, np.zeros((d, d)))
    assert_allclose(blocks["spatial"], a.T @ a, atol=1e-12)
    assert_allclose(
        actual["after_calibration_and_timing"]["information_hz_gaussian_per_km2"],
        projected.T @ projected,
        atol=1e-11,
    )


def test_column_unit_scaling_and_redundant_gauge_preserve_span():
    rng = np.random.default_rng(9)
    z = rng.normal(size=(20, 3))
    a = rng.normal(size=(20, 2))
    raw = a.T @ a
    expected = kernel.schur(raw, a.T @ z, z.T @ z)["information"]
    z = np.column_stack((z[:, 0] * 1e9, z[:, 1] * 1e-8, z[:, 2], z[:, 0] * 7))
    actual = kernel.schur(raw, a.T @ z, z.T @ z)
    assert actual["nuisance_rank"] == 3
    assert_allclose(expected, actual["information"], atol=1e-10)


def test_ridge_psd_and_no_double_counting_timing_mean_prior():
    rng = np.random.default_rng(4)
    z = rng.normal(size=(15, 4))
    a = rng.normal(size=(15, 2))
    raw = a.T @ a
    ordinary = kernel.schur(raw, a.T @ z, z.T @ z)["information"]
    ridge = kernel.schur(raw, a.T @ z, z.T @ z, precision=np.eye(4))["information"]
    assert np.linalg.eigvalsh(ridge - ordinary).min() > -1e-10
    assert np.linalg.eigvalsh(raw - ridge).min() > -1e-10
    tau = np.array([1.0, 2.0, -3.0, 7.0])
    q = kernel.total_timing_precision(4)
    expected = np.sum((tau - tau.mean()) ** 2) / 4 + tau.mean() ** 2 / 9
    assert_allclose(tau @ q @ tau, expected, atol=1e-12)
    assert_allclose(np.ones(4) @ q @ np.ones(4), 1 / 9, atol=1e-12)


def test_data_dimensions_and_zero_weight_do_not_invent_information():
    s = np.ones((4, 3, 2))
    t = np.ones((4, 3))
    c = np.ones((4, 2))
    w = np.zeros((4, 3))
    blocks = kernel.gram_blocks(s, t, c, w)
    result = kernel.compare(blocks, np.zeros((2, 2)))
    assert_allclose(result["after_calibration_and_timing"]["information_hz_gaussian_per_km2"], 0.0)
    with pytest.raises(ValueError):
        kernel.gram_blocks(s, t, c[:-1], w)
    with pytest.raises(ValueError):
        kernel.gram_blocks(s, t, c, -np.ones_like(w))
