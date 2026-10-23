from types import SimpleNamespace
import numpy as np
import resume_algo04_checkpoint as resume
from run_algo01_ds23_sample import write


def test_completed_hypothesis_is_verified_and_not_refit(tmp_path,monkeypatch):
    node={'seed':{'rows':[dict(component='A',candidate_index=0,candidate_norad=10)]},'aliases':[0]}
    d=dict(node=node,keep=np.array([False]),base=SimpleNamespace(slices=[slice(0,1)]),entries=[],all_means=np.array([.1]),arms={'old':1})
    row=dict(row_index=0,target=dict(component='A'));offer=dict(candidate_index=0,norad=10,aliases=[0])
    trial=dict(node=node,mask=[True],entries=[],means=[.1],additions=[dict(component='A',candidate_index=0,alias=0)],
        paired_valid=True,added_curved_points=1,arms={'c0':dict(corrected_selection_loss=1)})
    path=tmp_path/'positions.json';write(tmp_path/'positions_checkpoint.json',dict(trials=[trial]))
    monkeypatch.setattr(resume,'CONFIGURATIONS',lambda _: [[(row,offer)]])
    calls=[]
    def fake_positions(data,nom,destination):
        assert resume.study.engine.reentry.configurations(nom)==[]
        calls.append(True)
        return dict(trials=[],selected=None,policy_arms=data['arms'])
    monkeypatch.setattr(resume,'POSITIONS',fake_positions)
    result=resume.resume_positions(d,{},path)
    assert calls==[True] and result['trials']==[trial] and result['selected']==trial
    assert result['resumed_completed_hypotheses']==1
