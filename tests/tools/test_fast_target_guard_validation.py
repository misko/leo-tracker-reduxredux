import pytest
from validate_fast_target_guard import target_guard,validate_members


def test_guard_requires_original_acceptance_and_same_target_pass_in_both_arms():
    source=dict(status='accepted',proposal=dict(component='target'))
    pair={a:dict(gates=dict(tracks=[dict(component='target',compatible=True),dict(component='old',compatible=False)])) for a in ('c0','fitted_c')}
    assert target_guard(source,pair)
    pair['fitted_c']['gates']['tracks'][0]['compatible']=False
    assert not target_guard(source,pair)
    assert not target_guard(dict(status='rejected'),None)
    pair['fitted_c']['gates']['tracks']=[]
    assert not target_guard(source,pair)


def test_validation_excludes_development_recordings_and_wrong_capture_modes():
    row=dict(recording_id='new',dataset_label='V1',sample_rate_hz=10_000_000,recording_format='short_window_iq_recording')
    assert validate_members([row],['old'])==['V1']
    with pytest.raises(ValueError):validate_members([row],['new'])
    with pytest.raises(ValueError):validate_members([row,row],[])
    with pytest.raises(ValueError):validate_members([dict(row,sample_rate_hz=20_000_000)],[])
