"""Pure hypothesis projection tests; no recording or reference imports."""
import copy
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('freeze162_test', Path(__file__).with_name('freeze.py'))
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)


def receipts():
    claim = dict(label='A', mode='full', arm='zero-c', protocol_sha256=API.HYPOTHESIS_DIGEST)
    receipt = dict(claim, status='qualified', audit=dict(qualified=True),
                   solver=dict(vector=[1., 2., 999.]), error_km=123.)
    return receipt, claim


def test_projection_only_position_and_no_mutation():
    receipt, claim = receipts()
    original = copy.deepcopy(receipt)
    result = API.project(receipt, claim, 'A', 'zero-c')
    assert result == [1., 2.]
    result[0] = 100.
    assert receipt == original
    assert API.POLICY['maximum_fits'] == 12*2*2*2
    assert API.POLICY['fixed_position'] is True
    assert all('report' not in n and 'evaluation' not in n for n in API.SOURCE_FILES)


@pytest.mark.parametrize('target,key,value', [
    ('claim', 'arm', 'fitted-c'), ('receipt', 'label', 'B'),
    ('receipt', 'protocol_sha256', 'foreign'), ('receipt', 'status', 'failed')])
def test_foreign_or_failed_never_omitted(target, key, value):
    receipt, claim = receipts()
    (claim if target == 'claim' else receipt)[key] = value
    with pytest.raises(ValueError):
        API.project(receipt, claim, 'A', 'zero-c')


@pytest.mark.parametrize('vector', [[], [1.], [float('nan'), 2.], [True, 2.], ['1', 2.]])
def test_invalid_geometry_rejected(vector):
    receipt, claim = receipts()
    receipt['solver']['vector'] = vector
    with pytest.raises(ValueError):
        API.project(receipt, claim, 'A', 'zero-c')


def fixture_tree(tmp_path, monkeypatch, fault=None):
    prior = tmp_path/'reports'/'161'; here = tmp_path/'reports'/'162'
    prior.mkdir(parents=True); here.mkdir()
    members = [dict(label=str(i), selected_path='preserved', fold_path='unchanged') for i in range(12)]
    hashes = {}
    for member in members:
        folder = prior/'results'/member['label']; folder.mkdir(parents=True)
        for name in ('claim.json', 'result.json', *[m+'--'+a+s
                for m in ('full', 'train0', 'train1') for a in ('zero-c', 'fitted-c')
                for s in ('.json', '.claim.json')]):
            row = dict(label=member['label'], mode=name.split('--')[0],
                arm='zero-c' if '--zero-c' in name else 'fitted-c',
                protocol_sha256=API.HYPOTHESIS_DIGEST, status='qualified',
                audit=dict(qualified=True), solver=dict(vector=[1., 2., 3.]))
            path = folder/name; path.write_text(json.dumps(row))
            hashes[str(path.relative_to(prior/'results'))] = API.sha(path)
    plan = dict(members=members, source_sha256={}, input_sha256={},
                runtime=dict(interpreter=API.INTERPRETER, sha256={}))
    (prior/'protocol.json').write_text(json.dumps(plan))
    (prior/'SUMMARY.json').write_text(json.dumps(dict(protocol_sha256=API.HYPOTHESIS_DIGEST,raw_sha256=hashes)))
    with tarfile.open(prior/'raw-receipts.tar.gz', 'w:gz') as archive:
        for name in hashes:
            if fault=='missing-archive' and name=='11/full--fitted-c.claim.json': continue
            archive.add(prior/'results'/name, arcname=name)
    integrity = {name:API.sha(prior/name) for name in ('protocol.json','SUMMARY.json','raw-receipts.tar.gz')}
    (prior/'REPORT_INTEGRITY.json').write_text(json.dumps(integrity))
    for name in (*API.SOURCE_FILES,'PLAN.md'): (here/name).write_text('synthetic')
    for key, value in dict(ROOT=tmp_path,HERE=here,PRIOR=prior,
            AUTHORITY_SHA=API.sha(prior/'protocol.json'),
            INTEGRITY_SHA=API.sha(prior/'REPORT_INTEGRITY.json')).items():
        monkeypatch.setattr(API,key,value)
    if fault=='local-tamper':
        (prior/'results'/'11'/'full--fitted-c.claim.json').write_text('{}')


def test_archive_and_member_bindings(tmp_path, monkeypatch):
    fixture_tree(tmp_path,monkeypatch)
    plan = API.prepare()
    assert len(plan['members']) == 12
    assert plan['members'][0]['fold_path']=='unchanged'
    assert set(plan['members'][0]['hypotheses'])=={'zero-c','fitted-c'}
    assert plan['members'][0]['hypotheses']['zero-c']['position']==[1.,2.]
    assert not any(name.endswith('SUMMARY.json') for name in plan['input_sha256'])


@pytest.mark.parametrize('fault',['missing-archive','local-tamper'])
def test_archive_or_local_receipt_failure_retained(tmp_path,monkeypatch,fault):
    fixture_tree(tmp_path,monkeypatch,fault)
    with pytest.raises(ValueError): API.prepare()
