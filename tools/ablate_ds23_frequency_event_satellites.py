"""Paired single-scan satellite influence diagnostics after frequency repair.

Deletion targets are enumerated from accepted model observations, not selected
using reference coordinates. Original nuisance coordinates and event priors
remain in the design. Geographic evaluation is a separate report stage.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import itertools
import hashlib
import time
import numpy as np

from algo02_scan import pair_passes
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_frequency_events import OUT as EVENTS,ARMS,parameters,refit
from run_algo01_ds23_sample import ROOT,read,write,sha

CASE='DS23-0268'
OUT=ROOT/'reports/2026_10_20_ds23_0268_event_satellite_ablation'
MODELS=('receiver','receiver_reentry')


def removal_mask(rows,slices,mask,entries,norads=(),components=()):
    keep=np.asarray(mask,bool).copy();targets=set(norads);keys=set(components)
    for row,sl in zip(rows,slices,strict=True):
        if row['candidate_norad'] in targets or row['component'] in keys:keep[sl]=False
    predictive=[e for e in entries if e['norad'] not in targets and e['component'] not in keys]
    return keep,predictive


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    scan,node,_,base,old=context(CASE);entries=old['linear_entries'] if old['linear_paired_valid'] else []
    models={}
    for model in MODELS:
        document=read(EVENTS/CASE/(model+'.json'));mask=np.asarray(document['mask'],bool)
        families=sorted({r['candidate_norad'] for r,sl in zip(base.rows,base.slices,strict=True) if mask[sl].any()}
                        |{e['norad'] for e in entries})
        models[model]=dict(families=families,base_points=int(mask.sum()),predictive_points=sum(e['points'] for e in entries),
            source_sha256=sha(EVENTS/CASE/(model+'.json')))
    protocol=dict(case=CASE,models=models,position_search_start_km=[0,0],box_width_km=25,
        phase_rounds=5,position_steps_per_round=48,workers=24,
        full_original_nuisance_design_and_event_coordinates_retained=True,
        remove_all_curved_and_predictive_factors_of_each_target=True,
        same_masks_aliases_remaining_labels_priors_and_budgets_in_c_pair=True,
        no_raw_bound_comparison_between_different_observation_masks=True,
        targets_enumerated_without_GPS=True,diagnostic_deletion_not_a_deployment_selection_rule=True,
        source_sha256=sha(ROOT/'tools/ablate_ds23_frequency_event_satellites.py'))
    write(OUT/'protocol.json',protocol);return protocol


def job(model,norads=(),components=()):
    component_label=('track_'+components[0].split('-RF')[0].replace('DS23-0268-','') if len(components)==1 else
                     'block_'+hashlib.sha256('|'.join(components).encode()).hexdigest()[:12])
    label='drop_'+('_'.join(map(str,norads)) if norads else component_label)
    directory=OUT/model;directory.mkdir(parents=True,exist_ok=True);output=directory/(label+'.json')
    if output.exists():return dict(model=model,label=label,cached=True)
    scan,node,_,base,old=context(CASE);saved=read(EVENTS/CASE/(model+'.json'))
    original=np.asarray(saved['mask'],bool);entries=old['linear_entries'] if old['linear_paired_valid'] else []
    keep,predictive=removal_mask(base.rows,base.slices,original,entries,norads,components)
    powers,means,hyper=parameters(scan,base,old);started=time.monotonic()
    pair={arm:refit(scan,node,keep,arm,powers,means,hyper,saved['events'],predictive) for arm in ARMS}
    result=dict(case=CASE,model=model,norads=list(norads),components=list(components),arms=pair,
        removed_curved_points=int(original.sum()-keep.sum()),
        removed_predictive_points=sum(e['points'] for e in entries)-sum(e['points'] for e in predictive),
        remaining_curved_points=int(keep.sum()),remaining_predictive_points=sum(e['points'] for e in predictive),
        paired_valid=pair_passes(pair,include_linear=True),seconds=time.monotonic()-started,
        original_weights_and_full_nuisance_design_retained=True,
        event_time_and_prior_unchanged_event_amplitude_refitted=True,
        GPS_used=False,future_TLE_used=False,original_source_sha256=sha(EVENTS/CASE/(model+'.json')))
    write(output,result)
    row=dict(model=model,label=label,paired_valid=result['paired_valid'],seconds=result['seconds'])
    print(row,flush=True);return row


def execute(jobs,stage):
    started=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=24) as executor:
        futures={executor.submit(job,*j):j for j in jobs}
        for future in as_completed(futures):
            try:row=future.result()
            except Exception as exc:row=dict(job=futures[future],error=repr(exc))
            receipts.append(row)
            write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(jobs)))
    write(OUT/(stage+'_execution.json'),dict(receipts=receipts,seconds=time.monotonic()-started,
          all_terminal=True,errors=[r for r in receipts if 'error' in r]))


def identity_control(weighting):
    """Replay a previously RF-selected identity alternative; no GPS nomination."""
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    output=OUT/('identity_'+weighting+'.json')
    if output.exists():return dict(weighting=weighting,cached=True)
    parent=ROOT/'reports/2026_10_20_algo03_feasible_hybrids'
    selection=read(parent/'execution.json')['best_qualified_trial']
    source=parent/f"trial_{selection['index']:02d}.json";proposal=read(source)
    scan,original_node,_,base,old=context(CASE);node=proposal['node']
    saved=read(EVENTS/CASE/'receiver_reentry.json');keep=np.asarray(saved['mask'],bool)
    changed=[]
    for left,right in zip(original_node['seed']['rows'],node['seed']['rows'],strict=True):
        if left['component']!=right['component']:raise ValueError('candidate changed observation population')
        if left['candidate_norad']!=right['candidate_norad']:
            changed.append(dict(component=left['component'],original_norad=left['candidate_norad'],candidate_norad=right['candidate_norad']))
    if weighting=='matched':powers=np.asarray(saved['powers'])
    else:powers=np.asarray(read(ROOT/'reports/2026_10_20_algo03_reassociated_support/protocol.json')['powers'])
    hyper=old['hyperparameters_from_pre_RF_TLE_only'];labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    _,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,hyper['shrinkage'])
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    started=time.monotonic()
    pair={arm:refit(scan,node,keep,arm,powers,means,hyper,saved['events'],entries) for arm in ARMS}
    result=dict(case=CASE,weighting=weighting,node=node,mask=keep,powers=powers,events=saved['events'],arms=pair,
        paired_valid=pair_passes(pair,include_linear=True),changed=changed,seconds=time.monotonic()-started,
        all_curved_and_predictive_points_preserved=True,
        proposal_previously_selected_by_RF_bound_and_constraints_before_this_ablation=True,
        original_proposal_sha256=sha(source),GPS_used=False,future_TLE_used=False,
        inherited_support_control_is_separate_and_scores_are_not_compared_across_powers=True,
        finite_preexisting_candidate_control_not_new_exhaustive_reassociation=True)
    write(output,result)
    row=dict(weighting=weighting,paired_valid=result['paired_valid'],seconds=result['seconds'])
    print(row,flush=True);return row


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('singles','followup','identity'),default='singles')
    args=parser.parse_args()
    if args.stage=='singles':
        protocol=prepare()
        execute([(m,(n,),()) for m in MODELS for n in protocol['models'][m]['families']],'singles')
    elif args.stage=='followup':
        request=read(OUT/'followup_request.json')
        execute([(r['model'],tuple(r.get('norads',())),tuple(r.get('components',()))) for r in request['jobs']],'followup')
    else:
        with ProcessPoolExecutor(max_workers=2) as executor:
            for future in as_completed([executor.submit(identity_control,w) for w in ('matched','prior_support')]):
                print(future.result(),flush=True)
