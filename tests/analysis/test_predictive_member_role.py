from types import SimpleNamespace
import numpy as np
import pytest
from annotate_predictive_only import check_predictive_role


def test_inactive_curved_evidence_requires_explicit_role_and_cannot_duplicate_calibration():
    p=SimpleNamespace(members=[5,7],slices=[slice(0,2),slice(2,4)],keep=np.array([True,False,False,False]))
    check_predictive_role(p,9)
    with pytest.raises(ValueError,match='curved annotation'):check_predictive_role(p,7)
    check_predictive_role(p,7,True)
    with pytest.raises(ValueError,match='active calibration'):check_predictive_role(p,5,True)
    np.testing.assert_array_equal(p.keep,[True,False,False,False])
