from export_native_target_iq import measurement_point


def test_plan_contains_native_frequency_not_alias_lifted_or_orbit_prediction():
    track=dict(observation_ids=['a'],key='track',times=[4.],values=[999999.],norad=123)
    probe=dict(visit_index=3,valid_start_counter=40,edge='lower')
    candidate=dict(fractional_tracking_cfo_hz=12.,integer_epoch_sample=5,fractional_epoch_offset_samples=.2,candidate_rank=0)
    p=measurement_point(track,probe,candidate,0,1)
    assert p['CFO_hz']==12 and p['epoch_sample']==5.2
    assert not {'norad','values','position','residual'} & p.keys()
    assert p['observation_id']=='a' and p['sample_start']==40
