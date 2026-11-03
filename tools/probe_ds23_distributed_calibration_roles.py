"""Frozen22-case role ablation; all original GLRT retained, GPS report-only."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import inventory_ds23_distributed_calibration_curvature as inventory
import run_ds23_dbg01_iteration_016 as runner
import probe_ds23_graph_seeded_paths as paths
from ds23_calibration_roles import predictive_roles
from ds23_predictive_subsets import assert_realized_predictive_membership
from probe_ds23_family_cavity_position import fit_configuration
from audit_ds23_iteration013_recovery import check
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_23_ds23_distributed_calibration_roles'


def coverage(data, arm, saved):
    original=paths.build
    paths.build=lambda d,kind,a,reference: runner.engine.baseline.build(d,a,reference)
    try:return paths.coverage(data,'default',arm,saved)
    finally:paths.build=original


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s role ablation cap')))
    signal.alarm(180);runner.configure();data=runner.engine.current_setup(case)
    frozen=read(inventory.OUT/(case+'.json'))
    if sha(data['observations_path'])!=frozen['observations_sha256']:
        raise ValueError('observations changed after RF inventory')
    changed,receipt=predictive_roles(data,frozen)
    explicit=assert_realized_predictive_membership(changed['scan'],changed['entries'])
    old_ids=set(np.concatenate([np.asarray(data['scan'].tracks[i]['observation_ids'])[data['keep'][sl]]
        for i,sl in zip(data['base'].members,data['base'].slices,strict=True)]))
    old_ids.update(o for e in data['entries'] for o in e['observation_ids'])
    new_ids=set(explicit)
    new_ids.update(o for i,sl in zip(data['base'].members,data['base'].slices,strict=True)
        for o in np.asarray(data['scan'].tracks[i]['observation_ids'])[changed['keep'][sl]])
    if old_ids!=new_ids:raise ValueError('role change altered likelihood measurement union')
    baseline_coverage={a:coverage(data,a,s) for a,s in data['arms'].items()}
    if receipt['demoted']:
        result=fit_configuration(changed,changed['node'],changed['entries'],changed['means'])
        pair=result['arms']
    else:result=dict(paired_valid=True,constrained_refinement_attempted=False);pair=data['arms']
    checks=[];memberships={}
    for arm,saved in pair.items():
        p=runner.engine.baseline.build(changed,arm,saved['phase_reference'])
        checks.append(check(changed,p,arm,saved,'distributed_curvature_role'))
        memberships[arm]=coverage(changed,arm,saved)
    preserved={a:set(baseline_coverage[a]['accepted_observation_ids'])<=set(memberships[a]['accepted_observation_ids']) for a in pair}
    qualified=bool(result['paired_valid'] and all(preserved.values()))
    write(OUT/(case+'.json'),dict(case=case,status='complete',arms=pair,baseline_arms=data['arms'],
        baseline_coverage=baseline_coverage,coverage=memberships,role_receipt=receipt,
        paired_valid=result['paired_valid'],all_original_accepted_IDs_preserved=preserved,qualified=qualified,
        policy_arms=pair if qualified else data['arms'],
        policy_coverage=memberships if qualified else baseline_coverage,
        constrained_refinement_attempted=result['constrained_refinement_attempted'],
        independent_endpoint_checks=checks,all_likelihood_IDs_unchanged=True,
        inventory_sha256=sha(inventory.OUT/(case+'.json')),original_mask=data['keep'],mask=changed['keep'],
        no_new_association_or_orbit_mode_or_noise_fit=True))
    signal.alarm(0);print(case,'demoted',frozen['would_demote_points'],'qualified',qualified,flush=True)
    return dict(case=case,status='complete',demoted_points=frozen['would_demote_points'],qualified=qualified)


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve frozen role experiment')
    p=read(inventory.OUT/'protocol.json');assert read(inventory.OUT/'execution.json')['all_passed']
    write(OUT/'protocol.json',dict(cases=p['cases'],engineering=p['engineering'],random20=p['random20'],
        inventory_protocol_sha256=sha(inventory.OUT/'protocol.json'),source_sha256=sha(Path(__file__)),
        role_adapter_sha256=sha(ROOT/'tools/ds23_calibration_roles.py'),
        primary='RF-frozen degree2..4 jackknife weak original sources become predictive-only',
        predictive_variance='2 sigma_original^2 / original_power; existing predictive points unchanged',
        noise_and_role_change_not_pure_calibration_feedback_ablation=True,
        exact_original_likelihood_ID_union_labels_aliases_modes_and_other_priors_retained=True,
        qualification='both original gates, phase convergence, all original accepted IDs retained',
        incumbent_fallback_on_any_failure=True,source_role_assignment_not_selected_by_score_or_GPS=True,
        cold_start_km=[0,0],regional_center=[37.906,-122.545],box_width_km=25,
        phase_rounds=5,steps=48,unchanged_near_feasible5x40_trigger=True,
        no_GPS_following_TLE_history_new_RF_or_IQ=True,workers=4,per_case_seconds=180,
        same_site_previously_studied_cohort_not_untouched_or_new_location=True,
        evaluate_all22_even_if_engineering_negative=True,new_ALGO_release=False))
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,p['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
