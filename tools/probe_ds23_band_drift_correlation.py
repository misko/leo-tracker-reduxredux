"""Matched per-band drift-correlation trial with curvature-only RF selection."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_band_drift_correlation import make_band_drift_problem,ORIGINAL_CORRELATION
from ds23_frequency_events import attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached,summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_band_drift_correlation'
BULK=Path('/srv/bulk/leo/research/ds23-band-drift-correlation-20261021')
COHORT=ROOT/'reports/2026_10_21_ds23_linear_family_strength/protocol.json'
MODELS=dict(shared_drift_control=ORIGINAL_CORRELATION,independent_band_drift=0.)
PENALTY=float(2*np.log(2))


def make(context,arm,reference,method,linear=True):
    scan,node,mask,powers,means,hyper,entries,*_=context
    p=make_band_drift_problem(scan,node,mask,arm,reference,powers,means,hyper,MODELS[method])
    return attach_event_predictive(p,entries,powers) if linear else p


def refit(context,arm,method,linear=True):
    x=np.zeros(2);reference=np.zeros(len(context[4]));history=[]
    entries=context[6] if linear else []
    for _ in range(5):
        p=cached(make(context,arm,reference,method,linear));fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15);change=float(np.max(abs(phase-reference)))
        history.append(dict(fit=fitted,phase_change_s=change));reference=phase
    r=summary(p,x,entries);r.update(history=history,final_phase_change_s=change)
    return r


def run(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('600-second band-drift correlation budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(600)
    try:
        context=context_signed(case);signed,source=context[-2:];replays={}
        for arm,old in signed['policy_arms'].items():
            p=make(context,arm,np.array(old['phase_reference']),'shared_drift_control');r=summary(p,np.array(old['endpoint_east_north_km']),context[6])
            delta=r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta)>1e-6 or r['linear_calibration_max_difference']!=0:raise ValueError('original correlation null fails exact incumbent replay')
            replays[arm]=delta
        curved={m:refit(context,'c0',m,False) for m in MODELS}
        gain=curved['shared_drift_control']['negative_twice_elbo']-curved['independent_band_drift']['negative_twice_elbo']
        candidate=curved['independent_band_drift']
        choose=bool(gain>PENALTY and candidate['final_phase_change_s']<=.01
            and np.max(abs(candidate['endpoint_east_north_km']))<=12.5 and all(t['compatible'] for t in candidate['gates']['tracks']))
        models={}
        for method in MODELS:
            pair={arm:refit(context,arm,method) for arm in ARMS};accepted=valid(pair)
            models[method]=dict(arms=pair,paired_valid=accepted,policy_arms=pair if accepted else signed['policy_arms'])
            print(case,method,'paired gates',accepted,flush=True)
        policy=models['independent_band_drift']['policy_arms'] if choose else signed['policy_arms']
        record=dict(case=case,status='complete',models=models,curved_selection=curved,curved_RF_gain=gain,
            RF_selected_model='independent_band_drift' if choose else 'incumbent',RF_selected_policy_arms=policy,
            incumbent_arms=signed['policy_arms'],source_signed_sha256=sha(source),null_replays=replays,
            mask=context[2],powers=context[3],means_s=context[4],hyper=context[5],entries=context[6],
            prior_marginal_band_drift_variance_hz2_per_s2=100.25,no_original_observation_or_alias_or_satellite_change=True,
            no_GPS_future_TLE_or_RF_collection=True,linear_tracks_do_not_choose_correlation_or_update_calibration=True)
    except Exception as exc:record=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;write(target,record);return record


def freeze():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);cohort=read(COHORT)
    protocol=dict(development_cases=cohort['development_cases'],confirmation_cases=cohort['confirmation_cases'],
        unused_confirmation_preselected_by_seed=cohort['confirmation_seed'],models=MODELS,workers=10,per_case_seconds=600,
        same_number_of_nuisance_coordinates=True,each_band_prior_drift_variance_hz2_per_s2=100.25,
        original_band_difference_drift_sigma_hz_s=1.,independent_band_difference_sigma_hz_s=float(np.sqrt(200.5)),
        same_original_observations_values_masks_aliases_labels_other_priors_and_gates=True,
        RF_selector='curved-only c0 bound gain>2log2, phase convergence and original curved gates; no linear calibration or selection',
        fixed_independent_policy_also_disclosed=True,paired_c0_fitted_c=True,
        phase_rounds=5,position_iterations=48,cold_start=[0,0],regional_center=[37.906,-122.545],regional_width_km=25,
        original_normalized_prior_volume_and_full_predictive_covariance_retained=True,
        exact_incumbent_fallback_on_either_c_arm_failure=True,no_GPS_future_TLE_RF_or_cross_scan_position_prior=True,
        confirmation_trigger='RF-selected policy improves fitted-c mean AND median on development',
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_band_drift_correlation.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('band drift correlation protocol changed')
    if not path.exists():write(path,protocol)
    return protocol


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['development','confirmation'],required=True);args=parser.parse_args()
    protocol=freeze()
    if args.stage=='confirmation':
        old=read(OUT/'development_independent_replay.json')['statistics']
        if any(old['RF_selected']['fitted_c'][k]>=old['incumbent']['fitted_c'][k] for k in ['mean_km','median_km']):
            raise ValueError('curvature-selected correlation policy did not qualify for confirmation')
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        rows=[f.result() for f in as_completed([pool.submit(run,c) for c in protocol[args.stage+'_cases']])]
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete']))


if __name__=='__main__':main()
