import math
import pytest

from ds23_unknown_catalogue_prior import category_code,corrected_cost


def test_normalized_unknown_plus_all_named_categories():
    n=1402;p=.05
    assert p+n*((1-p)/n)==pytest.approx(1.)
    assert category_code(n,1,p)==pytest.approx(-2*math.log(p/((1-p)/n)))


def test_reweighting_is_exact_constant_not_new_fit():
    for n in (1,20,1402):
        for k in (0,1,2):
            assert corrected_cost(400.,n,k)==pytest.approx(400.-2*k*math.log(n))
    assert corrected_cost(123.,1,2)==123.


def test_invalid_catalogue_domain_rejected():
    with pytest.raises(ValueError):category_code(0,1)
    with pytest.raises(ValueError):category_code(1400,-1)
