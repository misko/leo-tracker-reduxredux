"""Historical orbit-state qualification, followed by matched DS23 RF experiments."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np

from ds23_tle_state_filter import pack,filter_histories,fit_parameters,fit_measurement_off,residual_diagnostics,predict_state
from ds23_continuous_forecast import arrays
from ds23_causal_phase_location import fit_location
from prepare_ds23_tle_state_filter import extract
from learn_ds23_causal_phase_forecast import distribution_cost
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_tle_state_filter'
COHORT=ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json'


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT/'tools/ds23_tle_state_filter.py',ROOT/'tools/prepare_ds23_tle_state_filter.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        protocol=read(path)
        if protocol['source_sha256']!=hashes():raise ValueError('frozen state-filter experiment changed')
        return protocol
    cohort=read(COHORT)
    protocol=dict(development_cases=cohort['development_cases'],confirmation_cases=cohort['confirmation_cases'],
        pilot_cases=cohort['pilot_cases'],source_sha256=hashes(),workers=24,
        hypothesis='TLE-to-TLE forecast error includes measurement noise; infer latent orbit phase/rate separately',
        state='phase seconds and phase-rate seconds/hour relative to first available SGP4 orbit; integrated white acceleration',
        measurement='phase/rate at publication UTC; diagonal Gaussian noise, common Gamma precision per satellite history, initial nu=3',
        initial_state='first TLE observation with covariance R, conditional diffuse state initialization',
        exact_model='Normal-Gamma filtering under the assumed 2D linear dynamics and measurement model',
        physics_limit='one-dimensional phase transport and independent TLE measurement errors are hypotheses; revisions are not orbit truth',
        bounds=dict(measurement_phase_sd_s=[.01,3.],measurement_rate_sd_s_per_hour=[.001,1.],sqrt_process_intensity=[.0003,1.]),
        fit='four deterministic initializations; minimize joint phase/rate conditional Student prediction cost on first 70% publication events excluding NORAD modulo five zero',
        null='same state-space model with measurement covariance exactly zero; fit process intensity only',
        qualification='phase predictive density in later events and later held satellites beats BOTH original forecast prior and measurement-off filter by >3log(training rows); joint training improvement >2log(training rows)',
        residual_qualification='winsorized phase innovation mean <.25 in magnitude and adjacent correlation <.2; at least 30 pairs',
        no_future_TLE_GPS_RF_or_observer_geometry_in_filter=True,
        baseline_bias_flag_conditioned_from_incumbent_but_filter_fit_is_TLE_only=True,
        RF_methods_planned=['mean_only','latent_state_variance','next_TLE_measurement_variance'],
        RF_projection='match filter phase mean and variance, retain original phase tail degrees and all other priors; this is a moment projection, not the exact filter posterior shape',
        RF_bounds='mean clipped at original min(15,3*raw_phase_sigma); sigma clipped [.02,15] seconds',
        same_observations_labels_aliases_noise_powers_gates_and_regional_cold_starts=True,
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        cohort_reused_not_untouched_locations=True,
        primary='latent-state fitted-c mean AND median improve in development AND confirmation; report measurement-noise and mean-only controls and c0',
        goal_population=413)
    write(path,protocol);return protocol


def baseline_cost(data,features,model,bias):
    output=np.zeros(data['valid'].shape);targets=[];coordinates=[]
    for j,series in enumerate(features['series']):
        for k,row in enumerate(series['baseline_transitions']):
            if row is not None:targets.append(row);coordinates.append((j,k))
    a=arrays(targets,model,bias)
    mean=np.clip(np.clip(model['shrinkage']*a['unit'],-a['limit'],a['limit'])+a['correction'],-a['limit'],a['limit'])
    costs=distribution_cost(a['target']-mean,a['sigma'],model['multiplier'],model['nu'])
    maximum_error=0.
    for row,(j,k),cost in zip(targets,coordinates,costs,strict=True):
        factor=row['phase_coordinate_factor'];expected=row['nominal_reference_phase_s']+factor*row['next_innovation_s']
        error=abs(data['observations'][j,k,0]-expected);maximum_error=max(maximum_error,error)
        output[j,k]=cost+2*np.log(factor)
    if maximum_error>1e-5:raise ValueError('transported validation target changed original forecast observation')
    return output,maximum_error


def qualify(features,forecast,model,bias_enabled):
    data=pack(features['series']);boundary=forecast['temporal_split_boundary_ns']
    train=data['score_eligible'] & (data['publication']<=boundary) & (data['norads'][:,None]%5!=0)
    future=data['score_eligible'] & (data['publication']>boundary)
    disjoint=future & (data['norads'][:,None]%5==0)
    if min(map(np.sum,(train,future,disjoint)))<30:
        return dict(qualified=False,reason='insufficient temporal/satellite transitions')
    prefix_model=forecast['prefix_distribution']
    training_rows=[r for s in features['series'] for r in s['baseline_transitions'] if r and
                   r['validation_time_ns']<=boundary and r['norad']%5!=0]
    bias=fit_location(training_rows,prefix_model) if bias_enabled else None
    old,transport_error=baseline_cost(data,features,prefix_model,bias)
    fitted=fit_parameters(data,train);off=fit_measurement_off(data,train)
    prediction=filter_histories(data,fitted['parameters']);null=filter_histories(data,off['parameters'])
    penalty=float(3*np.log(np.sum(train)));validation={}
    for name,mask in (('future',future),('disjoint_future',disjoint)):
        density=float(prediction['phase_cost'][mask].sum())
        diagnostic=residual_diagnostics(prediction['standardized'],mask)
        a=np.clip(prediction['standardized'][mask],-3,3);b=np.clip(prediction['whitened_rate'][mask],-3,3)
        validation[name]=dict(count=int(np.sum(mask)),phase_cost=density,baseline_cost=float(old[mask].sum()),
            measurement_off_cost=float(null['phase_cost'][mask].sum()),
            gain_vs_baseline=float(old[mask].sum()-density),
            gain_vs_measurement_off=float(null['phase_cost'][mask].sum()-density),
            phase_residual_diagnostics=diagnostic,whitened_phase_rate_correlation=float(np.corrcoef(a,b)[0,1]))
    training_gain=off['cost']-fitted['cost']
    qualified=bool(training_gain>2*np.log(np.sum(train)) and all(
        min(v['gain_vs_baseline'],v['gain_vs_measurement_off'])>penalty and
        v['phase_residual_diagnostics']['compatible'] for v in validation.values()))
    full=fit_parameters(data,data['score_eligible']) if qualified else None
    if full:
        posterior=filter_histories(data,full['parameters'])
        prediction_rf=predict_state(posterior,[s['target_hours'] for s in features['series']])
        moments=[]
        for j,s in enumerate(features['series']):
            factor=s['RF_phase_coordinate_factor']
            moments.append(dict(norad=s['norad'],mean_s=float((prediction_rf['mean'][j]-s['RF_nominal_reference_phase_s'])/factor),
                latent_sigma_s=float(np.sqrt(prediction_rf['latent_variance'][j])/factor),
                next_measurement_sigma_s=float(np.sqrt(prediction_rf['next_measurement_variance'][j])/factor),
                posterior_degrees=float(prediction_rf['posterior_degrees'][j]),
                maximum_phase_transport_discrepancy_s=s['maximum_phase_transport_discrepancy_s']))
    else:moments=[]
    return dict(qualified=qualified,prefix_model=fitted,measurement_off=off,full_model=full,
        validation=validation,training_gain_vs_measurement_off=training_gain,penalty=penalty,
        original_forecast_target_replay_max_error_s=transport_error,RF_moments=moments,
        training_count=int(train.sum()),future_count=int(future.sum()),disjoint_future_count=int(disjoint.sum()),
        no_RF_GPS_or_future_data_used_for_filter_fit=True)


def learn(case):
    prepare();path=OUT/(case+'_filter.json')
    if path.exists():return dict(case=case,cached=True)
    began=time.monotonic();history_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=history_path.with_name(case+'_forecast.json');elements_path=SOURCE/case/'nominal_elements.json'
    history,forecast=read(history_path),read(forecast_path)
    if forecast['history_sha256']!=sha(history_path) or history['cutoff_utc_ns']!=read(SOURCE/case/'receipt.json')['cutoff_utc_ns']:
        raise ValueError('causal history binding changed')
    feature_path=OUT/(case+'_features.json')
    features=extract(history,forecast,read(elements_path));write(feature_path,features)
    signed,binding=bound_incumbent(case);enabled=bool(signed['accepted'] and signed['selection']['qualified'])
    model=read(SOURCE/case/'algo02_result.json')['hyperparameters_from_pre_RF_TLE_only']
    result=qualify(features,forecast,model,enabled)
    write(path,dict(case=case,selection=result,features_sha256=sha(feature_path),
        history_sha256=sha(history_path),forecast_sha256=sha(forecast_path),elements_sha256=sha(elements_path),
        incumbent_binding=binding,baseline_bias_enabled=enabled,baseline_model=model,
        source_sha256=hashes(),seconds=time.monotonic()-began))
    row=dict(case=case,qualified=result['qualified'],validation=result.get('validation'),seconds=time.monotonic()-began)
    print(row,flush=True);return row


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','pilot','cohort'),required=True)
    stage=parser.parse_args().stage;protocol=prepare()
    if stage!='prepare':
        cases=protocol['pilot_cases'] if stage=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
        receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(learn,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        errors=[r for r in receipts if 'error' in r]
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,errors=errors))
        print('Terminal',len(receipts),'errors',errors,flush=True)
