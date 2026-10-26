"""Bounded deletion influence diagnostic, not an association rejection policy."""
from concurrent.futures import ProcessPoolExecutor
import json
import time

import numpy as np
import algo02_scan as algo
from investigate_dsx01_localization_failures import fit
from probe_ds23_graph_seeded_paths import build
from probe_ds23_frequency_events import summary
from replay_information import ROOTS, HERE, info


def one(job):
    case, norad = job
    began = time.monotonic()
    root = ROOTS['ch5_8']
    saved = json.loads((root/'family_cavity/position'/f'{case}.json').read_text())
    selected = saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(root)
    d = dict(scan=algo.load_scan(root, case), node=selected['node'] if selected else saved['baseline_node'],
             keep=np.asarray(saved['original_mask'], bool), powers=np.asarray(saved['powers']),
             means=np.asarray(selected['means'] if selected else saved['baseline_means']),
             entries=selected['entries'] if selected else saved['baseline_entries'], model=saved['model'])
    p = build(d, 'default', 'c0', saved['policy_arms']['c0']['phase_reference'])
    labels = np.asarray(p.labels)[p.flat_labels]
    target = int(np.flatnonzero(p.scan.norads == norad)[0])
    removed = int(np.sum(d['keep'] & (labels == target)))
    changed = dict(d, keep=d['keep'] & (labels != target),
                   entries=[e for e in d['entries'] if e['candidate_index'] != target])
    assert changed['keep'].any() and removed > 0
    results = {}
    for arm, parent in saved['policy_arms'].items():
        control = build(d, 'default', arm, parent['phase_reference'])
        x = np.asarray(parent['endpoint_east_north_km'])
        assert abs(control.calculate(x)['negative_twice_elbo']-parent['negative_twice_elbo']) < 1e-3
        reference = np.asarray(parent['phase_reference'])
        history = []
        for epoch in range(5):
            p = build(changed, 'default', arm, reference)
            assert p.labels == control.labels and p.supported == control.supported
            fitted = fit(p, x, iterations=48)
            x = np.asarray(fitted['parameters'])
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            history.append(dict(epoch=epoch, phase_change_s=float(max(abs(phase-reference))), fit=fitted))
            reference = phase
        assert history[-1]['phase_change_s'] <= .01, 'phase refresh did not converge'
        result = summary(p, x, changed['entries'])
        result.update(history=history, parent_endpoint=parent['endpoint_east_north_km'],
                      displacement_from_parent_m=float(1000*np.linalg.norm(x-np.asarray(parent['endpoint_east_north_km']))))
        results[arm] = result
    info.write(HERE/f'ablate_{case}_{norad}.json', dict(case=case, removed_norad=norad,
               removed_curved_points=removed,
               removed_predictive_points=sum(e['points'] for e in d['entries'] if e['candidate_index'] == target),
               arms=results, elapsed_seconds=time.monotonic()-began,
               original_nuisance_design_support_and_other_priors_preserved=True,
               same_deletion_mask_and_budgets_in_both_c_arms=True,
               influence_diagnostic_not_proof_of_wrong_identity=True,
               no_new_GPS_or_TLE_inputs=True))
    print(case, norad, {a: round(v['displacement_from_parent_m'], 1) for a, v in results.items()}, flush=True)


if __name__ == '__main__':
    # Top two absolute fixed-nuisance family gradient projections toward the
    # inferred full-band endpoint, from the sealed local mechanism replay.
    # No truth-coordinate vector is used in this ranking.
    jobs = [('DS24-0015', 62758), ('DS24-0015', 66543),
            ('DS24-0019', 48323), ('DS24-0019', 66466)]
    info.write(HERE/'ablation_protocol.json', dict(jobs=jobs, arms=['c0', 'fitted_c'],
               selection='two largest absolute conditional-family-gradient projections on inferred full-to-high displacement',
               original_support_kept=True, phase_rounds=5, position_steps=48,
               initial_position_and_phase='saved high-band parent',
               no_policy_selection_and_no_same_mask_score_comparison_across_deletions=True))
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, jobs))
