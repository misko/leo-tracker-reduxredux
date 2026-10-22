from probe_ds23_iteration010_path_feasibility import eligible


def test_only_failed_near_feasible_frozen_primary_is_refined():
    primary=dict(arms={'c0':{},'fitted_c':{}},accepted=False,paired_valid=False)
    assert eligible(primary,[-.0965,-.1153])
    assert not eligible(primary,[-.251,0.])
    assert not eligible(dict(primary,accepted=True),[.1,.2])
    assert not eligible(dict(primary,paired_valid=True),[.1,.2])
    assert not eligible(dict(accepted=False),[.1,.2])
