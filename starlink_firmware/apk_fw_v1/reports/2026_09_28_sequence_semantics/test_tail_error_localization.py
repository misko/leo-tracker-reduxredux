import numpy as np
from tail_error_localization import select_exceptions


def test_evaluation_errors_cannot_select_carrier_exclusions():
    errors = np.zeros((13, 3), int)
    support = np.full((13, 3), 100)
    errors[:6, 1] = 20
    expected = np.array([False, True, False])
    np.testing.assert_array_equal(select_exceptions(errors, support), expected)
    errors[6:, 0] = 100
    np.testing.assert_array_equal(select_exceptions(errors, support), expected)
