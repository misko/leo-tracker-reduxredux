"""Partial archived-IQ CFO intervention with unchanged DS23 labels and priors."""

import argparse
import copy
from pathlib import Path
import numpy as np
from leo.analysis.research.retained_track_likelihood import PERIOD
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,refit
from probe_ds23_raw_pilot_refinement import OUT
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,final_scan,read,write,sha


def proposed_delta(row,method):
    r=row[method]
    if r['frequency_search_boundary']:
        return 0.,'frequency boundary'
    if method=='joint_CFO_epoch_rate':
        if r['code_rate_search_boundary'] or r['epoch_search_boundary']:
            return 0.,'rate or epoch boundary'
        if r['margin']<=0:
            return 0.,'control beats exact'
    return float(r['CFO_hz']-row['archived_CFO_hz']),'refined'


def update_values(scan,rows,method):
    lookup={r['point']['observation_id']:r for r in rows}
    if len(lookup)!=len(rows):raise ValueError('one raw refinement per physical observation required')
    changed={};fallback={}
    for track in scan.tracks:
        track['values']=np.array(track['values'],copy=True)
        for k,oid in enumerate(track['observation_ids']):
            if oid not in lookup:continue
            r=lookup[oid];old=float(track['values'][k])
            difference=(old-r['archived_CFO_hz']+PERIOD/2)%PERIOD-PERIOD/2
            if abs(difference)>1e-6:raise ValueError('refinement does not match canonical original peak')
            delta,reason=proposed_delta(r,method)
            if reason=='refined':changed[oid]=delta
            else:fallback[oid]=reason
            track['values'][k]+=delta
    return dict(changed_observation_ids_and_delta_hz=changed,original_CFO_fallbacks=fallback)


def run(case):
    raw_path=OUT/(case+'_tracks.json');raw=read(raw_path)
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool);node=read(SOURCE/case/'result.json')['final_node']
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    scan=final_scan(case);p=problem(scan,node,'c0',keep)
    _,receipts=phase_widths(scan,p.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    results={}
    for method in ('fixed_epoch_CFO','joint_CFO_epoch_rate'):
        modified=copy.deepcopy(scan);updates=update_values(modified,raw['rows'],method)
        active_ids={oid for i,sl in zip(p.members,p.slices,strict=True)
                    for oid,active in zip(scan.tracks[i]['observation_ids'],keep[sl],strict=True) if active}
        updates['active_calibration_points_changed']=len(active_ids&set(updates['changed_observation_ids_and_delta_hz']))
        pair={arm:refit(modified,node,keep,arm,powers,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for a in pair.values() for t in a['gates']['tracks'])
        results[method]=dict(trial_arms=pair,paired_valid=valid,reported_arms=pair if valid else primary['arms'],updates=updates)
        write(OUT/(case+'_position_partial.json'),dict(case=case,results=results))
        print(case,method,'active changed',updates['active_calibration_points_changed'],'paired valid',valid,flush=True)
    write(OUT/(case+'_position.json'),dict(case=case,results=results,incumbent_arms=primary['arms'],
        GPS_used_for_inference=False,original_masks_labels_aliases_times_noise_priors_and_budgets_unchanged=True,
        no_original_observations_removed=True,paired_c=True,partial_IQ_refinement_not_full_scan_reanalysis=True,
        boundary_or_control_failure_falls_back_to_original_CFO=True,
        either_arm_gate_failure_falls_back_to_incumbent_pair=True,
        raw_refinement_sha256=sha(raw_path),learned_prior_sha256=sha(LEARNED/(case+'.json')),
        source_sha256=sha(Path(__file__))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
