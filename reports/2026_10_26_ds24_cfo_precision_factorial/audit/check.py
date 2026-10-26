"""Independent saved-artifact audit; no geometry, detector or position calls."""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'ds24-complete-owner-refinement-r01'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bindings(files):
    for p,h in files.items():assert sha(p)==h,p
    return len(files)
def save(name,data):
    with (ROOT/'audit'/name).open('x') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')

def gaussian_fixture():
    """Proper dense covariance oracle, including fractional-power constants."""
    start=time.monotonic()
    sys.path[:0]=['/tmp/algo03-feasible-deps','/home/mouse9911/gits/leo-tracker-reduxredux/src','/home/mouse9911/gits/leo-tracker-reduxredux/tools']
    from ds23_frozen_precision import conditional_gaussian,arm_prior_precision
    rng=np.random.default_rng(20261026);n,k=13,5
    features=rng.normal(size=(n,k));raw=rng.normal(size=n);sigma=np.linspace(.7,1.4,n)
    power=np.linspace(.4,1,n);tau=np.linspace(.5,2,n);prior=np.linspace(.8,2.2,k)
    got=conditional_gaussian(raw,features,sigma,power,tau,prior,1.)
    noise=sigma*sigma/(power*tau);cov=np.diag(noise)+(features/prior)@features.T
    logdet=np.linalg.slogdet(cov)[1]
    correction=np.sum(power*np.log(2*np.pi*sigma*sigma/tau))-np.sum(np.log(2*np.pi*noise))
    expected=raw@np.linalg.solve(cov,raw)+logdet+n*np.log(2*np.pi)+correction
    coefficient=(features.T/prior[:,None])@np.linalg.solve(cov,raw)
    assert abs(expected-got['objective'])<1e-10 and np.max(abs(coefficient-got['coefficient']))<1e-10
    assert abs(got['residual']@got['residual']+got['normalization_constant']-got['objective'])<1e-10
    full=np.linspace(1.,3.,15);full[8]=1.
    assert np.array_equal(arm_prior_precision(np.delete(full,8),True),full)
    save('gaussian_fixture.json',dict(all_passed=True,dense_objective_difference=float(abs(expected-got['objective'])),
        maximum_dense_coefficient_difference=float(np.max(abs(coefficient-got['coefficient']))),
        fractional_power_normalization_checked=True,fitted_c_index8_roundtrip_exact=True,
        audit_seconds=time.monotonic()-start,geometry_calls=0,optimizer_calls=0))

