import numpy as np
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('r03_coverage_mechanism',Path(__file__).with_name('run.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
c,CASE,OLD=module.c,module.CASE,module.OLD
nominate,predictive,posterior_root=module.nominate,module.predictive,module.posterior_root


def test_masks_and_common_holdout():
    d=c.context(CASE);prior=c.load(OLD/'matched/protocol.json')['cases'][CASE]
    masks,held,selection=nominate(d,prior)
    assert masks['overlap'].sum()==1034
    assert selection['dominant']['norad']==67123
    assert [r['norad'] for r in selection['omitted']]==[65089,68102]
    assert not np.any(masks['plus_AB'] & held)
    assert np.array_equal(masks['plus_AB']|held,masks['full'])
    assert held.sum()==1346


def test_actual_redaction_and_predictive_covariance():
    d=c.context(CASE);prior=c.load(OLD/'matched/protocol.json')['cases'][CASE]
    masks,held,_=nominate(d,prior);train=dict(d,keep=masks['overlap'],entries=[])
    p=c.frozen.build(train,'c0',np.zeros(len(d['means'])),prior['packets']['c0'])
    x=np.zeros(2);before=p.calculate(x)
    p.values[held]+=123456.
    after=p.calculate(x)
    np.testing.assert_array_equal(before['coefficient'],after['coefficient'])
    np.testing.assert_array_equal(before['residual'],after['residual'])
    raw,u,sigma=predictive(p,after,train,held)
    root=posterior_root(p,after,train)
    subset=np.arange(min(20,len(raw)));f=after['features'][held][subset]
    dense=np.diag(sigma[subset]**2)+f@np.linalg.solve(root.T,np.linalg.solve(root,f.T))
    actual=np.diag(sigma[subset]**2)+u[subset]@u[subset].T
    np.testing.assert_allclose(actual,dense,rtol=1e-10,atol=1e-5)
    score=c.h.gaussian_score(raw[subset],u[subset],sigma[subset])
    expected=raw[subset]@np.linalg.solve(dense,raw[subset])+np.linalg.slogdet(dense)[1]+len(subset)*np.log(2*np.pi)
    np.testing.assert_allclose(score['negative_twice_log_density'],expected,rtol=1e-9)
