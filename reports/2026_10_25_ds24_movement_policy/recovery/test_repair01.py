from types import SimpleNamespace

import numpy as np
import repair01 as repair


def test_support_replay_protection_comes_from_original_context_not_augmented_mask(monkeypatch):
    observed={}
    def make(*args):
        observed['protected']=args[-1]
        return SimpleNamespace()
    monkeypatch.setattr(repair,'make_problem',make)
    monkeypatch.setattr(repair.r,'attach_event_predictive',lambda *args:None)
    monkeypatch.setattr(repair.r,'cached',lambda p:p)
    d=dict(scan=None,node={},keep=np.array([True,True]),powers=np.ones(2),means=np.zeros(2),
        model={},original_protected={10},entries=[],
        base=SimpleNamespace(rows=[{'candidate_index':10},{'candidate_index':20}],
            slices=[slice(0,1),slice(1,2)]))
    assert repair.r.support.protected(d)=={10,20}
    repair.corrected_build(d,'c0',[0.,0.],'support')
    assert observed['protected']=={10}
    assert observed['protected'] is not d['original_protected']


def test_non_support_model_keeps_original_builder(monkeypatch):
    monkeypatch.setattr(repair,'ORIGINAL_BUILD',lambda *args:args)
    assert repair.corrected_build({},'c0',[],'graph')==({},'c0',[],'graph')
