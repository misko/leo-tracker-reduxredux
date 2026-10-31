from evaluate import selected_trial

def row(mode,margin=100,added=20,passed=True,tid='a'):
    return dict(mode=mode,identity={'minimum_margin':margin},track_id=tid,
        qualification={'qualified':passed,'added_points':{'fitted_c':added}})

def test_no_rejected_fit_is_selected():
    assert selected_trial([row('conditional',passed=False)]) is None

def test_frozen_mode_preference_precedes_margin():
    a=row('gap_default',margin=1);b=row('conditional_feasible',margin=999)
    assert selected_trial([b,a]) is a

def test_one_fit_only_not_union():
    a=row('conditional',margin=100,added=20);b=row('conditional',margin=50,added=30)
    assert selected_trial([b,a]) is a

def test_selection_does_not_read_position():
    a=row('conditional');a['endpoint_latlon']='not a coordinate'
    assert selected_trial([a]) is a
