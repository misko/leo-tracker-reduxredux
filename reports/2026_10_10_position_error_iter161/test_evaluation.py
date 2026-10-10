"""Synthetic sealing tests; never open a reference authority."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('evaluation161_test', Path(__file__).with_name('evaluation.py'))
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
        for mode in API.MODES:
            for arm in API.ARMS:
                key = mode+'--'+arm
                bound = dict(identity, mode=mode, arm=arm)
                (folder/(key+'.claim.json')).write_text(json.dumps(bound))
                path = folder/(key+'.json')
                path.write_text(json.dumps(dict(bound,status='qualified',solver={},audit={},scores={})))
                cells[key] = dict(status='qualified',path=path.name,sha256=API.sha(path))
        (folder/'result.json').write_text(json.dumps(dict(identity,status='complete',cells=cells)))
    return plan


def test_full_collection(tmp_path):
    result = API.collect(fixtures(tmp_path),'digest',tmp_path)
    assert len(result['cells']) == 72
    assert len(result['members']) == 12
    assert len(result['raw_sha256']) == 168


@pytest.mark.parametrize('fault', ['missing', 'foreign-claim', 'foreign-arm', 'nonterminal'])
def test_last_cell_blocks_evaluation_port(tmp_path,fault):
    plan = fixtures(tmp_path); folder=tmp_path/'11'; key='train1--fitted-c'
    path=folder/(key+'.json')
    if fault=='missing': path.unlink()
    elif fault=='foreign-claim':
        p=folder/(key+'.claim.json');r=json.loads(p.read_text());r['label']='other';p.write_text(json.dumps(r))
    else:
        r=json.loads(path.read_text());r['arm' if fault=='foreign-arm' else 'status']='other';path.write_text(json.dumps(r))
    calls=[]
    with pytest.raises((ValueError,FileNotFoundError)):
        API.evaluate(plan,'digest',tmp_path,{},evaluation_factory=lambda cell:calls.append(cell))
    assert calls==[]
