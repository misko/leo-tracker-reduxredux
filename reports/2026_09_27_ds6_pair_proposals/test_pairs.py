"""Proposal algebra and exact-marginalization acceleration checks."""
import importlib.util
import json
import hashlib
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from scipy.stats import t

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run import pair_squared_error,u
from collapsed import PhaseIntegral,combine
from full import zero_offset_scores


def test_sse_matrix_matches_explicit_profiled_residuals():
    rng=np.random.default_rng(25);a=rng.normal(size=(5,13))*1000;b=rng.normal(size=(7,13))*1000;y=rng.normal(size=13)*1000
    residual=y[None,None,:]-(b[None,:,:]-a[:,None,:]);residual-=residual.mean(axis=-1,keepdims=True)
    np.testing.assert_allclose(pair_squared_error(a,b,y),np.sum(residual**2,axis=-1),rtol=1e-12,atol=1e-7)
    np.testing.assert_allclose(pair_squared_error(a+12345,b-8910,y+999),pair_squared_error(a,b,y),rtol=1e-12,atol=1e-7)


def test_lookup_matches_original_concentration_integration():
    kappa=np.geomspace(.1,1e4,129);weights=np.ones(129);weights[[0,-1]]=.5;weights/=weights.sum()
    for n in [2,4]:
        lut=PhaseIntegral(n,kappa,weights)
        assert lut.audit()<1e-5
        for gap in [0.,1e-12,1e-6,.01,.5,float(n)]:
            assert abs(lut.from_resultant(n-gap)-lut.exact(n-gap))<1e-5


def test_collapsed_group_sums_match_original_likelihood():
    rng=np.random.default_rng(26);kappa=np.geomspace(.1,1e4,129);weights=np.ones(129);weights[[0,-1]]=.5;weights/=weights.sum()
    mask=np.array([True,False,True,False]);lut_train=PhaseIntegral(2,kappa,weights);lut_all=PhaseIntegral(4,kappa,weights)
    banks=[];groups=[]
    for _ in range(2):
        y=rng.normal(size=4);p=rng.normal(size=(3,7,4));a=rng.normal(size=(3,7));b=rng.normal(size=(3,7))-4
        banks.append(dict(y=y,mask=mask,geometry=p,cfo_train=a,cfo_joint=b))
        fit=np.stack([lut_train.score(y[mask],sign*p[...,mask]) for sign in [-1,1]])
        all_=np.stack([lut_all.score(y,sign*p) for sign in [-1,1]])
        groups.append(dict(train=logsumexp(a+fit,axis=-1),phase_all=logsumexp(a+all_,axis=-1),cfo_all=logsumexp(b+fit,axis=-1),cfo_train=logsumexp(a,axis=-1),cfo_joint=logsumexp(b,axis=-1)))
    expected=u.score_banks(banks,kappa,weights);actual=combine(groups)
    for key in ['training_log_evidence','held_phase_log_predictive','held_cfo_log_predictive','cfo_only_held_log_predictive']:
        assert abs(expected[key]-actual[key])<1e-5


def test_zero_offset_is_normalized_student_predictive_density():
    residual=np.array([[1.,3.,-7.,4.],[400.,300.,200.,100.]])
    mask=np.array([True,False,False,True]);sigma=27.
    train,joint=zero_offset_scores(residual,mask,sigma)
    expected=t.logpdf(residual/sigma,4)-np.log(sigma)
    np.testing.assert_allclose(train,expected[:,mask].sum(axis=-1),atol=1e-12)
    np.testing.assert_allclose(joint,expected.sum(axis=-1),atol=1e-12)
    changed=residual.copy();changed[:,~mask]+=1000
    np.testing.assert_array_equal(zero_offset_scores(changed,mask,sigma)[0],train)


def test_complete_catalogue_pair_accounting_and_source_bindings():
    proposal=json.loads((HERE/'results.json').read_text())
    for prefix in ['full','zero-offset']:
        result=json.loads((HERE/(prefix+'-results.json')).read_text())
        protocol=json.loads((HERE/(prefix+'-protocol.json')).read_text())
        assert result['complete'] and result['protocol_sha256']==hashlib.sha256((HERE/(prefix+'-protocol.json')).read_bytes()).hexdigest()
        assert protocol['proposal_results_sha256']==hashlib.sha256((HERE/'results.json').read_bytes()).hexdigest()
        assert len(result['scans'])==len(proposal['scans'])==2
        for scan,old in zip(result['scans'],proposal['scans']):
            assert scan['session_id']==old['session_id']
            for g,og in zip(scan['groups'],old['groups']):
                assert g['group']==og['group']
                assert g['pair_counts']==[v['all_visible_pairs'] for v in og['proposal_inventory']]
                assert len(g['maxima'])==11
            for r in scan['retention']:
                mass=[r['mass'][str(k)] for k in [256,512,1024]]
                assert all(-1e-10<=v<=1+1e-10 for v in mass)
                assert all(a<=b+1e-10 for a,b in zip(mass,mass[1:]))
            # With no geometric factor, phase cannot update the CFO hypotheses.
            null=scan['response_only']
            assert abs(null['held_cfo_log_predictive']-null['cfo_only_held_log_predictive'])<1e-8
