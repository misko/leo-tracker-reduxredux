"""Ownership remains exact when full-window companion methods share a target."""
import pytest
from graph_additions import stage_additions


def test_staging_preserves_originals_and_adds_one_new_owner():
    old=[dict(observation_id='old',measured_cfo_hz=1.,fractional_margin=.5)]
    candidate=dict(target_observation_id='new',native=dict(observation_id='new',receiver=1,native_receiver_id=0,
        channel=5,time_s=1.,actual_rf_hz=11709687500.),measured_cfo_hz=12.123456789,confirmation_margin=.1)
    result=stage_additions(old,[candidate])
    assert result[0]==old[0] and len(old)==1
    assert result[1]['measured_cfo_hz']==12.123456789
    with pytest.raises(ValueError,match='already has'):stage_additions(old,[candidate,candidate])
