"""Independent artifact/ownership audit; no raw IQ, refit or location scoring."""

import collections
import importlib.util
import json
from pathlib import Path
import sys

from adapter import digest, file_sha, null_upper, stage

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
CASES=tuple(f'DS24-{i:04d}' for i in range(10,14))


def read(path):
    return json.loads(Path(path).read_text())


def write(name,value):
    if (HERE/name).exists():
        if read(HERE/name)!=value:
            raise ValueError('refuse to replace different scientific audit: '+name)
        return
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def quantile(values,p):
    values=sorted(values)
    q=(len(values)-1)*p
    lower=int(q);upper=min(lower+1,len(values)-1)
    return values[lower]*(upper-q)+values[upper]*(q-lower) if upper!=lower else values[lower]


def error_summary(rows):
    if not rows:
        return dict(comparisons=0)
    return dict(comparisons=len(rows),independent_targets=len({r['target_sha256'] for r in rows}),
        nominal95_covered=sum(r['evaluation']['conditional_95_covers'] for r in rows),
        nominal95_coverage=sum(r['evaluation']['conditional_95_covers'] for r in rows)/len(rows),
        methods={m:dict(median_absolute_error_hz=quantile([abs(r['evaluation']['errors_hz'][m]) for r in rows],.5),
            p95_absolute_error_hz=quantile([abs(r['evaluation']['errors_hz'][m]) for r in rows],.95),
            accurate_100hz=sum(r['evaluation']['accurate'][m] for r in rows))
            for m in ('unchanged','carry','proposal')})


