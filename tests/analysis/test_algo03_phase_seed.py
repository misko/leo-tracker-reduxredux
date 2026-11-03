import numpy as np
import pytest

from probe_algo03_phase_seed import rf_seeds


def test_seeds_preserve_origin_and_rf_endpoint_without_duplicate_origin():
    point=np.array([2.,-3.])
    seeds=rf_seeds(point)
    np.testing.assert_array_equal(seeds[0],[0.,0.])
    np.testing.assert_array_equal(seeds[1],point)
    point[:]=0
    np.testing.assert_array_equal(seeds[1],[2.,-3.])
    assert len(rf_seeds([0.,0.]))==1


@pytest.mark.parametrize("value",[[float("nan"),0.],[13.,0.],[0.]])
def test_seeds_reject_nonregional_or_nonfinite_positions(value):
    with pytest.raises(ValueError):
        rf_seeds(value)
