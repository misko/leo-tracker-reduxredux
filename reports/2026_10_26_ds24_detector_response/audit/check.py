"""Independent algebra, binding and saved-artifact checks; no scientific reruns."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(files):
    for p,h in files.items():assert sha(p)==h,p
    return len(files)
def save(name,data):
    with (ROOT/'audit'/name).open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def influence_preflight():
    start=time.monotonic();here=ROOT/'influence';p=read(here/'protocol.json');checked=bind(p['bindings'])
    assert sha(here/'protocol.json')=='efbc9008eaae8ed87616aa673fa571bc11a38168a9f97c58866df2881bc882b5'
    assert p['cases']==['DS24-0010','DS24-0011'] and p['arms']==['c0','fitted_c']
    assert p['maximum_cumulative_worker_seconds']==180 and p['workers']==p['BLAS_threads']==1
    assert p['no_IQ_detector_position_or_GPS']
    source=ROOT.parent/'ds25-20261024';old=ROOT.parent/'ds24-nomination-information-r01/information'
    previous=read(old/'results.json');data=read(here/'complete_owner_ledger.json');smoke=read(here/'smoke.json')
    assert all(r['no_new_scores_computed'] for r in smoke['records'])
    counts={};checks=[]
    for d in data:
        case=d['case'];parents=read(ROOT.parent/'ds24-fast-identifiability-r01/transfer/ownership'/case/'parent.json')
        obs={r['observation_id']:r for r in read(source/case/'observations.json')}
        tracks={r['key']:r for r in read(source/case/'tracks.json')}
        assert len(d['owners'])==len(tracks)
        ids=[r['observation_id'] for r in d['ordered_rows']];assert len(ids)==len(set(ids))
        for arm in p['arms']:
            coverage=parents['coverage'][arm]
            assert set(ids)==set(coverage['curved_observation_ids']+coverage['predictive_observation_ids'])
            meta=next(r for r in previous['parents'] if r['case']==case and r['arm']==arm)
            assert sha(meta['array_path'])==meta['array_sha256']
            z=np.load(meta['array_path']);j,u,w=z['position_design'],z['nuisance_design'],z['weights']
            assert len(ids)==len(j)==len(u)==len(w)
            assert np.isfinite(j).all() and np.isfinite(u).all() and np.all(w>0)
            g=np.diag(z['prior'])+u.T@(w[:,None]*u);cross=u.T@(w[:,None]*j)
            assert np.max(abs(g-z['gram']))<1e-7 and np.max(abs(cross-z['cross']))<1e-7
            info=j.T@(w[:,None]*j)-cross.T@np.linalg.solve(g,cross)
            error=float(np.max(abs(info-z['information'])))
            assert np.allclose(info,z['information'],rtol=1e-6,atol=1e-7)
            assert np.min(np.linalg.eigvalsh(z['information']))>0 and abs(np.linalg.norm(z['weak'])-1)<1e-12
            checks.append(dict(case=case,arm=arm,rows=len(j),nuisance_columns=u.shape[1],Schur_identity_max_error=error))
        for owner in d['owners']:
            tr=tracks[owner['owner']];ss=set(tr['observation_ids'])
            assert ss==set(owner['observation_ids']) and len(ss)==owner['points']
            expected=len(ss)>=20 and all(ss<=set(parents['coverage'][a]['curved_observation_ids']) for a in p['arms'])
            assert bool(expected)==owner['eligible']
            assert {ids[i] for i in owner['likelihood_indices']}==ss.intersection(ids)
        for r in d['ordered_rows']:
            assert r['time_s']==obs[r['observation_id']]['time_s']
            assert r['q']==tracks[r['owner']]['rf_hz']/11.5e9
        counts[case]=dict(owners=len(d['owners']),eligible_complete_owners=sum(r['eligible'] for r in d['owners']))
    assert counts=={'DS24-0010':dict(owners=128,eligible_complete_owners=54),'DS24-0011':dict(owners=117,eligible_complete_owners=48)}
    tree=ast.parse((here/'raw_metadata.py').read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='windows' for n in ast.walk(tree))
    test=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(here/'test_local_math.py')],
        cwd=here,capture_output=True,text=True,timeout=20,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert test.returncode==0,test.stdout+test.stderr
    assert bind(p['bindings'])==checked
    save('influence_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),frozen_bindings_checked=checked,
        original_owner_counts=counts,saved_array_algebra_checks=checks,tests_stdout=test.stdout,tests_stderr=test.stderr,
        audit_seconds=time.monotonic()-start,new_detector_calls=0,new_geometry_or_position_fits=0,new_susceptibility_ranks=0,
        scope='Fixed original Gaussian/VI bias susceptibility and metadata-only request selection; no calibrated accuracy or information-gain claim.'))

def final_seal():
    start=time.monotonic();here=ROOT/'audit'
    names=['measurement_preflight.json','measurement_terminal.json','influence_preflight.json',
        'influence_terminal.json','recorded_preflight.json','recorded_terminal.json']
    receipts=[read(here/n) for n in names];assert all(r['all_passed'] for r in receipts)
    paths=[here/n for n in names]+[here/'check.py',here/'FINDINGS.md',here/'PRIOR_ART.md',
        ROOT/'README.md',ROOT/'COORDINATOR_PLAN.md',ROOT/'SOURCE_REVIEW.md',ROOT/'stage_report.py',
        ROOT/'RECORDED_SCOPE.md',here/'final_seal_attempt01.json']
    for branch in ('measurement','influence','recorded'):
        b=ROOT/branch;p=read(b/'protocol.json');bind(p.get('files',p.get('bindings')))
        rf=read(b/'RF_seal.json');bind({str(Path(k) if Path(k).is_absolute() else b/k):v for k,v in rf['files'].items()})
        manifest=read(b/'lean_publication.json')
        for rec in manifest['published']:
            assert sha(rec['path'])==rec['sha256'],rec['path']
        paths.extend([b/'protocol.json',b/'RF_seal.json',b/'FINDINGS.md',b/'lean_publication.json'])
        for relative in ('report/seal.json','report02/seal.json','final_seal.json'):
            report=b/relative
            if report.exists():
                d=read(report)
                if 'files' in d:bind({str(Path(k) if Path(k).is_absolute() else b/k):v for k,v in d['files'].items()})
                paths.append(report)
    result=read(ROOT/'recorded/results.json');raw=complete=0
    fields=read(ROOT/'recorded/protocol.json')['parity_float_tolerances']
    for r in result['records']:
        for rx in r['full_original_replay_result']['receivers']:
            raw+=len(rx['candidates'])
            complete+=sum(c['fractional_epoch_status']=='complete' and all(c[k] is not None for k in fields) for c in rx['candidates'])
    assert raw==128 and complete==96
    assert read(here/'recorded_terminal.json')['independently_checked_exported_float_fields']==complete*len(fields)==480
    # Independently verify the README's synthetic lag-one statement from saved rows.
    correlations={}
    for rx in (0,1):
        records=[read(ROOT/'measurement/results'/f'old24_{i:02}_RX{rx}.json') for i in range(24)]
        truth=np.array([100000+200*(i+.01) for i in range(24)])
        old=np.array([r['result']['old_tracking_cfo_hz'] for r in records])-truth
        new=np.array([r['result']['corrected_tracking_cfo_hz'] for r in records])-truth
        correlations[str(rx)]={'old':float(np.corrcoef(old[:-1],old[1:])[0,1]),'new':float(np.corrcoef(new[:-1],new[1:])[0,1])}
    diff=subprocess.run(['git','diff','--binary'],cwd='/home/mouse9911/gits/leo-tracker-reduxredux',capture_output=True,check=True).stdout
    digest=hashlib.sha256(diff).hexdigest();assert digest=='add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
    total=sum(r['audit_seconds'] for r in receipts)+1+time.monotonic()-start;assert total<120
    save('final_seal.json',dict(all_passed=True,passed_receipts=6,files={str(p):sha(p) for p in paths},
        recorded_returned_raw_candidates=128,recorded_archived_complete_candidates_compared=96,
        recorded_candidates_without_archived_complete_row=32,no_parity_claim_for_other32=True,
        synthetic_lag_one_correlation_readback=correlations,audit_seconds_including_conservative_document_failure_charge=total,
        original_coordinator_plan_exactly_restored=True,recorded_scope_preserved_as_separate_addendum=True,
        unrelated_repository_diff_sha256=digest,
        new_audit_IQ_reads=0,new_audit_detector_calls=0,new_optimization_or_geometry_calls=0,
        scope='Final scientific, reporting and narrative bindings; local numerical qualification and recorded parity do not establish real CFO truth or position improvement.'))


def recorded_terminal():
    start=time.monotonic();here=ROOT/'recorded';p=read(here/'protocol.json');checked=bind(p['files'])
    assert sha(here/'results.json')=='6f854a69aed8d6db7b5a85a8d9c0f76cc815502ab19ad7134ab2bcc47f3111e9'
    result=read(here/'results.json');requests=read(ROOT/'influence/window_requests.json')
    assert result['protocol_sha256']==sha(here/'protocol.json') and result['preflight_sha256']==sha(ROOT/'audit/recorded_preflight.json')
    assert result['requests_sha256']==sha(ROOT/'influence/window_requests.json') and result['refiner_sha256']==sha(ROOT/'measurement/refiner.py')
    assert result['declared_slots']==result['completed']==result['paired_detector_calls']==len(result['records'])==8
    assert result['status']=='terminal' and result['runtime_identity_unchanged'] and result['identity_before']==result['identity_after']
    assert result['identity_before']==read(here/'preparation.json')['identity'] and result['cumulative_worker_seconds']<180
    assert result['no_reselection_or_retry'] and result['no_graph_satellite_position_GPS'] and not result['real_frequency_truth_available']
    assert (here/'worker_stderr.log').read_text()==''
    tests=0;maxerror=0.;margin=0;deltas=[]
    for row,r in zip(result['records'],requests):
        assert row['request_id']==r['request_id'] and row['native_observation_id']==r['native_observation_id']
        assert row['status']=='complete' and row['full_reader_exhausted'] and row['original_rank_and_gate_preserved']
        assert row['IQ_sha256']==r['raw_authority']['index']['iq_sha256']
        original=read(r['tracking']['path']);probe=r['probe'];replay=row['full_original_replay_result']
        expected={q['receiver_id']:q['candidates'] for q in original['source']['probes'] if q['visit_index']==probe['visit_index'] and q['probe_index']==probe['probe_index']}
        assert replay['status']=='processed' and {q['receiver_id'] for q in replay['receivers']}==set(expected)
        for rx in replay['receivers']:
            actual=[q for q in rx['candidates'] if q['fractional_epoch_status']=='complete' and all(q[k] is not None for k in p['parity_float_tolerances'])]
            assert len(actual)==len(expected[rx['receiver_id']])
            for q,old in zip(actual,expected[rx['receiver_id']]):
                assert q['candidate_rank']==old['candidate_rank'] and q['epoch_sample']==old['integer_epoch_sample']
                assert bool(q['fractional_margin']>=.025)==old['passed_fractional_margin_gate']
                for field,tolerance in p['parity_float_tolerances'].items():
                    error=abs(q[field]-old[field]);assert error<=tolerance;maxerror=max(maxerror,error);tests+=1
        peak=row['original_replayed_candidate'];assert peak['candidate_rank']==r['original_candidate']['candidate_rank']
        assert peak['epoch_sample']==r['original_candidate']['integer_epoch_sample']
        q=row['refinement'];assert q['old_tracking_cfo_hz']==r['original_observation']['measured_cfo_hz']
        assert q['acquired_cfo_hz']==peak['acquired_cfo_hz'] and q['fractional_epoch_offset_samples']==peak['fractional_epoch_offset_samples']
        assert q['original_candidate_epoch_and_gate_preserved'] and not q['within_symbol_redemodulation_changed']
        delta=q['corrected_tracking_cfo_hz']-q['old_tracking_cfo_hz'];assert delta==row['correction_delta_hz']
        c=row['correlations'];times=np.array(c['times_s']);lags=times-times[:,:1];step=float(np.median(np.diff(times,axis=1)))
        for name in ('exact','control'):
            values=np.array(c[name+'_values_real'])+1j*np.array(c[name+'_values_imag']);v=q[name]
            ceiling=float(np.sum(np.sum(abs(values),axis=1)**2));grid=np.fft.fftfreq(512,d=step)
            spectrum=np.sum(abs(np.fft.fft(values,n=512,axis=1))**2,axis=0)/ceiling;k=int(np.argmax(spectrum))
            assert abs(grid[k]-v['original_bin_hz'])<1e-7 and abs(spectrum[k]-v['original_bin_score'])<1e-10
            f=v['residual_cfo_hz'];phase=np.exp(-2j*np.pi*f*lags);s=np.sum(values*phase,axis=1)
            d=np.sum(values*phase*(-2j*np.pi*lags),axis=1);dd=np.sum(values*phase*(-2j*np.pi*lags)**2,axis=1)
            value=float(np.sum(abs(s)**2)/ceiling);assert abs(value-v['score'])<1e-10
            curvature=float(2*np.real(np.vdot(d,d)+np.vdot(s,dd))/ceiling);assert curvature<0
            assert v['numerically_qualified'] and not v['boundary'] and not v['global_peak_certified']
            assert abs(f-v['reference_root_hz'])<=.01
            lower,upper=v['bracket_hz'];assert abs(lower-v['original_bin_hz']+1/(1024*step))<1e-8
            assert abs(upper-v['original_bin_hz']-1/(1024*step))<1e-8 and min(f-lower,upper-f)>.05
        assert q['numerical_frequency_qualified'];margin+=q['numerical_margin_qualified']
        deltas.append(dict(request_id=row['request_id'],correction_delta_hz=delta))
    assert margin==result['numerical_frequency_qualified']==8
    sealpath=here/'RF_seal.json';seal=read(sealpath)
    checked+=bind({str(Path(k) if Path(k).is_absolute() else here/k):v for k,v in seal['files'].items()})
    save('recorded_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),results_sha256=sha(here/'results.json'),
        RF_seal_sha256=sha(sealpath),frozen_bindings_checked=checked,requests_complete=8,paired_detector_calls=8,
        independently_checked_exported_float_fields=tests,maximum_paired_candidate_parity_error=maxerror,
        exhausted_verified_public_readers=8,frequency_qualified=8,margin_qualified=8,independently_checked_spectral_cells=16,
        correction_deltas=deltas,audit_seconds=time.monotonic()-start,new_audit_IQ_reads=0,new_audit_detector_calls=0,
        scope='Original paired candidate parity and same-cell refinement on eight recorded windows; real CFO truth and position accuracy remain unmeasured.'))


def recorded_preflight():
    start=time.monotonic();here=ROOT/'recorded';p=read(here/'protocol.json');checked=bind(p['files'])
    assert sha(here/'protocol.json')=='993c3cb4325b0fb9679cbf9653ce5ba771698ad413967dbd52668d43a8a9a8dc'
    assert p['maximum_paired_detector_calls']==8 and p['cap_cumulative_seconds']==180
    assert p['workers']==p['BLAS_threads']==1 and not p['IQ_during_preparation']
    assert p['no_graph_satellite_position_GPS'] and p['no_retry_reselection']
    assert read(ROOT/'audit/measurement_terminal.json')['all_passed'] and read(ROOT/'audit/influence_terminal.json')['all_passed']
    requests=read(ROOT/'influence/window_requests.json');assert p['request_ids']==[r['request_id'] for r in requests]
    assert len(requests)==8 and len({r['native_observation_id'] for r in requests})==8
    assert p['refiner_sha256']==sha(ROOT/'measurement/refiner.py')==read(ROOT/'measurement/protocol.json')['files'][str(ROOT/'measurement/refiner.py')]
    prep=read(here/'preparation.json');assert prep['all_passed'] and prep['tests']==4 and prep['IQ_reads']==prep['detector_calls']==0
    authority=read(here/'authority.json');assert authority['IQ_reads']==authority['detector_calls']==0
    for auth in authority['records']:
        assert auth['run_state']=='succeeded' and auth['identity_matches']
        assert auth['runtime_identity']==[prep['identity']['code_digest'],prep['identity']['environment_digest']]
        assert auth['execution']['code_revision']==auth['runtime_identity'][0]
        assert auth['execution']['environment_digest']==auth['runtime_identity'][1]
        assert sha(auth['tracking_path'])==auth['tracking_sha256']
    env=dict(os.environ,PYTHONPATH='/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src',
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/opt/leo-fast-auto/20261010-r1/venv/bin/python','-B','-m','unittest','discover',
        '-s',str(here),'-p','test_replay.py'],env=env,capture_output=True,text=True,timeout=20)
    assert test.returncode==0,test.stdout+test.stderr
    assert bind(p['files'])==checked
    save('recorded_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),frozen_bindings_checked=checked,
        exact_frozen_requests=8,historical_authority_verified_cases=2,unchanged_synthetic_qualified_refiner=True,
        tests_stdout=test.stdout,tests_stderr=test.stderr,public_reader_exhaustion_and_full_pair_parity_reviewed=True,
        original_requested_rank_epoch_and_gate_preserved=True,audit_seconds=time.monotonic()-start,new_IQ_reads=0,new_detector_calls=0,
        scope='Eight exact recorded-window parity/unchanged-refiner checks; no real CFO truth, localization comparison or new admission.'))


def measurement_terminal():
    start=time.monotonic();here=ROOT/'measurement';p=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bind(p['files'])+bind(seal['files']);assert seal['protocol_sha256']==sha(here/'protocol.json') and seal['all_selected_terminal']
    exe=read(here/'execution.json');assert len(exe['records'])==exe['total_receiver_slots']==exe['completed']==64
    assert exe['new_paired_detector_calls']==8 and exe['old_detector_replays']==0 and exe['cumulative_worker_seconds']<300
    assert exe['identity_unchanged'] and exe['identity_before']==exe['identity_after']==read(here/'preparation.json')['identity']
    assert exe['no_candidate_epoch_or_gate_reselection'] and exe['graph_fits']==exe['position_fits']==0
    attribution=read(here/'attribution.json');assert attribution['all48_final_errors_inherited_from_acquisition']
    assert len(attribution['rows'])==48 and all(r['fractional_residual_cfo_hz']==0 and r['final_cfo_hz']==r['acquired_cfo_hz'] for r in attribution['rows'])
    def select(candidates):
        c=[q for q in candidates if q['fractional_epoch_status']=='complete' and q['fractional_margin'] is not None and q['fractional_margin']>=.025]
        return max(c,key=lambda q:(q['fractional_margin'],-q['candidate_rank']))
    errors={key:{rx:[] for rx in (0,1)} for key in ('old_before','old_after','fresh_before','fresh_after')}
    maxscore=maxfreq=maxderiv=0.;numerically_qualified=margin_qualified=0;seen=set()
    for rec in exe['records']:
        assert rec['status']=='complete' and sha(rec['file'])==rec['sha256']
        row=read(rec['file']);key=(row['name'],row['receiver']);assert key not in seen;seen.add(key)
        old=row['name'].startswith('old24_');index=int(row['name'].rsplit('_',1)[1]);rx=row['receiver']
        if old:
            slot=read(ROOT.parent/'ds24-candidate-continuity-r01/single_source/slots'/f'single_source_{index:02}.json')
            assert row['input']['iq_sha256']==slot['input']['iq_sha256'] and row['input']['noise_sha256']==slot['input']['noise_sha256']
            truth=100000+200*(index+.01)
        else:
            slot=read(here/'fresh_slots'/f'fresh_{index:02}.json');definition=p['fresh'][index]
            assert slot['status']=='complete' and slot['definition']==definition
            assert row['input']==slot['input'] and row['input']['seed']==[p['fresh_seed'],index]
            assert row['input']['clipping_samples']==0
            truth=definition['base_cfo_hz']+definition['rate_hz_s']*(definition['time_s']+.01)
        candidate=select(next(a['candidates'] for a in slot['receivers'] if a['receiver_id']==rx))
        assert candidate==row['original_selected_candidate']
        result=row['result'];assert result['acquired_cfo_hz']==candidate['acquired_cfo_hz']
        assert result['integer_epoch_sample']==candidate['epoch_sample'] and result['fractional_epoch_offset_samples']==candidate['fractional_epoch_offset_samples']
        assert result['old_tracking_cfo_hz']==candidate['fractional_tracking_cfo_hz']
        assert result['original_candidate_epoch_and_gate_preserved'] and not result['within_symbol_redemodulation_changed']
        assert result['corrected_tracking_cfo_hz']==result['acquired_cfo_hz']+result['exact']['residual_cfo_hz']
        assert abs(result['corrected_margin']-result['exact']['score']+result['control']['score'])<1e-12
        assert sha(row['correlations_file'])==row['correlations_sha256'];a=np.load(row['correlations_file']);times=a['times_s'];lags=times-times[:,:1]
        step=float(np.median(np.diff(times,axis=1)));grid=np.fft.fftfreq(512,d=step)
        for name in ('exact','control'):
            values=a[name+'_values'];q=result[name];ceiling=float(np.sum(np.sum(abs(values),axis=1)**2))
            spectrum=np.sum(abs(np.fft.fft(values,n=512,axis=1))**2,axis=0)/ceiling
            maximum=int(np.argmax(spectrum));assert abs(grid[maximum]-q['original_bin_hz'])<1e-7
            assert abs(spectrum[maximum]-q['original_bin_score'])<1e-10
            f=q['residual_cfo_hz'];phase=np.exp(-2j*np.pi*f*lags);s=np.sum(values*phase,axis=1)
            d=np.sum(values*phase*(-2j*np.pi*lags),axis=1);dd=np.sum(values*phase*(-2j*np.pi*lags)**2,axis=1)
            value=float(np.sum(abs(s)**2)/ceiling);derivative=float(2*np.real(np.vdot(s,d))/ceiling)
            curvature=float(2*np.real(np.vdot(d,d)+np.vdot(s,dd))/ceiling)
            error=abs(value-q['score']);maxscore=max(maxscore,error);assert error<=1e-10
            assert curvature<0 and abs(derivative)<1e-8
            lo,hi=q['bracket_hz'];assert abs(lo-(q['original_bin_hz']-1/(1024*step)))<1e-8
            assert abs(hi-(q['original_bin_hz']+1/(1024*step)))<1e-8 and min(f-lo,hi-f)>.05
            assert q['numerically_qualified'] and not q['global_peak_certified']
            maxfreq=max(maxfreq,abs(f-q['reference_root_hz']));maxderiv=max(maxderiv,abs(derivative))
            assert abs(f-q['reference_root_hz'])<=.01
        numerically_qualified+=result['numerical_frequency_qualified'];margin_qualified+=result['numerical_margin_qualified']
        assert row['generated_truth']['midpoint_cfo_hz']==truth
        prefix='old' if old else 'fresh'
        errors[prefix+'_before'][rx].append(result['old_tracking_cfo_hz']-truth)
        errors[prefix+'_after'][rx].append(result['corrected_tracking_cfo_hz']-truth)
    rms={key:{str(rx):float(np.sqrt(np.mean(np.array(v)**2))) for rx,v in groups.items()} for key,groups in errors.items()}
    assert numerically_qualified==margin_qualified==64
    save('measurement_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,receiver_slots=64,frequency_qualified=64,margin_qualified=64,new_paired_detector_calls=8,
        independently_replayed_target_control_scores=128,maximum_direct_score_error=maxscore,maximum_saved_reference_frequency_error_hz=maxfreq,
        maximum_direct_derivative=maxderiv,midpoint_error_RMS_hz=rms,audit_seconds=time.monotonic()-start,
        new_audit_detector_calls=0,new_optimization_or_geometry_calls=0,
        scope='Exact residual-cell correction on inverse-template synthetic controls; not physical waveform validation, uncertainty calibration or position improvement.'))


def measurement_preflight():
    start=time.monotonic();here=ROOT/'measurement';p=read(here/'protocol.json');checked=bind(p['files'])
    assert sha(here/'protocol.json')=='947fd84697405a3f3609c3365833af68186f6091dc2aebe33ced5383940b3191'
    assert p['total_receiver_slots']==64 and p['old_receiver_slots']==48 and p['fresh_receiver_slots']==16
    assert p['maximum_new_paired_detector_calls']==8 and p['original_replayed_detector_calls']==0
    assert p['numerical_cap_seconds']==300 and p['worker_count']==p['blas_threads']==1
    assert p['score_symbols']==list(range(2,66)) and p['original_DFT_size']==512 and p['original_bin_half_cell']
    assert p['independent_frequency_tolerance_hz']==.01 and p['score_tolerance']==1e-10 and p['boundary_distance_hz']==.05
    assert p['old_candidate_epoch_window_gate_preserved'] and p['optimize_exact_and_control_symmetrically']
    assert not p['within_symbol_redemodulation_changed']
    expected=[(f,r,float(t)) for f in (100037.,-100113.) for r in (200.,-200.) for t in (0,7)]
    assert [(d['base_cfo_hz'],d['rate_hz_s'],d['time_s']) for d in p['fresh']]==expected
    prep=read(here/'preparation.json');assert prep['all_passed'] and prep['tests']==6 and prep['old_IQ_hash_smoke']
    assert prep['new_detector_calls']==prep['actual_control_refinement_evaluations']==0
    assert prep['identity']==read(ROOT.parent/'ds24-candidate-continuity-r01/single_source/preparation.json')['identity']
    tree=ast.parse((here/'refiner.py').read_text())
    assert not any(isinstance(n,ast.Name) and n.id in ('truth','source','seed','generated_truth') for n in ast.walk(tree))
    env=dict(os.environ,PYTHONPATH='/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src',
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/opt/leo-fast-auto/20261010-r1/venv/bin/python','-B','-m','unittest','discover',
        '-s',str(here),'-p','test_refiner.py'],env=env,capture_output=True,text=True,timeout=20)
    assert test.returncode==0,test.stdout+test.stderr
    assert bind(p['files'])==checked
    save('measurement_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),frozen_bindings_checked=checked,
        tests_stdout=test.stdout,tests_stderr=test.stderr,old_selected_candidate_and_epoch_preserved=True,
        symmetric_original_target_control_cells=True,explicit_terminal_denominator_on_prerequisite_and_input_failure=True,
        audit_seconds=time.monotonic()-start,new_detector_calls=0,new_control_refinements=0,
        scope='Exact deployed scope64 residual-cell intervention, not full redemodulation, global peak certification or physical waveform authority.'))


def influence_terminal():
    start=time.monotonic();here=ROOT/'influence';p=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bind(p['bindings'])+bind(seal['files'])
    assert seal['protocol_sha256']==sha(here/'protocol.json') and seal['preflight_sha256']==sha(ROOT/'audit/influence_preflight.json')
    data=read(here/'complete_owner_ledger.json');result=read(here/'results.json');summary=read(here/'summary.json')
    assert result['failure'] is summary['failure'] is None and summary['cumulative_worker_seconds']<180
    arrays=np.load(here/'response_arrays.npz');old=read(ROOT.parent/'ds24-nomination-information-r01/information/results.json')
    frows=result['families'];orows=result['owners'];maxerror=0.;scores=0
    def independent_score(h,weak,ix,rows):
        t=np.array([rows[i]['time_s'] for i in ix]);q=np.array([rows[i]['q'] for i in ix])
        degree=min(2,len(np.unique(t))-1);z=np.zeros(len(t)) if degree==0 else (t-t.min())/np.ptp(t)
        design=np.column_stack([z**k for k in range(degree+1)])
        left,_,_=np.linalg.svd(design,full_matrices=False)
        return float(np.linalg.norm((weak@h[:,ix]*q)@left)*np.sqrt(len(t)))
    for d in data:
        case=d['case'];rows=d['ordered_rows'];responses={}
        for arm in p['arms']:
            meta=next(r for r in old['parents'] if r['case']==case and r['arm']==arm);a=np.load(meta['array_path'])
            h=arrays[case+'_'+arm+'_response'];weak=arrays[case+'_'+arm+'_weak']
            rhs=(a['position_design']-a['nuisance_design']@np.linalg.solve(a['gram'],a['cross'])).T*a['weights']
            error=float(np.max(abs(a['information']@h-rhs)));assert error<1e-8
            assert np.array_equal(weak,a['weak']);responses[arm]=(h,weak)
        families=[r for r in frows if r['case']==case];owners=[r for r in orows if r['case']==case]
        assert len(owners)==len(d['owners'])
        for rec in families+[r for r in owners if r['eligible']]:
            ix=rec['likelihood_indices'] if 'owner' in rec else [i for i,r in enumerate(rows) if r['family']==rec['family']]
            for arm in p['arms']:
                h,weak=responses[arm];score=independent_score(h,weak,ix,rows)
                error=abs(score-rec['arms'][arm]['km_per_Hz_RMS']);maxerror=max(maxerror,error);assert error<1e-9
                assert abs(rec['arms'][arm]['one_Hz_proxy_m']-1000*score)<1e-6
                assert abs(rec['arms'][arm]['twenty_Hz_proxy_m']-20000*score)<1e-5;scores+=1
            assert rec['paired_score']==min(rec['arms'][arm]['km_per_Hz_RMS'] for arm in p['arms'])
        ranked=sorted([f for f in families if f['has_eligible_owner']],key=lambda f:(-f['paired_score'],f['family']))
        family=ranked[0];target=min((o for o in owners if o['eligible'] and o['family']==family['family']),key=lambda o:(-o['paired_score'],o['owner']))
        import math
        low=sorted([f for f in ranked if f['family']!=target['family'] and f['paired_score']>0],key=lambda f:(f['paired_score'],f['family']))[:max(1,math.ceil(len(ranked)/4))]
        fs={f['family']:f['paired_score'] for f in low}
        control=min((o for o in owners if o['eligible'] and o['family'] in fs),key=lambda o:(o['receiver']==target['receiver'],fs[o['family']],o['paired_score'],o['owner']))
        selected=next(s for s in result['selection'] if s['case']==case)
        assert selected['target']['owner']==target['owner'] and selected['control']['owner']==control['owner']
        for owner in (target,control):
            assert owner['eligible'] and len(owner['observation_ids'])==owner['points']>=20
    requests=read(here/'window_requests.json');assert len(requests)==summary['requests']==summary['metadata_ready']==8
    assert len({r['request_id'] for r in requests})==len({r['native_observation_id'] for r in requests})==8
    for r in requests:
        src=ROOT.parent/'ds25-20261024';obs={q['observation_id']:q for q in read(src/r['case']/'observations.json')}
        assert r['original_observation']==obs[r['native_observation_id']]
        owner=next(q for q in orows if q['case']==r['case'] and q['owner']==r['complete_owner'])
        ids=sorted(owner['observation_ids'],key=lambda oid:(obs[oid]['time_s'],oid))
        index=int(np.floor(r['time_quantile']*(len(ids)-1)+.5));assert ids[index]==r['native_observation_id']
        assert r['original_candidate']['fractional_tracking_cfo_hz']==r['original_observation']['measured_cfo_hz']
        a=r['raw_authority'];assert a['status']=='metadata_ready_IQ_and_detector_parity_unverified'
        assert a['payload_read'] is a['IQ_hash_newly_verified'] is False
        assert a['source_input']==r['source_input'] and a['global_visit']==r['probe']['visit_index']
        acquisition=a['index']['acquisition'];assert acquisition['sample_start']==r['probe']['window_start_counter']
        assert acquisition['sample_end']-acquisition['sample_start']==a['index']['sample_count']==r['probe']['duration_samples']
        assert r['probe']['receiver_id'] in a['receiver_ids'] and a['target']['channel']==r['probe']['channel']
        assert a['target']['rf_center_hz']==r['probe']['actual_rf_hz'] and r['acquired_cfo_hz'] is None
    save('influence_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,independent_SVD_basis_scores_checked=scores,maximum_score_discrepancy_km_per_Hz=maxerror,
        selected_owners=summary['selected_owners'],complete_owner_counts=summary['eligible_complete_owner_counts'],native_window_requests=8,
        public_metadata_ready=8,IQ_or_detector_parity_not_yet_verified=True,audit_seconds=time.monotonic()-start,
        new_detector_calls=0,new_propagation_or_position_fits=0,
        scope='Frozen Gaussian/VI measurement-bias susceptibility and exact metadata readiness, not a measured bias, physical calibration or position gain.'))

if __name__=='__main__':globals()[sys.argv[1]]()
