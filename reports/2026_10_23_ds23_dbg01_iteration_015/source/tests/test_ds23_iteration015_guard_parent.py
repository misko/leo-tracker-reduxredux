from probe_ds23_iteration015_guard_parent import use_guard


def test_composition_only_reuses_previously_changed_paired_guard_decisions():
    assert use_guard(dict(accepted=dict(published_c0_positive=True,paired_positive=False)))
    assert not use_guard(dict(accepted=dict(published_c0_positive=True,paired_positive=True)))
    assert not use_guard(dict(accepted=dict(published_c0_positive=False,paired_positive=False)))
