"""Test shared within-probe receiver variation on69 frozen native RF probes."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import time
import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_common_probe_frequency import CommonProbeFrequency,rebase_parameters
from ds23_probe_frequency_profile import frequency_only_fit
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_common_probe_frequency'
BULK=Path('/srv/bulk/leo/research/ds23-common-probe-frequency-20261021')
DEVELOPMENT=ROOT/'reports/2026_10_21_ds23_joint_component_refinement'
OLD_VALIDATION=ROOT/'reports/2026_10_21_ds23_frequency_profile_validation'
CONFIRMATION=ROOT/'reports/2026_10_21_ds23_frequency_profile_confirmation'


def jobs():
    original=read(DEVELOPMENT/'evaluation.json');fits={(r['case'],r['probe']):r for r in original['rows']}
    first=read(OLD_VALIDATION/'evaluation.json');second=read(CONFIRMATION/'evaluation.json')
    result=[]
    for stratum,root,evaluation in [('development',DEVELOPMENT,first),('point_disjoint_confirmation',CONFIRMATION,second)]:
        selected=read(root/'protocol.json')['jobs'];saved={(r['case'],r['probe']):r for r in evaluation['rows']}
        for item in selected:
            j=item['job'];old=saved[j['case'],j['probe']]
            initial=fits[j['case'],j['probe']]['full'] if stratum=='development' else old['whole_probe_seed_fit']
            result.append(dict(item=item,stratum=stratum,initial=initial,previous_profile_validation=old))
    if len(result)!=69 or len({(r['item']['job']['case'],r['item']['job']['probe']) for r in result})!=69:
        raise ValueError('69 distinct original RF probes required')
    return result


def one(job):
    item=job['item'];j=item['job'];target=BULK/(j['group']+f"_probe{j['probe']:06d}.json")
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('90-second shared within-probe RF cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(90)
    record=dict(case=j['case'],group=j['group'],probe=j['probe'],stratum=job['stratum'])
    try:
        with np.load(Path(item['source'])/'panels'/(j['case']+'.npz'),allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==j['probe'])
            v=z[point['window_key']][:,point['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float)
        p=JointComponentWorkspace(y,metadata['sample_rate_hz'],j['edge'],[j['first']['epoch'],j['second']['epoch']],
            [item['fit']['first_fit'],item['fit']['second_fit']]);initial=np.array(job['initial']['parameters'])
        model=CommonProbeFrequency(p,initial);full=model.optimize();constant=frequency_only_fit(p,initial)
        gauge=CommonProbeFrequency(p,initial,reference=0);rebased=rebase_parameters(full['parameters'],2,0)
        gauge_score=gauge.statistics(rebased,derivatives=False)['score']
        if abs(gauge_score-full['score'])>1e-10:raise ValueError('reference-part choice changes the RF likelihood')
        mean0=gauge.support_mean_design@rebased
        if np.max(abs(mean0-full['uniform_support_mean_CFO_hz']))>1e-8:raise ValueError('support-average CFO changes under gauge transform')
        folds=[]
        for parity in [0,1]:
            baseline=job['previous_profile_validation']['folds'][parity]
            before=p.statistics(baseline['baseline']['parameters'],parity,derivatives=False,prediction=True)
            if abs(before['heldout_squared_error']/baseline['baseline_prediction']['heldout_squared_error']-1)>1e-12:
                raise ValueError('original constant model held-symbol SSE changed')
            fit=model.optimize(parity);prediction=model.statistics(fit['parameters'],parity,derivatives=False,prediction=True)
            if prediction['heldout_samples']!=before['heldout_samples']:raise ValueError('shared model changed held-symbol support')
            gain=float(2*before['heldout_samples']*np.log(before['heldout_squared_error']/prediction['heldout_squared_error']))
            versus=float(2*before['heldout_samples']*np.log(baseline['piecewise_heldout_squared_error']/prediction['heldout_squared_error']))
            folds.append(dict(parity=parity,fit=fit,prediction=prediction,constant_prediction=before,
                heldout_profile_gain=gain,gain_vs_independent_three_part=versus,
                heldout_SSE_fractional_improvement=1-prediction['heldout_squared_error']/before['heldout_squared_error']))
        difference=abs(folds[0]['fit']['component_CFO_difference_hz']-folds[1]['fit']['component_CFO_difference_hz'])
        full_change=abs(full['component_CFO_difference_hz']-np.mean([f['fit']['component_CFO_difference_hz'] for f in folds]))
        checks=dict(both_folds_predict_better=all(f['heldout_profile_gain']>10 for f in folds),
            frequency_difference_fold_agreement=difference<=20.,full_vs_fold_average_difference=full_change<=10.,
            frequency_parameters_interior=not any(v['boundary'] for v in [full]+[f['fit'] for f in folds]),
            conditioned_RF_seed_interior=not job['initial']['boundary'])
        record.update(status='complete',full=full,folds=folds,constant_full=constant,checks=checks,RF_qualified=all(checks.values()),
            difference_fold_disagreement_hz=difference,full_vs_fold_average_difference_hz=full_change,
            difference_change_from_constant_hz=full['component_CFO_difference_hz']-float(constant['CFO_hz']@np.array([1.,-1.])),
            support_mean_changes_from_constant_hz=full['uniform_support_mean_CFO_hz']-constant['CFO_hz'],
            gauge_likelihood_difference=gauge_score-full['score'],
            no_assumption_that_any_part_is_settled=True,conditional_RF_covariance_not_calibrated_total_error=True,
            no_GPS_TLE_or_satellite_identity_used=True,no_measurement_or_position_adoption=True)
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;write(target,record);return record


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);selected=jobs()
    binding=read(ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json')
    for panel in {Path(r['item']['source'])/'panels'/(r['item']['job']['case']+'.npz') for r in selected}:
        if sha(panel)!=binding['saved_panel_sha256'][str(panel)]:raise ValueError('saved RF panel changed')
    protocol=dict(jobs=selected,workers=12,per_probe_seconds=90,common_frequency_parts=3,RF_nonlinear_parameters=4,
        code_epoch_rate_conditioned_on_prior_whole_probe_RF_fit=True,
        independent_complex_channels_per_original_frame_intersection_unchanged=True,
        all69_probes_including_negative_controls=True,
        reference_part_is_coordinate_gauge_not_settling_anchor=True,
        carrier_difference_and_uniform_observed_support_average_are_gauge_invariant=True,
        fixed_RF_checks=dict(both_held_symbol_gains_above=10.,difference_fold_disagreement_below_hz=20.,
            full_vs_fold_average_below_hz=10.,all_RF_parameters_and_conditioned_seed_interior=True),
        new_absolute_CFO_and_position_not_adopted=True,
        no_GPS_TLE_satellite_selection_or_new_RF_collection=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_common_probe_frequency.py',
            ROOT/'tools/ds23_joint_component_refinement.py',ROOT/'tools/ds23_probe_frequency_profile.py']},
        native_source_bindings_sha256=sha(ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json'))
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('common within-probe RF protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=12) as pool:
        for future in as_completed([pool.submit(one,j) for j in selected]):
            r=future.result();rows.append(r)
            print(r['group'],r['probe'],r['status'],r.get('checks'),r.get('error'),flush=True)
            if len(rows)%10==0:write(OUT/'progress.json',dict(terminal=len(rows),total=len(selected)))
    summary={}
    for name in ['development','point_disjoint_confirmation']:
        subset=[r for r in rows if r['status']=='complete' and r['stratum']==name];qualified=[r for r in subset if r['RF_qualified']]
        summary[name]=dict(probes=len(subset),both_folds_predict_better=sum(r['checks']['both_folds_predict_better'] for r in subset),
            qualified=len(qualified),median_absolute_difference_change_hz=float(np.median([abs(r['difference_change_from_constant_hz']) for r in subset])),
            median_absolute_support_mean_change_hz=float(np.median([abs(v) for r in subset for v in r['support_mean_changes_from_constant_hz']])),
            qualified_median_difference_sigma_proxy_hz=float(np.median([r['full']['difference_sigma_proxy_hz'] for r in qualified])) if qualified else None)
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],
        protocol_sha256=sha(target),point_disjoint_confirmation_same23_scans_not_new_location=True,
        no_CFO_or_position_correction_adopted=True))
    print('COMMON_PROBE_SUMMARY',summary,flush=True)


if __name__=='__main__':main()
