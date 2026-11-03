import json
from types import SimpleNamespace

import pytest

import polish_position_structure_study as polish


def setup_case(tmp_path, monkeypatch, converged):
    study=polish.study
    monkeypatch.setattr(study,'OUT',tmp_path)
    source=tmp_path/'final'/'N01-fitted-c-A10.json'
    source.parent.mkdir()
    initial=dict(vector=[0.,0.,7.,3.,4.],point_km=[1.,0.],parameters=[0.],
        coefficient=7.,objective=10.,success=converged,fixed_location=False)
    source.write_text(json.dumps(dict(records=[initial],best=initial,objective=10.,converged=converged,distance_m=1000.)))
    monkeypatch.setattr(study,'inputs',lambda scan:(None,{},None,None,None))
    monkeypatch.setattr(study,'make_objective',lambda *args:SimpleNamespace(size=2))
    monkeypatch.setattr(study,'metrics',lambda obj,data,r:dict(objective=r['objective'],
        converged=r['success'],distance_m=1000.,kkt=0. if r['success'] else 1.))
    monkeypatch.setattr(study.previous,'objective',lambda *args:None)
    monkeypatch.setattr(study,'reprice',lambda obj,r,arm,stage:r)
    monkeypatch.setattr(study.previous,'finish',lambda *args:dict(data_nll=9.))
    return source,initial


def test_converged_case_has_same_budget_receipt_without_extra_optimization(tmp_path,monkeypatch):
    source,_=setup_case(tmp_path,monkeypatch,True)
    def forbidden(*args,**kwargs):raise AssertionError('Already converged')
    monkeypatch.setattr(polish.study,'slsqp_fit',forbidden)
    monkeypatch.setattr(polish.study,'fitted',forbidden)
    output=polish.run(('N01','fitted-c','A10'))
    saved=json.loads(open(output).read())
    assert saved['continuation']['maximum_budgets_s']==polish.BUDGETS
    assert len(saved['records'])==1 and source.exists()
    assert polish.run(('N01','fitted-c','A10'))==output


def test_continuation_preserves_rf_coefficient_with_added_quadratic_terms(tmp_path,monkeypatch):
    _,initial=setup_case(tmp_path,monkeypatch,False)
    calls=[]
    def slsqp(obj,best,budget):
        calls.append(('slsqp',budget))
        return dict(initial,objective=9.,coefficient=4.)  # generic solver's last term is not c
    def fisher(obj,best,stage,budget):
        assert best['coefficient']==7.
        calls.append(('fisher',budget))
        return dict(initial,objective=8.,success=True)
    monkeypatch.setattr(polish.study,'slsqp_fit',slsqp)
    monkeypatch.setattr(polish.study,'fitted',fisher)
    output=polish.run(('N01','fitted-c','A10'))
    saved=json.loads(open(output).read())
    assert saved['objective']==8. and saved['converged']
    assert calls==[('slsqp',25.),('fisher',20.)]
    assert not saved['continuation']['original_converged']


def test_cached_result_rejects_changed_source(tmp_path,monkeypatch):
    source,_=setup_case(tmp_path,monkeypatch,True)
    polish.run(('N01','fitted-c','A10'))
    source.write_text(source.read_text()+'\n')
    with pytest.raises(AssertionError):polish.run(('N01','fitted-c','A10'))