def preflight():
    import os
    import subprocess
    start=time.monotonic();here=ROOT/'solver';p=read(here/'protocol.json');checked=bindings(p['files'])
    assert sha(here/'protocol.json')=='0279df94cbc7cfcfe4f080d8290ee2ebc912b2f95c00a2f84253a3f011804401'
    assert p['fit_count']==16 and p['cap_seconds']==600 and p['workers']==2 and p['BLAS_threads']==1 and p['maximum_seconds_per_fit']==30
    assert p['cold_position']==[0.,0.] and p['cold_phase_reference']=='zero' and p['phase_rounds']==5 and p['iterations']==48 and p['volume_weight']==1
    assert p['cells']==[['00','original','original'],['10','corrected','original'],['01','original','corrected'],['11','corrected','corrected']]
    prep=read(here/'preparation.json');packets=read(here/'packets.json')
    assert prep['all_passed'] and not prep['GPS_used'] and len(prep['controls'])==len(packets)==8
    expected={(c,a,o) for c in p['cases'] for a in p['arms'] for o in ('original','corrected')}
    assert {(r['case'],r['arm'],r['packet_origin']) for r in prep['controls']}==expected
    maximum={'coefficient':0.,'conditional_residual_hz':0.,'predictive_residual_hz':0.,'predictive_objective':0.};layouts={}
    for row in prep['controls']:
        case,arm,origin=row['case'],row['arm'],row['packet_origin'];packet=packets[case+'_'+arm+'_'+origin]
        old=read(packet['source_path']);assert sha(packet['source_path'])==packet['source_sha256']
        assert packet['final_phase_reference']==old['summary']['phase_reference']==old['summary']['history'][-1]['reference']
        assert packet['source_endpoint']==old['summary']['endpoint_east_north_km']
        assert packet['noise_precision']==old['noise_precision'] and packet['coefficient_prior_precision']==old['coefficient_prior_precision']
        assert row['packet_layout']==packet['layout'];layout=packet['layout'];layouts[(case,arm,origin)]=layout
        assert layout['hardware']==[0,8+int(arm=='fitted_c')]
        if arm=='fitted_c':assert packet['coefficient_prior_precision'][8]==1.
        a=np.load(row['array_path']);assert sha(row['array_path'])==row['array_sha256']
        assert np.array_equal(a['noise_precision'],packet['noise_precision']) and np.array_equal(a['prior_precision'],packet['coefficient_prior_precision'])
        assert np.array_equal(a['old_coefficient'],old['coefficient']) and np.array_equal(a['old_conditional_residual_hz'],old['conditional_residual_hz'])
        assert a['features'].shape==(len(a['keep']),layout['width']) and len(a['prior_precision'])==layout['width']
        active=np.unique(a['noise_groups'][a['keep']]);assert np.all(a['noise_precision'][active]>0) and np.all(a['prior_precision']>0)
        assert np.array_equal(active,row['active_noise_groups']) and row['inactive_noise_zeros']==np.sum(a['noise_precision']==0)
        dc=a['coefficient']-a['old_coefficient'];dr=a['conditional_residual_hz']-a['old_conditional_residual_hz']
        assert np.all(abs(dc)<=1e-6+1e-8*abs(a['old_coefficient'])) and np.max(abs(dr))<=1e-3
        assert np.max(abs(dr+a['features']@dc))<1e-6
        maximum['coefficient']=max(maximum['coefficient'],float(np.max(abs(dc))))
        maximum['conditional_residual_hz']=max(maximum['conditional_residual_hz'],float(np.max(abs(dr))))
        assert len(a['predictive_residual_hz'])==(615 if case=='DS24-0010' else 0)
        if len(a['predictive_residual_hz']):
            maximum['predictive_residual_hz']=max(maximum['predictive_residual_hz'],float(np.max(abs(a['predictive_residual_hz']-a['old_predictive_residual_hz']))))
        maximum['predictive_objective']=max(maximum['predictive_objective'],abs(row['predictive_objective_difference']))
        assert row['passed'] and row['full_prior_exact'] and row['noise_packet_exact'] and row['zero_CFO_delta_all_graph_arrays_exact']
        assert row['injection_receipt']==read(PRIOR/'position'/case/'injection.json')
        assert row['objectives_are_different'] and abs(row['predictive_objective_difference'])<=1e-3 and row['predictive_objective_relative_difference']<=1e-8
    for case in p['cases']:
        for arm in p['arms']:assert layouts[(case,arm,'original')]==layouts[(case,arm,'corrected')]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='/tmp/algo03-feasible-deps:/home/mouse9911/gits/leo-tracker-reduxredux/src:/home/mouse9911/gits/leo-tracker-reduxredux/tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',str(here/'test_model.py'),str(here/'test_evaluate.py')],env=env,capture_output=True,text=True,timeout=25)
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(p['files'])==checked and read(ROOT/'audit/gaussian_fixture.json')['all_passed']
    save('preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),checked_bindings=checked,
        eight_same_arm_packet_diagonals_checked=True,maxima=maximum,fitted_c_slot8_exact=True,
        packet_layout_and_units_exact=True,old_final_input_reference_verified=True,nuisance_mean_and_covariance_refit=True,
        original_predictive_factor_preserved=True,current_conditional_posterior_used_for_all_gates=True,
        conditional_objective_not_equated_with_VI=True,diagonal_endpoint_recovery_not_required=True,
        full_packet_effect_includes_noise_and_phase_prior_precision=True,tests_stdout=test.stdout,tests_stderr=test.stderr,
        root_GO_required=True,operational_policy='original_reference',audit_seconds=time.monotonic()-start,
        new_detector_calls=0,new_geometry_calls=0,new_optimizer_calls=0,GPS_read=False))

