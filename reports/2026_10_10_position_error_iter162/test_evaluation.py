"""Synthetic sealing tests; never open a reference authority."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('evaluation162_test', Path(__file__).with_name('evaluation.py'))
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)


def fixtures(tmp_path):
    plan = dict(members=[dict(label=str(i), dataset='DS16') for i in range(12)],
                source_sha256={}, input_sha256={})
    for member in plan['members']:
        label = member['label']; folder = tmp_path / label; folder.mkdir()
        identity = dict(label=label, protocol_sha256='digest')
        (folder/'claim.json').write_text(json.dumps(identity))
        cells = {}
        for hypothesis in API.HYPOTHESES:
            for mode in API.MODES:
                for arm in API.ARMS:
                    key = hypothesis+'--'+mode+'--'+arm
                    bound = dict(identity, hypothesis=hypothesis, mode=mode, arm=arm)
                    (folder/(key+'.claim.json')).write_text(json.dumps(bound))
                    path = folder/(key+'.json')
                    path.write_text(json.dumps(dict(bound,status='qualified',solver={},audit={},scores={})))
                    cells[key] = dict(status='qualified',path=path.name,sha256=API.sha(path))
        (folder/'result.json').write_text(json.dumps(dict(identity,status='complete',cells=cells)))
    return plan


def test_full_collection(tmp_path):
    result = API.collect(fixtures(tmp_path),'digest',tmp_path)
    assert len(result['cells']) == 96
    assert len(result['members']) == 12
    assert len(result['raw_sha256']) == 216


@pytest.mark.parametrize('fault', ['missing', 'foreign-claim', 'foreign-arm', 'foreign-hypothesis', 'nonterminal'])
def test_last_cell_blocks_evaluation_port(tmp_path,fault):
    plan = fixtures(tmp_path); folder=tmp_path/'11'; key='fitted-c--train1--fitted-c'
    path=folder/(key+'.json')
    if fault=='missing': path.unlink()
    elif fault=='foreign-claim':
        p=folder/(key+'.claim.json');r=json.loads(p.read_text());r['label']='other';p.write_text(json.dumps(r))
    else:
        field = {'foreign-arm':'arm', 'foreign-hypothesis':'hypothesis', 'nonterminal':'status'}[fault]
        r=json.loads(path.read_text());r[field]='other';path.write_text(json.dumps(r))
    calls=[]
    with pytest.raises((ValueError,FileNotFoundError)):
        API.evaluate(plan,'digest',tmp_path,{},evaluation_factory=lambda cell:calls.append(cell))
    assert calls==[]


def test_failed_cell_retains_full_coverage(tmp_path):
    plan = fixtures(tmp_path); folder=tmp_path/'11'; key='fitted-c--train1--fitted-c'
    path=folder/(key+'.json'); cell=json.loads(path.read_text())
    cell.update(status='failed', solver=None, error='synthetic failure')
    path.write_text(json.dumps(cell))
    path_member=folder/'result.json'; member=json.loads(path_member.read_text())
    member['status']='failed'; member['cells'][key].update(status='failed',sha256=API.sha(path))
    path_member.write_text(json.dumps(member))
    collected=API.collect(plan,'digest',tmp_path)
    assert len(collected['cells'])==96
    assert sum(cell['status']=='failed' for cell in collected['cells'])==1


def test_tampered_preference_blocks_reference_callback(tmp_path, monkeypatch):
    directory=tmp_path/'results';directory.mkdir();plan=fixtures(directory)
    here=tmp_path/'report';here.mkdir();preferences=here/'PREFERENCES.json'
    preferences.write_text('{}')
    authority=tmp_path/'authority.json';authority.write_text('{}')
    monkeypatch.setattr(API,'ROOT',tmp_path)
    monkeypatch.setattr(API,'HERE',here)
    monkeypatch.setattr(API,'AUTHORITY',authority)
    monkeypatch.setattr(API,'AUTHORITY_SHA',API.sha(authority))
    collection=API.collect(plan,'digest',directory)
    evaluation_plan=dict(inference_protocol_sha256='digest',
                         authority_sha256=API.AUTHORITY_SHA,
                         raw_sha256=collection['raw_sha256'],
                         labels=[m['label'] for m in plan['members']],
                         evaluation_source_sha256={},
                         input_sha256={'report/PREFERENCES.json':API.sha(preferences)})
    preferences.write_text('{"changed":true}')
    calls=[]
    with pytest.raises(ValueError,match='preference input differs'):
        API.evaluate(plan,'digest',directory,evaluation_plan,
                     evaluation_factory=lambda cell:calls.append(cell))
    assert calls==[]
