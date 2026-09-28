import numpy as np
from ds9_combined_reliability import gate_result


def test_threshold_erasures_and_carrier_selection_count_only_retained():
    values = np.array([[[0.1, -2.0], [-0.2, 3.0]]], complex)
    expected = np.array([[[-1, -1], [1, 1]]])
    r = gate_result(values, expected, 0.5, np.array([True, True]))
    assert r == dict(count=2, errors=0, disagreement=0)
    assert gate_result(values, expected, 0.5, np.array([True, False]))["count"] == 0
