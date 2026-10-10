"""Injected orchestration tests; no recordings, optimizer or references."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location('run163_test',Path(__file__).with_name('run.py'))
RUN=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUN)


def setup():
    calls=[];events=[]
    states={s:dict(vector=np.arange(8,dtype=float),clock=np.arange(4,dtype=float)) for s in RUN.STARTS}
    states['zero-c']['vector'][6]=0.;states['zero-c']['clock'][-2:]=0.
    prepared=dict(states=states,positions={s:np.array([1.,2.]) for s in RUN.HYPOTHESES},
                  models={m:m for m in RUN.MODES},preflight={},identity=lambda:'same',fingerprint='same')
    controls={}
    for h in RUN.HYPOTHESES:
        for m in RUN.MODES:
            for a in RUN.ARMS:
                v=states['zero-c']['vector'].copy();v[:2]=[1.,2.]
                controls[h+'--'+m+'--'+a]=dict(solver=dict(vector=v,clock_coefficients=states['zero-c']['clock'].copy(),objective=12.))
    prepared['controls']=controls
    def execute(model,v,c,**options):
        calls.append((options['arm'],v.copy(),c.copy()));events.append('fit')
        return dict(status='qualified',solver=dict(vector=v.copy(),clock_coefficients=c.copy(),objective=11.),
                    audit=dict(qualified=True,objective=11.))
    def audit(*args,**kwargs):
        events.append('audit')
        return dict(status='qualified',audit=dict(qualified=True,objective=12.))
    def held(*args):events.append('held');return {'0':dict(status='complete',nll=1.)}
    selection=RUN.module('selection163_test',RUN.HERE/'selection.py')
    ports=dict(np=np,execute=execute,audit_control=audit,choose=selection.choose,
               plain=plain,fit=None,problem=None)
    return prepared,ports,calls,events,held


def plain(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,list):return [plain(v) for v in x]
    return x


def test_matched_starts_selection_and_terminal_resume(tmp_path):
    p,ports,calls,events,held=setup();member=dict(label='sample')
    result=RUN.run_member(member,tmp_path,'digest',dependency_factory=lambda m:ports,
                          prepare=lambda m,x:p,held_score=held)
    assert result['status']=='complete' and len(calls)==16
    assert len(result['cells'])==8 and len(result['attempts'])==16
    for i in range(0,len(events),4):assert events[i:i+4]==['audit','fit','fit','held']
    for arm,v,c in calls:
        np.testing.assert_array_equal(v[:2],[1.,2.])
        if arm=='zero-c':assert v[6]==0 and np.all(c[-2:]==0)
    assert any(v[6]!=0 for arm,v,c in calls if arm=='fitted-c')
    RUN.run_member(member,tmp_path,'digest',dependency_factory=lambda m:pytest.fail('resume loaded models'))
    assert len(calls)==16


def test_fit_failure_retained_and_control_selected(tmp_path):
    p,ports,calls,events,held=setup()
    def failed(*args,**kwargs):return dict(status='failed',error='synthetic optimizer failure')
    ports['execute']=failed
    result=RUN.run_member(dict(label='sample'),tmp_path,'digest',dependency_factory=lambda m:ports,
                          prepare=lambda m,x:p,held_score=held)
    assert result['status']=='complete'
    assert all(a['status']=='failed' for a in result['attempts'].values())
    import json
    for c in result['cells'].values():
        row=json.loads((tmp_path/'sample'/c['path']).read_text())
        assert row['control_retained'] and row['selected_source']=='control'
        assert len(row['candidates'])==3


def test_orphan_claim_is_not_retried(tmp_path):
    folder=tmp_path/'sample';folder.mkdir();(folder/'claim.json').write_text('{}')
    with pytest.raises(FileExistsError):
        RUN.run_member(dict(label='sample'),tmp_path,'digest',dependency_factory=lambda m:pytest.fail('loaded'))


def test_held_exception_preserves_fit_qualification(tmp_path):
    p,ports,calls,events,held=setup()
    def failed_score(*args):raise RuntimeError('synthetic scoring failure')
    result=RUN.run_member(dict(label='sample'),tmp_path,'digest',dependency_factory=lambda m:ports,
                          prepare=lambda m,x:p,held_score=failed_score)
    assert result['status']=='complete' and not result['scores_complete']
    assert all(c['status']=='qualified' for c in result['cells'].values())
