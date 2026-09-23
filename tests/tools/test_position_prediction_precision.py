import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/audit_position_prediction_precision.py"
SPEC = importlib.util.spec_from_file_location("prediction_precision_subject", PATH)
assert SPEC.loader is not None
SUBJECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUBJECT
SPEC.loader.exec_module(SUBJECT)


def test_interpolation_indices_cover_endpoints_without_negative_indices():
    low, high, weight = SUBJECT.interpolation_indices(
        np.arange(-5.0, 5.25, 0.25), np.array([-5.0, -4.875, 5.0])
    )
    np.testing.assert_array_equal(low, [0, 0, 40])
    np.testing.assert_array_equal(high, [1, 1, 40])
    np.testing.assert_allclose(weight, [0.0, 0.5, 0.0])


@pytest.mark.parametrize("query", [-5.0001, 5.0001])
def test_interpolation_indices_reject_extrapolation(query):
    with pytest.raises(ValueError, match="outside cached state support"):
        SUBJECT.interpolation_indices(np.arange(-5.0, 5.25, 0.25), [query])
