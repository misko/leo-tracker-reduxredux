"""Restore independently curved unused data in an already active component.

The observation mask alone changes: satellite identities, aliases, fragments,
noise hyperpriors, receiver and orbital coordinates retain their definitions.
"""

import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import repair_ds23_iteration009_targets as repair
from localize_merged_track_catalogue import raw_curvature
from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'partial_mask_restoration'


def restoration_offers(p,entries,maximum=3):
    occupied={o for e in entries for o in e['observation_ids']};offers=[]
    for row,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)):
        active=p.keep[sl];track=p.scan.tracks[i]
        if not active.any() or active.all():continue
        use=~active
        if use.sum()<12 or occupied&set(np.asarray(track['observation_ids'])[use]):continue
        subset=dict(track,times=track['times'][use],values=track['values'][use])
        if not raw_curvature(subset):continue
        offers.append(dict(row_index=row,track_index=i,component=track['key'],added_points=int(use.sum()),
            added_observation_ids=np.asarray(track['observation_ids'])[use].tolist(),independently_curved_unused_subset=True))
    return sorted(offers,key=lambda r:(-r['added_points'],r['component']))[:maximum]


def one(case):
    repair.configure();d=repair.engine.current_setup(case)
    p=repair.engine.baseline.build(d,'c0',d['arms']['c0']['phase_reference']);offers=restoration_offers(p,d['entries'])
    trials=[]
    for offer in offers:
        keep=d['keep'].copy();keep[p.slices[offer['row_index']]]=True
        if not np.all(keep[d['keep']]):raise ValueError('restoration removed an incumbent likelihood observation')
        result=fit_configuration(dict(d,keep=keep),d['node'],d['entries'],d['means'])
        dd=dict(d,keep=keep,arms=result['arms']);checks=[];coverage={}
        for a,saved in result['arms'].items():
            checks.append(audit_baseline(dd,a,saved));coverage[a]=repair.engine.baseline.inventory(dd,a)
        result.update(mask=keep,offer=offer,added_curved_points=offer['added_points'],coverage=coverage,independent_audits=checks,
            original_node_labels_aliases_powers_means_and_priors_unchanged=True)
        trials.append(result);print(case,'restore',offer['added_points'],'valid',result['paired_valid'],flush=True)
    passing=[t for t in trials if t['paired_valid']];selected=max(passing,key=lambda t:t['added_curved_points']) if passing else None
    write(OUT/(case+'.json'),dict(case=case,offers=offers,trials=trials,selected=selected,
        no_GPS_following_TLE_new_parameter_or_original_point_deletion=True))
    return dict(case=case,status='complete',offers=len(offers),passing=len(passing))


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve partial-mask restoration')
    write(OUT/'protocol.json',dict(cases=read(repair.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        hypothesis='later nuisance and identity updates can make previously masked curved tails reusable',
        maximum_components_per_case=3,minimum_unused_points=12,
        unused_points_must_independently_pass_existing20s_250Hz_raw_curvature_rule=True,
        whole_missing_mask_restored_no_residual_based_point_selection=True,
        same_original_labels_aliases_powers_mean_priors_noise_model_and_nuisance_dimensions=True,
        cold_fits_use_existing5x48_and_original_bounded_feasibility_budget=True,
        both_c_arms_same_added_original_GLRT_IDs=True,
        selection='most newly admitted original points among both-arm passing trials; exact incumbent fallback',
        every_original_likelihood_point_kept=True,no_GPS_future_TLE_new_RF_or_new_parameters=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