def terminal():
    start=time.monotonic();here=ROOT/'solver';p=read(here/'protocol.json');s=read(here/'RF_seal.json')
    checked=bindings(p['files'])+bindings(s['files']);assert s['protocol_sha256']==sha(here/'protocol.json')
    assert read(ROOT/'audit/preflight.json')['all_passed'] and read(ROOT/'solver_go.json')['approved']
    assert read(ROOT/'solver_go.json')['protocol_sha256']==s['protocol_sha256']
    execution=read(here/'execution.json');slots=execution['all16_slots'];packets=read(here/'packets.json')
    assert len(slots)==16 and execution['all_selected_terminal'] and execution['cumulative_worker_seconds']<=600
    assert {(r['case'],r['arm'],r['cell']) for r in slots}=={(c,a,z[0]) for c in p['cases'] for a in p['arms'] for z in p['cells']}
    details=[];vectors=[];membership_source=ROOT.parent/'ds24-fast-identifiability-r01/transfer/ownership'
    for row in slots:
        case,arm,cell=row['case'],row['arm'],row['cell'];label,cfo,origin=next(z for z in p['cells'] if z[0]==cell)
        assert row['CFO']==cfo and row['packet']==origin
        assert row==read(here/case/arm/(cell+'_result.json'))
        if row['status']!='complete':
            details.append(dict(case=case,arm=arm,cell=cell,status=row['status'],raw_endpoint_saved=(here/case/arm/cell/'raw_endpoint.json').exists()));continue
        raw=read(here/case/arm/cell/'raw_endpoint.json');g=read(here/case/arm/cell/'gates.json');sm=raw['summary'];packet=packets[case+'_'+arm+'_'+origin]
        assert raw['noise_precision']==packet['noise_precision'] and raw['coefficient_prior_precision']==packet['coefficient_prior_precision']
        assert raw['precision_packet_sha256']==hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert raw['Gamma_updated'] is False and g['frozen_Gamma_no_convergence_claim'] and g['packet_exact']
        assert g['VI_rebuild'] is False and g['posterior_kind']=='conditional_Gaussian'
        assert g['membership']['VI_parent_rebuilt'] is False and g['membership']['posterior_kind']=='same_frozen_conditional_Gaussian_instance'
        assert sm['negative_twice_elbo']==raw['conditional_Gaussian_objective']==row['conditional_Gaussian_objective']
        x=np.asarray(sm['endpoint_east_north_km']);assert np.array_equal(x,row['endpoint_east_north_km']) and x.shape==(2,) and np.isfinite(x).all()
        history=sm['history'];assert len(history)==5
        for epoch,h in enumerate(history):
            assert h==read(here/case/arm/cell/f'epoch{epoch}.json')
            reference=np.asarray(h['reference']);phase=np.asarray(h['unclipped_phase_s'])
            assert np.isfinite(reference).all() and np.isfinite(phase).all()
            assert abs(float(np.max(abs(np.clip(phase,-15,15)-reference)))-h['phase_change_s'])<1e-12
            assert np.array_equal(reference,np.zeros_like(reference) if epoch==0 else np.clip(history[epoch-1]['unclipped_phase_s'],-15,15))
        assert np.array_equal(sm['phase_reference'],history[-1]['reference']) and sm['final_phase_change_s']==history[-1]['phase_change_s']
        phases=np.asarray(sm['state']['phases']);maximum=float(np.max(abs(phases)));tracks=sm['gates']['tracks']+sm['linear_gates']
        valid=bool(tracks and all(t['compatible'] for t in tracks) and np.max(abs(x))<=12.5+1e-8 and np.isfinite(phases).all() and maximum<=15.000001 and sm['final_phase_change_s']<=.01)
        assert valid==g['original_single_arm_valid']==row['original_single_arm_valid'] and maximum==g['maximum_unclipped_phase_s']==row['maximum_unclipped_phase_s']
        m=g['membership'];old=read(membership_source/case/'parent.json')['coverage'][arm]
        assert set(m['curved_observation_ids'])==set(old['curved_observation_ids']) and set(m['predictive_observation_ids'])==set(old['predictive_observation_ids'])
        assert not set(m['curved_observation_ids'])&set(m['predictive_observation_ids'])
        lost=sorted(set(old['accepted_observation_ids'])-set(m['accepted_observation_ids']))
        assert lost==g['original_accepted_IDs_lost'] and len(lost)==row['original_accepted_IDs_lost']
        assert row['fixed_likelihood_IDs']==m['likelihood_points']==len(m['curved_observation_ids'])+len(m['predictive_observation_ids'])
        assert row['associated_IDs']==m['associated']==len(m['accepted_observation_ids'])
        assert g['operational_policy']==row['operational_policy']=='original_reference'
        details.append(dict(case=case,arm=arm,cell=cell,status='complete',original_single_arm_valid=valid,
            final_phase_change_s=sm['final_phase_change_s'],maximum_unclipped_phase_s=maximum,original_accepted_IDs_lost=len(lost),
            failed_curved_tracks=sum(not t['compatible'] for t in sm['gates']['tracks']),failed_predictive_tracks=sum(not t['compatible'] for t in sm['linear_gates']),
            fixed_likelihood_IDs=row['fixed_likelihood_IDs'],packet_exact=True))
    for case in p['cases']:
        assert read(here/case/'injection.json')==read(PRIOR/'position'/case/'injection.json')
        for arm in p['arms']:
            r={z['cell']:z for z in slots if z['case']==case and z['arm']==arm}
            if any(z['status']!='complete' for z in r.values()):vectors.append(dict(case=case,arm=arm,complete=False));continue
            x={k:np.asarray(z['endpoint_east_north_km']) for k,z in r.items()}
            cfo0=x['10']-x['00'];cfo1=x['11']-x['01'];packet0=x['01']-x['00'];packet1=x['11']-x['10']
            cc=(cfo0+cfo1)/2;pp=(packet0+packet1)/2;total=x['11']-x['00'];interaction=cfo1-cfo0
            assert np.max(abs(cc+pp-total))<1e-12
            vectors.append(dict(case=case,arm=arm,complete=True,CFO_at_original_packet_km=cfo0.tolist(),CFO_at_refined_packet_km=cfo1.tolist(),
                packet_at_original_CFO_km=packet0.tolist(),packet_at_refined_CFO_km=packet1.tolist(),interaction_km=interaction.tolist(),
                symmetric_CFO_km=cc.tolist(),symmetric_packet_km=pp.tolist(),total_km=total.tolist()))
    assert bindings(p['files'])+bindings(s['files'])==checked
    save('terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),checked_bindings=checked,
        slots=details,all16_slots_retained=True,complete_slots=sum(r['status']=='complete' for r in details),factorial_vectors=vectors,
        precision_packets_exact_in_every_completed_fit=True,conditional_posterior_gates_not_VI=True,
        full_likelihood_membership_preserved=True,no_Gamma_convergence_claim=True,cumulative_worker_seconds=execution['cumulative_worker_seconds'],
        RF_ready_for_separate_geographic_evaluation=True,operational_policy='original_reference',audit_seconds=time.monotonic()-start,
        new_geometry_calls=0,new_optimizer_calls=0,GPS_read=False))

