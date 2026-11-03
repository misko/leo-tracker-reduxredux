"""Exploratory independent-RF calibration on three matched identity hypotheses.

No GPS or following TLE enters construction, qualification or optimization.
Uncertainty scales are engineering sensitivity controls, not calibrated error
bars inferred from the five-Hz leave-frame-out range.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy

import numpy as np

from algo02_scan import pair_passes
from ds23_radio_calibration_factor import make_calibrated_problem,attach_calibrated_predictive,principal_radio_contrast
from ds23_feasible_position import feasible_fit
from debug_ds23_0268_visibility_reentry import OUT as MODELS
from investigate_ds23_0268_remaining_tracks import load,fine_receiver_basis
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached,summary
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_0268_radio_calibration_principal'
WAVE=ROOT/'reports/2026_10_20_ds23_0268_shared_waveform'
HYPOTHESES=dict(original='trials/interior_add_66797.json',
    split='selected_split_all_RX1_constrained.json',whole='whole_family_67953_constrained.json')
ARMS=('c0','fitted_c')


def prepare():
    OUT.mkdir(exist_ok=True)
    p=OUT/'protocol.json'
    sources={str(path.relative_to(ROOT)):sha(path) for path in (
        ROOT/'tools/probe_ds23_0268_radio_calibration.py',ROOT/'tools/ds23_radio_calibration_factor.py',
        ROOT/'tools/dsx01_hierarchical_bound.py',ROOT/'tools/ds23_frequency_events.py')}
    if p.exists():
        protocol=read(p)
        if protocol['source_sha256']!=sources:raise ValueError('frozen calibration experiment changed')
        return protocol
    waveform=read(WAVE/'curved_pair_waveform_analysis.json')
    phase={r['visit_index']:r for r in read(WAVE/'shared_frame_gain_diagnostic.json')['rows']}
    plan={r['visit_index']:r for r in read(WAVE/'calibration_plan.json')['pairs']}
    observations={r['observation_id']:r for r in read(SOURCE/'DS23-0268/observations.json')}
    measurements=[]
    for row in waveform['rows']:
        carrier=row['whole_probe_carrier']
        fingerprint=phase[row['visit_index']]
        if not (row['best']['residual_coherence']>row['shuffled_control_maximum'] and
                carrier['coherence']>=.001 and carrier['leave_frame_out_range_hz']<=25 and
                fingerprint['shared_nonlinear_phase_fingerprint'] and fingerprint['amplitude_correlation']>=.9):
            continue
        pair=plan[row['visit_index']]
        point=pair['receivers']['0']
        measured=observations[point['observation_id']]
        measurements.append(dict(visit_index=row['visit_index'],time_s=measured['time_s'],
            channel=point['probe']['channel'],rf_hz=point['probe']['actual_rf_hz'],
            relative_CFO_hz=float(principal_radio_contrast(carrier['relative_CFO_hz'])),
            raw_relative_CFO_hz=carrier['relative_CFO_hz'],
            raw_panel_sha256=waveform['panel_sha256']))
    if not measurements:raise ValueError('no supported independent-RF calibration measurement')
    protocol=dict(case='DS23-0268',hypotheses={k:dict(path=v,sha256=sha(MODELS/v)) for k,v in HYPOTHESES.items()},
        measurements=measurements,sensitivity_sigma_hz=[100.,300.],source_sha256=sources,
        selection_is_posthoc_RF_diagnostic_not_prospective_qualification=True,
        same_original_observations_powers_aliases_masks_and_other_priors=True,
        no_added_nuisance_coordinates=True,new_measurement_not_counted_as_additional_GLRT=True,
        calibration_uses_curved_supported_RF_not_linear_tracks=True,
        no_GPS_or_future_TLE_used=True,per_scan_and_band_calibration_only=True,
        cold_start_km=[0,0],phase_rounds=5,position_iterations_per_round=48,
        constrained_phase_rounds=5,constrained_position_iterations=40,
        original_gates_unchanged=True,stricter_normalized_gate_slack=.01,
        calibration_innovation_limit_sigma=3.,
        raw_carrier_uncertainty_not_calibrated_and_shared_component_not_unique_identity=True)
    protocol.update(relative_carrier_uses_zero_centred_radio_gauge=True,
        absolute_alias_branch_not_independently_identified=True,
        previous_invalid_experiment='reports/2026_10_20_ds23_0268_radio_calibration',
        correction='Prior run used an unwrapped +3-period pilot-search alias as an absolute radio contrast; stopped and rejected.',
        raw_IQ_measurement_and_GLRT_errors_not_proven_independent=True)
    write(p,protocol)
    return protocol


def setup(hypothesis):
    scan,_,saved,_,_=load()
    record=read(MODELS/HYPOTHESES[hypothesis])
    old=context('DS23-0268')[4]
    changed=copy.copy(scan)
    changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    model=old['hyperparameters_from_pre_RF_TLE_only']
    labels=sorted({r['candidate_index'] for r in record['node']['seed']['rows']})
    _,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    entries=record.get('predictive_entries',old['linear_entries'])
    return changed,record,np.asarray(record['mask'],bool),np.asarray(record['powers']),means,model,saved['events'],entries


def make(hypothesis,arm,reference,measurements):
    scan,record,keep,powers,means,model,events,entries=setup(hypothesis)
    p=make_calibrated_problem(scan,record['node'],keep,arm,reference,powers,means,model,events,measurements,fine_receiver_basis)
    attach_calibrated_predictive(p,entries,powers)
    cached(p)
    return p,entries


def calibration_slacks(p,x,entries):
    old=np.array(list(gate_slacks(p,x,entries).values()))
    c=p.calculate(x)
    return np.r_[old,1-abs(c['calibration_residual_hz']/c['calibration_sigma_hz'])/3]


def verify():
    prepare()
    rows=[]
    for name in HYPOTHESES:
        _,record,_,_,_,_,_,_=setup(name)
        for arm in ARMS:
            saved=record['arms'][arm]
            p,_=make(name,arm,np.asarray(saved['phase_reference']),[])
            x=np.asarray(saved['endpoint_east_north_km'])
            delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-3:raise ValueError('disabled calibration does not reproduce incumbent')
            rows.append(dict(hypothesis=name,arm=arm,null_RF_difference=delta))
    write(OUT/'null_replays.json',dict(rows=rows))
    print('All six disabled-calibration endpoint replays passed',flush=True)


def job(name,sigma,constrained=False):
    protocol=prepare()
    suffix='_constrained' if constrained else ''
    path=OUT/f'{name}_{int(sigma)}{suffix}.json'
    if path.exists():return dict(hypothesis=name,sigma_hz=sigma,constrained=constrained,cached=True)
    measurements=[dict(r,sigma_hz=sigma) for r in protocol['measurements']]
    source=read(OUT/f'{name}_{int(sigma)}.json') if constrained else None
    _,record,_,_,_,_,_,_=setup(name)
    pair={}
    for arm in ARMS:
        reference=np.asarray(source['arms'][arm]['phase_reference']) if constrained else np.zeros(len(record['arms'][arm]['phase_reference']))
        x=np.asarray(source['arms'][arm]['endpoint_east_north_km']) if constrained else np.zeros(2)
        history=[]
        for epoch in range(5):
            p,entries=make(name,arm,reference,measurements)
            result=(feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:calibration_slacks(p,z,entries)-.01,x,p.lower,p.upper,iterations=40)
                if constrained else fit(p,x,iterations=48))
            x=np.asarray(result['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch,fit=result,phase_change_s=change))
            reference=phase
        c=p.calculate(x)
        state=p.state(x)
        # Independent physical-decoder check on the contrast design, including
        # receiver event amplitude and the original radio units/scales.
        for k,row in enumerate(measurements):
            t=np.array([row['time_s']]);rf=row['rf_hz'];predictions=[]
            for rx in (1,2):
                virtual=dict(times=t,receiver=rx,channel=row['channel'],rf_hz=rf)
                predictions.append(float((p.scan.hardware(virtual,state['beta'])+
                    rf/11.5e9*fine_receiver_basis(t)@state['smooth'][rx-1])[0]))
            if abs(predictions[1]-predictions[0]-(row['relative_CFO_hz']-c['calibration_residual_hz'][k]))>1e-6:
                raise ValueError('calibration design differs from physical decoder')
        pair[arm]=dict(summary(p,x,entries),history=history,final_phase_change_s=change,
            calibration_residual_hz=c['calibration_residual_hz'],
            calibration_innovation_sigma=c['calibration_residual_hz']/c['calibration_sigma_hz'],
            calibration_prior_log_density=c['calibration_prior_log_density'],
            minimum_gate_slack=float(calibration_slacks(p,x,entries).min()))
    valid=pair_passes(pair,include_linear=True) and all(np.max(abs(r['calibration_innovation_sigma']))<=3 for r in pair.values())
    result=dict(hypothesis=name,sigma_hz=sigma,constrained=constrained,arms=pair,paired_valid=bool(valid),
        measurements=measurements,input_record_sha256=protocol['hypotheses'][name]['sha256'],
        GPS_used=False,future_TLE_used=False,no_original_observations_trimmed=True)
    write(path,result)
    print(name,sigma,'constrained',constrained,'valid',valid,flush=True)
    return dict(hypothesis=name,sigma_hz=sigma,constrained=constrained,paired_valid=bool(valid))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('verify','run','constrained'),required=True)
    args=parser.parse_args()
    if args.stage=='verify':verify()
    else:
        protocol=prepare();receipts=[]
        with ProcessPoolExecutor(max_workers=6) as pool:
            futures={pool.submit(job,n,s,args.stage=='constrained'):(n,s)
                for n in HYPOTHESES for s in protocol['sensitivity_sigma_hz']}
            for future in as_completed(futures):
                try:receipts.append(future.result())
                except Exception as exc:receipts.append(dict(job=futures[future],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
