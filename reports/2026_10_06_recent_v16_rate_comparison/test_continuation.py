from continue_fits import choose,BUDGETS


def test_continuation_selection_uses_objective_not_roof_distance():
    base=dict(success=True,fixed_location=False)
    near=dict(base,objective=100.,point_km=[0.,0.])
    far=dict(base,objective=90.,point_km=[3.,0.])
    assert choose([near,far]) is far
    assert sum(BUDGETS.values())==120.
