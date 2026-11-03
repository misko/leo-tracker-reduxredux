"""Frozen joint-curve comparison on20 scans disjoint from pilot development.

This cohort was previously inspected in other experiments: it is not an
untouched holdout or a new-location validation. All20 scans count, including
no-offer, preflight failure and original-gate rejection fallbacks.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

from probe_ds23_joint_relative_position import OUT as PILOT,INPUT,CASES,VARIANTS,control_audit,one
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=PILOT/'confirmation20'
COHORT=ROOT/'reports/2026_10_22_ds23_unanchored_relative_position/confirmation20/protocol.json'


def preflight(case):
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s joint control preflight cap')));signal.alarm(90)
    try:
        incumbent=context_signed(case)[-2]['policy_arms']
        if not read(INPUT/(case+'.json'))['eligible']:result=dict(case=case,status='no_offer',original_incumbent=incumbent)
        else:
            audit=control_audit(case,OUT)
            result=dict(case=case,status='complete',original_incumbent=incumbent,audit=audit)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(OUT/(case+'_preflight.json'),result);return result


def main():
    OUT.mkdir(exist_ok=True);cases=read(COHORT)['cases'];assert not set(cases)&set(CASES)
    protocol=dict(cases=cases,development_cases=CASES,variants=[list(v) for v in VARIANTS],default='joint_bias424',
        earlier_relative_only_cohort_sha256=sha(COHORT),scan_disjoint_from_development=True,
        cohort_previously_inspected_by_other_algorithms_not_untouched_holdout=True,same_site_not_new_location=True,
        identical_RF_inputs_actual_IQ_quarantine_priors_masks_budgets_in_all_variants=True,
        original_c0_and_fitted_c_pair_required=True,all20_include_original_incumbent_fallbacks=True,
        no_GPS_inference_selection_or_future_TLE=True,cold_start_km=[0,0],region_width_km=25,
        phase_rounds=5,steps_per_round=48,workers=12,paired_fit_cap_s=300,
        numerical_core_sha256=sha(ROOT/'tools/ds23_joint_relative_position.py'),
        pilot_protocol_sha256=sha(PILOT/'protocol.json'),
        driver_sha256=sha(ROOT/'tools/probe_ds23_joint_relative_position.py'),
        confirmation_driver_sha256=sha(Path(__file__)),
        inputs={c:sha(INPUT/(c+'.json')) for c in cases})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen joint comparison protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        preflights=[f.result() for f in as_completed([pool.submit(preflight,c) for c in cases])]
    write(OUT/'preflight_execution.json',dict(rows=preflights,all_terminal=True))
    jobs=[];rows=[]
    for r in preflights:
        for variant,include,bias in VARIANTS:
            if r['status']=='complete':jobs.append((r['case'],variant,include,bias))
            else:
                record=dict(case=r['case'],variant=variant,status=r['status'],accepted=False,
                    original_incumbent=r.get('original_incumbent'),policy_arms=r.get('original_incumbent'),
                    no_offer_or_preflight_error=r.get('error'),reference_position_used=False)
                if record['original_incumbent'] is None:
                    record['original_incumbent']=record['policy_arms']=context_signed(r['case'])[-2]['policy_arms']
                write(OUT/(r['case']+'_'+variant+'.json'),record);rows.append(record)
    with ProcessPoolExecutor(max_workers=12) as pool:
        for future in as_completed([pool.submit(one,*job,output_dir=OUT) for job in jobs]):rows.append(future.result())
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all20_count_including_fallbacks=True))


if __name__=='__main__':main()
