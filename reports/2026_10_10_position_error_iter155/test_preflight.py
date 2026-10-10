"""Prepared fake-callback tests. No recordings, optimizer or reference port."""
from types import SimpleNamespace
import numpy as np
import pytest
from preflight import check


def fixture():
    class Model:
        size=8; smooth_clock_count=4; fixed_rf_drift=False
        observations=SimpleNamespace(receiver=np.array([0,1]))
        precision=np.diag([.25,1.,.25,1.,.01,.01])
        clock_design=np.array([[1.,0,0,0,0,0],[0,0,1.,0,0,0]])
        calls=0
        def evaluate_joint(self,v,c):
            self.calls+=1
            return 17.+.5*c@self.precision@c,np.zeros(8),self.precision@c,None
    return Model(),np.zeros(8),np.array([.3,.2,-.4,.1,0,0])


def run(model,v,c,factory,**options):
    stored=17.+.5*c@model.precision@c
    return check(model,v,c,arm='zero-c',stored_objective=stored,
                 conditional_factory=factory,feasible=options.pop('feasible',lambda *a:True),**options)


@pytest.fixture
def factory():
    # Explicit dependency injection avoids an ambient math_core module collision.
    import importlib.util
    from pathlib import Path
    folder=Path(__file__).resolve().parent.parent/'2026_10_10_position_error_iter152'
    spec=importlib.util.spec_from_file_location('math152_preflight155',folder/'math_core.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=(folder/'conditional.py').read_text().replace('from math_core import amplitude_interval','')
    namespace=dict(__name__='conditional152_preflight155',amplitude_interval=module.amplitude_interval)
    exec(compile(source,str(folder/'conditional.py'),'exec'),namespace)
    return namespace['ConditionalModes']


def test_factorization_six_calls_and_input_isolation(factory):
    model,v,c=fixture();before=c.copy()
    result=run(model,v,c,factory)
    assert result['status']=='passed' and result['joint_attempts']==model.calls==6
    assert all(call['called'] for call in result['calls'])
    np.testing.assert_array_equal(c,before);np.testing.assert_array_equal(v,np.zeros(8))


def test_coupled_callback_rejected(factory):
    model,v,c=fixture();original=model.evaluate_joint
    def coupled(v,c):
        value,p,g,a=original(v,c);g=g.copy();g[0]+=c[2];g[2]+=c[0]
        return value+c[0]*c[2],p,g,a
    model.evaluate_joint=coupled
    stored=17.+.5*c@model.precision@c+c[0]*c[2]
    result=check(model,v,c,arm='zero-c',stored_objective=stored,
                 conditional_factory=factory,feasible=lambda *a:True)
    assert result['status']=='failed' and result['joint_attempts']==6
    assert 'factorization' in result['error']


def test_feasibility_before_first_objective(factory):
    model,v,c=fixture();result=run(model,v,c,factory,feasible=lambda *a:False)
    assert model.calls==result['joint_attempts']==0 and result['status']=='failed'


def test_mutating_callback_cannot_change_fixed_state(factory):
    model,v,c=fixture();original=model.evaluate_joint
    def mutate(v,c):
        value=original(v,c);v[:]=99;c[:]=99;return value
    model.evaluate_joint=mutate
    result=run(model,v,c,factory)
    assert result['status']=='passed';assert np.all(v==0) and c[-1]==0


@pytest.mark.parametrize('mode',['nonfinite','budget','anchor','boundary','locks'])
def test_failures_are_preserved_and_bounded(factory,mode):
    model,v,c=fixture();options={}
    if mode=='nonfinite':model.evaluate_joint=lambda *a:(float('nan'),np.zeros(8),np.zeros(6),None)
    if mode=='budget':
        values=iter([0.,31.,32.]);options['clock']=lambda:next(values)
    if mode=='boundary':c[0]=2000
    if mode=='locks':v[6]=1
    if mode=='anchor':
        result=check(model,v,c,arm='zero-c',stored_objective=0,
            conditional_factory=factory,feasible=lambda *a:True)
    else:result=run(model,v,c,factory,**options)
    assert result['status']=='failed' and result['joint_attempts']<=6 and 'error' in result


def test_anchor_qualification_uses_existing_gradients_without_extra_call(factory):
    model,v,c=fixture();audits=[]
    def independent(v,c,pg,cg,arm):
        audits.append((pg.copy(),cg.copy(),arm));return dict(qualified=True)
    stored=17.+.5*c@model.precision@c
    result=check(model,v,c,arm='zero-c',stored_objective=stored,
                 stored_joint_objective=stored,anchor_audit=independent,
                 conditional_factory=factory,feasible=lambda *a:True)
    assert result['status']=='passed' and model.calls==6 and len(audits)==1
    np.testing.assert_array_equal(audits[0][1],model.precision@c)


def test_inference_array_mutation_fails_with_fingerprint(factory):
    model,v,c=fixture();model.precision=model.precision.copy();original=model.evaluate_joint
    def mutate(v,c):
        result=original(v,c);model.precision[0,0]+=1;return result
    model.evaluate_joint=mutate
    result=run(model,v,c,factory,fingerprint=lambda:model.precision.tolist())
    assert result['status']=='failed' and result['joint_attempts']==1
    assert 'inference arrays mutated' in result['error']
