"""Resume refinement without losing cached scores during legacy phase replay."""
from types import SimpleNamespace
import numpy as np
import refine_family_transfer as replay
from debug_fast_graph_unassociated import read,write


def test_legacy_phase_replay_preserves_converged_family_scores(tmp_path,monkeypatch):
    source=tmp_path/'source';prior=tmp_path/'prior';source.mkdir();prior.mkdir()
    history=[dict(x=[0,0],objective=0),dict(x=[0,0],objective=0)]
    held=[dict(candidate_index=j,norad=100+j,points=2,negative_twice_log_density=10.) for j in range(2)]
    endpoint=dict(history=history,endpoint_east_north_km=[0,0],held_families=held)
    write(source/'protocol.json',dict(job=dict(job_id='job',label='test'),targets=[dict(candidate_index=99)]))
    write(source/'result.json',dict(folds=[dict(split=dict(fold=0,training_families=[0],held_families=[1]),variants=dict(control=dict(c0=endpoint)))]))
    rows=[dict(fold=0,variant='control',arm='c0',norad=100+j,points=2,
        steps=[dict(step_s=.1,score=10.),dict(step_s=.05,score=9.,change=-1.)],score=9.,converged=(j==0)) for j in range(2)]
    write(prior/'result.json',dict(source=str(source),rows=rows))
    inv=tmp_path/'all-large-track-recovery/job';inv.mkdir(parents=True);write(inv/'inventory.json',{})
    class Problem:
        labels=np.array([0,1]);flat_labels=np.array([0,1]);keep=np.array([True,False])
        def state(self,x):return dict(phases=np.zeros(2))
        def calculate(self,x):return dict(negative_twice_elbo=0.,elevation=np.ones(2))
    p=Problem();d=dict(problems={'c0':(p,None)},keep=p.keep,node={},means=np.zeros(2),model={})
    monkeypatch.setattr(replay,'context',lambda _:d)
    monkeypatch.setattr(replay,'validation_inputs',lambda _:(None,None,np.ones(2),None))
    monkeypatch.setattr(replay,'held_entries',lambda *args:{j:[dict(candidate_index=j)] for j in range(2)})
    monkeypatch.setattr(replay,'make_event_problem',lambda *args,**kwargs:p)
    monkeypatch.setattr(replay,'cached',lambda p:p)
    calls=[]
    class Predictor:
        def __init__(self,scan,entries,model,**kwargs):self.j=entries[0]['candidate_index']
        def evaluate(self,*args):calls.append(self.j);return 8.999
    monkeypatch.setattr(replay,'NewFamily',Predictor)
    out=tmp_path/'out'
    replay.run(SimpleNamespace(input=source,output=out,previous_grid=prior,study=tmp_path,phase_steps=[.025]))
    result=read(out/'result.json')['rows']
    assert calls==[1]
    assert result[0]==rows[0]
    assert len(result[1]['steps'])==3 and result[1]['converged']
