"""Fixed-association high-band restart check; starts from saved band/full fits."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import time

import numpy as np
import algo02_scan as algo
from investigate_dsx01_localization_failures import fit
from probe_ds23_graph_seeded_paths import build
from probe_ds23_frequency_events import summary
from replay_information import ROOTS, HERE, info


def one(job):
    case, start_group = job
    began = time.monotonic()
    root = ROOTS['ch5_8']
    saved = json.loads((root/'family_cavity/position'/f'{case}.json').read_text())
    starts = json.loads((ROOTS[start_group]/'family_cavity/position'/f'{case}.json').read_text())
    selected = saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(root)
    d = dict(scan=algo.load_scan(root, case), node=selected['node'] if selected else saved['baseline_node'],
             keep=np.asarray(saved['original_mask'], bool), powers=np.asarray(saved['powers']),
             means=np.asarray(selected['means'] if selected else saved['baseline_means']),
             entries=selected['entries'] if selected else saved['baseline_entries'], model=saved['model'])
    records = {}
    for arm, parent in saved['policy_arms'].items():
        p = build(d, 'default', arm, parent['phase_reference'])
        old_x = np.asarray(parent['endpoint_east_north_km'])
        assert abs(p.calculate(old_x)['negative_twice_elbo']-parent['negative_twice_elbo']) < 1e-3
        x = np.asarray(starts['policy_arms'][arm]['endpoint_east_north_km'])
        reference = np.asarray(parent['phase_reference'])
        history = []
        for epoch in range(5):
            p = build(d, 'default', arm, reference)
            fitted = fit(p, x, iterations=48)
            x = np.asarray(fitted['parameters'])
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            history.append(dict(epoch=epoch, phase_change_s=float(max(abs(phase-reference))),
                                fit=fitted))
            reference = phase
        assert history[-1]['phase_change_s'] <= .01, 'phase refresh did not converge'
        result = summary(p, x, d['entries'])
        result.update(history=history, parent_endpoint=old_x,
                      displacement_from_parent_m=float(1000*np.linalg.norm(x-old_x)),
                      objective_difference_from_parent=float(result['negative_twice_elbo']-parent['negative_twice_elbo']))
        records[arm] = result
    record = dict(case=case, start_group=start_group, arms=records, elapsed_seconds=time.monotonic()-began,
                  original_high_band_observations_identities_priors_preserved=True,
                  no_new_GPS_or_TLE_input=True, new_association_search=False)
    info.write(HERE/f'restart_{case}_{start_group}.json', record)
    print(case, start_group, {a: round(v['displacement_from_parent_m'], 3) for a, v in records.items()}, flush=True)


if __name__ == '__main__':
    jobs = [(case, group) for case in ('DS24-0015', 'DS24-0019') for group in ('all', 'ch1_4')]
    info.write(HERE/'restart_protocol.json', dict(jobs=jobs, arms=['c0', 'fitted_c'],
               fixed_high_band_data_and_identites=True, phase_rounds=5, position_steps_per_round=48,
               reference_initialization='saved high-band reference in both starts',
               case_selection='two largest paired high-minus-low error gaps',
               starts_are_inferred_full_and_low_band_positions_not_GPS=True))
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, jobs))
