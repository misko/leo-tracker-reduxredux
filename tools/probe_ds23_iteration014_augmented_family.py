"""Use newly recovered owner evidence to test an entire family assignment."""

import copy
from pathlib import Path
import signal
import numpy as np

import run_ds23_dbg01_iteration_014 as runner
import probe_ds23_family_cavity_nominations as cavity
import probe_ds23_linear_family_groups as grouped
from ds23_family_cavity import coarse_phase_scores
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from probe_ds23_family_cavity_position import fit_configuration
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'augmented_family_replacement'


def choose_group(trials,active):
    rows=[t for t in trials if not t['paired_valid'] and len(t['additions'])>=2 and
        len({r['candidate_index'] for r in t['additions']})==1 and t['additions'][0]['candidate_index'] in active]
    return max(rows,key=lambda t:(t['added_curved_points'],tuple(r['component'] for r in t['additions']))) if rows else None


def relabel(d,proposal,target,candidate,aliases):
    node=copy.deepcopy(proposal['node']);entries=copy.deepcopy(d['entries'])
    for k,row in enumerate(node['seed']['rows']):
        if row['candidate_index']==target:
            row.update(candidate_index=candidate,candidate_norad=int(d['scan'].norads[candidate]))
            if row['component'] in aliases:node['aliases'][k]=int(aliases[row['component']])
    for e in entries:
        if e['candidate_index']==target:
            e.update(candidate_index=candidate,norad=int(d['scan'].norads[candidate]),alias=int(aliases[e['component']]))
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    return node,entries,d['all_means'][labels]


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s augmented-family cap')));signal.alarm(360)
    runner.configure();d=runner.engine.current_setup(case);prior=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']
    active={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()};proposal=choose_group(prior,active)
    result=dict(case=case,eligible=proposal is not None,trials=[],selected=None)
    if proposal is not None:
        target=proposal['additions'][0]['candidate_index'];s=d['arms']['c0'];d=dict(d,x=np.asarray(s['endpoint_east_north_km']),reference=np.asarray(s['phase_reference']))
        held=cavity.family_data(d,target);indices=[m['track_index'] for m in held['members']]+[next(i for i,t in enumerate(d['scan'].tracks) if t['key']==a['component']) for a in proposal['additions']]
        if len(indices)!=len(set(indices)):raise ValueError('augmented family source duplicated')
        if any(m['observation_ids']!=d['scan'].tracks[m['track_index']]['observation_ids'] for m in held['members']):raise ValueError('partial original family requires an explicit subset adapter')
        data=grouped.group_data(d,held['p'],d['x'],indices);data['target']=target
        f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means'])
        plus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']+.01)[0]
        minus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']-.01)[0]
        coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['q']*f,data['q']*(plus-minus)/.02,d['widths'],data['base_covariance'],data['groups'])
        scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7]
        if target not in pool:pool.append(target)
        candidates=sorted([cavity.candidate_prediction(d,data,j,coarse['aliases'][j]) for j in pool],key=lambda r:r['score'])
        alternatives=[r for r in candidates if r['candidate_index']!=target and r['qualified']]
        offers=[next(r for r in candidates if r['candidate_index']==target)]+alternatives[:1]
        result.update(original_norad=int(d['scan'].norads[target]),proposal=proposal['additions'],new_curved_points=proposal['added_curved_points'],
            cavity_curved_mask=held['calibration_mask'],held_original_IDs=held['held_ids'],nominations=candidates,all_causal_catalogue_coarse_best7_refined=True)
        write(OUT/(case+'_RF_nominations.json'),dict(result,RF_candidates_frozen_before_position_fits=True))
        for offer in offers:
            aliases={m['component']:int(a) for m,a in zip(data['members'],offer['aliases'],strict=True)};node,entries,means=relabel(d,proposal,target,offer['candidate_index'],aliases)
            same=offer['candidate_index']==target and node==proposal['node'] and entries==proposal['entries'] and np.array_equal(means,proposal['means'])
            trial=dict(proposal) if same else fit_configuration(dict(d,keep=np.asarray(proposal['mask'],bool)),node,entries,means)
            trial.update(node=node,entries=entries,means=means,mask=proposal['mask'],candidate_norad=offer['norad'],
                added_curved_points=proposal['added_curved_points'],original_same_mask_fit_reused=bool(same))
            result['trials'].append(trial);write(OUT/(case+'_checkpoint.json'),result)
            print(case,'augmented family',offer['norad'],'paired valid',trial['paired_valid'],'reused',same,flush=True)
        if len(result['trials'])==2:
            null,t=result['trials'];gains={a:null['arms'][a]['corrected_selection_loss']-t['arms'][a]['corrected_selection_loss'] for a in ['c0','fitted_c']};t['RF_gains']=gains;t['search_penalty']=float(2*np.log(2))
            t['accepted']=bool(t['paired_valid'] and min(gains.values())>t['search_penalty'])
            if t['accepted']:
                dd=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'],arms=t['arms'])
                t['coverage']={a:runner.engine.baseline.inventory(dd,a) for a in t['arms']};original=read(runner.RAW/case/'inventory.json')['arms']
                t['accepted']=all(set(original[a]['accepted_observation_ids'])<=set(c['accepted_observation_ids']) for a,c in t['coverage'].items())
            if t['accepted']:result['selected']=t
    result.update(RF_selection_before_geographic_evaluation=True,no_original_point_removed_and_no_GPS_used=True)
    write(OUT/(case+'.json'),result);signal.alarm(0)


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve augmented family experiment')
    cases=read(runner.RAW/'protocol.json')['cases'];write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        hypothesis='two newly observed owners can constrain the identity of an existing family better than its old sources alone',
        nomination='largest failed same-family multi-source addition to an already active family',maximum_groups_per_case=1,
        complete_original_family_excluded_before_radio_nomination=True,
        full_causal_catalogue_coarse_then_best7_refined=True,maximum_cold_hypotheses=2,
        original_and_best_phase_qualified_alternative_on_identical_original_plus_new_mask=True,
        original5x48_and_near_feasible5x40_budgets_and_all_gates_preserved=True,
        corrected_unused_phase_normalization_and_both_arm_RF_gain_above2log2_required=True,
        no_GPS_manual_satellite_choices_following_TLE_new_RF_or_original_ID_deletion=True,
        inspected014development_only_not_a_full_DS23_policy=True))
    for case in cases:one(case)
    write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
