import numpy as np
from carrier_reliability import disagreement


def test_per_carrier_errors_do_not_count_imaginary_axis_or_other_carriers():
    expected = np.array([[1, -1], [-1, 1], [1, 1]])
    values = expected.astype(complex) + 20j
    values[1, 0] *= -1
    errors, counts = disagreement(values, expected)
    assert errors.tolist() == [1, 0]
    assert counts.tolist() == [3, 3]