def evaluation_readback():
    import math
    start=time.monotonic();here=ROOT/'solver';rf=read(here/'rf_report/summary.json');geo=read(here/'geographic/summary.json')
    checked=bindings(read(here/'protocol.json')['files'])+bindings(read(here/'RF_seal.json')['files'])
    checked+=bindings(read(here/'rf_report/seal.json')['files'])+bindings(read(here/'geographic/seal.json')['files'])
    assert read(ROOT/'audit/terminal.json')['all_passed'] and len(rf['rows'])==len(geo['rows'])==16
    own=read(ROOT/'audit/terminal.json')['factorial_vectors']
    for r in rf['contrasts']:
        q=next(x for x in own if x['case']==r['case'] and x['arm']==r['arm']);assert r['complete']==q['complete']
        if not r['complete']:continue
        for key,value in r['vectors_km'].items():
            assert np.max(abs(np.array(value)-q[key+'_km']))<1e-12
            assert abs(r['norms_m'][key]-np.linalg.norm(value)*1000)<1e-9
    def v(lat,lon):
        a,b=math.radians(lat),math.radians(lon);return np.array([math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),math.sin(a)])
    target=v(*geo['reference_latlon'])
    def distance(x):
        z=v(37.906+x[1]/111.,-122.545+x[0]/(111.32*math.cos(math.radians(37.906))))
        return 6371.0088*math.atan2(float(np.linalg.norm(np.cross(z,target))),float(z@target))
    maximum=0.;paired=[];diagonal=[]
    for r in geo['rows']:
        original=read(PRIOR/'position'/r['case']/'original'/r['arm']/'raw_endpoint.json')['summary']['endpoint_east_north_km']
        old=distance(original);maximum=max(maximum,abs(old-r['operational_reference_error_km']));assert abs(old-r['operational_reference_error_km'])<1e-8
        assert r['operational_policy_error_km']==r['operational_reference_error_km'] and r['operational_policy']=='exact_original_reference'
        if r['status']=='complete':
            raw=read(here/r['case']/r['arm']/r['cell']/'raw_endpoint.json');error=distance(raw['summary']['endpoint_east_north_km'])
            maximum=max(maximum,abs(error-r['raw_position_error_km']));assert abs(error-r['raw_position_error_km'])<1e-8
            g=read(here/r['case']/r['arm']/r['cell']/'gates.json');assert r['original_single_arm_valid']==g['original_single_arm_valid'] and r['original_accepted_IDs_lost']==len(g['original_accepted_IDs_lost'])
        else:assert r['raw_position_error_km'] is None
    for case in ('DS24-0010','DS24-0011'):
        for arm in ('c0','fitted_c'):
            rows={r['cell']:r for r in geo['rows'] if r['case']==case and r['arm']==arm}
            if all(r['status']=='complete' for r in rows.values()):
                paired.append(dict(case=case,arm=arm,CFO_gain_original_packet_m=1000*(rows['00']['raw_position_error_km']-rows['10']['raw_position_error_km']),
                    CFO_gain_refined_packet_m=1000*(rows['01']['raw_position_error_km']-rows['11']['raw_position_error_km'])))
                for cell,origin in (('00','original'),('11','corrected')):
                    old=read(PRIOR/'position'/case/origin/arm/'raw_endpoint.json')['summary']['endpoint_east_north_km']
                    current=np.array([rows[cell]['east_km'],rows[cell]['north_km']]);difference=(current-old)*1000
                    diagonal.append(dict(case=case,arm=arm,cell=cell,conditional_minus_VI_endpoint_east_north_m=difference.tolist(),norm_m=float(np.linalg.norm(difference))))
    save('evaluation_readback.json',dict(all_passed=True,checked_bindings=checked,RF_seal_sha256=sha(here/'RF_seal.json'),
        geographic_seal_sha256=sha(here/'geographic/seal.json'),all16_rows_retained=True,all_signed_RF_contrasts_and_norms_verified=True,
        independent_unit_vector_distances=True,maximum_distance_difference_km=maximum,within_packet_CFO_error_contrasts=paired,
        separate_diagonal_conditional_vs_VI_comparison=diagonal,conditional_gate_and_retention_labels_exact=True,
        operational_reference_unchanged=True,root_released_evaluation=True,audit_seconds=time.monotonic()-start,new_fits=0,new_geometry=0))

