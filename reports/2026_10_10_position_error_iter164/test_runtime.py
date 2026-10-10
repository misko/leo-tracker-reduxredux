"""Synthetic runtime/controller tests without inference imports or recordings."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE=Path(__file__).parent


def load(name,monkeypatch):
    if name!='ports':
        ports=load('ports',monkeypatch);monkeypatch.setitem(sys.modules,'ports',ports)
        if name=='batch':monkeypatch.setitem(sys.modules,'execute',load('execute',monkeypatch))
    spec=importlib.util.spec_from_file_location('runtime164_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_ports_preserve151_policy_and_arm_separation(monkeypatch):
    api=load('ports',monkeypatch)
    source=(api.PARENT/'search.py').read_text();changed=api.search_source(source)
    assert 'else "zero-c"' in changed
    assert 'scores"]["native"]' in changed
    assert api.POLICY['point_budget']==400 and api.POLICY['local_radius_km']==25
    with pytest.raises(ValueError):api.search_source('changed source')


def test_matching_pending_and_orphan_rejected(tmp_path,monkeypatch):
    api=load('batch',monkeypatch);folder=tmp_path/'A'/'native'/'slices';folder.mkdir(parents=True)
    claim=dict(protocol_sha256='d',slice=1)
    (folder/'baseline-01.started.json').write_text(json.dumps(claim))
    with pytest.raises(ValueError):api.authoritative_status(tmp_path,'A','native','d')
    done=dict(protocol_sha256='d',slice=1,label='A',branch='native',status='pending')
    (folder/'baseline-02.done.json').write_text(json.dumps(done))
    with pytest.raises(ValueError):api.authoritative_status(tmp_path,'A','native','d')
    (folder/'baseline-02.done.json').rename(folder/'baseline-01.done.json')
    assert api.authoritative_status(tmp_path,'A','native','d')=='pending'


def test_scientific_failures_do_not_gate_next_phases(monkeypatch):
    api=load('batch',monkeypatch);calls=[]
    def invoke(label,phase):calls.append(phase);return 'failed'
    assert api.run_member(dict(label='A'),invoke,lambda *a:None)==dict(search='failed',native='failed',zero='failed')
    assert calls==['search','native','zero']


def test_resource_checkpoint_requires_both_shards_and_coverage(tmp_path,monkeypatch):
    api=load('batch',monkeypatch);batches=[['A','B','C','D']]
    for shard in (0,1):
        row=dict(protocol_sha256='d',batch=0,shard=shard,status='terminal',members=[
            dict(label=label,phases=dict(search='failed',native='not-run-search-failed',zero='not-run-search-failed'))
            for label in batches[0][shard::2]])
        (tmp_path/f'batch-0-shard-{shard}.json').write_text(json.dumps(row))
        (tmp_path/f'batch-0-shard-{shard}.claim.json').write_text(json.dumps(dict(protocol_sha256='d',batch=0,shard=shard)))
    api.prior_batches(tmp_path,1,'d',batches)
    path=tmp_path/'batch-0-shard-1.json';row=json.loads(path.read_text());row['members']=[];path.write_text(json.dumps(row))
    with pytest.raises(ValueError):api.prior_batches(tmp_path,1,'d',batches)


def test193partition(monkeypatch):
    api=load('batch',monkeypatch);labels=[str(i) for i in range(193)]
    plan=dict(members=[dict(label=l) for l in labels],execution_batches=[labels[:4]]+[labels[i:i+16] for i in range(4,193,16)])
    assert len(api.validate_batches(plan))==193
    plan['execution_batches'][-1][0]='0'
    with pytest.raises(ValueError):api.validate_batches(plan)


def test_binding_failure_seals_all_three_phases_no_overwrite(tmp_path,monkeypatch):
    api=load('execute',monkeypatch)
    member=dict(label='A',binding_status='failed',binding_error='missing metadata')
    for phase in ('search','native','zero'):
        row=api.admission_failure({},member,phase,tmp_path,'missing metadata')
        assert row['status']==('failed' if phase=='search' else 'not-run-search-failed')
        assert row['binding_error']=='missing metadata'
        assert (tmp_path/phase/'result.json').exists()
    with pytest.raises(FileExistsError):api.admission_failure({},member,'search',tmp_path,'retry')
