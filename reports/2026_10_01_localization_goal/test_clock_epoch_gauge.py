import numpy as np
import pytest
from diagnose_clock_epoch_gauge import conditional_minima, prior_terms


@pytest.mark.parametrize('heavy', [False, True])
def test_prior_derivatives(heavy):
    totals = np.array([-.8, .2, 1.3])
    c, h = .4, 1e-5
    value = prior_terms(c, totals, heavy)
    left, right = prior_terms(c-h, totals, heavy), prior_terms(c+h, totals, heavy)
    np.testing.assert_allclose((right[0]-left[0])/(2*h), value[1], atol=1e-8)
    np.testing.assert_allclose((right[1]-left[1])/(2*h), value[2], atol=1e-8)


def test_gaussian_profile_and_nonconvex_student_prior():
    totals = np.array([-.8, .2, 1.3])
    roots = conditional_minima(totals, .4, False)
    assert len(roots) == 1
    assert roots[0]['clock_s'] == pytest.approx(4*sum(totals)/(1+4*len(totals)))
    # A separated two-cluster configuration has genuine multiple prior modes.
    totals = np.array([-2.]*6+[2.]*6)
    roots = conditional_minima(totals, 0., True)
    assert len(roots) == 2
    assert prior_terms(0., totals, True)[2] < 0
    assert all(r['prior_terms'][2] > 0 for r in roots)
