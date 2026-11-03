"""Replay RF optima before and after gate constraints; no evaluation location."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from probe_algo03_frame_peak_recovery import context
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import parameters, refit
from probe_ds23_gate_retention_cohort import OUT, ARMS, make
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from run_algo01_ds23_sample import read, write


def run(case):
    destination = OUT / (case + '_constraint_diagnosis.json')
    if destination.exists():
        return dict(case=case, cached=True)
    saved = read(OUT / (case + '.json'))
    scan, node, mask, base, old = context(case)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    fine = copy.copy(scan)
    fine.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
    node = copy.deepcopy(node)
    node['seed']['state']['smooth'] = np.zeros((2, fine.rx_basis[0].shape[1]))
    output = {}
    for name, keep, selected in (
        ('original_mask', mask, saved['fine_arms']),
        ('growth_mask', np.asarray(saved['offered_mask'], bool), saved['growth_arms']),
    ):
        if selected is None:
            continue
        output[name] = {}
        for arm in ARMS:
            free = refit(fine, node, keep, arm, powers, means, hyper, [], entries)
            records = {}
            for label, record in (('unconstrained', free), ('gate_constrained', selected[arm])):
                p = make(fine, node, keep, arm, np.asarray(record['phase_reference']), powers, means, hyper, entries)
                x = np.asarray(record['endpoint_east_north_km'])
                slack = gate_slacks(p, x, entries)
                records[label] = dict(record=record, all_gate_slacks=slack,
                    failed_gates={k:v for k,v in slack.items() if v < 0},
                    nearest_gates=dict(sorted(slack.items(), key=lambda kv:kv[1])[:12]))
            records['constraint_displacement_km'] = float(np.linalg.norm(
                np.asarray(selected[arm]['endpoint_east_north_km']) - free['endpoint_east_north_km']))
            records['constraint_objective_cost'] = float(selected[arm]['negative_twice_elbo'] - free['negative_twice_elbo'])
            output[name][arm] = records
            print(case, name, arm, 'displacement', records['constraint_displacement_km'],
                  'RF cost', records['constraint_objective_cost'],
                  'failed', records['unconstrained']['failed_gates'], flush=True)
    write(destination, dict(case=case, results=output,
        GPS_used=False, observations_aliases_nominations_and_priors_matched=True))
    return dict(case=case, completed=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case')
    parser.add_argument('--cohort', action='store_true')
    args = parser.parse_args()
    if args.cohort:
        selected = []
        for case in read(OUT / 'protocol.json')['cases']:
            record = read(OUT / (case + '.json'))
            if record['fine_receipt']['constrained'] or record['growth_receipt'].get('constrained'):
                selected.append(case)
        with ProcessPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(run, case):case for case in selected}
            results = []
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(dict(case=futures[future], error=repr(exc)))
            write(OUT / 'constraint_diagnosis_execution.json', dict(results=results))
    elif args.case:
        run(args.case)
    else:
        parser.error('provide --case or --cohort')
