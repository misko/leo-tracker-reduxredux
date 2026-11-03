import numpy as np
import pytest
from position_bias_contributors import contributions


def test_additive_gradient_and_units():
    w=np.array([[1.,-2.],[3.,4.]])
    d=np.arange(8.).reshape(2,2,2)
    terms=contributions(w,d)
    np.testing.assert_allclose(terms.sum(axis=(0,1)),100*np.einsum('ij,ijk->k',w,d))
    np.testing.assert_allclose(terms.sum(axis=0).sum(axis=0),terms.sum(axis=(0,1)))
    with pytest.raises(ValueError):contributions(w,d[:,:,0])
