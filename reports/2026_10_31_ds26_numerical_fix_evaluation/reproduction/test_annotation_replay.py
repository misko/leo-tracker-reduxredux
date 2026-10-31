import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
import annotation_replay as replay


def test_overflow_trigger_checks_early_history_even_if_final_round_passes():
    a={'folds':[{'proposals':[{'arms':{'c0':{'phase_reference_check':{'phase_outside_reference_window':False},
        'history':[{'phase_outside_reference_window':True},{'phase_outside_reference_window':False}]}}}]}]}
    assert replay.has_phase_overflow(a)


def test_overflow_trigger_accepts_numeric_receipt_but_not_unrelated_convergence():
    assert replay.has_phase_overflow({'history':[{'maximum_phase_overflow_s':.001}]})
    assert not replay.has_phase_overflow({'final_phase_change_s':20,'history':[{'maximum_phase_overflow_s':0}]})


def test_frozen_signature_detects_alias_changes_and_does_not_mutate_source():
    source={'folds':[{'seed':1,'split':{'held_blocks':[2]},'proposals':[{'candidate_index':4,'norad':55,'alias':-1}]}]}
    before=copy.deepcopy(source);signature=replay.competition_signature(source)
    assert source==before
    source['folds'][0]['proposals'][0]['alias']=0
    assert replay.competition_signature(source)!=signature


def test_inactive_fragment_uses_validated_source_route(monkeypatch):
    import inactive_graph_fragment
    expected={'track_id':'parent','track_index':1,'component':'fragment','observation_ids':['a','b'],'inactive_graph_fragment':True}
    changed={'scan':SimpleNamespace(tracks=[None,{'key':'fragment','observation_ids':['a','b']}])}
    seen=[]
    def validated(d,inv,source):seen.append(source);return changed,copy.deepcopy(expected)
    monkeypatch.setattr(inactive_graph_fragment,'validated_inactive_context',validated)
    actual,target=replay.target_context({}, {}, {'track_id':'parent','component':'fragment','inactive_graph_fragment':True},
        {'target':expected},'frozen-source')
    assert actual is changed and target==expected and seen==['frozen-source']


def test_target_route_rejects_changed_fragment_observations(monkeypatch):
    import inactive_graph_fragment
    target={'track_id':'parent','track_index':0,'component':'fragment','observation_ids':['changed']}
    monkeypatch.setattr(inactive_graph_fragment,'validated_inactive_context',lambda *a:({'scan':SimpleNamespace(tracks=[{'key':'fragment','observation_ids':['changed']}])},target))
    with pytest.raises(ValueError,match='observation_ids changed'):
        replay.target_context({}, {}, {'track_id':'parent','component':'fragment','inactive_graph_fragment':True},
            {'target':dict(target,observation_ids=['original'])},'source')


def test_final_bank_check_rejects_extrapolated_actual_phase():
    p=SimpleNamespace(labels=[0],sky={'time_s':np.array([-2.,12.])},flat_times=np.array([10.]),flat_labels=np.array([0]),
        state=lambda x:{'phases':np.array([3.])})
    with pytest.raises(ValueError,match='causal orbit bank'):replay.check_bank(p,np.zeros(2))


def test_original_inventory_ids_may_be_sorted_while_native_graph_is_chronological():
    target={'track_id':'t','track_index':0,'component':'curve','observation_ids':['a','b'],'all_track_observation_ids':['b','a']}
    d={'scan':SimpleNamespace(tracks=[{'key':'curve','observation_ids':['b','a']}])}
    actual,_=replay.target_context(d,{'tracks':[target]},{'track_id':'t','component':'curve'}, {'target':target},'source')
    assert actual is d
