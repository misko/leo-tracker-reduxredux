from types import SimpleNamespace
import repair_algo04_empty_audit as repair
from audit_algo04_legacy_reference import same_decisions


def test_empty_entry_representation_only(monkeypatch):
    seen=[]
    monkeypatch.setattr(repair,'ORIGINAL',lambda d,p,*args:seen.append(p))
    p=SimpleNamespace();repair.checked({'entries':[]},p,'c0',{},'test')
    assert p.linear_slices==[] and seen==[p]
    nonempty=SimpleNamespace(linear_slices=[slice(0,2)])
    repair.checked({'entries':[1]},nonempty,'c0',{},'test')
    assert nonempty.linear_slices==[slice(0,2)]


def test_legacy_replay_cannot_hide_changed_decisions_ids_or_counts():
    original=dict(compatible=True,points=2,ids=['a','b'],rms=10.)
    assert same_decisions(original,dict(original,rms=10.001))
    assert not same_decisions(original,dict(original,compatible=False))
    assert not same_decisions(original,dict(original,points=3))
    assert not same_decisions(original,dict(original,ids=['a','c']))
