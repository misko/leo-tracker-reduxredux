"""Replay original ALGO02 recoveries; geographic truth is reporting only."""

from pathlib import Path
import numpy as np

from algo02_scan import bind_run_directory, load_scan, validate_history, pair_passes
from audit_ds23_algo01_coverage import coverage
from ds23_frequency_events import make_event_problem, attach_event_predictive
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import summary, cached
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_algo02_ds23 import DEFAULT_RUN, verify_freeze

OUT=ROOT/'reports/2026_10_20_ds23_discovery_completion_v2'
RUNS={
    'DS23-0004':ROOT/'reports/2026_10_20_ds23_unavailable_recovery',
    'DS23-0080':ROOT/'reports/2026_10_20_ds23_unavailable_recovery',
    'DS23-0118':ROOT/'reports/2026_10_20_ds23_unavailable_recovery',
    'DS23-0064':ROOT/'reports/2026_10_20_ds23_initial_checkpoint_recovery',
    'DS23-0266':ROOT/'reports/2026_10_20_ds23_initial_checkpoint_recovery',
    'DS23-0068':OUT,
}


def verify(case,root):
    bindings=read(root/'protocol.json')['input_sha256']
    bindings=bindings[case] if case in bindings else bindings
    for relative,expected in bindings.items():
        if sha(root/relative)!=expected or sha(DEFAULT_RUN/relative)!=expected:
            raise ValueError('original or copied recovery input changed')
    bind_run_directory(root)
    scan=load_scan(root,case)
    original=read(root/case/'result.json');record=read(root/case/'algo02_result.json')
    if original['status']!='complete' or record['status']!='accepted':
        raise ValueError('recovered original pipeline has not accepted this case')
    forecast=root/'causal_phase_history'/(case+'_forecast.json')
    history=root/'causal_phase_history'/(case+'.json')
    model,qualified=validate_history(read(history),read(forecast),scan,sha(history))
    if model!=record['hyperparameters_from_pre_RF_TLE_only']:
        raise ValueError('historical physical prior changed')
    node=original['final_node'];mask=np.asarray(record['mask'],bool);powers=np.asarray(record['weights'])
    base=problem(scan,node,'c0',mask);_,prior_rows=phase_widths(scan,base.labels)
    means=forecast_phase_mean(prior_rows,model['shrinkage'])
    entries=record['linear_entries'] if record['linear_paired_valid'] else []
    ids={o['observation_id'] for o in read(root/case/'observations.json')}
    arms={};gates={}
    for arm,saved in record['policy_arms'].items():
        p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers);cached(p)
        x=np.asarray(saved['endpoint_east_north_km'])
        replay=summary(p,x,entries)
        delta=replay['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3 or replay['linear_calibration_max_difference']>1e-10:
            raise ValueError('original RF objective or calibration changed')
        replay['final_phase_change_s']=saved.get('final_phase_change_s',0.)
        gates[arm]=replay
        extension=extend_associations(p,x,replay['gates'])
        accepted={r['component']:r for r in extension['tracks'] if r['compatible']}
        for r in replay['gates']['tracks']+replay['linear_gates']:
            if r['compatible']:accepted[r['component']]=r
        counted=coverage(list(accepted.values()),scan.tracks,ids)
        if counted['associated_additional_peaks']:
            raise ValueError('additional peaks entered original winner numerator')
        arms[arm]=dict(RF_replay_difference=delta,
            original_curved_and_predictive_gates=all(r['compatible'] for r in replay['gates']['tracks']+replay['linear_gates']),
            associated_points=counted['associated_original_winners'],
            associated_percent=counted['associated_original_percent'],
            original_GLRT_points=len(ids),associated_tracks=counted['associated_tracks'],
            endpoint_latlon=saved['endpoint_latlon'],
            position_error_km_report_only=position_error(saved['endpoint_latlon']))
    if not pair_passes(gates,include_linear=bool(entries)):
        raise ValueError('fresh paired gate replay failed')
    return dict(case=case,arms=arms,result_sha256=sha(root/case/'algo02_result.json'),
        paired_gates_replayed=True,original_source_inputs_unchanged=True)


def main():
    verify_freeze(DEFAULT_RUN)
    rows=[verify(case,root) for case,root in sorted(RUNS.items())]
    original=read(DEFAULT_RUN/'sample.json')['selected']
    accepted=[r['dataset_label'] for r in original
        if (DEFAULT_RUN/r['dataset_label']/'algo02_result.json').exists()
        and read(DEFAULT_RUN/r['dataset_label']/'algo02_result.json')['status']=='accepted']
    if set(accepted)&set(RUNS):raise ValueError('recovery silently replaced an original accepted case')
    remaining=sorted({r['dataset_label'] for r in original}-set(accepted)-set(RUNS))
    write(OUT/'independent_recovery_evaluation.json',dict(rows=rows,all_verified=True,
        original_population=len(original),original_accepted=len(accepted),
        independently_replayed_recoveries=len(rows),available_original_ALGO02_with_recoveries=len(accepted)+len(rows),
        remaining_cases=remaining,source_sha256=sha(Path(__file__)),
        published_signed_prior_benchmark_not_recomputed_or_replaced=True,
        no_localization_improvement_claimed_from_availability_recovery=True,
        GPS_used_only_in_report_side_position_error=True))
    print(rows,flush=True)
    print('Original availability',len(accepted)+len(rows),'/',len(original),'remaining',remaining,flush=True)


if __name__=='__main__':
    main()
