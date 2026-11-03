"""Matched position tests after strictly historical consensus mean qualification."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_historical_phase_consensus import runtime_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_frequency_events import refit
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_historical_phase_consensus_v2 import OUT as PRIORS
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=PRIORS/'position'
BULK=Path('/srv/bulk/leo/research/ds23-historical-consensus-position-20261021')
METHODS=('matched_next_revision','consensus')


def one(case):
    path=BULK/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('180second causal consensus paired-position cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
    try:
        context=context_signed(case);scan,node,mask,powers,means,hyper,entries,signed,signed_path=context
        prior=next(r for r in read(PRIORS/'evaluation.json')['rows'] if r['case']==case)
        if prior['status']!='complete':raise ValueError('historical prior job failed')
        if prior['cutoff_utc_ns']!=scan.receipt['cutoff_utc_ns']:raise ValueError('historical prior cutoff changed')
        selection=prior['selection'];replays={};results={}
        for arm,saved in signed['policy_arms'].items():
            p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,hyper,[])
            attach_event_predictive(p,entries,powers)
            delta=p.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-6:raise ValueError('unchanged signed incumbent fails replay')
            replays[arm]=delta
        if selection['qualified']:
            p=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,hyper,[])
            _,receipts=phase_widths(scan,p.labels)
            for method in METHODS:
                fit=selection['final_mean_models'][method]
                changed,applied=runtime_means(receipts,hyper,fit,means)
                pair={arm:refit(scan,node,mask,arm,powers,changed,hyper,[],entries) for arm in ['c0','fitted_c']}
                accepted=valid(pair)
                results[method]=dict(arms=pair,accepted=accepted,policy_arms=pair if accepted else signed['policy_arms'],
                    modified_means_s=changed,original_means_s=means,applied_label_indices=applied,
                    maximum_mean_shift_s=float(max(abs(changed-means))),original_sigma_multiplier=hyper['multiplier'],
                    original_phase_tail_degrees=hyper['nu'])
        else:
            for method in METHODS:results[method]=dict(accepted=False,arms={},policy_arms=signed['policy_arms'],
                reason='historical consensus forecast did not qualify')
        result=dict(case=case,status='complete',historical_prior_qualified=selection['qualified'],results=results,
            incumbent_arms=signed['policy_arms'],incumbent_path=str(signed_path),incumbent_sha256=sha(signed_path),
            original_endpoint_replays=replays,prior_evaluation_sha256=sha(PRIORS/'evaluation.json'),
            original_masks_labels_aliases_noise_sigma_and_tail_degrees_unchanged=True,
            matched_c0_fitted_c=True,cold_start=[0,0],regional_box_width_km=25,
            phase_rounds=5,steps_per_round=48,no_GPS_current_post_scan_TLE_new_RF_or_cross_scan_positions_used=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,result['status'],result.get('historical_prior_qualified'),
        {k:v['accepted'] for k,v in result.get('results',{}).items()},result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);prior=read(PRIORS/'evaluation.json')
    if not prior['all_terminal']:raise ValueError('historical prior qualification still live')
    cases=[r['case'] for r in prior['rows']]
    protocol=dict(cases=cases,methods=METHODS,prior_evaluation_sha256=sha(PRIORS/'evaluation.json'),
        only_qualified_forecasts_change_means=True,current_phase_variance_and_tail_degrees_fixed=True,
        matched_next_revision_control_has_same_historical_rows_mean_class_and_fit_budgets=True,
        no_satellite_nomination_or_GLRT_changes=True,original_full_paired_gates_and15s_phase_bound=True,
        matched_c0_fitted_c=True,regional_center=[37.906,-122.545],regional_box_km=25,cold_start=[0,0],
        phase_rounds=5,steps_per_round=48,workers=5,per_case_seconds=180,
        historical_targets_use_only_revisions_available_before_current_scan=True,
        no_GPS_post_scan_TLE_new_RF_or_cross_scan_position_prior=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_historical_phase_consensus.py',
            'probe_ds23_frequency_events.py','ds23_frequency_events.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen consensus mean position protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,case) for case in cases])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),
        no_position_error_used_for_inference_or_selection=True))


if __name__=='__main__':main()
