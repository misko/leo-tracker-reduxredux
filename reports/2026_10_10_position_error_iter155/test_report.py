"""Fake receipt aggregation only; no model, production or reference imports."""
import json

import pytest

from report import build, canonical, markdown


def fixture(tmp_path):
    plan=dict(members=[dict(label=f'x{i}',dataset='DS16' if i<4 else 'DS17' if i<8 else 'DS18') for i in range(12)],
              source_sha256={},input_sha256={},runtime={'sha256':{}})
    protocol=tmp_path/'protocol.json';protocol.write_text(json.dumps(plan))
    digest=canonical(plan);folder=tmp_path/'results';folder.mkdir()
    for m in plan['members']:
        row=dict(label=m['label'],protocol_sha256=digest,status='failed',matched_model=None,
                 input_reconstruction_elapsed_s=3.,elapsed_s=4.,arms={arm:dict(status='failed',
                 error='synthetic input failure',reconstruction_elapsed_s=.5) for arm in ('fitted-c','zero-c')})
        (folder/(m['label']+'.json')).write_text(json.dumps(row))
        (folder/(m['label']+'.claim.json')).write_text(json.dumps(dict(label=m['label'],protocol_sha256=digest)))
    return protocol,folder


def test_all_failed_terminal_coverage_keeps_cost_and_missing_checks(tmp_path):
    protocol,folder=fixture(tmp_path)
    s=build(protocol,folder,root=tmp_path)
    assert len(s['rows'])==12 and s['coverage']['all12']['arms']['zero-c']['failed']==12
    assert s['rows'][0]['arms']['zero-c']['reconstruction_elapsed_s']==.5
    assert s['rows'][0]['arms']['zero-c']['objective_elapsed_s'] is None
    text=markdown(s)
    assert 'synthetic input failure' in text and 'unavailable' in text
    assert len(s['artifact_sha256'])==25
    assert s['protocol_file_sha256']!=s['protocol_canonical_digest']


@pytest.mark.parametrize('failure',['missing','foreign-claim','missing-arm','passed-without-calls'])
def test_gate_rejects_incomplete_or_inconsistent_receipts(tmp_path,failure):
    protocol,folder=fixture(tmp_path);path=folder/'x0.json'
    if failure=='missing':path.unlink()
    elif failure=='foreign-claim':
        claim=folder/'x0.claim.json';value=json.loads(claim.read_text());value['protocol_sha256']='bad';claim.write_text(json.dumps(value))
    else:
        value=json.loads(path.read_text())
        if failure=='missing-arm':value['arms'].pop('zero-c')
        else:
            value['status']='complete'
            for arm in value['arms']:value['arms'][arm]['status']='passed'
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):build(protocol,folder,root=tmp_path)


def test_failed_objective_cost_is_preserved_separately(tmp_path):
    protocol,folder=fixture(tmp_path);path=folder/'x0.json';value=json.loads(path.read_text())
    value['arms']['fitted-c']['diagnostic']=dict(status='failed',joint_attempts=1,elapsed_s=.3,
        calls=[dict(label='anchor',called=True,objective_elapsed_s=.02,elapsed_s=.1,error='failed objective')])
    path.write_text(json.dumps(value));s=build(protocol,folder,root=tmp_path)
    arm=s['rows'][0]['arms']['fitted-c']
    assert arm['actual_calls']==1 and arm['attempts']==1
    assert arm['objective_elapsed_s']==.02 and arm['guarded_call_elapsed_s']==.1 and arm['diagnostic_elapsed_s']==.3


def test_runtime_source_hash_failure_blocks_aggregation(tmp_path):
    protocol,folder=fixture(tmp_path);plan=json.loads(protocol.read_text())
    source=tmp_path/'source.py';source.write_text('fake')
    plan['source_sha256']={'source.py':'wrong'};protocol.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='frozen artifact changed'):build(protocol,folder,root=tmp_path)
