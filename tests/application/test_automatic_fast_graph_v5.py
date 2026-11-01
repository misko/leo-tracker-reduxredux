from contextlib import contextmanager
from pathlib import Path
import pytest
from leo.application.automatic_fast_graph_v5 import process

class Store:
    def __init__(self,path):self.folder=path;self.saved=None;self.verified=False
    @contextmanager
    def owner(self,_):yield True
    def path(self,_):return self.folder
    def status(self,_):return self.saved
    def verify_input(self,_):self.verified=True
    def update(self,job,**changes):self.saved=dict(job,**changes);return self.saved
    def terminal(self,_):return dict(state='complete',position=dict(latitude_deg=1,longitude_deg=2)),dict(sha256='receipt')

def test_bounded_worker_and_completed_result_not_retried(tmp_path):
    store=Store(tmp_path);job=dict(job_id='new',source_job=dict(job_id='old'))
    calls=[]
    def run(command,**kwargs):calls.append((command,kwargs['timeout']));return 0
    result=process(job,store=store,command=['worker'],maximum_seconds=20,runner=run)
    assert result['state']=='complete' and store.verified
    assert calls[0][0]==['worker','--job','old','--output',str(tmp_path/'output'),'--maximum-seconds','20']
    assert calls[0][1]==35
    assert process(job,store=store,command=['worker'],runner=run)==result
    assert len(calls)==1

@pytest.mark.parametrize('budget',[0,1201,True,1.5])
def test_bad_budget_rejected(tmp_path,budget):
    with pytest.raises(ValueError):process({},store=Store(tmp_path),command=['worker'],maximum_seconds=budget)
