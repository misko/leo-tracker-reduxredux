"""Independent static and saved-artifact checks; no IQ, detector or position runs."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'ds24-detector-response-r01'

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bindings(files):
    for p,h in files.items():assert sha(p)==h,p
    return len(files)
def save(name,data):
    with (ROOT/'audit'/name).open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')

def measurement_preflight():
    start=time.monotonic();here=ROOT/'measurement';p=read(here/'protocol.json');checked=bindings(p['files'])
    assert sha(here/'protocol.json')=='837ebabc034a2af0290f36780536c34cb771fac8173f3dd17c7aca038772739d'
    assert p['total_slots']==159 and p['prior_reused_slots']==8 and p['maximum_new_paired_detector_calls']==151
    assert p['cap_cumulative_worker_seconds']==480 and p['workers']==2 and p['BLAS_threads']==1
    assert p['original_CFO_fallback_no_drop'] and p['no_graph_orbit_position_GPS']
    requests=read(here/'requests.json');assert len(requests)==len({r['native_observation_id'] for r in requests})==159
    with (PRIOR/'influence/report/complete_selected_owner_points.csv').open() as f:points=list(csv.DictReader(f))
    assert {r['native_observation_id'] for r in requests}=={r['native_id'] for r in points}
    assert sorted(Counter(r['complete_owner'] for r in requests).values())==[20,37,38,64]
    metadata=read(here/'metadata_receipt.json');assert metadata['returncode']==0
    verified={r['request_id']:r['raw_authority'] for r in json.loads(metadata['stdout'])}
    previous={r['native_observation_id']:r for r in read(PRIOR/'influence/window_requests.json')}
    previous_result=read(PRIOR/'recorded/results.json');previous_rows={r['request_id']:r for r in previous_result['records']}
    assert previous_result['refiner_sha256']==sha(PRIOR/'measurement/refiner.py')
    assert previous_result['identity_before']==previous_result['identity_after']==read(here/'preparation.json')['identity']
    public={};groups={};reused=[]
    for r in requests:
        a=r['raw_authority'];assert a==verified[r['request_id']] and a['status']=='metadata_ready_IQ_and_detector_parity_unverified'
        assert a['payload_read'] is a['IQ_hash_newly_verified'] is False
        public[r['source_input']['path']]=r['source_input']['sha256'].removeprefix('sha256:')
        public[a['index_path']]=a['index_sha256'].removeprefix('sha256:')
        assert a['source_input']==r['source_input'] and a['index']['acquisition']['sample_start']==r['probe']['window_start_counter']
        assert r['original_candidate']['fractional_tracking_cfo_hz']==r['original_observation']['measured_cfo_hz']
        if r['reused_prior_request_id']:
            old=previous[r['native_observation_id']];assert r['reused_prior_request_id']==old['request_id']
            for key in ('case','role','complete_owner','native_observation_id','original_observation','tracking','source_input','source_session_id','recording_id','raw_recording_authority_digest','probe','original_candidate'):
                assert r[key]==old[key]
            for key in ('segment','segment_manifest_sha256','index_path','index_sha256','local_sequence','index','target','sample_rate_hz','receiver_ids'):
                assert a[key]==old['raw_authority'][key]
            rec=previous_rows[old['request_id']];assert rec['status']=='complete' and all(q['all_passed'] for q in rec['candidate_parity'].values())
            reused.append(r['native_observation_id'])
        else:
            q=r['probe'];key=(r['case'],q['visit_index'],q['probe_index'],q['window_start_counter'])
            groups.setdefault(key,[]).append(r['request_id'])
    assert public==p['public_data_bindings'] and len(public)==55 and len(reused)==8
    ordered=sorted(groups);expected=[[groups[k] for k in ordered[i::2]] for i in range(2)]
    assert read(here/'batches.json')==expected and list(map(len,expected))==[76,75]
    assert len(groups)==151
    prep=read(here/'preparation.json');assert prep['all_passed'] and prep['tests']==4 and prep['metadata_only']
    assert prep['IQ_reads']==prep['detector_calls']==0 and p['preparation_seconds']>=prep['seconds']
    env=dict(os.environ,PYTHONPATH='/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/opt/leo-fast-auto/20261010-r1/venv/bin/python','-B','-m','unittest','discover','-s',str(here),'-p','test_complete.py'],
        env=env,capture_output=True,text=True,timeout=20)
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(p['files'])==checked
    save('measurement_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),frozen_source_and_receipt_bindings_checked=checked,
        metadata_verified_public_bindings=55,public_bindings_rechecked_by_service_worker_before_payload=True,unique_native_IDs=159,
        exact_prior_reuses=8,new_physical_windows=151,batch_sizes=[76,75],outer_process_limits_match_fixed_worker_shares=True,
        tests_stdout=test.stdout,tests_stderr=test.stderr,audit_seconds=time.monotonic()-start,new_IQ_reads=0,new_detector_calls=0,
        scope='Complete fixed-owner measurement intervention; numerical-frequency fallback retains original CFO, while raw/parity incompleteness remains explicit.'))

def position_preflight():
    start=time.monotonic();here=ROOT/'position';p=read(here/'protocol.json');checked=bindings(p['files'])
    assert sha(here/'protocol.json')=='cc6c77ca5fd4a8455cc9012950c5702bb08f708d8e4b0fee3c32118b4beb2b1f'
    assert p['cases']==['DS24-0010','DS24-0011'] and p['arms']==['c0','fitted_c'] and p['methods']==['original','corrected']
    assert p['total_fits']==8 and p['cap_seconds']==600 and p['workers']==2 and p['BLAS_threads']==1
    assert p['maximum_seconds_per_fit']==60 and p['outer_refresh_rounds']==5 and p['iterations_per_round']==48
    assert p['start_km']==[0.,0.] and p['initial_phase_reference']=='all_zero' and p['operational_policy']=='original_reference'
    prep=read(here/'preparation.json');assert prep['all_passed'] and not prep['GPS_used'] and len(prep['records'])==4
    measurement=read(ROOT/'measurement/protocol.json');requests=read(ROOT/'measurement/requests.json')
    assert bindings(measurement['files'])>0
    all_ids=set();actual=[]
    for row in prep['records']:
        assert row['zero_delta_exact'] and all(v==0 for v in row['zero_delta_errors'].values())
        assert row['original_saved_objective_replay_difference']==0
        ids=row['likelihood_membership'];flat=ids['curved']+ids['predictive'];assert len(flat)==len(set(flat))
        expected=set(p['selected'][row['case']]['native_IDs']);assert len(expected) in (75,84) and expected<=set(ids['curved'])
        assert expected=={r['native_observation_id'] for r in requests if r['case']==row['case']}
        injection=row['injection'];assert set(injection['native_IDs'])==expected and injection['zero_delta']
        assert injection['nonselected_graph_values_exact'] and injection['original_native_IDs_exact']
        assert injection['native_delta_sign']=='+new_minus_old'
        assert {r['native_observation_id'] for r in injection['coordinate_rows']}==expected
        assert all(r['delta_hz']==0 and r['original_graph_value_hz']==r['corrected_graph_value_hz'] for r in injection['coordinate_rows'])
        all_ids|=expected;actual.append(dict(case=row['case'],arm=row['arm'],curved=ids['curved_count'],predictive=ids['predictive_count']))
    assert len(all_ids)==159
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python','-B','-m','unittest','discover','-s',str(here),'-p','test_replacement.py'],env=env,capture_output=True,text=True,timeout=20)
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(p['files'])==checked
    save('position_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),frozen_bindings_checked=checked,
        actual_contexts=actual,zero_delta_score_coefficients_Gamma_residual_exact=True,unique_selected_native_IDs=159,
        native_delta_added_to_every_graph_occurrence_and_native_observation=True,aliases_and_nonselected_values_preserved=True,
        original_five_refresh_48_iteration_solver_and_full_predictive_factor_retained=True,
        raw_parity_incomplete_vector_blocks_launch=True,unqualified_numerical_frequency_falls_back_without_drop=True,
        baseline_reproduction_and_original_paired_gates_required=True,operational_policy='original_reference',
        tests_stdout=test.stdout,tests_stderr=test.stderr,audit_seconds=time.monotonic()-start,
        new_IQ_reads=0,new_detector_calls=0,new_geometry_calls=0,new_position_fits=0,
        launch_prerequisite='Root position_go.json must bind the complete correction vector and immutable measurement RF seal.'))

def measurement_terminal():
    import numpy as np
    start=time.monotonic();here=ROOT/'measurement';p=read(here/'protocol.json');s=read(here/'RF_seal.json')
    checked=bindings(p['files'])+bindings(s['files']);assert s['protocol_sha256']==sha(here/'protocol.json')
    assert read(ROOT/'audit/measurement_preflight.json')['protocol_sha256']==s['protocol_sha256']
    assert sha(here/'RF_seal.json')=='c121691a2a087355004b2ca6e39b546caa15e2971541f289e10355f02ff48413'
    req=read(here/'requests.json');out=read(here/'corrections.json');rows={r['native_observation_id']:r for r in out['rows']}
    assert len(req)==len(rows)==out['total_slots']==159 and out['coverage_complete'] and out['all_frequency_qualified']
    workers=[read(here/f'worker{i}.json') for i in (0,1)];new={r['request_id']:r for w in workers for r in w['records']}
    previous={r['request_id']:r for r in read(PRIOR/'recorded/results.json')['records']}
    assert len(new)==151 and sum(w['paired_detector_calls'] for w in workers)==151
    assert [w['paired_detector_calls'] for w in workers]==[76,75]
    for i,w in enumerate(workers):
        assert w['status']=='terminal' and w['identity_before']==w['identity_after']==read(here/'preparation.json')['identity']
        assert not (here/f'worker{i}_stderr.log').read_text()
        assert w['seconds']<w['allowance_seconds']
    expected_time=p['preparation_seconds']+sum(w['process']['seconds'] for w in out['workers'])
    assert abs(out['cumulative_worker_seconds']-expected_time)<1e-9 and expected_time<=480
    for w in out['workers']:assert w['process']['returncode']==0 and not w['process']['timed_out']
    tracking={path:read(path) for path in {r['tracking']['path'] for r in req}}
    maxima={'score_error':0.,'reference_score_error':0.,'frequency_reference_difference_hz':0.,'parity_float_error':0.}
    compared=raw_count=parity_checks=reuses=0;physical=set();owner_counts=Counter();all_margins=True
    for q in req:
        rec=previous[q['reused_prior_request_id']] if q['reused_prior_request_id'] else new[q['request_id']]
        reuses+=bool(q['reused_prior_request_id']);assert rec['status']=='complete' and rec['full_reader_exhausted']
        assert rec['IQ_sha256']==q['raw_authority']['index']['iq_sha256']
        z=rows[q['native_observation_id']];f=rec['refinement'];peak=rec['original_replayed_candidate']
        assert z['status']=='complete' and z['payload_and_parity_complete'] and z['numerical_frequency_qualified'] and not z['fallback_to_original']
        assert z['reused_prior_result']==bool(q['reused_prior_request_id']) and z['complete_owner']==q['complete_owner']
        old=q['original_observation']['measured_cfo_hz'];assert z['original_cfo_hz']==old==peak['fractional_tracking_cfo_hz']
        assert z['corrected_cfo_hz']==f['corrected_tracking_cfo_hz'] and z['correction_delta_hz']==z['corrected_cfo_hz']-old
        assert peak['candidate_rank']==q['original_candidate']['candidate_rank']
        assert peak['epoch_sample']==q['original_candidate']['integer_epoch_sample']==f['integer_epoch_sample']
        assert peak['fractional_epoch_offset_samples']==q['original_candidate']['fractional_epoch_offset_samples']==f['fractional_epoch_offset_samples']
        assert f['acquired_cfo_hz']==peak['acquired_cfo_hz'] and f['old_residual_cfo_hz']==peak['fractional_residual_cfo_hz']
        assert f['original_candidate_epoch_and_gate_preserved'] and not f['within_symbol_redemodulation_changed']
        assert max(f['original_grid_closure'].values())<=1e-7
        result=rec['full_original_replay_result'];probe=q['probe'];key=(q['case'],probe['visit_index'],probe['probe_index'],probe['window_start_counter'])
        assert result['sample_start']==probe['window_start_counter'] and result['sample_end']-result['sample_start']==probe['duration_samples']
        assert abs((probe['window_start_counter']-probe['origin_counter']+probe['duration_samples']/2)/q['raw_authority']['sample_rate_hz']-probe['time_s'])<1e-9
        if key not in physical:
            physical.add(key);t=tracking[q['tracking']['path']]
            expected={r['receiver_id']:r['candidates'] for r in t['source']['probes'] if r['visit_index']==probe['visit_index'] and r['probe_index']==probe['probe_index']}
            assert set(expected)=={r['receiver_id'] for r in result['receivers']}
            fields=('fractional_epoch_offset_samples','fractional_tracking_cfo_hz','fractional_exact_score','fractional_control_score','fractional_margin')
            for rx in result['receivers']:
                raw_count+=len(rx['candidates'])
                actual=[c for c in rx['candidates'] if c['fractional_epoch_status']=='complete' and all(c[k] is not None for k in fields)]
                assert len(actual)==len(expected[rx['receiver_id']]);compared+=len(actual)
                for a,b in zip(expected[rx['receiver_id']],actual,strict=True):
                    assert a['candidate_rank']==b['candidate_rank'] and a['integer_epoch_sample']==b['epoch_sample']
                    assert a['passed_fractional_margin_gate']==(b['fractional_margin']>=.025)
                    for field in fields:
                        error=abs(a[field]-b[field]);maxima['parity_float_error']=max(maxima['parity_float_error'],error);assert error==0;parity_checks+=1
        c=rec['correlations'];times=np.asarray(c['times_s']);lags=times-times[:,:1]
        for kind in ('exact','control'):
            values=np.asarray(c[kind+'_values_real'])+1j*np.asarray(c[kind+'_values_imag']);a=f[kind]
            assert values.shape==times.shape and values.shape[1]==64
            ceiling=float(np.sum(np.sum(abs(values),axis=1)**2))
            def score(freq):return float(np.sum(abs(np.sum(values*np.exp(-2j*np.pi*freq*lags),axis=1))**2)/ceiling)
            error=abs(score(a['residual_cfo_hz'])-a['score']);maxima['score_error']=max(maxima['score_error'],error);assert error<=1e-10
            err=abs(score(a['reference_root_hz'])-a['score']);maxima['reference_score_error']=max(maxima['reference_score_error'],err);assert err<=1e-10
            maxima['frequency_reference_difference_hz']=max(maxima['frequency_reference_difference_hz'],a['reference_frequency_difference_hz'])
            assert a['numerically_qualified'] and not a['boundary'] and not a['global_peak_certified'] and a['reference_frequency_difference_hz']<=.01
            assert a['direct_curvature']<0 and a['score']>=a['original_bin_score']-1e-12
            lower,upper=a['bracket_hz'];assert abs((upper-lower)-a['grid_spacing_hz'])<1e-8
            assert lower<a['residual_cfo_hz']<upper and abs(score(a['original_bin_hz'])-a['original_bin_score'])<=1e-10
        all_margins=all_margins and f['numerical_margin_qualified'];owner_counts[q['complete_owner']]+=1
    assert reuses==8 and len(physical)==159 and sorted(owner_counts.values())==[20,37,38,64]
    assert bindings(p['files'])+bindings(s['files'])==checked
    save('measurement_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),corrections_sha256=sha(here/'corrections.json'),
        checked_bindings=checked,unique_native_IDs=159,owner_counts=dict(owner_counts),complete_and_frequency_qualified=159,numerical_margin_qualified=all_margins,
        new_paired_calls=151,exact_prior_reuses=8,unique_physical_windows=159,raw_returned_candidate_records=raw_count,
        archived_complete_fractional_candidate_rows_compared=compared,exact_candidate_float_comparisons=parity_checks,
        independent_direct_complex_sum_cells=318,maxima=maxima,cumulative_worker_seconds=expected_time,
        same_native_delta_both_c_arms=True,no_rewrap_drop_reselection=True,position_launch_input_complete=True,
        audit_seconds=time.monotonic()-start,new_IQ_reads=0,new_detector_calls=0,new_optimizer_calls=0,
        scope='Exact historical parity applies to archived complete fractional candidates, not every raw detector return. Local score maxima are numerically qualified, not physical CFO truth or position improvement.'))

def position_terminal():
    import numpy as np
    start=time.monotonic();here=ROOT/'position';p=read(here/'protocol.json');s=read(here/'RF_seal.json')
    checked=bindings(p['files'])+bindings(s['files']);assert s['protocol_sha256']==sha(here/'protocol.json')
    pre=read(ROOT/'audit/position_preflight.json');assert pre['all_passed'] and pre['protocol_sha256']==s['protocol_sha256']
    go=read(ROOT/'position_go.json');assert go['approved'] and go['protocol_sha256']==s['protocol_sha256']
    assert sha(ROOT/'measurement/corrections.json')==go['corrections_sha256'] and sha(ROOT/'measurement/RF_seal.json')==go['measurement_RF_seal_sha256']
    checked+=bindings(read(ROOT/'measurement/RF_seal.json')['files'])
    execution=read(here/'execution.json');assert execution['all_selected_terminal'] and execution['cumulative_worker_seconds']<=600
    assert execution['corrections_sha256']==go['corrections_sha256'] and execution['measurement_RF_seal_sha256']==go['measurement_RF_seal_sha256']
    assert execution['operational_policy']=='original_reference' and not execution['GPS_used']
    rows=execution['all8_slots'];assert len(rows)==8
    assert {(r['case'],r['method'],r['arm']) for r in rows}=={(c,m,a) for c in p['cases'] for m in p['methods'] for a in p['arms']}
    corrections={r['native_observation_id']:r for r in read(ROOT/'measurement/corrections.json')['rows']}
    prep={(r['case'],r['arm']):r for r in read(here/'preparation.json')['records']}
    output=[];cases=[]
    for case in p['cases']:
        result=read(here/case/'result.json');injection=read(here/case/'injection.json')
        previous=prep[(case,'c0')]['injection']
        for key in ('native_IDs','unchanged_inference_fingerprint','unchanged_graph_metadata_fingerprint','unchanged_noise_fingerprint'):
            assert injection[key]==previous[key]
        old_rows={(r['component'],r['index']):r for r in previous['coordinate_rows']}
        assert len(injection['coordinate_rows'])==len(old_rows)
        for coord in injection['coordinate_rows']:
            old=old_rows[(coord['component'],coord['index'])];q=corrections[coord['native_observation_id']]
            assert coord['original_graph_value_hz']==old['original_graph_value_hz'] and coord['integer_graph_lift']==old['integer_graph_lift']
            assert coord['delta_hz']==q['corrected_cfo_hz']-q['original_cfo_hz']
            assert coord['corrected_graph_value_hz']==coord['original_graph_value_hz']+coord['delta_hz']
        original_ok=[];corrected_ok=[]
        for method in p['methods']:
            for arm in p['arms']:
                r=read(here/case/method/(arm+'_result.json'));assert r==next(x for x in rows if (x['case'],x['method'],x['arm'])==(case,method,arm))
                base=here/case/method/arm
                if r['status']!='complete':
                    output.append(dict(case=case,method=method,arm=arm,status=r['status'],raw_endpoint_saved=(base/'raw_endpoint.json').exists()))
                    (original_ok if method=='original' else corrected_ok).append(False);continue
                raw=read(base/'raw_endpoint.json');g=read(base/'gates.json');sm=raw['summary'];x=np.asarray(sm['endpoint_east_north_km'])
                assert np.array_equal(x,r['endpoint_east_north_km']) and np.isfinite(x).all() and x.shape==(2,)
                assert raw['likelihood_membership']==prep[(case,arm)]['likelihood_membership']
                assert raw['full_objective']==sm['negative_twice_elbo']==r['full_objective']
                assert abs(raw['full_objective']-sm['curved_negative_twice_elbo']-raw['predictive_objective'])<=1e-8
                assert np.isfinite(np.asarray(raw['noise_precision'])).all() and np.isfinite(np.asarray(raw['coefficient'])).all()
                history=sm['history'];assert len(history)==5
                for epoch,h in enumerate(history):
                    assert h==read(base/f'epoch{epoch}.json')
                    reference=np.asarray(h['reference']);phase=np.asarray(h['unclipped_phase_s'])
                    assert abs(float(np.max(abs(np.clip(phase,-15,15)-reference)))-h['phase_change_s'])<1e-12
                    if epoch==0:assert np.array_equal(reference,np.zeros_like(reference))
                    else:assert np.array_equal(reference,np.clip(history[epoch-1]['unclipped_phase_s'],-15,15))
                assert np.array_equal(sm['phase_reference'],history[-1]['reference'])
                tracks=sm['gates']['tracks']+sm['linear_gates'];ph=np.asarray(sm['state']['phases']);maxphase=float(np.max(abs(ph)))
                single=bool(tracks and all(t['compatible'] for t in tracks) and sm['final_phase_change_s']<=.01 and np.max(abs(x))<=12.5+1e-8 and np.isfinite(ph).all() and maxphase<=15.000001)
                gamma=bool(np.isfinite(raw['final_log_precision_change']) and raw['final_log_precision_change']<=1e-5)
                assert single==g['original_single_arm_valid']==r['original_single_arm_valid'] and gamma==g['Gamma_converged']==r['Gamma_converged']
                assert maxphase==g['maximum_unclipped_phase_s'] and sm['final_phase_change_s']==history[-1]['phase_change_s']==r['final_phase_change_s']
                m=g['membership'];orig=read(Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')/case/'parent.json')['coverage'][arm]
                lost=sorted(set(orig['accepted_observation_ids'])-set(m['accepted_observation_ids']))
                assert lost==g['original_accepted_IDs_lost'] and len(lost)==r['postfit_IDs_lost'] and (not lost)==r['all_original_accepted_IDs_preserved']
                assert set(m['curved_observation_ids'])==set(orig['curved_observation_ids']) and set(m['predictive_observation_ids'])==set(orig['predictive_observation_ids'])
                if method=='original':
                    parent=read(Path('/srv/bulk/leo/research/ds25-20261024/family_cavity/position')/(case+'.json'))['policy_arms'][arm]
                    dx=float(np.linalg.norm(x-parent['endpoint_east_north_km']));df=raw['full_objective']-parent['negative_twice_elbo'];rel=abs(df)/max(1,abs(parent['negative_twice_elbo']))
                    rep=g['baseline_reproduction'];assert abs(rep['endpoint_difference_km']-dx)<1e-12 and rep['objective_difference']==df
                    passed=dx<=.001 and abs(df)<=1e-3 and rel<=1e-8;assert passed==rep['passed'];original_ok.append(passed)
                else:corrected_ok.append(single and gamma and not lost)
                output.append(dict(case=case,method=method,arm=arm,status='complete',original_single_arm_valid=single,Gamma_converged=gamma,
                    maximum_unclipped_phase_s=maxphase,final_phase_change_s=sm['final_phase_change_s'],failed_curved_tracks=sum(not t['compatible'] for t in sm['gates']['tracks']),
                    failed_predictive_tracks=sum(not t['compatible'] for t in sm['linear_gates']),original_accepted_IDs_lost=len(lost),likelihood_IDs_exact=True,
                    baseline_reproduction=g['baseline_reproduction']))
        assert result['original_baseline_reproduced_both_arms']==all(original_ok)
        qualified=all(original_ok) and all(corrected_ok);assert result['corrected_research_paired_qualified']==qualified
        cases.append(dict(case=case,original_reproduced=all(original_ok),corrected_research_paired_qualified=qualified,operational_policy='original_reference'))
    assert bindings(p['files'])+bindings(s['files'])+bindings(read(ROOT/'measurement/RF_seal.json')['files'])==checked
    save('position_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        checked_bindings=checked,slots=output,cases=cases,all8_slots_preserved=True,completed_slots=sum(r['status']=='complete' for r in output),
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],RF_ready_for_separate_geographic_evaluation=True,
        native_alias_and_every_occurrence_injection_exact=True,full_curved_plus_predictive_factor_verified=True,
        five_original_phase_refresh_rounds_and_current_value_gates_verified=True,operational_policy='original_reference',
        audit_seconds=time.monotonic()-start,new_geometry_calls=0,new_optimizer_calls=0,GPS_read=False))

def geographic_readback():
    import math
    import numpy as np
    start=time.monotonic();here=ROOT/'position';geo=here/'geographic';freeze=read(here/'evaluation_freeze.json')
    checked=bindings(freeze['files'])+bindings(read(geo/'seal.json')['files'])+bindings(read(here/'RF_seal.json')['files'])
    terminal=read(ROOT/'audit/position_terminal.json');assert terminal['all_passed'] and terminal['RF_ready_for_separate_geographic_evaluation']
    summary=read(geo/'summary.json');assert summary['slots']==8 and summary['new_fits']==0 and summary['operational_policy']=='exact_original_reference'
    ref=summary['reference_latlon']
    def vector(lat,lon):
        a,b=math.radians(lat),math.radians(lon);return np.array([math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),math.sin(a)])
    target=vector(*ref)
    def distance(x):
        v=vector(37.906+x[1]/111.,-122.545+x[0]/(111.32*math.cos(math.radians(37.906))))
        return 6371.0088*math.atan2(float(np.linalg.norm(np.cross(v,target))),float(v@target))
    maximum=0.;by={}
    for row in summary['rows']:
        key=(row['case'],row['method'],row['arm']);assert key not in by;by[key]=row
        saved=read(Path('/srv/bulk/leo/research/ds25-20261024/family_cavity/position')/(row['case']+'.json'))['policy_arms'][row['arm']]
        baseline=distance(saved['endpoint_east_north_km']);err=abs(baseline-row['original_reference_error_km']);maximum=max(maximum,err);assert err<1e-8
        assert row['operational_policy_error_km']==row['original_reference_error_km'] and row['operational_policy']=='exact_original_reference'
        if row['status']=='complete':
            endpoint=read(here/row['case']/row['method']/row['arm']/'raw_endpoint.json')['summary']['endpoint_east_north_km']
            err=abs(distance(endpoint)-row['raw_position_error_km']);maximum=max(maximum,err);assert err<1e-8
        else:assert row['raw_position_error_km'] is None
    assert len(by)==8
    for pair in summary['paired']:
        a=by[(pair['case'],'original',pair['arm'])];b=by[(pair['case'],'corrected',pair['arm'])]
        assert pair['original_error_km']==a['raw_position_error_km'] and pair['corrected_error_km']==b['raw_position_error_km']
        assert abs(pair['raw_gain_m']-1000*(a['raw_position_error_km']-b['raw_position_error_km']))<1e-9
        expected=next(r['corrected_research_paired_qualified'] for r in terminal['cases'] if r['case']==pair['case'])
        assert pair['corrected_research_paired_qualified']==expected
    save('geographic_readback.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        geographic_seal_sha256=sha(geo/'seal.json'),evaluator_source_sha256=sha(here/'report.py'),checked_bindings=checked,
        complete_slots=8,paired=summary['paired'],maximum_independent_vector_distance_difference_km=maximum,
        operational_policy_unchanged=True,qualification_from_pre_geographic_RF_audit=True,
        root_released_saved_endpoint_evaluation=True,audit_seconds=time.monotonic()-start,new_fits=0,new_RF_processing=0))

def response_readback():
    import numpy as np
    start=time.monotonic();here=ROOT/'response';seal=read(here/'seal.json');checked=bindings(seal['source_bindings'])
    checked+=bindings({str(here/path):h for path,h in seal['files'].items()})
    old=PRIOR/'influence';old_seal=read(old/'RF_seal.json')
    for path in ('response_arrays.npz','complete_owner_ledger.json'):
        assert old_seal['files'][str(old/path)]==sha(old/path)
    arrays=__import__('numpy').load(old/'response_arrays.npz');ledger={r['case']:r for r in read(old/'complete_owner_ledger.json')}
    corrections=read(ROOT/'measurement/corrections.json')['rows'];summary=read(here/'summary.json')
    assert summary['posthoc'] and summary['tests']==2 and summary['cumulative_numeric_seconds']<=20 and summary['not_an_accuracy_forecast']
    assert summary['actual_native_ids']==159 and summary['no_additional_q']
    slots=read(ROOT/'position/execution.json')['all8_slots'];maximum=0.;owners=0
    for case,l in ledger.items():
        native=l['ordered_rows'];indices={r['observation_id']:i for i,r in enumerate(native)}
        selected=[r for r in corrections if r['case']==case];total=np.zeros(len(native));smooth=np.zeros(len(native))
        for owner in sorted({r['complete_owner'] for r in selected}):
            rr=sorted([r for r in selected if r['complete_owner']==owner],key=lambda r:(r['time_s'],r['native_observation_id']))
            ix=[indices[r['native_observation_id']] for r in rr];t=np.array([native[i]['time_s'] for i in ix]);q=np.array([native[i]['q'] for i in ix])
            assert all(native[i]['owner']==owner for i in ix)
            z=(t-t.min())/np.ptp(t)*2-1
            basis=np.column_stack([np.ones(len(t)),z,z*z])*q[:,None]
            u,sv,_=np.linalg.svd(basis,full_matrices=False);assert sv[-1]>sv[0]*1e-12
            delta=np.array([r['corrected_cfo_hz']-r['original_cfo_hz'] for r in rr]);low=u@(u.T@delta);rest=delta-low
            total[ix]=delta;smooth[ix]=low
            for arm in ('c0','fitted_c'):
                h=arrays[case+'_'+arm+'_response'];actual=next(r for r in summary['owner_rows'] if (r['case'],r['arm'],r['owner'])==(case,arm,owner))
                for component,v in (('total',delta),('quadratic',low),('rest',rest)):
                    answer=h[:,ix]@v*1000
                    reported=np.array([actual[component+'_east_m'],actual[component+'_north_m']]);error=float(np.max(abs(answer-reported)));maximum=max(maximum,error);assert error<1e-7
                owners+=1
        for arm in ('c0','fitted_c'):
            actual=next(r for r in summary['case_rows'] if (r['case'],r['arm'])==(case,arm));h=arrays[case+'_'+arm+'_response']
            for component,v in (('predicted',total),('quadratic',smooth),('rest',total-smooth)):
                answer=h@v*1000;reported=np.array([actual[component+'_east_m'],actual[component+'_north_m']]);error=float(np.max(abs(answer-reported)));maximum=max(maximum,error);assert error<1e-7
            original=next(r for r in slots if (r['case'],r['arm'],r['method'])==(case,arm,'original'))
            corrected=next(r for r in slots if (r['case'],r['arm'],r['method'])==(case,arm,'corrected'))
            answer=(np.asarray(corrected['endpoint_east_north_km'])-original['endpoint_east_north_km'])*1000
            assert np.max(abs(answer-np.array([actual['actual_RF_endpoint_east_m'],actual['actual_RF_endpoint_north_m']])))<1e-10
            assert abs(np.linalg.norm(answer)-actual['actual_RF_endpoint_norm_m'])<1e-10
    save('response_readback.json',dict(all_passed=True,response_seal_sha256=sha(here/'seal.json'),checked_bindings=checked,
        actual_native_IDs=159,owner_arm_rows=owners,case_arm_rows=4,independent_SVD_polynomial_subspace_projection=True,
        native_deltas_not_RF_scaled_again=True,maximum_vector_component_difference_m=maximum,
        actual_RF_endpoints_verified=True,posthoc_frozen_Gaussian_response_not_accuracy_forecast=True,
        audit_seconds=time.monotonic()-start,new_geometry=0,new_optimization=0,GPS_read=False))

def postfit_readback():
    import math
    start=time.monotonic();here=ROOT/'position/postfit_readback';protocol=read(here/'protocol.json');s=read(here/'seal.json')
    checked=bindings(protocol['files'])+bindings(s['files']);assert s['protocol_sha256']==sha(here/'protocol.json')
    out=read(here/'result.json');assert out['failure'] is None and out['all8_owner_contexts_complete'] and len(out['rows'])==8
    assert out['cumulative_seconds']<=30 and out['position_fits']==out['detector_calls']==0 and not out['gates_changed']
    corrected_ids={r['native_observation_id'] for r in read(ROOT/'measurement/corrections.json')['rows']}
    summary=[];candidate_checks=0
    for r in out['rows']:
        original=read(ROOT/'position/DS24-0011'/r['method']/r['arm']/'gates.json')['membership']['associations']
        accepted=next((g for g in original if g['component']==r['owner'] and g['compatible']),None)
        assert r['saved_status_reproduced'] and bool(accepted)==(r['chosen_norad'] is not None)
        if accepted:assert not set(accepted['observation_ids'])&corrected_ids
        raw=read(ROOT/'position/DS24-0011'/r['method']/r['arm']/'raw_endpoint.json')['summary']
        labels={g['candidate_index'] for g in raw['gates']['tracks'] if g['compatible']}
        assert labels=={c['candidate_index'] for c in r['candidates']} and not r['phase_excluded_candidates']
        passing=[]
        for c in r['candidates']:
            n=c['noise'];pred=dict(profile_RMS=c['profile_RMS_hz']<=450,profile_bias=abs(c['bias_hz'])<=3000,
                noise_mean=n['mean_z']<=3,noise_slope=n['slope_z']<=3,noise_quadratic=n['quadratic_bic_gain']<=10,
                noise_step=n['maximum_step_z']<=4,noise_ACF=abs(n['lag1_acf'])<=4/math.sqrt(r['points']),
                line_of_sight=c['minimum_elevation']>=0,supported_receiver_band=r['supported_group'],phase_in_operational_domain=abs(c['phase_s'])<=15)
            assert pred==c['predicates'] and [k for k,v in pred.items() if not v]==c['failed_predicates']
            assert all(pred.values())==c['passing'] and c['phase_s']==raw['state']['phases'][c['candidate_index']]
            if c['passing']:passing.append(c)
            candidate_checks+=1
        selected=min(passing,key=lambda c:c['cost']) if passing else None
        assert (selected['norad'] if selected else None)==r['chosen_norad']
        if accepted:
            assert abs(selected['profile_RMS_hz']-accepted['native_rms_hz'])<=1e-6 and abs(selected['bias_hz']-accepted['bias_hz'])<=1e-6
        label=57955 if '-RX1-' in r['owner'] else 56094;c=next(c for c in r['candidates'] if c['norad']==label)
        summary.append(dict(owner=r['owner'],arm=r['arm'],method=r['method'],norad=label,points=r['points'],slope_z=c['noise']['slope_z'],
            RMS_hz=c['profile_RMS_hz'],failed_predicates=c['failed_predicates'],accepted=r['chosen_norad'] is not None))
    failed=[r for r in summary if r['arm']=='c0' and r['method']=='corrected']
    assert len(failed)==2 and sum(r['points'] for r in failed)==57 and all(r['failed_predicates']==['noise_slope'] and not r['accepted'] for r in failed)
    save('postfit_readback.json',dict(all_passed=True,readback_protocol_sha256=sha(here/'protocol.json'),readback_seal_sha256=sha(here/'seal.json'),
        checked_bindings=checked,contexts=8,candidate_predicate_rows_checked=candidate_checks,originally_assigned_hypotheses=summary,
        c0_loss_is_only_slope_threshold_crossing=True,threshold_unchanged=3,points_lost=57,
        not_physical_identity_failure_proof=True,audit_seconds=time.monotonic()-start,new_geometry_calls=0,new_optimizer_calls=0))

def final_seal():
    receipts=('measurement_preflight.json','measurement_terminal.json','position_preflight.json','position_terminal.json','geographic_readback.json','response_readback.json','postfit_readback.json')
    passed=[read(ROOT/'audit'/name) for name in receipts];assert all(r['all_passed'] for r in passed)
    numerical_seconds=25.+sum(r.get('audit_seconds',0.) for r in passed);assert numerical_seconds<=120
    paths=[ROOT/name for name in ('README.md','COORDINATOR_PLAN.md','EVALUATION_SCOPE.md','position_go.json','stage_report.py')]
    paths += [p for p in (ROOT/'audit').iterdir() if p.is_file() and p.name!='final_seal.json' and p.suffix in ('.md','.py','.json')]
    for branch in ('measurement','position','response'):
        manifest=ROOT/branch/'lean_publication.json';paths.append(manifest)
        for row in read(manifest)['published']:
            path=Path(row['path']);assert sha(path)==row['sha256'];paths.append(path)
    for seal_path in (ROOT/'measurement/RF_seal.json',ROOT/'position/RF_seal.json',ROOT/'position/geographic/seal.json'):
        bindings(read(seal_path)['files'])
    repo=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
    paths +=[repo/'tools/report_470384_continuous_glrt_refinement.py',repo/'reports/2026_08_23_470384_continuous_glrt.md']
    diff=subprocess.run(['git','diff','--binary'],cwd=repo,capture_output=True,check=True).stdout
    diff_hash=hashlib.sha256(diff).hexdigest();assert diff_hash=='add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
    files={str(p):sha(p) for p in sorted(set(paths))}
    save('final_seal.json',dict(all_passed=True,passed_receipts=len(passed),receipt_names=list(receipts),files=files,
        numerical_audit_seconds_including_failed_attempt_allowance=numerical_seconds,audit_cap_seconds=120,
        original_dirty_diff_sha256=diff_hash,scientific_sources_inputs_and_outputs_unchanged=True,
        methodological_prior_art_corrected=True,operational_policy='original_reference',
        no_audit_IQ_detector_geometry_or_optimizer_calls=True,scope='Artifact and scientific-claim review; no new inference.'))

if __name__=='__main__':globals()[sys.argv[1]]()
