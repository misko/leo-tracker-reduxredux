"""Seal the declared 24-case/two-partition study without position fits."""
import argparse
import sys
from pathlib import Path

import numpy as np
import scipy

from common import (ARMS, CONTROLS, MODELS, ORIGINAL, PLAN, SCALES, SEEDS,
    binding, digest, read, value_digest, verify_bindings, write_new)
from kernel import build, family_partition
from matched_controls import cohort, load_baseline, measurement_binding, phase_pair_valid


def freeze(root):
    root = Path(root).resolve()
    if (root/'protocol.json').exists() or (root/'results').exists():
        raise ValueError('refuse to overwrite a frozen or executed movement batch')
    study = read(root.parent/'protocol.json')
    ledger = read(root.parent/'cohort_ledger.json')
    if study['cases'] != cohort() or len(study['cases']) != 24:
        raise ValueError('root cohort differs from original receiver intersection')
    if study['seeds'] != list(SEEDS) or len(study['job_dispatch']) != 144:
        raise ValueError('unexpected parent job matrix')
    ledger_rows = {r['case']: r for r in ledger['rows'] if r['eligible']}
    inputs, full_data = {}, {}
    for case in study['cases']:
        row = ledger_rows[case]
        file_bindings = [row['baseline'], row['existing_rx1']] + row['frozen_scan_files']
        verify_bindings(file_bindings)
        d = load_baseline(case)
        p = build(d, 'c0', np.zeros(len(d['means'])), 'baseline')
        partitions = {}
        for seed in SEEDS:
            partition = family_partition(d, seed)
            folds = []
            for fold, held in enumerate(partition['folds']):
                owners = dict(curved_training_ids=[], curved_held_ids=[], predictive_training_ids=[], predictive_held_ids=[])
                for r, i, sl in zip(p.rows, p.members, p.slices, strict=True):
                    ids = np.asarray(p.scan.tracks[i]['observation_ids'])[d['keep'][sl]].tolist()
                    owners['curved_held_ids' if r['candidate_index'] in held else 'curved_training_ids'].extend(ids)
                for entry in d['entries']:
                    owners['predictive_held_ids' if entry['candidate_index'] in held else 'predictive_training_ids'].extend(entry['observation_ids'])
                training_ids = owners['curved_training_ids'] + owners['predictive_training_ids']
                held_ids = owners['curved_held_ids'] + owners['predictive_held_ids']
                if set(training_ids) & set(held_ids) or len(set(training_ids + held_ids)) != len(training_ids + held_ids):
                    raise ValueError('duplicate or overlapping likelihood IDs')
                if not held_ids or not owners['curved_training_ids']:
                    raise ValueError('unscorable empty fold')
                folds.append(dict(fold=fold, held_families=held,
                    held_norads=[int(d['scan'].norads[j]) for j in held], **owners,
                    training_ids_sha256=value_digest(training_ids), held_ids_sha256=value_digest(held_ids)))
            partitions[str(seed)] = dict(active_family_indices=partition['active_family_indices'],
                active_norads=[int(d['scan'].norads[j]) for j in partition['active_family_indices']],
                permutation=partition['permutation'], folds=folds)
        baseline_saved = read(d['baseline_path'])
        candidate = read(row['existing_rx1']['path'])
        if candidate['baseline_sha256'] != d['baseline_sha256'] or candidate['input_binding_sha256'] != measurement_binding(d):
            raise ValueError('saved RX1 and baseline inputs differ')
        original_valid = candidate['status'] == 'complete' and phase_pair_valid(candidate.get('arms', {}))
        if original_valid != candidate['paired_valid']:
            raise ValueError('saved original paired gate status does not replay')
        full_data[case] = dict(eligible=bool(candidate['eligible']), original_adopted=bool(candidate['adopted']),
            original_policy_source=candidate['policy_source'], original_paired_gates_pass=bool(original_valid),
            baseline_pair={a: baseline_saved['policy_arms'][a]['endpoint_east_north_km'] for a in ARMS},
            candidate_pair={a: candidate['arms'][a]['endpoint_east_north_km'] for a in ARMS},
            baseline_binding=row['baseline'], candidate_binding=row['existing_rx1'],
            exact_original_gate_bindings_preserved=True)
        inputs[case] = dict(baseline_sha256=d['baseline_sha256'], measurement_binding_sha256=measurement_binding(d),
            causal_receipt=d['scan'].receipt, file_bindings=file_bindings,
            original_curved_noise_sha256=value_digest(p.point_noise),
            inherited_full_RF_fixed_noise=d['scan'].fixed_window_noise, partitions=partitions)
        print('prepared', case, 'families', len(partition['active_family_indices']), flush=True)
    write_new(root/'input_manifest.json', inputs)
    write_new(root/'full_data_bindings.json', full_data)
    files = set(root.glob('*.py'))
    files.update([PLAN, ORIGINAL/'heldout.py', ORIGINAL/'freeze.py', ORIGINAL/'test_heldout.py',
        CONTROLS/'receiver/selection.json', CONTROLS/'receiver/protocol.json', CONTROLS/'receiver/position_protocol_rf.json'])
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and (str(path).startswith('/home/mouse9911/gits/leo-tracker-reduxredux/src/')
                or str(path).startswith('/home/mouse9911/gits/leo-tracker-reduxredux/tools/')
                or str(path).startswith(str(CONTROLS)) or str(path).startswith('/tmp/algo03-feasible-deps/')):
                files.add(path)
    sources = [binding(path) for path in sorted(files)]
    write_new(root/'source_manifest.json', sources)
    bindings = sources + [binding(root/name) for name in ('input_manifest.json', 'source_manifest.json', 'full_data_bindings.json')]
    bindings += [binding(root.parent/name) for name in ('protocol.json', 'cohort_ledger.json', 'preflight.json')]
    protocol = dict(schema='ds24-movement-policy/v1', cases=study['cases'], models=MODELS, arms=ARMS, seeds=SEEDS,
        jobs=study['job_dispatch'], smoke_jobs=study['smoke_jobs'], phase_rounds=5, position_steps=48,
        start_east_north_km=[0., 0.], box_km=[25., 25.], sigma_multipliers=SCALES,
        primary_sigma_multiplier=float(np.sqrt(2.)), randomization='Generator(PCG64(SeedSequence([seed,numeric_case_suffix]))), sorted active indices, array_split(permutation,3)',
        gain_tolerance=1e-8, required_positive_joint_aggregates_per_case=24,
        phase_tolerance_s=.01, gamma_log_precision_tolerance=1e-5,
        accepted_final_position_termination=['small_step_and_improvement', 'no_accepted_damped_step'],
        job_seconds_cap=240, batch_seconds_cap=2700, start_workers=2, max_workers=6, blas_threads=1,
        expected_counts=study['expected_counts'], resource_rule=study['resources']['expansion_rule'],
        bindings=bindings, GPS_used=False, new_RF=False, development_replication=True,
        policy='original_eligible_and_original_paired_gates_and_all_valid_and_all24_joint_sums_gt_1e-8_else_exact_baseline_pair',
        score='Full joint Gaussian moment prediction; inherited full-RF graph/noise; conditional variational nuisance posterior; plug-in training-only position',
        excluded_uncertainty=['nonlinear held phase geometry', 'training position uncertainty', 'fully training-only graph/noise selection'],
        environment=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__))
    write_new(root/'protocol.json', protocol)
    verify_bindings(bindings)
    write_new(root/'freeze_seal.json', dict(protocol_sha256=digest(root/'protocol.json'),
        input_manifest_sha256=digest(root/'input_manifest.json'), source_manifest_sha256=digest(root/'source_manifest.json'),
        full_data_bindings_sha256=digest(root/'full_data_bindings.json'), GPS_used=False, fits_executed=0))
    print('frozen', root, '144jobs/576fits/1152vectors', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    freeze(parser.parse_args().root)
