import eligibility02 as e


def test_dormant_new_nominee_is_not_an_incumbent_but_active_owner_modes_are():
    assert e.required_modes([1,2,3],{1,2})=={1,2}
    required=e.required_modes([1,2,3],{1,2})
    assert required <= {1,2}
    assert not required <= {1,3}


def test_predictive_incumbent_is_protected_even_without_curved_owner():
    assert e.required_modes([1,2,3],{1,3})=={1,3}
