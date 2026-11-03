"""Fixed family-support variance in predictive linear tracks, paired c arms."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import random
import signal
import time
import numpy as np
from ds23_frequency_events import make_event_problem
from ds23_linear_family_strength import attach_supported_prediction
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_sign_carrier_position import context_signed, SIGNED_AUDIT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_linear_family_strength'
BULK = Path('/srv/bulk/leo/research/ds23-linear-family-strength-20261021')
DEVELOPMENT = ['DS23-0202','DS23-0274','DS23-0293','DS23-0240','DS23-0112','DS23-0114','DS23-0289']
MODELS = ['unit_control','family_strength']


def make(context, arm, reference, method):
    scan,node,mask,powers,means,hyper,entries,*_ = context
    p = make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
    return attach_supported_prediction(p,entries,powers,unit_control=method=='unit_control')


def refit(context, arm, method):
    x = np.zeros(2); reference = np.zeros(len(context[4])); history=[]
    for _ in range(5):
        p=cached(make(context,arm,reference,method)); result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15);change=float(np.max(abs(phase-reference)))
        history.append(dict(fit=result,phase_change_s=change));reference=phase
    record=summary(p,x,context[6]);record.update(history=history,final_phase_change_s=change,
        linear_family_strength=getattr(p,'linear_family_strength',np.array([])))
    return record


def run(case):
    path=BULK/(case+'.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('600-second family-strength case budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(600)
    try:
        context=context_signed(case);signed,source=context[-2:];replay={}
        for arm,old in signed['policy_arms'].items():
            p=make(context,arm,np.asarray(old['phase_reference']),'unit_control')
            r=summary(p,np.asarray(old['endpoint_east_north_km']),context[6]);delta=r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta)>1e-6 or r['linear_calibration_max_difference']!=0:raise ValueError('unit prediction fails incumbent replay')
            replay[arm]=delta
        models={}
        for method in MODELS:
            pair={arm:refit(context,arm,method) for arm in ARMS};accepted=valid(pair)
            models[method]=dict(arms=pair,paired_valid=accepted,policy_arms=pair if accepted else signed['policy_arms'])
            print(case,method,'paired gates',accepted,flush=True)
        record=dict(case=case,status='complete',models=models,incumbent_arms=signed['policy_arms'],
            unit_endpoint_replay=replay,source_signed_sha256=sha(source),mask=context[2],powers=context[3],
            means_s=context[4],hyper=context[5],entries=context[6],
            all_original_observations_values_labels_aliases_and_gates_preserved=True,
            no_GPS_future_TLE_or_RF_used=True, no_RF_score_selection_across_different_noise_models=True)
    except Exception as exc:record=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;write(path,record);return record


def freeze():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);path=OUT/'protocol.json'
    available=sorted(read(SIGNED_AUDIT)['evidence'])
    prior=read(ROOT/'reports/2026_10_21_ds23_joint_component_refinement/protocol.json')
    excluded=set(DEVELOPMENT)|{r['job']['case'] for r in prior['jobs']}
    confirmation=random.Random(2026102107).sample([c for c in available if c not in excluded],20)
    protocol=dict(development_cases=DEVELOPMENT,confirmation_cases=confirmation,confirmation_seed=2026102107,
        confirmation_selected_before_development_position_results=True,confirmation_disjoint_from_development_and_previous23_RF_scans=True,
        confirmation_same_site_not_new_location=True,models=MODELS,workers=10,
        rule='fixed maximum active curved support strength per satellite family; independent linear noise variance multiplied by1/strength',
        strength_is_heuristic_not_calibrated_identity_probability=True,
        shared_curved_posterior_covariance_and300Hz_fragment_bias_prior_unchanged=True,
        original_unseen_Gamma_noise_variance_factor2_retained=True,
        linear_points_do_not_update_calibration=True,all_original_points_labels_aliases_priors_and_gates_unchanged=True,
        paired_c0_fitted_c=True,phase_rounds=5,position_iterations=48,cold_start=[0,0],regional_center=[37.906,-122.545],regional_width_km=25,
        exact_incumbent_fallback_on_either_arm_failure=True,no_GPS_future_TLE_or_RF_collection=True,
        no_noise_model_selection_by_RF_objective_or_truth=True,
        confirmation_trigger='family-strength policy improves both fitted-c mean and median on development; c0 always disclosed',
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_linear_family_strength.py']},
        signed_audit_sha256=sha(SIGNED_AUDIT))
    if path.exists() and read(path)!=protocol:raise ValueError('family-strength protocol changed')
    if not path.exists():write(path,protocol)
    return protocol


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['development','confirmation'],required=True);args=parser.parse_args()
    protocol=freeze()
    if args.stage=='confirmation':
        old=read(OUT/'development_independent_replay.json')['statistics']
        if any(old['family_strength']['fitted_c'][k]>=old['incumbent']['fitted_c'][k] for k in ['mean_km','median_km']):
            raise ValueError('development does not qualify for confirmation')
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        rows=[f.result() for f in as_completed([pool.submit(run,c) for c in protocol[args.stage+'_cases']])]
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete']))


if __name__=='__main__':main()
