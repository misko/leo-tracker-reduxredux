"""Correct physical predictive support in two earlier RF-clock controls.

Original frozen artifacts are preserved. This is a data-membership correction,
not a new claimed full-DS23 localization method or a new RF collection.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from ds23_radio_calibration_factor import make_calibrated_problem,attach_calibrated_predictive
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import summary,cached
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

SOURCE=ROOT/'reports/2026_10_21_ds23_screened_joint_clock_position_v2'
OUT=ROOT/'reports/2026_10_22_ds23_differential_information/realized_clock_controls'
CASES=['DS23-0154','DS23-0216']
NOISES=['control','bootstrap','plus_radio']


def one(case,noise):
    path=OUT/(case+'_'+noise+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180second membership-corrected RF-clock paired fit cap')));signal.alarm(180)
    try:
        plan=read(SOURCE/case/'plan.json');selected=plan['plans']['strict'];saved_old=read(SOURCE/case/('strict_'+noise+'.json'))
        scan,node,_,powers,means,hyper,_,signed,signed_path=context_signed(case)
        assert sha(signed_path)==plan['signed_sha256']
        keep=np.asarray(selected['keep'],bool);entries=selected['entries']
        augmented,realized,receipt=realize_predictive_subsets(scan,entries)
        excluded=selected['disjoint']['excluded_probe_graph_ids']
        actual_ids=assert_realized_predictive_membership(augmented,realized,excluded)
        measurements=[] if noise=='control' else selected['measurements']
        if noise=='plus_radio':measurements=[dict(r,sigma_hz=float(np.sqrt(r['sigma_hz']**2+2*scan.radio_sigma_hz**2))) for r in measurements]
        legacy_replay={};pair={}
        for arm,old in saved_old['arms'].items():
            legacy=make_calibrated_problem(scan,node,keep,arm,np.array(old['phase_reference']),powers,means,hyper,[],measurements,projected_receiver_basis)
            attach_calibrated_predictive(legacy,entries,powers)
            delta=legacy.calculate(np.array(old['endpoint_east_north_km']))['negative_twice_elbo']-old['negative_twice_elbo']
            assert abs(delta)<1e-5;legacy_replay[arm]=delta
            x=np.zeros(2);reference=np.zeros(len(means));history=[]
            for _ in range(5):
                p=make_calibrated_problem(augmented,node,keep,arm,reference,powers,means,hyper,[],measurements,projected_receiver_basis)
                attach_calibrated_predictive(p,realized,powers);cached(p)
                fitted=fit(p,x,iterations=48);x=np.array(fitted['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
            result=summary(p,x,realized);result.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
            c=p.calculate(x)
            if measurements:result.update(calibration_residual_hz=c['calibration_residual_hz'],calibration_sigma_hz=c['calibration_sigma_hz'])
            assert result['linear_calibration_max_difference']==0
            assert sum(s.stop-s.start for s in p.linear_slices)==len(actual_ids)
            pair[arm]=result
        accepted=valid(pair) and all(not measurements or np.max(abs(np.asarray(r['calibration_residual_hz'])/r['calibration_sigma_hz']))<=3 for r in pair.values())
        record=dict(case=case,noise=noise,status='complete',arms=pair,paired_valid=bool(accepted),
            actual_RF_GLRT_support_disjoint=True,realized_predictive_subsets=receipt,
            source_plan_sha256=sha(SOURCE/case/'plan.json'),legacy_endpoint_replay_differences=legacy_replay,
            source_old_arms=saved_old['arms'],original_signed_incumbent=signed['policy_arms'],measurements=measurements,
            physical_predictive_observation_ids=actual_ids,matched_c0_fitted_c=True,
            no_GPS_future_TLE_or_new_RF_collection=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();record=dict(case=case,noise=noise,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-began;write(path,record)
    print(case,noise,record['status'],record.get('paired_valid'),record.get('error'),flush=True);return record


def main():
    OUT.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,noises=NOISES,source=str(SOURCE),
        correction='declared predictive IDs now select the actual time/value/basis/noise rows',
        original_persisted_contracts_and_frozen_outputs_preserved=True,original_incumbents_unmodified=True,
        source_plans_sha256={c:sha(SOURCE/c/'plan.json') for c in CASES},
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_predictive_subsets.py']},
        cold_start=[0,0],regional_width_km=25,phase_rounds=5,steps_per_round=48,workers=6,per_pair_seconds=180,
        matched_c0_fitted_c=True,original_gates_and_physical_priors_unchanged=True,
        no_GPS_inference_or_new_RF_or_postscan_TLE=True)
    p=OUT/'protocol.json'
    if p.exists() and read(p)!=protocol:raise ValueError('physical predictive support correction protocol changed')
    if not p.exists():write(p,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c,n) for c in CASES for n in NOISES])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_new_algorithm_promoted=True))


if __name__=='__main__':main()
