import numpy as np
import pytest
from probe_ds23_shared_rate import rate_design


def test_same_satellite_rate_scales_with_RF_across_receivers_and_changes_sign_about_midscan():
    result=rate_design([1,1,2,1],[1,1.1,1,1],[100,100,150,200],[1],.25)
    np.testing.assert_allclose(result[:,0],[-12.5,-13.75,0,12.5])


def test_rates_cannot_affect_other_satellites_or_create_modes_when_disabled():
    assert rate_design([1,2],[1,1],[0,300],[1],0).shape==(2,0)
    assert rate_design([1,2],[1,1],[0,300],[],1).shape==(2,0)
    np.testing.assert_allclose(rate_design([1,2],[1,1],[0,300],[1],1)[:,0],[-150,0])


def test_invalid_physical_width_rejected():
    with pytest.raises(ValueError):rate_design([1],[1],[0],[1],-1)
