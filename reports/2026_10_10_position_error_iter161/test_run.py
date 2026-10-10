"""Injected orchestration checks; no real models, optimizers or recordings."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location('run161_test',Path(__file__).with_name('run.py'))
RUN=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUN)


def fake():
    seen=[]
    class Model:
        def evaluate_joint(self,v,c):
            return 3.,np.zeros(8),np.zeros(4),NS(nll=2.,responsibilities=np.ones((2,1)),residual_hz=np.ones((2,1)))
    models={name:Model() for name in RUN.MODES}
    prepared=dict(models=models,vector=np.zeros(8),clock=np.zeros(4),counts=[2,2],
                  identity=lambda:'same',fingerprint='same',preflight={'calls':3})
    def execute(model,v,c,**options):
        seen.append((v.copy(),c.copy(),options['arm']))
        v[0]=1
        return dict(status='qualified',solver=dict(vector=v.tolist(),clock_coefficients=c.tolist()),
                    audit={'qualified':True})
    ports=dict(np=np,execute=execute,fit=None,problem=None,plain=lambda x:x)
    return ports,prepared,seen


def test_six_cells_common_seed_fixed_scores_and_idempotent_terminal(tmp_path):
    ports,prepared,seen=fake();member={'label':'member'}
    result=RUN.run_member(member,tmp_path,'digest',dependency_factory=lambda _:ports,
                          prepare=lambda *a:prepared)
    assert result['status']=='complete' and len(seen)==6
    assert all(np.array_equal(v,np.zeros(8)) and np.array_equal(c,np.zeros(4)) for v,c,a in seen)
    assert prepared['vector'][0]==0
    for key,binding in result['cells'].items():
        cell=json.loads((tmp_path/'member'/binding['path']).read_text())
        assert cell['scores']['0']['nll']==2 and cell['scores']['1']['observations']==2
        assert cell['mode']+'--'+cell['arm']==key
        assert (tmp_path/'member'/(key+'.claim.json')).exists()
    old=RUN.run_member(member,tmp_path,'digest',dependency_factory=lambda _:pytest.fail('replayed'))
    assert old==result


def test_input_failure_preserves_six_failed_cells(tmp_path):
    def fail(member):raise RuntimeError('source unavailable')
    row=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=fail)
    assert row['status']=='failed' and len(row['cells'])==6
    assert all(c['status']=='failed' for c in row['cells'].values())
    assert 'source unavailable' in row['preparation_error']


def test_orphan_claim_never_restarts(tmp_path):
    directory=tmp_path/'member';directory.mkdir()
    (directory/'claim.json').write_text(json.dumps({'label':'member','protocol_sha256':'digest'}))
    with pytest.raises(FileExistsError,match='no automatic retry'):
        RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:pytest.fail('replayed'))


def test_unqualified_cell_is_not_scored_and_other_cells_continue(tmp_path):
    ports,prepared,_=fake();original=ports['execute'];count=[0]
    def execute(*a,**k):
        count[0]+=1
        return dict(status='unqualified',solver={'preserved':True}) if count[0]==1 else original(*a,**k)
    ports['execute']=execute
    row=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    cell=json.loads((tmp_path/'member'/'full--zero-c.json').read_text())
    assert row['status']=='failed' and count[0]==6
    assert cell['scores'] is None and cell['solver']['preserved']


def test_held_score_failure_does_not_discard_qualified_position(tmp_path):
    ports,prepared,_=fake()
    def broken(*a):raise RuntimeError('held scoring failed')
    prepared['models']['train0'].evaluate_joint=broken
    row=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    assert row['status']=='complete' and row['scores_complete'] is False
    assert all(cell['status']=='qualified' for cell in row['cells'].values())
    cell=json.loads((tmp_path/'member'/'full--zero-c.json').read_text())
    assert cell['status']=='qualified' and cell['audit']['qualified']
    assert cell['scores']['0']['status']=='failed' and cell['scores']['1']['status']=='complete'
    assert cell['score_error'] and cell['solver']['vector'][0]==1


def test_model_mutation_preserves_solver_and_blocks_later_fits(tmp_path):
    ports,prepared,seen=fake();original=ports['execute'];changed=[False]
    def execute(*a,**k):
        value=original(*a,**k);changed[0]=True;return value
    ports['execute']=execute;prepared['identity']=lambda:'changed' if changed[0] else 'same'
    row=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    assert row['status']=='failed' and len(seen)==1
    cell=json.loads((tmp_path/'member'/'full--zero-c.json').read_text())
    assert cell['solver'] and 'mutated' in cell['error']


def test_terminal_hash_or_foreign_claim_rejected(tmp_path):
    ports,prepared,_=fake()
    RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    path=tmp_path/'member'/'full--zero-c.json'
    value=json.loads(path.read_text());value['extra']='changed';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='hash differs'):
        RUN.run_member({'label':'member'},tmp_path,'digest')


def preparation_fixture(monkeypatch):
    full=NS(observations=NS(window_ids=('a','b')),index=None)
    def terms(nll,values):
        array=np.array(values,float).reshape(-1,1)
        return NS(nll=nll,responsibilities=array,residual_hz=array,prediction_gradient=array)
    full.evaluate_joint=lambda v,c:(6.,np.ones(8)*3,np.ones(4)*3,terms(4,[1,2]))
    def row(model,indices):
        result=NS(_delegate=NS(index=indices),index=indices)
        result.evaluate_joint=lambda v,c:(4.,np.ones(8)*2,np.ones(4)*2,terms(2,[i+1 for i in indices]))
        return result
    selected=dict(label='member',branch='native',protocol_sha256='original')
    folds=dict(label='member',status='complete',protocol_sha256='folds',groups=dict(session_id='s',
        observation_order_signature='order',grouping=dict(folds={'0':[0],'1':[1]})))
    monkeypatch.setattr(RUN,'read_bound',lambda path,sha: selected if path=='selected' else folds)
    member=dict(label='member',selected_path='selected',selected_sha256='x',selected_protocol_digest='original',
        fold_path='folds',fold_sha256='y',fold_protocol_digest='folds',binding=dict(session_id='s',
        expected_input_binding={'observation_order_signature':'order'}))
    ports=dict(np=np,loader=lambda b:{},reconstruct=lambda *a,**k:dict(model=full,vector=np.zeros(8),
        clock=np.zeros(4),saved_objective=6.),construct=None,components=None,problem=None,
        fingerprint=lambda model:{'index':model.index},row_objective=row,
        prior_terms=lambda *a:(2.,np.ones(8),np.ones(4)))
    return member,ports,folds


def test_actual_preparation_decomposition_terms_and_partition(monkeypatch):
    member,ports,folds=preparation_fixture(monkeypatch)
    prepared=RUN.prepare_member(member,ports)
    assert prepared['preflight']['decomposition_max_abs']==[0.,0.,0.]
    assert all(v==0 for v in prepared['preflight']['likelihood_term_max_abs'].values())
    folds['groups']['grouping']['folds']['1']=[0]
    with pytest.raises(ValueError,match='partition'):
        RUN.prepare_member(member,ports)


def test_bad_decomposition_prevents_fits(monkeypatch):
    member,ports,_=preparation_fixture(monkeypatch)
    ports['prior_terms']=lambda *a:(5.,np.ones(8),np.ones(4))
    with pytest.raises(ValueError,match='mismatch'):
        RUN.prepare_member(member,ports)
