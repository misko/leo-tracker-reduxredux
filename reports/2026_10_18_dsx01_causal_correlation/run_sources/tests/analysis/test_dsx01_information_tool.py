import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("audit_dsx01_position_information")
    finally:
        sys.path.remove(path)


def test_free_nuisance_can_remove_one_position_direction_and_prior_restores_it(tool):
    position = np.eye(2)
    nuisance = np.array([[1.0], [0.0]])
    unanchored = tool.information(position, nuisance)
    assert unanchored["information_eigenvalues_per_km2"][0] == pytest.approx(0)
    anchored = tool.information(
        np.vstack([position, np.zeros((1, 2))]), np.vstack([nuisance, [[1.0]]])
    )
    np.testing.assert_allclose(anchored["information_eigenvalues_per_km2"], [0.5, 1])
    np.testing.assert_allclose(anchored["conditional_axis_scales_km"], [np.sqrt(2), 1])
