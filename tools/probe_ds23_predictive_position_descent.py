"""Cold continuous leave-family-out predictive-position prototype.

Optimize the prior experiment's cross-family score directly, instead of only
ranking a few subset-generated positions. Original labels, masks and physical
priors are fixed. Every original point is restored for the final gate checks.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from functools import lru_cache
import gc
import signal
import time
import numpy as np

from ds23_predictive_position_search import search
from ds23_multifamily_proposals import score_position
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_predictive_position_descent'
BULK=Path('/srv/bulk/leo/research/ds23-predictive-position-descent-20261021')
COHORT=ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json'
CASES=['DS23-0268','DS23-0405']+read(COHORT)['pilot_cases']


def full_at(context,arm,position):
    scan,node,mask,powers,means,hyper,entries,*_=context
    reference=np.zeros(len(means));history=[]
    for _ in range(5):
        p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
        attach_event_predictive(p,entries,powers)
        phase=np.clip(p.state(position)['phases'][p.labels],-15,15)
        history.append(float(max(abs(phase-reference))));reference=phase
    return dict(summary(p,position,entries),final_phase_change_s=history[-1],phase_change_history_s=history)


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('240second bounded continuous family-predictive position cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    try:
        context=context_signed(case);scan,node,mask,powers,means,hyper,entries,signed,_=context
        arms={};null={};scores={};searches={}
        for arm in ['c0','fitted_c']:
            calls=0
            @lru_cache(maxsize=512)
            def evaluate(point):
                nonlocal calls
                x=np.asarray(point,float);cross=score_position(scan,node,mask,arm,powers,means,hyper,x)
                full=full_at(context,arm,x)
                linear=full['negative_twice_elbo']-full['curved_negative_twice_elbo']
                result=dict(score=cross['score']+linear,cross_family=cross,linear_predictive_objective=linear,
                    full_phase_change_s=full['final_phase_change_s'])
                calls+=1
                if calls%10==0:write(BULK/(case+'_progress.json'),dict(case=case,arm=arm,score_evaluations=calls,
                    elapsed_s=time.monotonic()-began,last_position=x,last_score=result['score']))
                gc.collect();return result
            old=signed['policy_arms'][arm]
            null[arm]=evaluate(tuple(old['endpoint_east_north_km']))
            result=search(lambda x:evaluate(tuple(x))['score'],maxiter=20)
            searches[arm]=result;x=np.asarray(result['position']);scores[arm]=evaluate(tuple(x))
            arms[arm]=full_at(context,arm,x)
            print(case,arm,'descent',result['converged'],'evaluations',result['score_evaluations'],
                'score gain',null[arm]['score']-scores[arm]['score'],flush=True)
        gains={a:null[a]['score']-scores[a]['score'] for a in arms}
        qualified=bool(all(r['converged'] for r in searches.values()) and all(g>2*np.log(2) for g in gains.values())
            and all(null[a]['cross_family']['qualified'] and scores[a]['cross_family']['qualified'] for a in arms)
            and valid(arms))
        result=dict(case=case,status='complete',searches=searches,arms=arms,null_scores=null,candidate_scores=scores,
            score_gains=gains,accepted=qualified,policy_arms=arms if qualified else signed['policy_arms'],
            incumbent_arms=signed['policy_arms'],incumbent_path=str(context[-1]),incumbent_sha256=sha(context[-1]),
            every_original_curved_point_scored_once_outside_own_family=True,
            all_original_predictive_linear_points_scored_once_without_calibration_updates=True,
            original_curved_and_predictive_gates_unchanged=True,original_satellite_nominations_fixed=True,
            no_GPS_future_TLE_new_RF_or_cross_scan_position_used=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc),
            searches=searches if 'searches' in locals() else {})
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(target,result);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,engineering_cases=CASES[:2],preexisting_random_pilots=CASES[2:],cohort_sha256=sha(COHORT),
        objective='sum of complete leave-family-out curved Gaussian predictive scores plus original shared linear predictive score',
        family_scoring='same existing5refresh full-covariance moment-matched score from multi-family proposal experiment',
        optimizer='cold L-BFGS-B from0,0;20iterations;50m central differences;25km box',
        workers=5,per_case_seconds=240,matched_c0_fitted_c_masks_candidates_priors_budgets=True,
        acceptance='optimizer converged, both CPO gains>2log2, fold phase convergence and original paired full-data gates',
        no_original_points_removed=True,no_satellite_label_or_alias_changes=True,
        linear_data_never_update_calibration=True,no_GPS_future_TLE_or_new_RF_used=True,
        new_objective_is_composite_prediction_not_calibrated_identity_probability=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_predictive_position_search.py',
            'ds23_multifamily_proposals.py','ds23_family_predictive_selection.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen continuous predictive descent protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,case) for case in CASES])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),
        no_position_error_used_for_inference_or_selection=True))


if __name__=='__main__':main()
