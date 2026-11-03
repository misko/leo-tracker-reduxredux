"""Select orbit-state hyperparameters by phase prediction, independent of GPS."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np

from ds23_tle_state_filter import pack,residual_diagnostics
from ds23_phase_score_filter import fit,filter_with_mean,predict_with_mean
from ds23_causal_phase_location import fit_location
from probe_ds23_tle_state_filter import OUT as CONTROL,baseline_cost
from prepare_ds23_tle_state_filter import extract
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_phase_score_filter'


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_phase_score_filter.py',
        ROOT/'tools/ds23_tle_state_filter.py',ROOT/'tools/prepare_ds23_tle_state_filter.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen phase-score model changed')
        return p
    original=read(CONTROL/'protocol.json')
    p=dict(original,source_sha256=hashes(),
        differences='optimize phase-prequential NLL rather than joint phase/rate NLL; select zero mean versus one constant acceleration mean by k log N and Gaussian prior',
        fit='four deterministic starts for measurement model, two for no-measurement model; minimize conditional phase prediction score plus optional mean prior, select mean order by k log N',
        acceleration_bounds_s_per_hour2=[-.1,.1],acceleration_prior_sigma_s_per_hour2=.02,
        measurement_off_control='fit its process intensity and optional acceleration using the same phase score and selection rule',
        qualification='later all and held-satellite phase density beats BOTH incumbent and measurement-off phase-score model by >3log(training count)+2log2; original residual diagnostics unchanged',
        earlier_three_TLE_pilot_validation_exposed_for_model_design=True,
        position_errors_of_new_filter_variants_not_used_for_design=True)
    write(path,p);return p


def qualify(features,forecast,model,bias_enabled):
    data=pack(features['series']);boundary=forecast['temporal_split_boundary_ns']
    train=data['score_eligible'] & (data['publication']<=boundary) & (data['norads'][:,None]%5!=0)
    future=data['score_eligible'] & (data['publication']>boundary)
    disjoint=future & (data['norads'][:,None]%5==0)
    if min(map(np.sum,(train,future,disjoint)))<30:return dict(qualified=False,reason='insufficient past transitions')
    prefix_model=forecast['prefix_distribution']
    training_rows=[r for s in features['series'] for r in s['baseline_transitions'] if r and r['validation_time_ns']<=boundary and r['norad']%5!=0]
    bias=fit_location(training_rows,prefix_model) if bias_enabled else None
    baseline,replay_error=baseline_cost(data,features,prefix_model,bias)
    fitted=fit(data,train);off=fit(data,train,measurement=False)
    predicted=filter_with_mean(data,fitted['parameters']);null=filter_with_mean(data,off['parameters'])
    penalty=float(3*np.log(train.sum())+2*np.log(2));validation={}
    for name,mask in (('future',future),('disjoint_future',disjoint)):
        cost=float(predicted['phase_cost'][mask].sum());diagnostic=residual_diagnostics(predicted['standardized'],mask)
        validation[name]=dict(count=int(mask.sum()),phase_cost=cost,baseline_cost=float(baseline[mask].sum()),
            measurement_off_cost=float(null['phase_cost'][mask].sum()),gain_vs_baseline=float(baseline[mask].sum()-cost),
            gain_vs_measurement_off=float(null['phase_cost'][mask].sum()-cost),phase_residual_diagnostics=diagnostic)
    qualified=bool(all(min(v['gain_vs_baseline'],v['gain_vs_measurement_off'])>penalty and
                       v['phase_residual_diagnostics']['compatible'] for v in validation.values()))
    full=fit(data,data['score_eligible']) if qualified else None;moments=[]
    if full:
        state=filter_with_mean(data,full['parameters']);prediction=predict_with_mean(state,[s['target_hours'] for s in features['series']])
        for j,s in enumerate(features['series']):
            factor=s['RF_phase_coordinate_factor']
            moments.append(dict(norad=s['norad'],mean_s=float((prediction['mean'][j]-s['RF_nominal_reference_phase_s'])/factor),
                latent_sigma_s=float(np.sqrt(prediction['latent_variance'][j])/factor),
                next_measurement_sigma_s=float(np.sqrt(prediction['next_measurement_variance'][j])/factor),
                posterior_degrees=float(prediction['posterior_degrees'][j]),
                maximum_phase_transport_discrepancy_s=s['maximum_phase_transport_discrepancy_s']))
    return dict(qualified=qualified,prefix_model=fitted,measurement_off=off,full_model=full,validation=validation,
        RF_moments=moments,penalty=penalty,training_count=int(train.sum()),
        original_forecast_target_replay_max_error_s=replay_error,no_current_RF_or_GPS_used_for_fitting=True)


def learn(case):
    prepare();path=OUT/(case+'_filter.json')
    if path.exists():return dict(case=case,cached=True)
    began=time.monotonic();history_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=history_path.with_name(case+'_forecast.json');elements_path=SOURCE/case/'nominal_elements.json'
    history,forecast=read(history_path),read(forecast_path)
    if forecast['history_sha256']!=sha(history_path) or history['cutoff_utc_ns']!=read(SOURCE/case/'receipt.json')['cutoff_utc_ns']:
        raise ValueError('causal input changed')
    old_feature=CONTROL/(case+'_features.json')
    if old_feature.exists():
        old=read(CONTROL/(case+'_filter.json'))
        if old['history_sha256']!=sha(history_path) or old['features_sha256']!=sha(old_feature) or old['elements_sha256']!=sha(elements_path):
            raise ValueError('cached feature input binding changed')
        features=read(old_feature)
    else:features=extract(history,forecast,read(elements_path))
    feature_path=OUT/(case+'_features.json');write(feature_path,features)
    signed,binding=bound_incumbent(case);enabled=bool(signed['accepted'] and signed['selection']['qualified'])
    model=read(SOURCE/case/'algo02_result.json')['hyperparameters_from_pre_RF_TLE_only']
    result=qualify(features,forecast,model,enabled)
    write(path,dict(case=case,selection=result,features_sha256=sha(feature_path),history_sha256=sha(history_path),
        forecast_sha256=sha(forecast_path),elements_sha256=sha(elements_path),incumbent_binding=binding,
        baseline_bias_enabled=enabled,baseline_model=model,source_sha256=hashes(),seconds=time.monotonic()-began))
    row=dict(case=case,qualified=result['qualified'],validation=result.get('validation'),seconds=time.monotonic()-began)
    print(row,flush=True);return row


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','pilot','cohort'),required=True)
    stage=parser.parse_args().stage;p=prepare()
    if stage!='prepare':
        cases=p['pilot_cases'] if stage=='pilot' else p['development_cases']+p['confirmation_cases'];receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(learn,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        errors=[r for r in receipts if 'error' in r]
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,errors=errors))
        print('Terminal',len(receipts),'errors',errors,flush=True)
