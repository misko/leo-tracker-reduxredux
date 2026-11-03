import numpy as np
import pytest

from ds23_epoch_linked_bias import linked_covariance


def test_common_carrier_changes_only_verified_connected_components():
    keys = ['a','b','c','d']
    c = linked_covariance(keys,[('a','b'),('b','c')])
    np.testing.assert_allclose(np.diag(c),300**2)
    assert c[0,2] == 300**2-30**2
    assert c[0,3] == 0
    np.testing.assert_allclose(c[0,0]+c[1,1]-2*c[0,1],2*30**2)
    assert np.linalg.eigvalsh(c).min() > 0


def test_unknown_fragment_cannot_introduce_calibration_information():
    with pytest.raises(ValueError):
        linked_covariance(['a'],[('a','linear')])
