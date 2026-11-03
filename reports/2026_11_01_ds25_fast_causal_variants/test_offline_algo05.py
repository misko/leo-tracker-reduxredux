"""Private export resume must preserve bytes and refuse scientific reruns."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import offline_algo05 as adapter

def setup(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'recovery').mkdir()
    terminal=dict(model_version='algo04-causal-numerical-v1',input_sha256='test',session_id='scan',state='complete')
    (source/'terminal.json').write_text(json.dumps(terminal));(source/'recovery/evidence.txt').write_text('unchanged')
    monkeypatch.setattr(adapter,'verify_release',lambda:None)
    monkeypatch.setattr(adapter,'validate_terminal',lambda t,**_:t)
    monkeypatch.setattr(adapter,'guarded_replay',lambda *a,**k:dict(read_audit={'verified':True},selected=None))
    monkeypatch.setattr(adapter,'envelope',lambda inc,c,a,s,f:dict(state='complete',decision='fallback',failure=f,incumbent=inc))
    args=SimpleNamespace(source_terminal=source/'terminal.json',source_recovery=source/'recovery',output=tmp_path/'out')
    return args,terminal

def test_private_v3_descriptor_and_input_bytes(tmp_path,monkeypatch):
    a,t=setup(tmp_path,monkeypatch);adapter.run(a)
    d=json.loads((a.output/'source-export/descriptor.json').read_text())
    assert d['model_version']==t['model_version'] and d['incumbent']==t
    assert (a.source_recovery/'evidence.txt').read_text()=='unchanged'
    assert (a.output/'source-export/recovery/evidence.txt').read_text()=='unchanged'

def test_resume_pre_numerical_export(tmp_path,monkeypatch):
    a,t=setup(tmp_path,monkeypatch)
    adapter.export_recovery(a.source_terminal,a.source_recovery,a.output/'source-export',t)
    adapter.run(a)
    assert json.loads((a.output/'terminal.json').read_text())['state']=='complete'

def test_resume_rejects_changed_bytes_or_started_numerics(tmp_path,monkeypatch):
    a,t=setup(tmp_path,monkeypatch)
    adapter.export_recovery(a.source_terminal,a.source_recovery,a.output/'source-export',t)
    (a.output/'launch.json').write_text('{}')
    with pytest.raises(AssertionError,match='before numerical'):adapter.run(a)
    (a.output/'launch.json').unlink()
    (a.output/'source-export/recovery/evidence.txt').write_text('changed')
    with pytest.raises(AssertionError):adapter.run(a)
