from types import SimpleNamespace
import numpy as np
import pytest
from full_calibration_seed_audit import seed_vector


def test_seed_uses_selected_bank_not_all_visible_satellite_timings():
    basis = np.array([[1.], [-1.]])/np.sqrt(2.)
    obj = SimpleNamespace(base=SimpleNamespace(basis=basis))
    p = np.r_[np.arange(6.), 99., 2., 98., 4.]
    v = seed_vector(obj, p, [1, 3], 17.)
    np.testing.assert_array_equal(v[:6], p[:6])
    np.testing.assert_allclose(v[6]+basis@v[7:-1], [2., 4.])
    assert v[-1] == 17.
    with pytest.raises(ValueError): seed_vector(obj, p, [0, 2], 0.)
