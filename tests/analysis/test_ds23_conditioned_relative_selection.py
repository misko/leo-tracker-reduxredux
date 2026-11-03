from probe_ds23_conditioned_relative_position import chosen_groups


def group(name='g',pair=(1,2),selected=True,gap=10.):
    return dict(group=name,selected=selected,qualified_runner_up_gap=gap,best=dict(first_index=pair[0],second_index=pair[1],
        first_norad=101+pair[0],second_norad=101+pair[1],difference_alias=0))


def test_strict_selection_requires_both_arms_and_unique_same_pair():
    document=dict(arms=dict(c0=dict(groups=[group()]),fitted_c=dict(groups=[group(selected=False)])))
    assert chosen_groups(document,'conditioned_best') and not chosen_groups(document,'conditioned_strict')
    document['arms']['fitted_c']['groups']=[group(pair=(1,3))]
    assert not chosen_groups(document,'conditioned_strict')
    document['arms']['fitted_c']['groups']=[group()]
    assert chosen_groups(document,'conditioned_strict')['g']['second_index']==2


def test_absence_of_a_qualified_runner_up_is_not_infinite_identity_confidence():
    document=dict(arms=dict(c0=dict(groups=[group(gap=None)]),fitted_c=dict(groups=[group(gap=None)])))
    assert chosen_groups(document,'conditioned_best') and not chosen_groups(document,'conditioned_strict')
