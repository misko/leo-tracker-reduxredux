from pathlib import Path
import sys
import copy
import pytest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import account


def test_additions_cannot_replace_original_owner_or_mutate_original():
    original=[dict(observation_id='a',measured_cfo_hz=5.,fractional_margin=.2)]
    candidate=dict(native=dict(observation_id='b',receiver=1,native_receiver_id=0,channel=5,time_s=4.,actual_rf_hz=12e9),measurement=dict(measured_cfo_hz=8.,fractional_margin=.05))
    saved=copy.deepcopy(original);rows=account.stage(original,[candidate])
    assert original==saved and rows[:1]==original and len(rows)==2
    candidate['native']['observation_id']='a'
    with pytest.raises(AssertionError):account.stage(original,[candidate])


def test_standard_native_ID_binding_rejects_changed_authority():
    support=account.observation_id('session',0,123)
    assert support==account.observation_id('session',0,123)
    assert support!=account.observation_id('session',1,123)
    assert support!=account.observation_id('other',0,123)