def optimizer_readback():
    from collections import Counter
    start=time.monotonic();here=ROOT/'solver';counts=Counter();epochs=0;maximum_increase=0.
    for slot in read(here/'execution.json')['all16_slots']:
        if slot['status']!='complete':continue
        previous=np.zeros(2)
        for epoch in range(5):
            h=read(here/slot['case']/slot['arm']/slot['cell']/f'epoch{epoch}.json')['fit'];trace=h['history']
            assert 1<=len(trace)<=49 and np.array_equal(trace[0]['parameters'],previous)
            assert np.array_equal(trace[-1]['parameters'],h['parameters']) and abs(trace[-1]['score']-h['score'])<1e-8
            scores=np.array([q['score'] for q in trace]);points=np.array([q['parameters'] for q in trace])
            assert np.isfinite(scores).all() and np.isfinite(points).all() and np.max(abs(points))<=12.5+1e-8
            if len(scores)>1:
                increase=float(np.max(np.diff(scores)));maximum_increase=max(maximum_increase,increase);assert increase<=1e-8
            counts[h['stopped']]+=1;previous=np.asarray(h['parameters']);epochs+=1
    assert epochs==80
    save('optimizer_readback.json',dict(all_passed=True,epochs=epochs,stopping_reasons=dict(counts),
        accepted_score_histories_monotone=True,starts_bounds_and_final_parameters_exact=True,
        maximum_accepted_score_increase=maximum_increase,no_new_optimizer_qualification_rule=True,
        mathematical_global_convergence_not_claimed=True,audit_seconds=time.monotonic()-start,new_fits=0))

