"""Final policy fallback preserves baseline positions and physical IDs."""
import variants


def test_failed_native_candidate_keeps_reportable_baseline(monkeypatch):
    candidate={a:{'bad':True} for a in variants.engine.ARMS}
    parent_cov={a:{'accepted_observation_ids':['original']} for a in variants.engine.ARMS}
    baseline={'arms':{a:{'position':'baseline'} for a in variants.engine.ARMS},'coverage':parent_cov}
    monkeypatch.setattr(variants,'qualified',lambda pair:False)
    monkeypatch.setattr(variants.paths,'coverage',lambda *args:{'accepted_observation_ids':[]})
    saved=variants.package({},candidate,parent_cov,baseline)
    assert saved['accepted'] and not saved['candidate_accepted']
    assert saved['fallback']=='baseline'
    assert saved['arms']==baseline['arms'] and saved['coverage']==baseline['coverage']
    assert saved['candidate_arms']==candidate


def test_paired_gates_are_insufficient_when_parent_ids_are_lost(monkeypatch):
    pair={a:{} for a in variants.engine.ARMS}
    cov={a:{'accepted_observation_ids':['original']} for a in variants.engine.ARMS}
    monkeypatch.setattr(variants,'qualified',lambda pair:True)
    monkeypatch.setattr(variants.paths,'coverage',lambda *args:{'accepted_observation_ids':['new']})
    saved=variants.package({},pair,cov,{'arms':pair,'coverage':cov})
    assert not saved['candidate_accepted']
    assert not saved['all_parent_IDs_preserved']