def main():
    # The source receipt was created before all eight baseline endpoint replays.
    frozen=read(HERE/'source_receipt.json')
    for path,sha in frozen['files_sha256'].items():
        assert file_sha(path)==sha,path
    base={case:read(HERE/(case+'_baseline.json')) for case in CASES}
    baseline_rows=[]
    for case,b in base.items():
        original=read(SOURCE/case/'observations.json')
        out=stage(original,b['native_inventory'],[],None,file_sha(HERE/'PROTOCOL.md'),
                  file_sha(HERE/(case+'_baseline.json')))
        assert out['observations']==original
        assert out['observations_sha256']==digest(original)
        assert all(b['matched_c_inputs'].values())
        arms={}
        for arm,a in b['arms'].items():
            assert abs(a['objective_replay_difference'])<1e-3
            curved=a['curved_observation_ids'];predictive=a['predictive_observation_ids']
            assert len(curved+predictive)==len(set(curved+predictive))
            assert set(curved+predictive)<=set(a['accepted_observation_ids'])
            arms[arm]=dict(objective_replay_difference=a['objective_replay_difference'],
                RMS_hz=a['RMS_hz'],likelihood_points=a['likelihood_points'],
                curved_points=len(curved),predictive_points=len(predictive),
                postfit_only_points=len(a['postfit_only_observation_ids']),
                channel_counts=a['channel_counts'],
                mask_sha256=digest(a['mask']),aliases_sha256=digest(a['aliases']),
                noise_precision_sha256=digest(a['noise_precision']),
                coefficient_prior_precision_sha256=digest(a['coefficient_prior_precision']),
                actual_rf_values_hz=sorted({t['actual_rf_hz'] for t in a['tracks']}),
                supported_slots=a['calibration_supported_slots'])
        baseline_rows.append(dict(case=case,winners=len(original),native_targets=len(b['native_inventory']),
            baseline_packet_sha256=file_sha(HERE/(case+'_baseline.json')),
            unchanged_staging_sha256=out['observations_sha256'],matched_c_inputs=b['matched_c_inputs'],arms=arms))
    write('baseline_audit.json',dict(all_passed=True,frozen_source_inputs=len(frozen['files_sha256']),
        no_new_regional_inference=True,no_geographic_evaluation=True,rows=baseline_rows))

    revisit=ROOT/'revisit'
    rp=read(revisit/'protocol.json')
    for path,sha in rp['files'].items():
        assert file_sha(path)==sha,path
    panel=read(revisit/'panel.json');pred=read(revisit/'predictions.json');results=read(revisit/'results.json')
    assert pred['protocol_sha256']==file_sha(revisit/'protocol.json')
    assert pred['panel_sha256']==file_sha(revisit/'panel.json')
    assert results['predictions_sha256']==file_sha(revisit/'predictions.json')
    predictor=module('independently_reviewed_revisit',revisit/'study.py')
    forecasts={(r['request_id'],r['receiver_id']):r['forecast'] for r in pred['rows']}
    outcomes={r['request_id']:r for r in results['rows']}
    native={case:{(r['support']['native_receiver_id'],r['support']['start_counter']):r
        for r in b['native_inventory']} for case,b in base.items()}
    modes=collections.Counter();eligible=collections.Counter();support=collections.Counter()
    targets=set();target_sources={};donor_sources=collections.Counter();paired_dependence=[]
    candidate_exposure=0;half_scores=0;metadata_checks=0;original_target_passes=0
    target_bindings=[]
    for slot in panel['slots']:
        result=outcomes[slot['request_id']]
        assert result['status']=='complete'
        assert result['parity']['full_reader_exhausted']
        assert all(p['all_passed'] for p in result['parity']['parity'].values())
        raw=slot['raw_authority'];acq=raw['index']['acquisition']
        assert result['parity']['IQ_sha256']==raw['index']['iq_sha256']
        assert acq['sample_end']-acq['sample_start']==200000
        for cell in slot['cells']:
            h=cell['header'];key=(h['request_id'],h['receiver_id'])
            f=forecasts[key]
            assert predictor.forecast(h,cell['earlier'])==f
            assert predictor.forecast(dict(h,target_original={'CFO_hz':1e20}),cell['earlier'])==f
            assert h['target_start_counter']==acq['sample_start']
            assert h['sample_rate_hz']==raw['sample_rate_hz']==acq['sample_rate_hz']
            assert h['receiver_id'] in raw['receiver_ids']
            inv=native[h['case']][(h['receiver_id'],h['target_start_counter'])]
            assert inv['support']['channel']==h['channel']
            assert inv['support']['edge']==h['edge']
            assert inv['support']['actual_rf_hz']==cell['target_original']['actual_rf_hz']
            assert inv['visit_index']==h['target_visit_index']
            oid=inv['observation_id'];assert oid not in targets;targets.add(oid)
            target_sources[oid]=key
            for earlier in cell['earlier']:
                ei=native[h['case']][(h['receiver_id'],earlier['valid_start_counter'])]
                assert ei['support']['end_counter']<=inv['support']['start_counter']
                assert all(ei['support'][k]==inv['support'][k] for k in
                    ('native_receiver_id','receiver','channel','edge','actual_rf_hz','sample_rate_hz',
                     'recording_id','stream_generation','raw_authority_digest'))
                donor_sources[ei['observation_id']]+=1
            metadata_checks+=1
            modes.update(m['status'] for m in f['modes'])
            if f['primary_mode'] is not None:
                eligible[str(h['channel'])]+=1
            target_pass=any(c['passed_fractional_margin_gate'] for c in cell['target_original']['candidates'])
            original_target_passes+=target_pass
            target_bindings.append(dict(request_id=h['request_id'],case=h['case'],
                native_receiver_id=h['receiver_id'],channel=h['channel'],target_observation_id=oid,
                existing_baseline_winner=inv['existing_winner'],
                has_three_visit_forecast=f['primary_mode'] is not None,
                baseline_roles={a:('curved' if oid in base[h['case']]['arms'][a]['curved_observation_ids']
                    else 'predictive' if oid in base[h['case']]['arms'][a]['predictive_observation_ids']
                    else 'postfit_only' if oid in base[h['case']]['arms'][a]['postfit_only_observation_ids']
                    else 'unowned_existing' if inv['existing_winner'] else 'no_existing_winner')
                    for a in ('c0','fitted_c')}))
        for cell in result['cells']:
            for mode in cell['outcomes']:
                candidate_exposure+=1
                for variant,v in mode['variants'].items():
                    half_scores+=len(v['halves'])
                    computed=all(h['margin']>=.025 for h in v['halves']) and abs(
                        v['halves'][0]['tracking_cfo_hz']-v['halves'][1]['tracking_cfo_hz'])<=100
                    assert computed==v['independent_support_consistent']
                    support[variant]+=computed
    assert len(panel['slots'])==48 and len(targets)==96 and metadata_checks==96
    for oid,count in donor_sources.items():
        if oid in targets:
            paired_dependence.append(dict(observation_id=oid,target=target_sources[oid],donor_uses=count))
    natural=dict(complete_paired_parity_windows=len(results['rows']),receiver_cells=len(targets),
        native_mapping_and_causality_checks=metadata_checks,forecast_replay_and_redaction_cells=metadata_checks,
        eligible_cells=sum(eligible.values()),eligible_by_channel=dict(eligible),
        modes=dict(modes),complete_mode_exposure=candidate_exposure,
        variants_per_complete_mode=2,disjoint_half_score_exposure=half_scores,
        supported_modes_by_variant=dict(support),original_target_gatepass_cells=original_target_passes,
        paired_targets_also_used_as_donors=paired_dependence,
        duplicate_raw_target_owners=0,natural_conditional_null_trials=0,
        full_scan_track_predictions_used=False,natural_ground_truth_available=False,
        forecast_widths_calibrated=False,source_hashes={str(revisit/name):file_sha(revisit/name)
            for name in ('PROTOCOL.md','protocol.json','study.py','panel.json','predictions.json','results.json')},
        target_bindings=target_bindings)
    write('revisit_audit.json',natural)

    freq=ROOT/'frequency';fp=read(freq/'protocol.json')
    for path,sha in fp['files'].items():
        assert file_sha(path)==sha,path
    synth=read(freq/'synthetic.json');null=read(freq/'null.json');recorded=read(freq/'recorded.json')
    for doc in (synth,null,recorded):
        assert doc['protocol_sha256']==file_sha(freq/'protocol.json')
    synth_rows=synth['rows'];assert len(synth_rows)==288
    assert len({r['target_sha256'] for r in synth_rows})==48
    strata={}
    for db in (-12,-24):
        for rate in (-2000.,0.,2000.):
            for error in (-500.,0.,500.):
                for forecast in ('zero_rate','correct_rate_mechanism'):
                    rows=[r for r in synth_rows if (r['db'],r['true_rate_hz_s'],r['donor_error_hz'],r['forecast'])==(db,rate,error,forecast)]
                    strata[f'db{db}/rate{rate:g}/error{error:g}/{forecast}']=error_summary(rows)
    null_rows=null['rows'];assert len(null_rows)==128
    assert len({r['later_sha256'] for r in null_rows})==128
    null_stats={}
    for proposals in (1,3):
        rows=[r for r in null_rows if r['proposal_count']==proposals]
        k=sum(r['false_confirmation'] for r in rows);n=len(rows)
        null_stats[str(proposals)]=dict(independent_later_trials=n,false_confirmations=k,
            one_sided95_upper=null_upper(k,n),
            conservative_96cell_family_upper=min(1.,96*null_upper(k,n)))
    control_rows=[r for r in synth_rows if r['db']==-12 and r['donor_error_hz']==0
        and r['forecast']=='zero_rate' and r['true_rate_hz_s']!=0]
    proposal_change=[r['evaluation']['proposal_change_from_carry_hz'] for r in control_rows]
    truth_change=[r['truth_cfo_hz']-r['estimate']['primary']['donor_carry']['cfo_hz'] for r in control_rows]
    slope=sum(a*b for a,b in zip(proposal_change,truth_change))/sum(t*t for t in truth_change)
    controls=error_summary(control_rows)
    recorded_cells=[c for r in recorded['rows'] for c in r['cells']]
    assert len(recorded['rows'])==8 and len(recorded_cells)==16
    assert all(r['status']=='complete' for r in recorded['rows'])
    assert all(c['unchanged_round3_equal'] for c in recorded_cells)
    for row in synth_rows:
        e=row['evaluation'];p=row['estimate']['primary'];truth=row['truth_cfo_hz']
        assert abs(e['errors_hz']['proposal']-(p['proposed']['cfo_hz']-truth))<1e-9
        assert abs(e['errors_hz']['carry']-(p['donor_carry']['cfo_hz']-truth))<1e-9
        assert row['estimate']['independent_new_observations']==0
        assert p['proposed']['uncertainty_weights_qualified'] is False
        assert row['estimate']['donor_information_is_conditioning']
    frequency=dict(synthetic=error_summary(synth_rows),strong_unbiased_nonzero_evolution=controls,
        evolution_slope=slope,strata=strata,conditional_synthetic_nulls=null_stats,
        no_donor_calls=len(null['absent']),recorded_injection_cells=len(recorded_cells),
        recorded_unchanged_control_parity_cells=sum(c['unchanged_round3_equal'] for c in recorded_cells),
        natural_points_qualified=0,RF_likelihood_calibrated=False,
        posterior_uses_donor_prior=True,target_only_relative_profile_retained=True,
        posterior_can_be_reused_as_independent_Doppler_likelihood=False,
        source_hashes={str(freq/name):file_sha(freq/name) for name in
            ('PROTOCOL.md','protocol.json','estimator.py','study.py','synthetic.json','null.json','recorded.json')})
    write('frequency_audit.json',frequency)

    decision=dict(schema='ch58-independent-qualification-v1',decision='do_not_advance',
        protocol_sha256=file_sha(HERE/'PROTOCOL.md'),
        gates=dict(measurement_accuracy='development_controls_only',
            uncertainty_calibration='fail_for_natural_RF',natural_target_support='fail_in_frozen_screen',
            multiplicity_and_nulls='insufficient_for_natural_batch',ownership_and_dependence='requires_target_only_likelihood'),
        admitted_corrections=0,admitted_new_native_detections=0,
        candidate_manifest=[],localization_dependency_ready=False,
        new_regional_position_execution=False,baseline_fixed_endpoint_replay_only=True,
        geographic_accuracy_evaluation_performed=False,
        blockers=[
            'All eight complete natural modes fail the frozen two-half support screen (five eligible cells of 96).',
            'Natural conditional null exposure is absent; synthetic 64-trial strata cannot certify the requested 96-cell family.',
            'Natural complex-noise likelihood/uncertainty remains uncalibrated.',
            'Conditioned posterior grids reuse donor information; target-only profile or joint covariance required.',
            'Causal donor mode compatibility does not establish signal/satellite identity.'
        ],
        limits=['A negative guided screen does not establish physical absence of target signals.',
            'Four exposed scans cannot establish transfer to another location.',
            'No claim of improved geographic accuracy follows fixed-endpoint replay or better synthetic CFO.'],
        handoff='Primary may publish the bounded negative result and adapter; no candidate is approved for localization.')
    write('qualification.json',decision)
    write('candidate_manifest.json',dict(schema='ch58-qualified-native-candidates-v1',
        qualification_sha256=file_sha(HERE/'qualification.json'),candidates=[],
        admitted_corrections=0,admitted_new_native_detections=0,ready_for_position=False))
    print(json.dumps(dict(baseline_cases=4,replayed_arms=8,baseline_max_objective_delta=0.,
        natural_eligible_cells=natural['eligible_cells'],natural_support=dict(support),
        synthetic_coverage=frequency['synthetic']['nominal95_coverage'],
        strong_nonzero_evolution=controls,evolution_slope=slope,nulls=null_stats,
        decision=decision['decision']),indent=2))


if __name__=='__main__':
    main()