def linearization_readback():
    import csv
    start=time.monotonic();here=ROOT/'linearization';seal=read(here/'seal.json')
    checked=bindings(seal['source_bindings'])+bindings({str(here/p):h for p,h in seal['files'].items()})
    summary=read(here/'summary.json');own=read(ROOT/'audit/terminal.json')['factorial_vectors']
    previous=read(PRIOR/'response/summary.json')['case_rows'];rows=summary['rows'];assert len(rows)==4
    errors=[]
    for r in rows:
        case,arm=r['case'],r['arm'];old=next(q for q in previous if (q['case'],q['arm'])==(case,arm));new=next(q for q in own if (q['case'],q['arm'])==(case,arm))
        h=np.array([old['predicted_east_m'],old['predicted_north_m']]);isolated=np.array(new['CFO_at_original_packet_km'])*1000
        total=np.array(new['total_km'])*1000;interaction=np.array(new['interaction_km'])*1000
        original=read(PRIOR/'position'/case/'original'/arm/'raw_endpoint.json')['summary']['endpoint_east_north_km']
        corrected=read(PRIOR/'position'/case/'corrected'/arm/'raw_endpoint.json')['summary']['endpoint_east_north_km']
        vi=(np.asarray(corrected)-original)*1000
        for label,value in (('Hdelta',h),('isolated_CFO',isolated),('full_conditional',total),('previous_VI',vi)):
            assert np.max(abs(value-np.array([r[label+'_east_m'],r[label+'_north_m']])))<1e-10
        error=float(np.linalg.norm(h-isolated));assert abs(error-r['H_vs_isolated_difference_norm_m'])<1e-10
        assert abs(np.linalg.norm(h-vi)-r['H_vs_previous_VI_difference_norm_m'])<1e-10
        assert abs(np.linalg.norm(total-vi)-r['full_conditional_vs_previous_VI_difference_norm_m'])<1e-10
        assert abs(np.linalg.norm(interaction)-r['factorial_interaction_norm_m'])<1e-10
        errors.append(dict(case=case,arm=arm,H_vs_original_packet_CFO_difference_m=error))
    assert summary['saved_only'] and not summary['GPS_or_geometry_or_fits'] and summary['cumulative_numeric_seconds']<=5
    checked+=bindings({str(here/p):h for p,h in read(here/'plot02_seal.json')['files'].items()})
    save('linearization_readback.json',dict(all_passed=True,checked_bindings=checked,source_seal_sha256=sha(here/'seal.json'),
        comparisons=errors,all_signed_vectors_and_units_verified=True,posthoc_not_forecast_or_noise_only_cause=True,
        audit_seconds=time.monotonic()-start,new_fits=0,new_geometry=0,GPS_read=False))

