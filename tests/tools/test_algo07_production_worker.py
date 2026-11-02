"""The ALGO07 process boundary preserves its published fallback and budget."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'contracts'))
from test_fast_graph_position_v6 import terminal
import algo07_production_worker as worker


def test_envelope_keeps_qualified_ownership_and_both_arms():
    value=terminal();old=copy.deepcopy(value['incumbent'])
    result=worker.envelope(old,value['candidate'],{'verified':True},12.0)
    assert result['decision']=='ALGO07_reassociation'
    assert result['incumbent']==old
    assert result['total_seconds']==old['total_seconds']+12


@pytest.mark.parametrize('failure',['timeout','ambiguous_identity','incomplete_control'])
def test_fallback_is_exact_published_incumbent(failure):
    old=terminal()['incumbent'];saved=copy.deepcopy(old)
    result=worker.envelope(old,None,None,4.,failure)
    assert result['decision']=='ALGO06_fallback'
    assert result['position']==saved['position']
    assert result['incumbent']==saved
    assert result['failure']==failure


def test_budget_reserves_time_for_atomic_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(worker.time,'monotonic',lambda:100.)
    with pytest.raises(TimeoutError,match='budget'):
        worker.guarded_replay(tmp_path,{},deadline=114.)
    assert list(tmp_path.iterdir())==[]


def test_slow_preparation_has_its_own_bounded_alarm(monkeypatch):
    import signal
    calls=[]
    monkeypatch.setattr(worker.time,'monotonic',lambda:100.)
    monkeypatch.setattr(signal,'setitimer',lambda *args: calls.append(args) or (0.,0.))
    original=signal.getsignal(signal.SIGALRM)
    with worker.preparation_budget(120.):
        with pytest.raises(TimeoutError,match='deadline'):
            signal.getsignal(signal.SIGALRM)(None,None)
    assert calls==[(signal.ITIMER_REAL,10.),(signal.ITIMER_REAL,0.,0.)]
    assert signal.getsignal(signal.SIGALRM)==original


def test_every_preparation_error_retains_qualified_baseline(tmp_path,monkeypatch):
    old=terminal()['incumbent'];receipt={'sha256':'same'}
    class Store:
        def __init__(self,*a):pass
        def status(self,*a):return {'state':'complete'}
        def terminal(self,*a):return copy.deepcopy(old),dict(receipt)
        def export_recovery(self,*a):raise ValueError('invalid_export')
    monkeypatch.setattr(worker,'FastGraphPositionStoreV5Export',Store)
    monkeypatch.setattr(worker,'verify_release',lambda:None)
    result=worker.run(SimpleNamespace(bulk_root=tmp_path,job='x',output=tmp_path/'out',maximum_seconds=1200))
    assert result['decision']=='ALGO06_fallback'
    assert result['position']==old['position']
    assert 'invalid_export' in result['failure']
    assert (tmp_path/'out/terminal.json').is_file()


def test_changed_upstream_never_publishes_terminal(tmp_path,monkeypatch):
    old=terminal()['incumbent']
    class Store:
        reads=0
        def __init__(self,*a):pass
        def status(self,*a):return {'state':'complete'}
        def terminal(self,*a):
            self.reads+=1
            return copy.deepcopy(old),{'sha256':str(self.reads)}
        def export_recovery(self,*a):raise ValueError('invalid_export')
    monkeypatch.setattr(worker,'FastGraphPositionStoreV5Export',Store)
    monkeypatch.setattr(worker,'verify_release',lambda:None)
    with pytest.raises(ValueError,match='ALGO06 changed'):
        worker.run(SimpleNamespace(bulk_root=tmp_path,job='x',output=tmp_path/'out',maximum_seconds=1200))
    assert not (tmp_path/'out/terminal.json').exists()
