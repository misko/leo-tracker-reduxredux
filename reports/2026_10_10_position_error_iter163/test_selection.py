import importlib.util
from pathlib import Path
import pytest

SPEC=importlib.util.spec_from_file_location('selection163_test',Path(__file__).with_name('selection.py'))
S=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(S)


def candidate(value):return dict(status='qualified',audit=dict(qualified=True,objective=value))


def test_tolerance_is_relative_to_global_minimum():
    c=dict(control=candidate(1.0000018),**{'zero-c':candidate(1.0000009),'fitted-c':candidate(1.)})
    assert S.choose(c)=='zero-c'


def test_reference_and_held_fields_do_not_choose_start():
    c=dict(control=candidate(9),**{'zero-c':candidate(8),'fitted-c':candidate(7)})
    c['control'].update(error_km=0,held_nll=-1e99)
    c['fitted-c'].update(error_km=100,held_nll=1e99)
    assert S.choose(c)=='fitted-c'


def test_retains_control_at_tie_and_rejects_unqualified_better_score():
    c=dict(control=candidate(1),**{'zero-c':candidate(1),'fitted-c':dict(status='unqualified',audit=dict(objective=0))})
    assert S.choose(c)=='control'
    for r in c.values():r['status']='failed'
    assert S.choose(c) is None


def test_qualification_cannot_be_claimed_without_independent_audit():
    c={key:dict(status='failed') for key in S.PRIORITY};c['control']=dict(status='qualified')
    with pytest.raises(ValueError,match='without audit'):S.choose(c)
