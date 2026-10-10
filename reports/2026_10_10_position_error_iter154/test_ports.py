import json
from pathlib import Path
import pytest
from batch import authoritative_status, run_cell
from ports import load, PRIOR, continuation_source


def test_source_transform_exact_sealed_binding_and_own_seed():
    previous = load('ports151_test154', PRIOR/'ports.py')
    source = continuation_source((previous.PARENT/'continuation.py').read_text(), previous)
    compile(source, 'synthetic154', 'exec')
    assert source.count('plan["discovery_digest"]') == 3
    assert '"fitted-c" if branch == "native" else "zero-c"' in source
    assert 'local_radius_km=25.0' in source


def test_condition_swap_and_orphan_claim_rejected(tmp_path):
    folder = tmp_path/'native'; folder.mkdir()
    row = dict(protocol_sha256='repair-digest', label='x', branch='native', status='complete')
    (folder/'result.json').write_text(json.dumps(row))
    assert authoritative_status(tmp_path, 'x', 'native', 'repair-digest') == 'complete'
    with pytest.raises(ValueError): authoritative_status(tmp_path,'x','native','control-digest')
    (folder/'result.json').unlink(); (folder/'slices').mkdir()
    (folder/'slices/01.started.json').write_text(json.dumps(row))
    with pytest.raises(ValueError): authoritative_status(tmp_path,'x','native','repair-digest')


def test_pending_cap_and_terminal_failure_no_retry():
    calls=[]; states=iter(['pending','complete'])
    assert run_cell(lambda: calls.append(1) or next(states), lambda:None) == 'complete'
    assert len(calls)==2
    assert run_cell(lambda:pytest.fail('retry'),lambda:'failed')=='failed'
    with pytest.raises(ValueError):run_cell(lambda:'pending',lambda:None)


def test_pending_requires_matching_named_receipt(tmp_path):
    folder=tmp_path/'native/slices';folder.mkdir(parents=True)
    start=dict(protocol_sha256='d',phase='baseline',slice=1)
    end=dict(protocol_sha256='d',label='x',branch='native',slice=1,status='pending')
    (folder/'baseline-01.started.json').write_text(json.dumps(start))
    (folder/'baseline-02.done.json').write_text(json.dumps(end))
    with pytest.raises(ValueError):authoritative_status(tmp_path,'x','native','d')
    (folder/'baseline-02.done.json').rename(folder/'baseline-01.done.json')
    assert authoritative_status(tmp_path,'x','native','d')=='pending'
    end['slice']=2;(folder/'baseline-01.done.json').write_text(json.dumps(end))
    with pytest.raises(ValueError):authoritative_status(tmp_path,'x','native','d')


def test_actual_continuation_original_seeds_and_condition_digest(tmp_path, monkeypatch):
    import sys
    monkeypatch.delitem(sys.modules,'adapter',raising=False)
    from types import SimpleNamespace
    from ports import continue_slice
    previous=load('ports151_runtime_test154',PRIOR/'ports.py')
    _,driver,adapter=previous.dependencies()
    driver.case_identity=lambda c:{'physical':'same'}
    plan={'discovery_digest':'sealed151'}; member=dict(label='x',binding={},sealed_search_path=str(tmp_path/'search'))
    search=tmp_path/'search'; regions=[dict(east_km=float(i),north_km=0.) for i in range(3)]
    driver.append(search/'result.json',dict(protocol_sha256='sealed151',label='x',status='complete',searches={'zero':dict(regions=regions)}))
    driver.append(search/'case.json',dict(protocol_sha256='sealed151',identity={'physical':'same'}))
    for i in range(3):
        point=[float(i),0.];vector=[*point,*([0.]*7)]
        for key,value in [(['bootstrap',point],dict(satellite_indices=[0,1],vector=vector)),(['point',*point,'zero-c'],dict(fit=dict(vector=vector,objective=1.,converged=True)))]:
            driver.append(search/'points'/(driver.canonical_digest(key)[7:]+'.json'),dict(protocol_sha256='sealed151',key=key,status='complete',value=value))
    class Expired(Exception):pass
    env={};exec('def load_case(binding): return None',env)
    env.update(core=SimpleNamespace(HARD60_SCORE={},RegionalSliceExpired=Expired),
               claim_slice=lambda *a,**k:1,recovered_region=lambda *a:pytest.fail('uninjected'),
               run_joint_stages=lambda *a:({}, {}, ['synthetic unavailable']))
    case=dict(observations=None,prior={},bank=SimpleNamespace(numbers=driver.np.array([1,2])),identity={'input_manifest_sha256':'input'})
    class Loader:
        load_case=env['load_case']
        def __call__(self,binding):return case
    calls=[]
    def factory(backend,arm):
        assert arm=='zero-c'
        def recover(o,b,p,t,s):
            calls.append(t);return dict(finals=[],recovery=s(t['key'],90,lambda:dict(status='synthetic-failure',calibration=None)))
        return recover
    for condition in ['control','repair']:
        row=continue_slice(plan,member,'zero',condition,tmp_path/condition,Loader(),driver,adapter,recovery_factory=factory)
        assert row['status']=='complete'
        assert row['protocol_sha256']==driver.canonical_digest(dict(plan,execution_condition=condition))
        assert row['reasons']==['synthetic unavailable']
    assert len(calls)==6 and all(t['identity']['local_radius_km']==25 for t in calls)
    # The same directory cannot be resumed with the other condition identity.
    with pytest.raises(ValueError):
        continue_slice(plan,member,'zero','repair',tmp_path/'control',Loader(),driver,adapter,recovery_factory=factory)
