"""Synthetic600-file gate and training-only selection reproduction."""
import importlib.util
import json
from pathlib import Path

import pytest


def load(name):
    spec=importlib.util.spec_from_file_location(name+'163_test',Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


API=load('evaluation');SELECT=load('selection')


def fixtures(tmp_path,monkeypatch):
    monkeypatch.setattr(API,'ROOT',tmp_path)
    directory=tmp_path/'results';directory.mkdir()
    members=[]
    def write(path,row):path.write_text(json.dumps(row));return API.sha(path)
    for i in range(12):
        label=str(i);folder=directory/label;folder.mkdir()
        identity=dict(label=label,protocol_sha256='new')
        write(folder/'claim.json',identity)
        member=dict(label=label,dataset='DS16',controls={});members.append(member)
        terminal=dict(identity,status='complete',cells={},attempts={})
        for h in API.HYPOTHESES:
            for m in API.MODES:
                for a in API.ARMS:
                    key=h+'--'+m+'--'+a;bound=dict(identity,hypothesis=h,mode=m,arm=a)
                    fit=dict(vector=[1.,2.],objective=1.);audit=dict(qualified=True,objective=1.)
                    control=dict(status='qualified',solver=fit,audit=audit)
                    raw=dict(bound,protocol_sha256='old',**control)
                    rawpath=tmp_path/(label+'-'+key+'.json');claimpath=tmp_path/(label+'-'+key+'.claim.json')
                    member['controls'][key]=dict(raw_path=rawpath.name,sha256=write(rawpath,raw),
                        claim_path=claimpath.name,claim_sha256=write(claimpath,dict(bound,protocol_sha256='old')),
                        protocol_sha256='old')
                    candidates=dict(control=control)
                    for source in API.ARMS:
                        ak=key+'--start-'+source;aid=dict(bound,start_source=source)
                        attempt=dict(aid,status='qualified',solver=fit,audit=dict(qualified=True,objective=2.))
                        candidates[source]=attempt
                        write(folder/(ak+'.claim.json'),aid)
                        terminal['attempts'][ak]=dict(status='qualified',path=ak+'.json',sha256=write(folder/(ak+'.json'),attempt))
                    cell=dict(bound,status='qualified',candidates=candidates,control_audit=control,
                        selected_source='control',control_retained=True,solver=fit,audit=audit)
                    write(folder/(key+'.claim.json'),bound)
                    terminal['cells'][key]=dict(status='qualified',path=key+'.json',sha256=write(folder/(key+'.json'),cell))
        write(folder/'result.json',terminal)
    return dict(members=members),directory


def test_complete600_and192_attempts(tmp_path,monkeypatch):
    plan,directory=fixtures(tmp_path,monkeypatch)
    result=API.collect(plan,'new',directory,choose=SELECT.choose)
    assert len(result['raw_sha256'])==600
    assert len(result['attempts'])==192 and len(result['cells'])==96


def test_failed_attempt_retained_while_control_explicitly_selected(tmp_path,monkeypatch):
    plan,directory=fixtures(tmp_path,monkeypatch)
    folder=directory/'0';key='zero-c--train0--zero-c';ak=key+'--start-zero-c'
    attempt=json.loads((folder/(ak+'.json')).read_text())
    attempt.update(status='failed',error='bounded failure')
    (folder/(ak+'.json')).write_text(json.dumps(attempt))
    cell=json.loads((folder/(key+'.json')).read_text())
    cell['candidates']['zero-c']=attempt
    (folder/(key+'.json')).write_text(json.dumps(cell))
    terminal=json.loads((folder/'result.json').read_text())
    terminal['attempts'][ak].update(status='failed',sha256=API.sha(folder/(ak+'.json')))
    terminal['cells'][key]['sha256']=API.sha(folder/(key+'.json'))
    (folder/'result.json').write_text(json.dumps(terminal))
    result=API.collect(plan,'new',directory,choose=SELECT.choose)
    assert result['attempts'][0]['status']=='failed'
    assert result['cells'][0]['control_retained'] is True


@pytest.mark.parametrize('fault',['missing','foreign','selection'])
def test_final_cell_failure_blocks_every_evaluation_callback(tmp_path,monkeypatch,fault):
    plan,directory=fixtures(tmp_path,monkeypatch)
    folder=directory/'11';key='fitted-c--train1--fitted-c'
    path=folder/(key+'.json')
    if fault=='missing':path.unlink()
    else:
        row=json.loads(path.read_text())
        row['label' if fault=='foreign' else 'selected_source']='other' if fault=='foreign' else 'zero-c'
        path.write_text(json.dumps(row))
        terminal=json.loads((folder/'result.json').read_text())
        terminal['cells'][key]['sha256']=API.sha(path)
        (folder/'result.json').write_text(json.dumps(terminal))
    calls=[]
    # Inject only the pure selector so the test never touches recording closures.
    original=API.collect
    monkeypatch.setattr(API,'collect',lambda p,d,r:original(p,d,r,choose=SELECT.choose))
    with pytest.raises((ValueError,FileNotFoundError)):
        API.evaluate(plan,'new',directory,{},evaluation_factory=lambda c:calls.append(c))
    assert calls==[]
