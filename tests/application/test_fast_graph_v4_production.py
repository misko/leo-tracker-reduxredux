"""ALGO05 discovery, immutable fallback and restart behavior."""
import pytest
from tests.application.test_fast_graph_v3_production import setup as prior_setup, fallback
from leo.storage.fast_graph_position_v3_export import FastGraphPositionStoreV3Export
from leo.storage.fast_graph_position_v4 import FastGraphPositionStoreV4
from leo.storage.fast_scan import immutable_json
from leo.application.automatic_fast_graph_v4 import process
from algo05_production_worker import envelope

def setup(tmp_path):
    _, prior, source, terminal, _, cutoff=prior_setup(tmp_path)
    incumbent=FastGraphPositionStoreV3Export(tmp_path,incumbent=prior)
    source_job=incumbent.job(source);old=fallback(terminal)
    immutable_json(incumbent.path(source_job['job_id'])/'output/terminal.json',old)
    incumbent.update(source_job,state='complete')
    return incumbent,source_job,old,FastGraphPositionStoreV4(tmp_path,incumbent=incumbent),cutoff

def test_discovery_uses_completed_algo04_and_separate_namespace(tmp_path):
    incumbent,source,_,store,cutoff=setup(tmp_path)
    jobs=list(store.inputs(minimum_completed_utc_ns=cutoff))
    assert len(jobs)==1 and jobs[0]['source_job']['job_id']==source['job_id']
    assert jobs[0]['job_id']!=source['job_id'] and store.namespace!=incumbent.namespace
    with pytest.raises(ValueError):list(store.inputs(minimum_completed_utc_ns=0))

def test_publish_fallback_and_restart_without_rerun(tmp_path):
    incumbent,source,old,store,_=setup(tmp_path);job=store.job(source);calls=[]
    path=incumbent.path(source['job_id'])/'output/terminal.json';before=path.read_bytes()
    def runner(command,**kwargs):
        calls.append(command);assert kwargs['timeout']==45
        immutable_json(store.path(job['job_id'])/'output/terminal.json',envelope(old,None,None,2))
        return 0
    result=process(job,store=store,command=['worker'],maximum_seconds=30,runner=runner)
    assert result['state']=='complete' and result['result']['position']==old['position']
    store.update(job,state='running')
    assert process(job,store=store,command=['worker'],runner=runner)['state']=='complete'
    assert len(calls)==1 and path.read_bytes()==before
    assert calls[0][calls[0].index('--job')+1]==source['job_id']

def test_interrupted_attempt_is_not_silently_retried(tmp_path):
    _,source,_,store,_=setup(tmp_path);job=store.job(source);store.update(job,state='running')
    r=process(job,store=store,command=['worker'],runner=lambda *a,**k:pytest.fail('unexpected retry'))
    assert r['state']=='failed'
