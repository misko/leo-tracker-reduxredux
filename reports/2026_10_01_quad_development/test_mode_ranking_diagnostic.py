from mode_ranking_diagnostic import objective_choice


def test_objective_choice_ignores_geographic_error_and_near_ties():
    row=dict(recovered=dict(accepted=True,error_m=99999),variant=dict(accepted=True,error_m=1),
             objective_changes=dict(recovered=-1e-8))
    assert objective_choice(row)=='recovered'
    row['objective_changes']['recovered']=-2
    assert objective_choice(row)=='variant'
    row['variant']['error_m']=999999
    assert objective_choice(row)=='variant'


def test_rejected_modes_are_never_selected():
    row=dict(recovered=dict(accepted=True),variant=dict(accepted=False),objective_changes=dict(recovered=-1000))
    assert objective_choice(row)=='recovered'
    row['recovered']['accepted']=False
    assert objective_choice(row) is None
