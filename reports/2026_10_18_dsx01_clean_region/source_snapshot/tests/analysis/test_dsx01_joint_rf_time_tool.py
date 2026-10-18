"""RF contrast rates are per receiver, native Hz/s/GHz and zero at scan midpoint."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_joint_rf_time")
    finally:
        sys.path.pop(0)


def test_RF_and_time_coordinates_have_native_units_and_no_receiver_crosstalk(tool):
    centres = {(1, 0): 11e9, (1, 1): 12e9, (2, 0): 11e9, (2, 1): 12e9}
    result = tool.rf_time_columns(
        [100, 200, 150, 250],
        [1, 1, 2, 2],
        [0, 1, 0, 1],
        [10.75e9, 12.25e9, 11.25e9, 11.75e9],
        centres,
        2,
    )
    np.testing.assert_array_equal(result, [[25, 0], [25, 0], [0, 0], [0, -50]])
