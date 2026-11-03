"""Matched, IQ-disjoint position pilot using validated windowed RF contrasts."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
from pathlib import Path
import signal
import time
import numpy as np

from ds23_disjoint_rf_calibration import exclude_probes
from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from ds23_windowed_differential_factor import make_differential_problem,attach_differential_predictive
from ds23_frequency_events import make_event_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import summary,cached
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from select_ds23_differential_information import OUT as PARENT

OUT=PARENT/'windowed_position'
METHODS=['matched_control','conditional_RF','plus_radio_RF']


def prepare(measurement_model='windowed'):
    source_path=PARENT/('chirped_aliases/evaluation.json' if measurement_model=='chirped' else 'smooth_validation/evaluation.json')
    source=read(source_path);assert source['all_terminal']
    wide=read(PARENT/'profile_response_smooth_rate5000/evaluation.json');assert wide['all_terminal']
    wide_pass={(r['case'],r['probe']) for r in wide['rows'] if r['status']=='complete'
        and r['maximum_observed_response_discrepancy_hz']<=.3}
    rows=([r for r in source['rows'] if r.get('RF_qualified')] if measurement_model=='chirped' else
        [r for r in source['rows'] if r.get('RF_and_epoch_qualified') and (r['case'],r['probe']) in wide_pass])
    cases=sorted({r['case'] for r in rows});OUT.mkdir(exist_ok=True)
    protocol=dict(cases=cases,methods=METHODS,source_sha256=sha(source_path),measurement_model=measurement_model,
        selection='RF/fold/alias/bootstrap qualified before geographic evaluation; constant model additionally requires validated finite-window rate response',
        wide_rate_check_sha256=sha(PARENT/'profile_response_smooth_rate5000/evaluation.json'),
        no_satellite_identity_change=True,full_phase_and_orbit_and_radio_uncertainty_retained=True,
        exact_GLRT_IQ_quarantine=True,physical_predictive_subset_membership=True,
        conditional_sigma='max original conditional sigma,5Hz,smooth paired-frame bootstrap,fold disagreement,common model change',
        plus_radio_sigma='sqrt(conditional sigma^2+2*original radio sigma^2)',
        matched_c0_fitted_c=True,cold_start=[0,0],regional_width_km=25,
        phase_rounds=5,steps_per_round=48,workers=6,per_pair_seconds=240,
        new_RF_or_GPS_or_future_TLE=False,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_windowed_differential_factor.py',ROOT/'tools/ds23_predictive_subsets.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('windowed RF position protocol changed')
    if not path.exists():write(path,protocol)
    for case in cases:
        path=OUT/(case+'_plan.json')
        if path.exists():continue
        scan,node,mask,powers,means,model,entries,signed,signed_path=context_signed(case)
        selected=[r for r in rows if r['case']==case];measurements=[]
        for r in selected:
            j=r['job'];measurements.append(dict(probe=r['probe'],time_s=j['time_s'],channel=j['lane'][1],rf_hz=j['lane'][2],
                curve_rows=j['curve_rows'],curve_components=j['curve_components'],proposed_norads=j['proposed_norads'],
                difference_hz=r['full']['contrast'][0] if measurement_model=='chirped' else r['full']['difference_hz'],sigma_hz=r['declared_sigma_hz'],
                frequency_rate_response_s=[0.,0.] if measurement_model=='chirped' else r['frequency_rate_response_s'],
                carrier_epoch_s=j['time_s']+r.get('carrier_epoch_relative_to_GLRT_s',0.),
                native_CFO_hz=[j['first']['cfo_hz'],j['second']['cfo_hz']],
                lifted_CFO_hz=[j['first_lifted_value'],j['second_lifted_value']]))
        p=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,model,[])
        keep,predictive,receipt=exclude_probes(scan,p,mask,entries,measurements)
        augmented,realized,subset=realize_predictive_subsets(scan,predictive)
        actual=assert_realized_predictive_membership(augmented,realized,receipt['excluded_probe_graph_ids'])
        write(path,dict(case=case,signed_sha256=sha(signed_path),keep=keep,entries=predictive,
            measurements=measurements,disjoint=receipt,predictive_subsets=subset,
            physical_predictive_observation_ids=actual,selection_without_geographic_error=True))
    return protocol


def one(case,method):
    path=OUT/(case+'_'+method+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s windowed differential paired position cap')));signal.alarm(240)
    try:
        plan=read(OUT/(case+'_plan.json'))
        scan,node,_,powers,means,model,_,signed,signed_path=context_signed(case)
        assert sha(signed_path)==plan['signed_sha256']
        augmented,entries,subset=realize_predictive_subsets(scan,plan['entries'])
        actual=assert_realized_predictive_membership(augmented,entries,plan['disjoint']['excluded_probe_graph_ids'])
        keep=np.array(plan['keep'],bool);measurements=plan['measurements'] if method!='matched_control' else []
        if method=='plus_radio_RF':
            measurements=[dict(r,sigma_hz=float(np.sqrt(r['sigma_hz']**2+2*scan.radio_sigma_hz**2))) for r in measurements]
        pair={}
        for arm in ['c0','fitted_c']:
            x=np.zeros(2);reference=np.zeros(len(means));history=[]
            for _ in range(5):
                p=make_differential_problem(augmented,node,keep,arm,reference,powers,means,model,measurements)
                attach_differential_predictive(p,entries,powers);cached(p)
                fitted=fit(p,x,iterations=48);x=np.array(fitted['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
            r=summary(p,x,entries);r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
            assert r['linear_calibration_max_difference']==0
            assert sum(s.stop-s.start for s in p.linear_slices)==len(actual)
            if measurements:
                c=p.calculate(x);r.update(differential_residual_hz=c['differential_residual_hz'],differential_sigma_hz=c['differential_sigma_hz'])
            pair[arm]=r
        passed=valid(pair) and all(not measurements or np.max(abs(np.asarray(r['differential_residual_hz'])/r['differential_sigma_hz']))<=3 for r in pair.values())
        result=dict(case=case,method=method,status='complete',arms=pair,paired_valid=bool(passed),
            original_signed_incumbent=signed['policy_arms'],actual_RF_GLRT_support_disjoint=True,
            measurements=measurements,plan_sha256=sha(OUT/(case+'_plan.json')),
            no_GPS_future_TLE_new_RF_or_identity_selection=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,method=method,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,method,result['status'],result.get('paired_valid'),result.get('error'),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model',choices=['windowed','chirped'],default='windowed')
    args=parser.parse_args()
    global OUT
    if args.model=='chirped':OUT=PARENT/'instantaneous_chirp_position_recovery'
    protocol=prepare(args.model)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c,m) for c in protocol['cases'] for m in METHODS])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,new_algorithm_not_promoted=True))


if __name__=='__main__':main()
