from reconcile_predictive_inclusion_sources import coverage,trial_role,recorded_checks


def test_partial_point_overlap_does_not_cover_whole_curve():
    assert coverage(['a'],['a','b'])=='partial_curve'
    assert coverage(['a','b','c'],['a','b'])=='full_curve'
    assert coverage(['c'],['a','b'])=='none'


def test_old_calibration_trial_is_not_predictive():
    assert trial_role(dict(curved_targets_calibrate_receiver=True))=='calibration_participating'
    assert trial_role(dict(family_prior={}))=='predictive_only'
    assert trial_role(dict(target_calibrates_receiver=False))=='predictive_only'
    assert trial_role({})=='unresolved_role'


def test_paired_pass_without_replay_does_not_qualify():
    p=dict(arms={'c0':{},'fitted_c':{}},paired_valid=True)
    assert recorded_checks(p,p,None)=='paired_pass_replay_missing'
    assert recorded_checks(p,p,dict(all_verified=False))=='recorded_replay_rejected'
    assert recorded_checks(p,dict(p,paired_valid=False),dict(all_verified=True))=='recorded_pair_rejected'
    assert recorded_checks(p,p,dict(all_verified=True))=='paired_and_replay_pass'
