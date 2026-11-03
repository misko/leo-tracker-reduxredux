import numpy as np
import pytest
from review import longest_segment, validate_and_score


def fixture():
    arrays = dict(catalog_numbers=np.array([10, 20]), group=np.array([3, 3]),
                  receiver=np.zeros(2, int), channel=np.ones(2, int),
                  times_s=np.array([1., 1.]), residual_hz=np.array([[10., 20.], [30., 40.]]))
    data = dict(arrays=arrays, duplicate_rows={}, log_gain=np.ones((2, 2)),
                native_residual_hz=arrays["residual_hz"])
    rows = [dict(row_index=0, catalog_number=10, receiver=0, channel=1, time_s=1., residual_hz=10.),
            dict(row_index=1, catalog_number=20, receiver=0, channel=1, time_s=1., residual_hz=40.)]
    return data, rows


def test_validate_concurrent():
    data, rows = fixture()
    assert validate_and_score(data, rows)["simultaneous_target_groups"] == 1


def test_invalid_assignment_rejected():
    data, rows = fixture()
    with pytest.raises(ValueError, match="Nonexclusive"):
        validate_and_score(data, rows+[rows[0]])
    data["duplicate_rows"] = {1: 0}
    with pytest.raises(ValueError, match="Alias-period"):
        validate_and_score(data, rows)


def test_gap_not_counted_as_coverage():
    assert longest_segment(np.array([0., 1., 2., 20., 21.])) == (2., 3)
