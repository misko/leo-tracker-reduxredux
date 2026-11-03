"""Include already associated curved evidence in position, one bounded pass."""

import copy
from pathlib import Path

import numpy as np

from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
import run_ds23_dbg01_iteration_002 as iteration
from run_algo01_ds23_sample import read, write, sha

OUT=iteration.RAW/'curved_promotion'


def promotable_curves(rows, curved_keys, active_keys, original_points):
    return [r for r in rows if r['compatible'] and r['component'] in curved_keys
            and r['component'] not in active_keys and r['points']==original_points[r['component']]]


def one(case):
    d=iteration.current_setup(case)
    previous=read(iteration.RAW/'family_alternatives'/(case+'.json'))
    original=previous['selected'];trials=[];checks=[]
    variants=[('incumbent',None),('growth',original)] if original else [('incumbent',None)]
    for kind,parent in variants:
        node=copy.deepcopy(parent['node'] if parent else d['node'])
        keep=np.asarray(parent['mask'],bool).copy() if parent else d['keep'].copy()
        coverage=previous['coverage'] if parent else read(iteration.RAW/case/'inventory.json')['arms']
        active={r['component'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if keep[sl].any()}
        curved={d['scan'].tracks[i]['key'] for i in d['scan'].curved}
        proposals=promotable_curves(coverage['c0']['associations']['tracks'],curved,active,
                                   {t['key']:len(t['times']) for t in d['scan'].tracks})
        if not proposals:continue
        promotions=[]
        for row in proposals:
            slot=next(k for k,r in enumerate(node['seed']['rows']) if r['component']==row['component'])
            if node['seed']['rows'][slot]['candidate_index']!=row['candidate_index']:
                raise ValueError('promotion must preserve the existing association identity and alias')
            keep[d['base'].slices[slot]]=True
            promotions.append(dict(component=row['component'],norad=row['norad'],candidate_index=row['candidate_index'],alias=node['aliases'][slot]))
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
        trial=fit_configuration(dict(d,keep=keep),node,d['entries'],d['all_means'][labels])
        trial.update(mask=keep,additions=(copy.deepcopy(parent['additions']) if parent else [])+promotions,
            added_curved_points=int(keep.sum()-d['keep'].sum()),promotions=promotions,source_variant=kind)
        trials.append(trial)
        print(case,'curved position evidence promotion',kind,[r['component'] for r in promotions],trial['paired_valid'],flush=True)
        dd=dict(d,node=node,keep=keep,entries=d['entries'],means=np.asarray(trial['means']))
        for arm,saved in trial['arms'].items():checks.append(audit_baseline(dd,arm,saved))
    choices=([original] if original else [])+[r for r in trials if r['paired_valid']]
    selected=max(choices,key=lambda r:r['added_curved_points']) if choices else None
    coverage=previous['coverage']
    if selected is not None and selected is not original:
        dd=dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),entries=selected['entries'],
                means=np.asarray(selected['means']),arms=selected['arms'])
        coverage={a:iteration.baseline.inventory(dd,a) for a in ['c0','fitted_c']}
    record=dict(case=case,trials=trials,selected=selected,coverage=coverage,checks=checks,all_passed=True,
        promotion_selection_sealed_before_geographic_evaluation=True,
        original_points_aliases_candidate_IDs_and_all_gates_preserved=True,
        no_new_ALGO_version=True,prior_stage_sha256=sha(iteration.RAW/'family_alternatives'/(case+'.json')))
    write(OUT/(case+'.json'),record)
    return dict(case=case,all_passed=True,new_trial_arms_audited=len(checks),
                selected_added_curved_points=selected['added_curved_points'] if selected else 0)


def main():
    iteration.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve sealed promotion evidence')
    write(OUT/'protocol.json',dict(cases=read(iteration.RAW/'protocol.json')['cases'],
        purpose='separate associated GLRT from actively used position evidence',
        proposals='all already-associated wholly inactive whole curved tracks at original current aliases and IDs',
        controls=['incumbent only plus promotion','recovered evidence plus promotion'],
        selection='most added curved points among original paired-gate-valid hypotheses',
        no_linear_calibration_or_new_candidates_or_priors_or_gate_relaxation=True,
        one_pass_only=True,regional_start=[0,0],phase_rounds=5,fit_steps=48,
        matched_c0_and_fitted_c=True,no_GPS_or_following_TLE=True,source_sha256=sha(Path(__file__))))
    rows=[one(c) for c in read(iteration.RAW/'protocol.json')['cases']]
    write(OUT/'execution.json',dict(rows=rows,all_passed=True,all_terminal=True,
                                  no_geographic_evaluation_before_selection=True))


if __name__=='__main__':main()
