from types import SimpleNamespace
import numpy as np
import pytest
import probe_ds23_position_cavity as cavity
from run_algo01_ds23_sample import read


def test_actual_held_value_perturbation_check_detects_an_unmasked_objective():
    p=SimpleNamespace(values=np.array([2.,7.,4.]),keep=np.array([True,False,True]),lower=np.full(2,-12.5),upper=np.full(2,12.5))
    def calculate(x):
        value=p.values[p.keep].sum()+x.sum()
        return dict(negative_twice_elbo=value,coefficient=np.array([value]))
    p.calculate=calculate;original=p.values.copy()
    checks=cavity.prove_exclusion(p,np.array([.4,-.2]))
    assert len(checks)==3 and all(c['loss_difference']==c['coefficient_difference']==0 for c in checks)
    np.testing.assert_array_equal(p.values,original)
    p.calculate=lambda x:dict(negative_twice_elbo=p.values.sum(),coefficient=np.array([p.values.sum()]))
    with pytest.raises(ValueError,match='held CFO entered'):cavity.prove_exclusion(p,np.zeros(2))
    np.testing.assert_array_equal(p.values,original)


def test_cavity_position_covariance_matches_dense_joint_precision_and_ignores_held_rows(monkeypatch):
    rng=np.random.default_rng(80);u=rng.normal(size=(14,4));j=rng.normal(size=(14,2));keep=np.ones(14,bool);keep[-3:]=False
    prior=np.array([1.,2.,3.,4.]);p=SimpleNamespace(keep=keep,q=np.ones(14),noise_groups=np.zeros(14,int),point_noise=np.ones(14))
    p.calculate=lambda x:dict(coefficient=np.zeros(4),features=u,coefficient_prior_precision=prior,noise_precision=np.array([.7]))
    monkeypatch.setattr(cavity,'geometry_features',lambda p,x,h:dict(intercept=j@x,features=u))
    actual=cavity.position_covariance(p,np.zeros(2),np.array([.8]))
    design=np.column_stack((j,u))[keep];precision=design.T@design*.7*.8+np.diag(np.r_[0.,0.,prior])
    np.testing.assert_allclose(actual,np.linalg.inv(precision)[:2,:2],atol=1e-12)
    j[~keep]*=1e6;u[~keep]*=1e6
    np.testing.assert_allclose(cavity.position_covariance(p,np.zeros(2),np.array([.8])),actual,atol=1e-12)


def test_nonconverged_family_does_not_discard_another_familys_offer(tmp_path,monkeypatch):
    source=tmp_path/'incumbent.json';source.write_text('{}')
    base=SimpleNamespace(rows=[dict(candidate_index=0),dict(candidate_index=1)],slices=[slice(0,1),slice(1,2)])
    d=dict(base=base,keep=np.ones(2,bool),scan=SimpleNamespace(norads=np.array([100,101,102])),node={},
        powers=np.ones(2),means=np.zeros(2),model={},binding=source)
    monkeypatch.setattr(cavity,'OUT',tmp_path)
    for v in cavity.VARIANTS:(tmp_path/v).mkdir()
    monkeypatch.setattr(cavity.old,'setup',lambda case:d)
    def fit(scan,node,keep,*args):
        return dict(final_phase_change_s=.02 if not keep[0] else 0.,endpoint_east_north_km=[0.,0.],phase_reference=[0.,0.])
    monkeypatch.setattr(cavity,'refit',fit)
    p=SimpleNamespace(lower=np.full(2,-12.5),upper=np.full(2,12.5),calculate=lambda x:dict(negative_twice_elbo=0.))
    monkeypatch.setattr(cavity.old,'family_data',lambda d,t:dict(p=p,values=np.ones(1),members=[dict(component='other')],held_ids=['other'],cavity_phase_change_s=0.))
    monkeypatch.setattr(cavity,'position_covariance',lambda *a:np.eye(2)*.01)
    monkeypatch.setattr(cavity,'prove_exclusion',lambda *a:[])
    monkeypatch.setattr(cavity,'coarse',lambda *a:dict(score=np.array([4.,5.,6.]),aliases=np.zeros((3,1),int)))
    monkeypatch.setattr(cavity.old,'candidate_prediction',lambda d,data,j,alias:dict(candidate_index=j,norad=100+j,aliases=alias,score=4.+j,qualified=True))
    assert cavity.one('DS23-0001')['status']=='complete'
    for variant in cavity.VARIANTS:
        saved=read(tmp_path/variant/'DS23-0001_nominations.json')
        assert saved['families'][0]['best'] is None
        assert saved['families'][0]['skipped_reason']=='other_family_position_phase_not_converged'
        assert saved['families'][1]['best']['candidate_index']==0
        assert abs(saved['families'][1]['predictive_gain']-1.)<1e-12
