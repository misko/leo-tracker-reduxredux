import importlib.util
from pathlib import Path
import pytest

SPEC=importlib.util.spec_from_file_location('preference162_test',Path(__file__).with_name('preference.py'))
P=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(P)


def cells():
    return [dict(label='A',hypothesis=h,mode=m,arm=a,status='qualified',
        scores={held:dict(status='complete',nll=5 if h=='zero-c' else 4,observations=10)})
        for h in P.HYPOTHESES for m,held in [('train0','1'),('train1','0')] for a in P.ARMS]


def test_preferences_ignore_reference_errors_and_training_objective():
    data=cells();first=P.preferences(data,['A'])
    for c in data:c.update(error_km=-999,objective=-1e20)
    assert P.preferences(data,['A'])==first
    assert all(r['selected_hypothesis']=='fitted-c' and r['delta_nll']==-2 for r in first)


def test_one_failed_fold_makes_only_its_arm_unresolved():
    data=cells();data[0]['status']='failed'
    rows=P.preferences(data,['A'])
    assert rows[0]['status']=='incomplete' and rows[0]['selected_hypothesis'] is None
    assert rows[1]['status']=='selected'


def test_tie_does_not_arbitrarily_choose_geometry():
    data=cells()
    for c in data:
        for s in c['scores'].values():s['nll']=5
    assert all(r['status']=='tie' and r['selected_hypothesis'] is None for r in P.preferences(data,['A']))


def test_counts_must_match_hypotheses():
    data=cells();next(iter(data[0]['scores'].values()))['observations']=11
    with pytest.raises(ValueError,match='unmatched'):P.preferences(data,['A'])
