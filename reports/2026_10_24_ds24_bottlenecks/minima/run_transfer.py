"""Finite whole-assignment proposals transferred from half to full DS24 data."""
import argparse
import copy
from pathlib import Path
import signal
import time

import numpy as np

from run_fixed import OUT, FULL, HALF, ARMS, refit
import ds24_engine as engine
from algo02_scan import pair_passes
from ds23_family_cavity import unused_student_gap
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_family_cavity_position import unused_count
from probe_ds23_gate_retention_cohort import constrained
from probe_ds23_graph_seeded_paths import build
from run_algo01_ds23_sample import read, write, sha


def configuration(d, case, group):
    saved = read(HALF/group/'family_cavity/position'/(case+'.json'))
    selected = saved['selected'] if saved['accepted'] else None
    source_node = selected['node'] if selected else saved['baseline_node']
    half_tracks = {t['key']:t for t in read(HALF/group/case/'tracks.json')}
    full_tracks = {t['key']:t for t in d['scan'].tracks}
    lookup = {r['component']:(r,a) for r,a in zip(source_node['seed']['rows'],source_node['aliases'],strict=True)}
    norad_index = {int(n):k for k,n in enumerate(d['scan'].norads)}
    node = copy.deepcopy(d['node'])
    entries = copy.deepcopy(d['entries'])
    active = {r['component']:int(d['keep'][sl].sum())
        for r,sl in zip(d['base'].rows,d['base'].slices,strict=True)}
    transferred = []
    for k,row in enumerate(node['seed']['rows']):
        if row['component'] not in lookup:
            continue
        source,alias = lookup[row['component']]
        old = full_tracks[row['component']]
        new = half_tracks[row['component']]
        assert old['observation_ids'] == new['observation_ids']
        np.testing.assert_array_equal(old['times'],new['times'])
        np.testing.assert_array_equal(old['values'],new['values'])
        candidate = norad_index[int(source['candidate_norad'])]
        if (row['candidate_index'], node['aliases'][k]) != (candidate,alias):
            transferred.append(dict(component=row['component'], original_norad=row['candidate_norad'],
                proposed_norad=source['candidate_norad'], original_alias=node['aliases'][k],proposed_alias=alias,
                total_points=len(old['times']),full_retained_points=active[row['component']],
                common_observation_ids=old['observation_ids']))
        row.update(candidate_index=candidate,candidate_norad=int(d['scan'].norads[candidate]))
        node['aliases'][k] = int(alias)
    for entry in entries:
        if entry['component'] in lookup:
            source,alias = lookup[entry['component']]
            entry.update(candidate_index=norad_index[int(source['candidate_norad'])],
                norad=int(source['candidate_norad']),alias=int(alias))
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    if set(e['candidate_index'] for e in entries)-set(labels):
        raise ValueError('transferred hypothesis removes an existing predictive family coordinate')
    return dict(d,node=node,entries=entries,means=d['all_means'][labels]),transferred,saved['policy_arms']


def corrected(d, arm, saved):
    p=build(d,'default',arm,saved['phase_reference'])
    return saved['negative_twice_elbo'] - unused_count(p,d['entries'])*unused_student_gap(d['model']['nu'])


def main(case,group):
    destination=OUT/(case+'_transfer.json')
    if destination.exists():
        print(case,'cached',flush=True)
        return
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s assignment-transfer cap')))
    signal.alarm(240)
    d=engine.cavity_context(case,root=FULL)
    dd,changes,half_arms=configuration(d,case,group)
    original_loss={a:corrected(d,a,s) for a,s in d['arms'].items()}
    trials=[]
    for name in ('cold','half_endpoint'):
        starts={a:[0,0] if name=='cold' else half_arms[a]['endpoint_east_north_km'] for a in ARMS}
        arms={a:refit(dd,a,starts[a]) for a in ARMS}
        attempted=False
        slacks={a:min(gate_slacks(build(dd,'default',a,r['phase_reference']),
            np.asarray(r['endpoint_east_north_km']),dd['entries']).values()) for a,r in arms.items()}
        if not pair_passes(arms,include_linear=True) and min(slacks.values())>=-.25:
            arms=constrained(dd['scan'],dd['node'],dd['keep'],dd['powers'],dd['means'],dd['model'],dd['entries'],arms)
            attempted=True
        for a,r in arms.items():
            r['corrected_selection_loss']=corrected(dd,a,r)
        valid=bool(pair_passes(arms,include_linear=True) and all(r['final_phase_change_s']<=.01 for r in arms.values()))
        gates={a:dict(curved_failures=[g['component'] for g in r['gates']['tracks'] if not g['compatible']],
            predictive_failures=[g['component'] for g in r['linear_gates'] if not g['compatible']],
            final_phase_change_s=r['final_phase_change_s']) for a,r in arms.items()}
        trials.append(dict(name=name,starts=starts,arms=arms,paired_valid=valid,gate_failures=gates,
            unconstrained_minimum_gate_slack=slacks,constrained_refinement_attempted=attempted,
            gain={a:original_loss[a]-r['corrected_selection_loss'] for a,r in arms.items()}))
        print(case,group,name,'valid',valid,'gains',trials[-1]['gain'],'gates',gates,flush=True)
    eligible=[t for t in trials if t['paired_valid']]
    best=min(eligible,key=lambda t:t['arms']['c0']['corrected_selection_loss']) if eligible else None
    gain=best['gain']['c0'] if best else None
    selection=dict(best=best['name'] if best else None,gain_c0=gain,
        accepted=bool(gain is not None and gain>1e-4),
        rule='equal assignment priors, minimum corrected normalized full-data c0 objective, paired gates and phase convergence; gain >1e-4 numerical floor',
        no_geographic_error_or_GPS_accessed=True)
    result=dict(case=case,group=group,status='complete',transferred_changes=changes,
        changed_retained_points=sum(c['full_retained_points'] for c in changes),
        original_corrected_loss=original_loss,original_arms=d['arms'],trials=trials,RF_selection=selection,
        full_mask_points=int(d['keep'].sum()),total_mask_points=len(d['keep']),
        full_observations_mask_weights_and_physical_prior_hyperparameters_unchanged=True,
        exact_common_track_observation_ids_times_and_values_asserted=True,
        full_causal_phase_prior_means_used_for_transferred_candidate_labels=True,
        finite_half_assignment_proposal_not_exhaustive_association_search=True,
        phase_rounds=5,position_steps_per_round=48,seconds=time.monotonic()-began,
        source_sha256=sha(Path(__file__)))
    write(destination,result)
    signal.alarm(0)
    print(case,'complete',result['seconds'],selection,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('case')
    p.add_argument('group',choices=['ch1_4','ch5_8'])
    a=p.parse_args()
    main(a.case,a.group)
