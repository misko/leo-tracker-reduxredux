"""Lean independent RX2-source preflight; no corpus numerical evaluations."""
import ast
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time
from unittest.mock import patch

import numpy as np
import pytest

HERE=Path(__file__).resolve().parent
SCI=HERE.parent/'scientific'
sys.path.insert(0,str(SCI))
import witness02 as w
import test_witness02 as fixtures
import input_check


def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def function_source(path,name):
    text=Path(path).read_text();tree=ast.parse(text)
    node=next(q for q in tree.body if isinstance(q,ast.FunctionDef) and q.name==name)
    return ast.get_source_segment(text,node)


def main():
    output=HERE/'preflight.json'
    if output.exists():raise FileExistsError('preserve frozen preflight')
    started=time.monotonic();results=[]
    def check(name,passed,**detail):results.append(dict(name=name,passed=bool(passed),**detail))
    protocol_path=SCI/'protocol02.json';protocol_hash=sha(protocol_path);p=read(protocol_path)
    bindings=p['source_input_hashes'];bad=[path for path,h in bindings.items() if sha(path)!=h]
    check('exact revised protocol and all scientific/input bindings',
          protocol_hash==read(SCI/'protocol_seal02.json')['protocol_sha256'] and not bad,
          bindings=len(bindings),bad_paths=bad)
    check('no scientific run before independent preflight',not (SCI/'execution_started.json').exists())
    check('standing authorization exact',p['coordinator_authorization']==sha(HERE.parent/'COORDINATOR_PLAN.md'))
    results.extend(input_check.check_inputs())
    check('three complete matched sources and bounded denominators',
          [len(row['observation_ids']) for row in p['sources']]==[24,57,43] and
          p['maximum_owner_arm_results']==6 and p['maximum_candidate_contexts']==48 and
          p['budget']['cumulative_scientific_seconds']==600 and p['budget']['workers']==2 and
          p['budget']['numeric_threads']==1 and p['fitted_position_count']==0 and
          p['operational_identity_assignment'] is False and p['discovery_conditioned_evidence_executed'] is False)
    # The exact earlier stable reference is reused, not a newly tuned null.
    old_qr=Path('/srv/bulk/leo/research/ds24-identity-support-r01/audit/preflight.py')
    check('null QR function is byte-identical to independently audited reference',
          function_source(SCI/'witness02.py','null_qr')==function_source(old_qr,'null_qr') and
          str(old_qr) in bindings)
    test_status=pytest.main(['-q','-p','no:cacheprovider',str(SCI/'test_witness02.py')])
    check('all ten owned port/math controls independently rerun',test_status==0)

    # Exercise the real owner02 background port with existing predictive rows,
    # then compare with direct observation-space Gaussian conditioning.
    d,parent,cal,entries=fixtures.fake_context()
    d['entries']=[dict(track_index=2,component='t2',candidate_index=1,alias=0)]
    rng=np.random.default_rng(2026102531)
    he=rng.normal(size=(3,len(cal['coefficient'])))*.7
    intercept=np.array([2.,-1.,3.])
    before={key:value.copy() for key,value in cal.items()}
    with patch.object(w.k.owners.m.r,'build',return_value=parent),patch.object(
        w.k.owners.m.original,'geometry_features',return_value=dict(features=he,intercept=intercept)):
        actual=w.background(d,'c0',np.zeros(2),entries)
        tv,values,sigma,groups,_=w.k.owners.m.original.linear_geometry(parent,w.clean_entries(d,entries))
        ev,ey,es,eg,_=w.k.owners.m.original.linear_geometry(parent,d['entries'])
        hw=tv.hardware.copy();hw[:,[4,6]]*=10
        ht=np.column_stack((hw,tv.smooth*200))
        weights=cal['noise_precision'][parent.noise_groups]/parent.point_noise**2
        train=cal['features'];precision=np.diag(cal['coefficient_prior_precision'])+train.T@(weights[:,None]*train)
        v=np.linalg.inv(precision);mean=cal['coefficient']
        cee=he@v@he.T+np.diag(2*es**2)+300**2*(eg[:,None]==eg[None,:])
        cwe=ht@v@he.T
        residual=ey-ev.q*intercept-he@mean
        expected_raw=values-ht@mean-cwe@np.linalg.solve(cee,residual)
        expected_cov=np.diag(2*sigma**2)+ht@v@ht.T+300**2*(groups[:,None]==groups[None,:])-cwe@np.linalg.solve(cee,cwe.T)
        raw_error=float(np.max(abs(actual['raw']-expected_raw)))
        covariance_error=float(np.max(abs(actual['covariance']-expected_cov)))
        covariance_relative=float(np.linalg.norm(actual['covariance']-expected_cov)/np.linalg.norm(expected_cov))
        actual_root=np.linalg.cholesky(actual['covariance']);expected_root=np.linalg.cholesky(expected_cov)
        left=np.linalg.solve(actual_root,actual['covariance']-expected_cov)
        whitened_error=float(np.linalg.norm(np.linalg.solve(actual_root,left.T).T))
        def density_cost(root):
            z=np.linalg.solve(root,actual['raw'])
            return float(z@z+2*np.log(np.diag(root)).sum()+len(z)*np.log(2*np.pi))
        density_error=abs(density_cost(actual_root)-density_cost(expected_root))
        check('existing-predictive joint conditioning matches independent dense Gaussian oracle',
              raw_error<1e-7 and covariance_relative<1e-12 and whitened_error<1e-6 and density_error<1e-3,
              maximum_mean_error_hz=raw_error,maximum_covariance_error_hz2=covariance_error,
              covariance_scale_hz2=float(np.max(abs(expected_cov))),covariance_relative_error=covariance_relative,
              covariance_whitened_error=whitened_error,density_objective_error=density_error,
              oracle_tolerance_explanation='PERIOD-scale hardware covariance requires relative/whitened comparison; absolute scientific objective tolerance remains1e-3')
        check('predictive and target evaluations preserve original curved state',
              all(np.array_equal(value,cal[key]) for key,value in before.items()))
        single=w.background(d,'c0',np.zeros(2),entries[:1])
        marginal=w.marginal(actual,actual['slices'][0])
        check('single-source marginal equality with old predictive conditioning retained',
              np.allclose(single['raw'],marginal['raw'],atol=1e-9,rtol=0) and
              np.allclose(single['covariance'],marginal['covariance'],atol=1e-8,rtol=0))

    # q must occur once, including catalogue phase derivatives.
    dd=dict(d,all_means=np.zeros(12),widths=np.ones(12));dd['scan'].norads=np.arange(12);dd['scan'].sky={}
    base=np.arange(36.).reshape(12,3);derivative=np.ones_like(base)*.37;q=np.array([.9,1.,1.1])
    def fake_frequency(bank,times,*args,phase_seconds):
        return base+np.asarray(phase_seconds)[:,None]*derivative,np.ones_like(base)
    with patch.object(w.k,'phase_frequency_grid',side_effect=fake_frequency):
        cat=w.catalogue(dd,np.zeros(2),entries[0],q)
    check('RF/q applied once in physical catalogue mean and tangent',
          np.array_equal(cat['frequency_hz'],base*q) and
          np.allclose(cat['derivative_hz_per_s'],derivative*q,atol=1e-11,rtol=0))
    # Actual process submissions carry only serializable metadata/coordinates.
    check('worker payload serializable without mutable fitted-context closures',
          bool(pickle.dumps((np.zeros(2),p['sources'],'c0',123.))) and
          'pool.submit(arm_worker, x, owners, arm, deadline)' in (SCI/'witness02.py').read_text())
    check('sources and protocol unchanged throughout preflight',
          protocol_hash==sha(protocol_path) and all(sha(path)==h for path,h in bindings.items()))
    elapsed=time.monotonic()-started;prior=read(HERE/'input_check.json')['seconds']
    failed=read(HERE/'preflight01.json')
    prior+=failed['numeric_and_hash_wall_seconds']+1.316950697
    receipt=dict(all_passed=all(q['passed'] for q in results),protocol_sha256=protocol_hash,
        checks=results,source_sha256=sha(__file__),independent_input_source_sha256=sha(HERE/'input_check.py'),
        numeric_and_hash_wall_seconds=elapsed,cumulative_audit_seconds=elapsed+prior,cap_seconds=180,
        corpus_propagation_calls=0,new_owner_CFO_scores=0,position_fits=0,geographic_truth_read=False,
        scope='one bounded first-stage execution only; standing coordinator plan already authorizes on pass',
        interpretation='finite-pool conditional ordering distinct from absolute precision, curve adequacy and identity qualification')
    receipt['preserved_failed_preflight_sha256']=sha(HERE/'preflight01.json')
    receipt['preserved_failed_source_sha256']=sha(HERE/'preflight01.py')
    receipt['technical_audit_revision']='scale-aware covariance fixture plus whitened/density checks; frozen scientific source and thresholds unchanged'
    receipt['earlier_scale_probe_wall_seconds']=1.316950697
    output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=receipt['all_passed'],protocol_sha256=protocol_hash,
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'],failed=[q for q in results if not q['passed']])))


if __name__=='__main__':main()
