"""Bounded causal alternatives and expanded-family check on frozen018 evidence."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse
import copy
import signal
import numpy as np
import probe_ds23_iteration018_recovery as binding
import probe_ds23_iteration014_augmented_family as augmented
import audit_ds23_iteration014_augmented_family as augmented_audit
from probe_ds23_family_cavity_position import fit_configuration
from audit_ds23_iteration013_recovery import check
from run_algo01_ds23_sample import read,write,sha

RAW=binding.runner.RAW
OUT=RAW/'conflict_alternatives'


def eligible_targets(targets,active_components):
    result=[]
    for target in targets:
        if target['target']['component'] in active_components:continue
        choices=[c for c in target['candidates'] if c['qualified'] and c['conditional_RMS_hz']<=750][:3]
        if len(choices)>=2:result.append((target,choices))
    return result[:2]


def single_source_group(trials,active):
    rows=[t for t in trials if not t['paired_valid'] and len(t['additions'])>=1
          and len({r['candidate_index'] for r in t['additions']})==1
          and t['additions'][0]['candidate_index'] in active]
    return max(rows,key=lambda t:(t['added_curved_points'],tuple(r['component'] for r in t['additions']))) if rows else None


def alternatives(case):
    binding.configure('paths');paths=binding.paths.paths
    d,parent_coverage,kind,_=paths.parent(case)
    if kind!='default':raise ValueError('this frozen pair requires the original default model')
    active={r['component'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    targets=read(RAW/'single_curve_reentry'/(case+'_nominations.json'))['targets']
    result=dict(case=case,parent_kind=kind,parent_arms=d['arms'],groups=[],status='complete')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 second paired alternatives cap')));signal.alarm(180)
    try:
        for target,offers in eligible_targets(targets,active):
            trials=[]
            for offer in offers:
                node=copy.deepcopy(d['node']);keep=d['keep'].copy();k=target['row_index']
                assert node['seed']['rows'][k]['component']==target['target']['component']
                keep[d['base'].slices[k]]=True
                node['seed']['rows'][k].update(candidate_index=offer['candidate_index'],candidate_norad=offer['norad'])
                node['aliases'][k]=int(offer['aliases'][0])
                labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
                trial=fit_configuration(dict(d,keep=keep),node,d['entries'],means)
                changed=dict(d,node=node,keep=keep,means=means,arms=trial['arms'])
                audits=[];coverage={}
                for arm,saved in trial['arms'].items():
                    p=paths.build(changed,kind,arm,saved['phase_reference'])
                    audits.append(check(changed,p,arm,saved,'whole_source_alternative'))
                    coverage[arm]=paths.coverage(changed,kind,arm,saved)
                preserved={a:set(parent_coverage[a]['accepted_observation_ids'])<=set(coverage[a]['accepted_observation_ids']) for a in coverage}
                trial.update(norad=offer['norad'],component=target['target']['component'],node=node,mask=keep,means=means,
                    coverage=coverage,endpoint_audits=audits,parent_IDs_preserved=preserved,
                    qualified_for_selection=bool(trial['paired_valid'] and all(preserved.values())))
                trials.append(trial)
                write(OUT/(case+'_checkpoint.json'),dict(result,current_component=target['target']['component'],current_trials=trials))
                print(case,offer['norad'],'paired',trial['paired_valid'],'all IDs',all(preserved.values()),flush=True)
            qualified=[t for t in trials if t['qualified_for_selection']]
            winner=min(qualified,key=lambda t:t['arms']['c0']['corrected_selection_loss']) if qualified else None
            incumbent=next((t for t in qualified if t['norad']==target['best']['norad']),None)
            penalty=float(2*np.log(len(trials)))
            if winner is not None and incumbent is not None and winner is not incumbent:
                gains={a:incumbent['arms'][a]['corrected_selection_loss']-winner['arms'][a]['corrected_selection_loss'] for a in ('c0','fitted_c')}
                if min(gains.values())<=penalty:winner=incumbent
            result['groups'].append(dict(component=target['target']['component'],points=target['target']['points'],
                trials=trials,selected_norad=winner['norad'] if winner else None,search_penalty=penalty,
                no_loss_comparison_across_different_observation_masks=True))
    except Exception as exc:
        import traceback
        result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0)
    write(OUT/(case+'.json'),result)
    return dict(case=case,status=result['status'],groups=len(result['groups']))


def family():
    folder=RAW/'single_source_augmented_family';folder.mkdir(exist_ok=True)
    if (folder/'protocol.json').exists():raise FileExistsError('preserve expanded family experiment')
    write(folder/'protocol.json',dict(cases=read(RAW/'protocol.json')['cases'],
        hypothesis='one whole independent curved source can reveal conflict with the entire existing family',
        target_rule='largest failed one-or-more-source addition sharing a single already-active family',
        only_change_to_previous_trigger='minimum new curved sources two to one',
        unchanged_full_causal_cavity_best7_original_plus_best_alternative_same_mask5x48_and_optional5x40=True,
        both_c_arms_RF_gain_above2log2_all_gates_all_parent_IDs_required=True,
        no_GPS_future_TLE_or_point_trimming=True,source_sha256=sha(Path(__file__))))
    binding.configure('augmented');augmented.runner=binding.runner;augmented.OUT=folder
    augmented.choose_group=single_source_group
    for case in read(RAW/'protocol.json')['cases']:augmented.one(case)
    write(folder/'execution.json',dict(all_passed=True,all_terminal=True))
    augmented_audit.study=augmented;augmented_audit.main()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--family',action='store_true');args=parser.parse_args()
    if args.family:family();return
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve alternatives')
    cases=read(RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        target_rule='up to two longest unused nominated curves with at least two phase-qualified RMS<=750Hz candidates',
        candidate_rule='first three existing full-causal nominations',parent='RF-selected graph parent, before native paths',
        whole_source_and_all_parent_IDs_preserved=True,selection='qualified same-mask minimum c0 loss; replacing a valid best nomination requires both-arm gain above2log(pool)',
        masks_candidates_aliases_priors_and_search_budgets_matched_between_c_arms=True,
        final_original_gates_unchanged=True,no_GPS_future_TLE_or_point_trimming=True,case_cap_seconds=180))
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows=[f.result() for f in as_completed([pool.submit(alternatives,c) for c in cases])]
    write(OUT/'execution.json',dict(rows=rows,all_passed=all(r['status']=='complete' for r in rows),all_terminal=True))


if __name__=='__main__':main()
