from report_predictive_role_reassessment import complete_replay_slacks


def test_new_family_continuous_target_failures_are_not_omitted():
    diag=dict(component='RX2-CH4',profile_RMS_hz=20,profile_bias_hz=0,times_s=list(range(100)),minimum_elevation_deg=10,
        noise=dict(mean_z=0,slope_z=0,quadratic_bic_gain=-5,maximum_step_z=4.1,lag1_acf=.8))
    row=dict(exact_incumbent_family_replays=[],target=None,continuous_target={'diagnostics':[diag]})
    slacks=complete_replay_slacks(row)
    assert slacks['RX2-CH4/continuous_target/step']<0
    assert slacks['RX2-CH4/continuous_target/lag1']==-1
    assert slacks['RX2-CH4/continuous_target/rms']>0
