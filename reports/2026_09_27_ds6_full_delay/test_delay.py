import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('delay',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_delay_density_and_held_isolation():
    rng=np.random.default_rng(4);r=rng.normal(size=(3,4));df=np.array([1000.,2000.,3000.,4000.]);d=np.linspace(-1e-5,1e-5,7);mask=np.array([True,False,True,False])
    fit,all_=m.delay_scores(r,df,d,mask);direct=np.cos(r[:,:,None]-2*np.pi*df[None,:,None]*d[None,None,:])-m.log_i0(1.)
    np.testing.assert_allclose(fit,direct[:,mask].sum(axis=1),atol=1e-12);np.testing.assert_allclose(all_,direct.sum(axis=1),atol=1e-12)
    r[:,~mask]+=10;np.testing.assert_array_equal(m.delay_scores(r,df,d,mask)[0],fit)


def test_uniform_offset_matches_dense_quadrature():
    r=np.array([[.1,.4,-.2,.7]]);mask=np.array([True,True,False,False]);offset=np.linspace(-np.pi,np.pi,10000,endpoint=False)
    fit,all_=m.offset_scores(r,mask)
    for take,expected in [(mask,fit),(np.ones(4,dtype=bool),all_)]:
        density=np.sum(np.cos(r[0,take,None]-offset),axis=0)-take.sum()*m.log_i0(1.)
        np.testing.assert_allclose(m.logsumexp(density)-np.log(len(offset)),expected[0],atol=1e-12)


def test_completed_full_pair_accounting_and_null_cancellation():
    root=Path(__file__).resolve().parent
    result=json.loads((root/'results-101.json').read_text())
    prior=json.loads((root.parent/'2026_09_27_ds6_pair_proposals/full-results.json').read_text())
    assert result['complete'] and len(result['scans'])==2
    assert result['protocol_sha256']==hashlib.sha256((root/'protocol-101.json').read_bytes()).hexdigest()
    for scan,old in zip(result['scans'],prior['scans']):
        assert scan['session_id']==old['session_id']
        for group,previous in zip(scan['groups'],old['groups']):
            assert group['group']==previous['group'] and group['pair_counts']==previous['pair_counts']
        # Geometry-zero phase factors are independent of identity and timing.
        # Their integration must cancel out of a conditional CFO score.
        for arm in ['delay_null','offset_null']:
            np.testing.assert_allclose(scan['scores'][arm]['held_cfo'],old['response_only']['cfo_only_held_log_predictive'],atol=1e-9,rtol=0)
