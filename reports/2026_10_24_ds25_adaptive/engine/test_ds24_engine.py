"""Adapter isolation and paired-cohort failure behavior."""
import json
import sys
from types import SimpleNamespace
import pytest
import ds24_engine as engine


def test_only_empty_predictive_evidence_gets_empty_legacy_gates():
    pair={a:{'endpoint_east_north_km':[1.,2.]} for a in engine.ARMS}
    normalized=engine.normalize_empty_predictive(pair,[])
    assert all(s['linear_gates']==[] for s in normalized.values())
    assert all('linear_gates' not in s for s in pair.values())
    assert engine.normalize_empty_predictive(pair,[{'observation_ids':['physical']}]) is pair


def test_rejects_unqualified_fresh_incumbent(tmp_path, monkeypatch):
    case='DS24-0001'; (tmp_path/case).mkdir()
    (tmp_path/case/'algo02_result.json').write_text(json.dumps({'status':'failed'}))
    monkeypatch.setattr(engine.algo,'bind_run_directory',lambda root: None)
    with pytest.raises(ValueError,match='no qualified paired'):
        engine.context(case,tmp_path)


def test_cavity_explicitly_rebinds_both_stages_and_preserves_failure(tmp_path,monkeypatch):
    calls=[]
    nom=SimpleNamespace(one=lambda case,output_dir: calls.append((case,output_dir)) or {'status':'failed'})
    pos=SimpleNamespace()
    monkeypatch.setitem(sys.modules,'probe_ds23_family_cavity_nominations',nom)
    monkeypatch.setitem(sys.modules,'probe_ds23_family_cavity_position',pos)
    monkeypatch.setattr(engine,'context',lambda case,root: (case,root))
    assert engine.cavity('DS24-0010',tmp_path)=={'status':'failed'}
    assert nom.setup is pos.setup
    assert nom.setup('DS24-0010')==('DS24-0010',tmp_path)
    assert calls==[('DS24-0010',tmp_path/'family_cavity')]


def test_cavity_refuses_failed_reference_context(tmp_path,monkeypatch):
    monkeypatch.setattr(engine,'context',lambda *args: {})
    folder=tmp_path/'family_cavity/position'; folder.mkdir(parents=True)
    (folder/'DS24-0001.json').write_text(json.dumps({'status':'failed'}))
    with pytest.raises(ValueError,match='incomplete'):
        engine.cavity_context('DS24-0001',tmp_path)
