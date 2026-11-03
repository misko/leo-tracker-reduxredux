"""Revalidate smooth-template RF contrasts before any localization use."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
from pathlib import Path
import signal
import time
import numpy as np

from audit_ds23_targeted_differential_rf import reconstruct
from ds23_common_probe_frequency import CommonProbeFrequency
from ds23_profiled_carrier_response import tight_fit
from ds23_smooth_component_workspace import SmoothComponentWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha
from select_ds23_differential_information import OUT as PARENT

OUT=PARENT/'smooth_validation'


def one(record):
    began=time.monotonic();case,probe=record['case'],record['probe'];path=OUT/f'{case}_probe{probe:06d}.json'
    if path.exists():return read(path)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s smooth RF validation cap')));signal.alarm(300)
    try:
        response=read(PARENT/'profile_response_smooth'/f'{case}_probe{probe:06d}.json')
        assert response['status']=='complete'
        p=SmoothComponentWorkspace.from_workspace(reconstruct(record))
        full=tight_fit(p,response['tight_full']['parameters']);folds=[]
        for parity in [0,1]:
            fitted=tight_fit(p,full['parameters'],parity)
            prediction=p.statistics(fitted['parameters'],parity,derivatives=False,prediction=True)
            alternatives=[]
            for offset in [-750.,750.]:
                other=copy.copy(p);other.start=p.start.copy();other.start[0]+=offset
                initial=np.asarray(full['parameters']).copy();initial[0]+=offset
                alternate=tight_fit(other,initial,parity,iterations=100)
                held=other.statistics(alternate['parameters'],parity,derivatives=False,prediction=True)
                alternatives.append(dict(offset_hz=offset,fit=alternate,
                    held_gain_favoring_nominal=float(2*prediction['heldout_samples']*
                    np.log(held['heldout_squared_error']/prediction['heldout_squared_error']))))
            folds.append(dict(fit=fitted,prediction=prediction,alternative_carriers=alternatives))
        common=CommonProbeFrequency(p,np.asarray(full['parameters'])).optimize(iterations=40)
        rng=np.random.default_rng(2026102200+probe);segments=list(p.segments);boot=[]
        for k in range(31):
            draw=rng.integers(0,len(segments),len(segments));view=copy.copy(p);view.segments=[segments[i] for i in draw]
            f=tight_fit(view,full['parameters'],iterations=100)
            boot.append(dict(index=k,frames=draw,fit=f))
        sd=float(np.std([r['fit']['difference_hz'] for r in boot],ddof=1))
        disagreement=abs(folds[0]['fit']['difference_hz']-folds[1]['fit']['difference_hz'])
        common_change=abs(common['component_CFO_difference_hz']-full['difference_hz'])
        sigma=max(5.,sd,disagreement/np.sqrt(2),common_change,record['declared_sigma_hz'])
        checks=dict(original_RF_qualified=record['RF_qualified'],
            full_and_folds_interior=not any(r['boundary'] for r in [full]+[r['fit'] for r in folds]),
            full_and_fold_stationarity=all(r['maximum_standardized_score']<=.01 for r in [full]+[r['fit'] for r in folds]),
            at_most_one_bootstrap_boundary=sum(r['fit']['boundary'] for r in boot)<=1,
            at_least28_bootstrap_stationary=sum(r['fit']['maximum_standardized_score']<=.01 for r in boot)>=28,
            fold_difference_agreement=disagreement<=20.,shared_receiver_contrast_stable=common_change<=20.,
            both_folds_resolve750Hz_relative_carrier=all(a['held_gain_favoring_nominal']>10 for f in folds for a in f['alternative_carriers']),
            original_epoch_response_threshold=response['maximum_observed_response_discrepancy_hz']<=.3,
            positive_stable_observed_curvature=response['observed_response']['minimum_eigenvalue']>0 and
                response['observed_response']['hessian_asymmetry']<.001 and response['response_step_difference_s']<1e-6)
        result=dict(case=case,probe=probe,status='complete',job=record['job'],full=full,folds=folds,
            common_full=common,bootstrap_replicates=boot,bootstrap_sigma_hz=sd,fold_difference_hz=disagreement,
            common_model_difference_change_hz=common_change,declared_sigma_hz=sigma,
            frequency_rate_response_s=response['observed_response']['response_s'],checks=checks,
            RF_and_epoch_qualified=all(checks.values()),
            original_RF_source_sha256=sha(PARENT/'RF_pilot.json'),response_sha256=sha(PARENT/'profile_response_smooth'/f'{case}_probe{probe:06d}.json'),
            no_new_RF_or_position_GPS_TLE=True,uncertainty_is_conditional_not_absolute_coverage=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,probe=probe,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,probe,result['status'],result.get('RF_and_epoch_qualified'),result.get('checks'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'RF_pilot.json');selected=[r for r in source['rows'] if r.get('RF_qualified')]
    protocol=dict(source_sha256=sha(PARENT/'RF_pilot.json'),
        response_protocol_sha256=sha(PARENT/'profile_response_smooth/protocol.json'),
        selected_probes=[dict(case=r['case'],probe=r['probe']) for r in selected],workers=3,maximum_seconds_per_probe=300,
        bootstrap_frames=31,disjoint_symbol_parity_folds=[0,1],relative_carrier_alternatives_hz=[-750,750],
        sigma='max(original sigma,5Hz,whole-frame bootstrap SD,fold disagreement/sqrt2,common-profile change)',
        retained_observations_and_channel_model_and_native_parameter_bounds=True,
        no_GPS_future_TLE_new_RF_or_position_fit=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_profiled_carrier_response.py',ROOT/'tools/ds23_smooth_component_workspace.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('smooth validation protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in selected])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,qualified=sum(r.get('RF_and_epoch_qualified',False) for r in rows)))


if __name__=='__main__':main()
