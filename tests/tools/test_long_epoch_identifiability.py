import importlib.util
from pathlib import Path

import numpy as np


def test_profile_matches_dense_schur_complement_and_strengthens_with_ridge():
    path = Path(__file__).parents[2] / "reports/2026_09_23_long_epoch_identifiability/audit.py"
    spec = importlib.util.spec_from_file_location("epoch_info_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = np.random.default_rng(51)
    a = rng.normal(size=(60, 2))
    b = np.zeros((60, 3))
    b[np.arange(60), np.arange(60) % 3] = rng.normal(size=60)
    h = a.T @ a
    groups = {k: {"cross": a.T @ b[:, k], "epoch_curvature": b[:, k] @ b[:, k]} for k in range(3)}
    previous = None
    for ridge in (0, 1, 1000):
        actual = module.profile_information(h, groups, ridge)
        expected = h - a.T @ b @ np.linalg.solve(b.T @ b + ridge * np.eye(3), b.T @ a)
        np.testing.assert_allclose(actual["profiled_position_matrix"], expected, atol=1e-12)
        eigenvalues = np.asarray(actual["directional_fractions_retained"])
        assert np.all(eigenvalues >= -1e-12)
        assert np.all(eigenvalues <= 1 + 1e-12)
        if previous is not None:
            assert np.all(eigenvalues >= previous - 1e-12)
        previous = eigenvalues
