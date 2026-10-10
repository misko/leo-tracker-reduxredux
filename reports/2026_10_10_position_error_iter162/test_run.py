"""Actual runner with injected synthetic ports; no recording or optimizer work."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location('run162_test',Path(__file__).with_name('run.py'))
RUN=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUN)


def fixture():
    scores=[];fits=[]
    class Model:
        def __init__(self,fold):self.fold=fold
        def evaluate_joint(self,v,c):
            scores.append((self.fold,v.copy(),c.copy()))
            return 3.,np.zeros(8),np.zeros(4),NS(nll=2.,responsibilities=np.ones((2,1)),residual_hz=np.ones((2,1)))
    vector=np.zeros(8);vector[2]=12.
    coefficients=np.array([3.,4.,0.,0.])
    prepared=dict(vector=vector,clock=coefficients,counts=[2,2],
        models={f'train{i}':Model(i) for i in (0,1)},positions={'zero-c':np.array([1.,2.]),'fitted-c':np.array([3.,4.])},
        fingerprint='same',identity=lambda:'same',preflight={'calls':3})
    def execute(model,v,c,**options):
        fits.append((model.fold,v.copy(),c.copy(),options['arm']))
        # A changed nuisance must never be reused as another cell's start.
        v[2]=99.;c[0]=100.
        return dict(status='qualified',solver=dict(vector=v.tolist(),clock_coefficients=c.tolist()),audit={'qualified':True})
    ports=dict(np=np,execute=execute,fit=None,problem=None,plain=lambda v:v)
    return prepared,ports,fits,scores


def test_eight_independent_hypothesis_arm_starts_and_opposite_scores(tmp_path):
    prepared,ports,fits,scores=fixture()
    result=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    assert result['status']=='complete' and result['scores_complete'] and len(fits)==len(scores)==8
    for index,(fold,v,c,arm) in enumerate(fits):
        hypothesis='zero-c' if index<4 else 'fitted-c'
        np.testing.assert_array_equal(v[:2],prepared['positions'][hypothesis])
        assert v[2]==12. and v[6]==0
        np.testing.assert_array_equal(c,[3.,4.,0.,0.])
        assert scores[index][0]==1-fold
    assert prepared['vector'][2]==12. and prepared['clock'][0]==3.
    for key,binding in result['cells'].items():
        row=json.loads((tmp_path/'member'/binding['path']).read_text())
        claim=json.loads((tmp_path/'member'/(key+'.claim.json')).read_text())
        assert key=='--'.join(row[k] for k in ('hypothesis','mode','arm'))
        assert all(claim[k]==row[k] for k in ('hypothesis','mode','arm','protocol_sha256'))
        assert set(row['scores'])==({'1'} if row['mode']=='train0' else {'0'})
    assert RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:pytest.fail('retry'))==result


def test_missing_inputs_write_all_eight_failed_cells(tmp_path):
    def fail(*a):raise ValueError('missing hypothesis')
    result=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=fail)
    assert result['status']=='failed' and len(result['cells'])==8
    assert all(v['status']=='failed' for v in result['cells'].values())


def test_orphan_member_claim_never_retried(tmp_path):
    folder=tmp_path/'member';folder.mkdir();(folder/'claim.json').write_text('{}')
    with pytest.raises(FileExistsError,match='no automatic retry'):
        RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:pytest.fail('retry'))


def test_held_failure_preserves_fit_qualification(tmp_path):
    prepared,ports,_,_=fixture()
    def fail(*a):raise RuntimeError('held failed')
    prepared['models']['train0'].evaluate_joint=fail
    result=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    assert result['status']=='complete' and not result['scores_complete']
    row=json.loads((tmp_path/'member'/'zero-c--train1--zero-c.json').read_text())
    assert row['status']=='qualified' and row['score_error'] and row['solver']


def test_model_mutation_blocks_remaining_fits(tmp_path):
    prepared,ports,fits,_=fixture();original=ports['execute'];changed=[False]
    def execute(*a,**k):
        result=original(*a,**k);changed[0]=True;return result
    ports['execute']=execute;prepared['identity']=lambda:'changed' if changed[0] else 'same'
    result=RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    assert result['status']=='failed' and len(fits)==1
    row=json.loads((tmp_path/'member'/'zero-c--train0--zero-c.json').read_text())
    assert row['solver'] and 'mutated' in row['error']


def test_swapped_hypothesis_claim_rejected(tmp_path):
    prepared,ports,_,_=fixture()
    RUN.run_member({'label':'member'},tmp_path,'digest',dependency_factory=lambda _:ports,prepare=lambda *a:prepared)
    path=tmp_path/'member'/'zero-c--train0--zero-c.claim.json'
    row=json.loads(path.read_text());row['hypothesis']='fitted-c';path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='Foreign'):
        RUN.run_member({'label':'member'},tmp_path,'digest')


def hypothesis_fixture(monkeypatch):
    prepared,ports,_,_=fixture()
    member=dict(label='member',hypotheses={})
    documents={}
    for h in RUN.HYPOTHESES:
        member['hypotheses'][h]=dict(raw_path=h,raw_sha256='raw',claim_path=h+'claim',claim_sha256='claim',
            protocol_sha256='original',position=prepared['positions'][h].tolist())
        identity=dict(label='member',mode='full',arm=h,protocol_sha256='original')
        documents[h]=dict(identity,status='qualified',audit={'qualified':True},
                          solver={'vector':prepared['positions'][h].tolist()+[0.]*6})
        documents[h+'claim']=copy.deepcopy(identity)
    monkeypatch.setattr(RUN.PREVIOUS,'prepare_member',lambda *a:prepared)
    monkeypatch.setattr(RUN.PREVIOUS,'read_bound',lambda path,digest:documents[path])
    return member,ports,documents


def test_actual_preparation_authenticates_both_ordinary_hypotheses(monkeypatch):
    member,ports,documents=hypothesis_fixture(monkeypatch)
    result=RUN.prepare_member(member,ports)
    assert set(result['positions'])==set(RUN.HYPOTHESES)
    documents['fitted-c']['solver']['vector'][0]+=1.
    with pytest.raises(ValueError,match='changed geometry'):
        RUN.prepare_member(member,ports)


@pytest.mark.parametrize('fault',['claim','raw','qualification','missing'])
def test_hypothesis_admission_rejects_foreign_or_unqualified(monkeypatch,fault):
    member,ports,documents=hypothesis_fixture(monkeypatch)
    if fault=='claim':documents['fitted-cclaim']['arm']='zero-c'
    if fault=='raw':documents['zero-c']['protocol_sha256']='other'
    if fault=='qualification':documents['zero-c']['audit']['qualified']=False
    if fault=='missing':del member['hypotheses']['fitted-c']
    with pytest.raises(ValueError):RUN.prepare_member(member,ports)
