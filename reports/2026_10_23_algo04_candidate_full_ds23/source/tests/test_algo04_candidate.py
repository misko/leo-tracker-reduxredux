from run_algo04_candidate import preserve_ids


def test_preservation_requires_every_parent_id_in_both_arms():
    parent={a:dict(accepted_observation_ids=['a','b']) for a in ['c0','fitted_c']}
    child={a:dict(accepted_observation_ids=['a','b','c']) for a in parent}
    assert preserve_ids(parent,child)
    child['fitted_c']['accepted_observation_ids']=['a','c']
    assert not preserve_ids(parent,child)


def test_order_and_additional_ids_do_not_change_preservation():
    parent={a:dict(accepted_observation_ids=['b','a']) for a in ['c0','fitted_c']}
    child={a:dict(accepted_observation_ids=['c','a','b']) for a in parent}
    assert preserve_ids(parent,child)