def metadata_readback():
    start=time.monotonic();here=ROOT/'validation';d=read(here/'cohort_ledger.json');checked=bindings(d['source_bindings'])
    rows=d['rows'];assert len(rows)==32 and len({r['recording_id'] for r in rows})==32
    assert sum(r['previous_later8'] for r in rows)==8
    eligible=[r for r in rows if r['metadata_eligible_remaining']]
    assert len(eligible)==22
    selected=[r['recording_id'] for r in sorted(eligible,key=lambda r:(r['name_time_proxy_utc_ns'],r['recording_id']))[:4]]
    assert selected==d['proposed_fixed4_recordings']
    for r in rows:
        predicate=not r['previous_later8'] and r['current_state']=='complete' and r['current_session_id']==r['session_id'] and any(q['sample_rate_hz']==10000000 and q['qualified'] for q in r['contract_metadata'])
        assert predicate==r['metadata_eligible_remaining']
        assert not r['full_input_validated_now'] and not r['raw_authority_reconstructed_now'] and not r['research_parent_ready']
    assert d['metadata_only'] and not d['IQ_or_RF_arrays'] and not d['positions_or_errors_read'] and not d['untouched_holdout_claimed']
    exposure=read(here/'exposure_match.json')
    save('metadata_readback.json',dict(all_passed=True,checked_bindings=checked,cohort_ledger_sha256=sha(here/'cohort_ledger.json'),
        rows=32,previous_later8=8,remaining_metadata_eligible=22,first_four_recordings=selected,
        recording_name_chronology_not_acquisition_authority=True,full_input_raw_parent_readiness_not_established=True,
        incomplete_exposure_search_not_zero_matches=True,not_clean_holdout_claim=True,
        audit_seconds=time.monotonic()-start,no_external_metadata_queries=True,new_scientific_processing=0))

def final_seal():
    import subprocess
    names=('gaussian_fixture.json','preflight.json','terminal.json','optimizer_readback.json','evaluation_readback.json','linearization_readback.json','metadata_readback.json')
    receipts=[read(ROOT/'audit'/n) for n in names];assert all(r['all_passed'] for r in receipts)
    seconds=1.+sum(r.get('audit_seconds',0.) for r in receipts);assert seconds<=120
    paths=[ROOT/n for n in ('README.md','COORDINATOR_PLAN.md','LINEARIZATION_READBACK.md','solver_go.json','stage_report.py')]
    paths +=[p for p in (ROOT/'audit').iterdir() if p.is_file() and p.name!='final_seal.json' and p.suffix in ('.md','.py','.json')]
    paths +=[p for p in (ROOT/'validation').iterdir() if p.is_file()]
    for branch in ('solver','linearization'):
        m=ROOT/branch/'lean_publication.json';paths.append(m)
        for row in read(m)['published']:
            p=Path(row['path']);assert sha(p)==row['sha256'];paths.append(p)
    for p in (ROOT/'solver/protocol.json',ROOT/'solver/RF_seal.json',ROOT/'solver/rf_report/seal.json',ROOT/'solver/geographic/seal.json'):
        bindings(read(p)['files'])
    scope=read(ROOT/'validation/prepared_parent_scope.json')
    for row in scope['checks']:assert sha(row['path'])==row['sha256'] and row['exact_selected_identity_matches']==[]
    assert scope['verified_research_parent_ready_count']==0
    coverage=[]
    for r in read(ROOT/'solver/rf_report/summary.json')['rows']:
        if r['status']=='complete':coverage.append(dict(case=r['case'],arm=r['arm'],cell=r['cell'],associated=r['associated_IDs'],
            denominator=r['total_GLRT'],percent=100*r['associated_IDs']/r['total_GLRT']))
    diff=subprocess.run(['git','diff','--binary'],cwd='/home/mouse9911/gits/leo-tracker-reduxredux',capture_output=True,check=True).stdout
    diff_hash=hashlib.sha256(diff).hexdigest();assert diff_hash=='add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
    save('final_seal.json',dict(all_passed=True,passed_receipts=len(receipts),receipt_names=list(names),files={str(p):sha(p) for p in sorted(set(paths))},
        numerical_audit_seconds=seconds,audit_cap_seconds=120,root_association_percentages_recomputed=coverage,
        original_dirty_diff_sha256=diff_hash,operational_policy='original_reference',no_audit_geometry_detector_or_optimizer_calls=True,
        conditional_factorial_not_physical_noise_calibration=True,metadata_block_not_verified_holdout=True))

if __name__=='__main__':globals()[sys.argv[1]]()
