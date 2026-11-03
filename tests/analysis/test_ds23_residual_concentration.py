import numpy as np
import pytest
from inventory_ds23_residual_concentration import concentration


def test_one_large_error_differs_from_a_uniformly_noisy_curve():
    a=concentration(np.r_[np.ones(31),100.],np.ones(32))
    assert a['maximum_raw_energy_fraction']>.99 and a['diagnostic_RMS_without_maximum_hz']==1
    b=concentration(np.ones(32),np.ones(32))
    assert b['maximum_raw_energy_fraction']==1/32


def test_declared_noise_can_explain_large_raw_error_and_zero_energy_is_defined():
    a=concentration(np.array([1.,100.]),np.array([1.,100.]))
    assert a['maximum_raw_energy_fraction']>.99 and a['maximum_normalized_energy_fraction']==.5
    assert concentration(np.zeros(3),np.ones(3))['maximum_raw_energy_fraction']==0
    with pytest.raises(ValueError):concentration([1,2],[0,1])
