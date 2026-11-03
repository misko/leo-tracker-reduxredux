"""Disjoint recording confirmation of unchanged family-position estimators.

The adapter supplies each recording's real published prior inputs. It does not
change the frozen estimator, gate rules, c-arm matching, or deletion budgets.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_family_position_consensus as engine
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_symmetric_family_selection import bound_incumbent
from probe_algo03_frame_peak_recovery import context,SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha
from ds23_frequency_events import make_event_problem,attach_event_predictive
from run_dsx01_clean_region import zero_state

OUT=ROOT/'reports/2026_10_20_ds23_family_position_consensus_validation'
INPUTS=OUT/'prior_inputs'
DEVELOPMENT=engine.OUT


def bind():
    engine.OUT=OUT;engine.BANK=INPUTS


def prepare():
    OUT.mkdir(exist_ok=True);INPUTS.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['adapter_sha256']!=sha(Path(__file__)):raise ValueError('frozen confirmation adapter changed')
        bind();engine.prepare();return p
    excluded=set(read(DEVELOPMENT/'protocol.json')['cases'])
    pool=[p.parent.name for p in sorted(SOURCE.glob('DS23-*/algo02_result.json'))
          if read(p)['status']=='accepted' and p.parent.name not in excluded]
    cases=sorted(np.random.default_rng(2026102041).choice(pool,20,replace=False).tolist())
    write(INPUTS/'protocol.json',dict(cases=cases,seed=2026102041,pool=pool,
        excluded_development_cases=sorted(excluded),no_GPS_errors_read_for_selection=True))
    receipts=[]
    for case in cases:
        directory=INPUTS/case;directory.mkdir(exist_ok=True)
        scan,node,keep,base,old=context(case);signed,binding=bound_incumbent(case)
        model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(old['weights'])
        if signed['accepted']:means=np.asarray(signed['means_s'])
        else:
            _,rows=phase_widths(scan,base.labels);means=forecast_phase_mean(rows,model['shrinkage'])
        global_means=np.zeros(len(scan.norads));global_means[base.labels]=means
        node=dict(node,seed=dict(node['seed'],state=zero_state(scan)))
        entries=old['linear_entries'] if old['linear_paired_valid'] else []
        replays=[]
        for arm in ('c0','fitted_c'):
            saved=signed['policy_arms'][arm]
            p=make_event_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
            attach_event_predictive(p,entries,powers)
            delta=p.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-3:raise ValueError('published signed-prior input replay failed')
            replays.append(dict(arm=arm,RF_difference=delta))
        write(directory/'result.json',dict(purpose='prior_input_metadata_not_a_new_RF_fit',
            incumbent_arms=signed['policy_arms'],powers=powers,means_s=global_means,
            published_prior_binding=binding,original_mask=keep,disabled_model_replays=replays,
            no_GPS_or_future_TLE_used=True))
        receipts.append(dict(case=case,input_sha256=sha(directory/'result.json'),replays=replays))
    bind();p=engine.prepare()
    p.update(stage='disjoint_recording_confirmation',seed=2026102041,
        disjoint_from_development=sorted(excluded),available_pool=pool,
        adapter_sha256=sha(Path(__file__)),input_receipts=receipts,
        primary_criterion='fitted-c policy mean AND median beat published signed-prior incumbent; c0 comparison reported without hiding regression',
        previous_stricter_all_four_metric_development_check_not_passed=True,
        mean_and_geometric_median_are_confirmation_targets=True,
        jackknife_kept_as_original_prespecified_control=True,
        baseline_full_corpus_results_already_available_not_untouched_locations=True,
        frozen_before_new_family_deletion_fits_or_geographic_evaluation=True)
    write(path,p);return p


def finalize_small(case):
    scan,node,keep,base,old,powers,means,incumbent,binding=engine.setup(case)
    result=dict(case=case,policies={k:dict(accepted=False,trial_arms={},policy_arms=incumbent,
        rejection_reason='fewer than four active curved families') for k in engine.KINDS},
        incumbent_arms=incumbent,baseline_arms=old['policy_arms'],candidate_positions={},
        all_deletion_fits_qualified=False,held_family_count=len(engine.plan(case)['families']),
        GPS_used=False,future_TLE_used=False,every_original_observation_reinstated_in_final_gate_replay=True)
    write(OUT/case/'result.json',result);return dict(case=case,accepted={k:False for k in engine.KINDS})


if __name__=='__main__':
    protocol=prepare();tasks=[]
    for case in protocol['cases']:
        plan=engine.plan(case)
        if plan['minimum_family_count_met']:tasks.extend((case,j) for j in plan['families'])
    receipts=[]
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures={pool.submit(engine.fold_job,*task):task for task in tasks}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(task=futures[f],error=repr(exc)))
            write(OUT/'fold_progress_cohort.json',dict(receipts=receipts,completed=len(receipts),total=len(tasks)))
    errors=[r for r in receipts if 'error' in r]
    final=[engine.finalize(c) if engine.plan(c)['minimum_family_count_met'] else finalize_small(c)
           for c in protocol['cases']] if not errors else []
    write(OUT/'execution_cohort.json',dict(all_terminal=True,receipts=receipts,errors=errors,final=final))
