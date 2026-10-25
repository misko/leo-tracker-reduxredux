"""Lean independent archived-input, null-density and physical-bound preflight."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
SCI=HERE.parent/'scientific'
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/nomination')
sys.path.insert(0,str(SCI))
import support_replay as s
import numerical_checks


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())


def null_qr(raw,covariance,times,period):
    """Independent augmented-QR density, avoiding full broad-prior covariance."""
    z=2*(times-times.min())/np.ptp(times)-1
    modes=np.polynomial.legendre.legvander(z,4)*period/np.sqrt(6)
    root=np.linalg.cholesky(covariance)
    u=solve_triangular(root,modes,lower=True)
    _,rr=np.linalg.qr(np.vstack((u,np.eye(5))),mode='reduced')
    shifted=raw[None]+np.arange(-4,5)[:,None]*period
    w=solve_triangular(root,shifted.T,lower=True).T
    coefficient=np.linalg.solve(rr,np.linalg.solve(rr.T,(w@u).T)).T
    residual=w-coefficient@u.T
    energy=np.sum(residual**2,axis=1)+np.sum(coefficient**2,axis=1)
    volume=2*np.log(np.diag(root)).sum()+2*np.log(abs(np.diag(rr))).sum()
    return float(-2*(logsumexp(-.5*(energy+volume+len(raw)*np.log(2*np.pi)))-np.log(9)))


def main():
    output=HERE/'preflight.json'
    if output.exists(): raise FileExistsError('preserve independent preflight')
    began=time.monotonic();protocol_path=SCI/'protocol.json';protocol_hash=sha(protocol_path)
    protocol=read(protocol_path);results=[]
    def check(name,condition,**evidence):
        results.append(dict(name=name,passed=bool(condition),**evidence))
    source_hashes={str(p):sha(p) for p in [Path(__file__),HERE/'numerical_checks.py',
        SCI/'support_bounds.py',SCI/'support_geometry.py',SCI/'support_math.py',
        SCI/'support_replay.py',SCI/'test_support.py',SCI/'PROTOCOL.md']}
    check('frozen protocol seal',read(SCI/'protocol_seal.json')['protocol_sha256']==protocol_hash)
    bad=[path for path,digest in protocol['source_input_hashes'].items() if sha(path)!=digest]
    check('all frozen scientific sources and inputs unchanged',not bad,bad_paths=bad,
          bindings=len(protocol['source_input_hashes']))
    old_seal=read(OLD/'RF_seal.json')
    old_bad=[path for path,digest in old_seal['files'].items() if sha(path)!=digest]
    check('old scientific capsule immutable',not old_bad and old_seal['protocol_sha256']==sha(OLD/'protocol.json'),
          bad_paths=old_bad,old_scientific_bindings=len(old_seal['files']))
    check('declared bounded old12-only design',protocol['maximum_trials']==12 and
          protocol['maximum_arm_rows']==24 and protocol['maximum_candidate_contexts']==192 and
          protocol['maximum_scientific_worker_seconds']==600 and protocol['workers']==2 and
          protocol['BLAS_threads']==1 and protocol['original_absolute_objective_tolerance']==1e-3 and
          protocol['original_alias_support']==list(range(-4,5)) and
          protocol['no_new_draws_parent_refits_positionfits_RF_GPS_or_operational_assignments'])
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(SCI),pattern='test_support.py')
    owned=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
    check('owned algebra/support/control tests independently rerun',owned.wasSuccessful(),
          tests=owned.testsRun,output=stream.getvalue())
    results.extend(numerical_checks.checks())
    maximum_null=0.;closure=0.;archive_rows=[]
    for case in ('DS24-0010','DS24-0011'):
        context=read(OLD/case/'context.json');ids=context['target_entries'][0]['observation_ids']
        for trial in range(6):
            directory=OLD/case/f'trial{trial}';screen=read(directory/'screen.json')
            with np.load(directory/'observations.npz') as obs:
                times=obs['times_s'].copy();native=obs['native_ids'].copy();values=obs['values_hz'].copy();q=obs['q'].copy()
            valid=list(native)==ids and len(native)==len(set(native)) and np.isfinite(values).all() and np.all(q>0)
            valid=bool(valid and not screen['forced_or_reserved_candidate'] and len(screen['candidate_indices'])==8 and
                [context['catalogue_norads'][j] for j in screen['candidate_indices']]==screen['candidate_norads'])
            for arm in ('c0','fitted_c'):
                with np.load(directory/(arm+'_conditional.npz')) as saved:
                    raw=saved['raw_hz'].copy();cov=saved['covariance_hz2'].copy();radio=saved['radio_mean_hz'].copy()
                closure=max(closure,float(np.max(abs(raw+radio-values))))
                np.linalg.cholesky(cov)
                oracle=null_qr(raw,cov,times,s.k.PERIOD)
                old=read(directory/(arm+'_result.json'))['null']['objective']
                comp=dict(d={'target_track':{'times':times}},raw=raw,covariance=cov,
                          shifts=np.arange(-4,5)[:,None]*np.ones((1,len(raw)))*s.k.PERIOD)
                candidate=s.null_reference(comp)
                delta=max(abs(oracle-old),abs(oracle-candidate))
                maximum_null=max(maximum_null,delta)
                archive_rows.append(dict(case=case,trial=trial,arm=arm,whole_source_unchanged=valid,
                    null_QR_objective=oracle,old_null_objective=old,new_eigen_null_objective=candidate,
                    maximum_null_discrepancy=delta))
    check('all12 exact old observations and ordinary shortlists retained',
          all(row['whole_source_unchanged'] for row in archive_rows),rows=24)
    check('same-data conditional raw plus frozen radio closure',closure<1e-8,
          maximum_error_hz=closure)
    check('all24 actual archived nulls agree with independent augmented-QR oracle',
          maximum_null<=1e-6,maximum_objective_discrepancy=maximum_null,rows=archive_rows)
    go_control=[]
    for go, should_pass in [(dict(approved=False,protocol_sha256='fixture'),False),
                           (dict(approved=True,protocol_sha256='wrong'),False),
                           (dict(approved=True,protocol_sha256='fixture'),True)]:
        def fake_read(path):
            name=Path(path).name
            if name=='protocol.json': return dict(source_input_hashes={})
            if name=='protocol_seal.json': return dict(protocol_sha256='fixture')
            if name=='preflight.json': return dict(all_passed=True,protocol_sha256='fixture')
            if name=='coordinator_go.json': return go
            raise AssertionError('unexpected gate input')
        with patch.object(s.r,'read',side_effect=fake_read),patch.object(s.r,'sha',return_value='fixture'):
            try: s.verify(approval=True); passed=True
            except ValueError: passed=False
        go_control.append(passed==should_pass)
    check('coordinator approval and exact-protocol gates exercised without workers',all(go_control))
    unchanged=protocol_hash==sha(protocol_path) and all(sha(path)==digest for path,digest in source_hashes.items())
    check('sources and protocol unchanged throughout independent checks',unchanged)
    elapsed=time.monotonic()-began
    previous_seconds=sum(read(p).get('numeric_seconds',0.) for p in
        (HERE/'narrow_mode_precheck.json',HERE/'numerical_precheck.json'))
    previous_seconds+=read(HERE/'narrow_mode_precheck.json')['prior_exploratory_seconds']
    receipt=dict(all_passed=all(row['passed'] for row in results),protocol_sha256=protocol_hash,
        scientific_permission='old12 archived replay only; coordinator go also required',
        checks=results,independent_sources=source_hashes,numeric_and_hash_wall_seconds=elapsed,
        previous_numeric_seconds=previous_seconds,cumulative_audit_seconds=elapsed+previous_seconds,
        maximum_audit_seconds=180,corpus_propagation_calls=0,position_fits=0,geographic_truth_read=False,
        synthetic_geometry_only=True,
        mathematical_review='positive Woodbury energy, actual interpolation support, mean/covariance derivative envelopes, original prior/finite-alias normalization, strict evidence dominance separate from absolute precision')
    output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=receipt['all_passed'],
        protocol_sha256=protocol_hash,cumulative_audit_seconds=receipt['cumulative_audit_seconds'],
        failed=[row['name'] for row in results if not row['passed']])))


if __name__=='__main__': main()
