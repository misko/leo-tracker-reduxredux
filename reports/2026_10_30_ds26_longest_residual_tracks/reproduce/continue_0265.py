"""Bounded diagnostic continuation of frozen 0265 training graphs only."""
import hashlib
import json
import signal
import time
from pathlib import Path

import numpy as np

from annotate_predictive_only import context
from annotate_track_predictively import prior_means, training_factory
from ds23_frequency_events import make_event_problem
from investigate_dsx01_localization_failures import fit
from leo.analysis.research.grouped_prediction import replay_split
from phase_reference_checks import phase_refresh
from probe_ds23_frequency_events import cached

OUT = Path('/srv/bulk/leo/research/ds26-longest-residual-20261030/rejection-audit')
ROOT = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases/DS26-0265/candidate-v2/recovery')
TID = '36f621d91e81526b1ce4'
BEGAN = time.monotonic()
result = dict(scope='training-graph numerical diagnostic only; frozen identity decision unchanged',
    same_training_masks_priors_candidates_and_c_arms=True, maximum_seconds=600,
    extra_rounds_per_fold_arm=10, original_rounds_replayed_without_refitting=5,
    GPS_used=False, new_RF=False, frozen_files_changed=False, rows=[], source_sha256={})


def read(path):
    data = path.read_bytes()
    result['source_sha256'][str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def save():
    result['seconds'] = time.monotonic() - BEGAN
    (OUT / '0265-continuation.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


def timeout(*unused):
    raise TimeoutError('Bounded 590-second diagnostic deadline')


def phase_record(p, x, reference):
    actual = p.state(x)['phases'][p.labels]
    updated, check = phase_refresh(actual, reference)
    order = np.argsort(-np.abs(actual - reference))
    offenders = []
    for index in order[:5]:
        j = p.labels[int(index)]
        offenders.append(dict(norad=int(p.scan.norads[j]), candidate_index=int(j),
            reference_s=float(reference[index]), actual_phase_s=float(actual[index]),
            movement_s=float(actual[index] - reference[index]), next_reference_s=float(updated[index])))
    return updated, dict(**check, largest_phase_movements=offenders)


def run():
    inv_path = next((ROOT / 'all-large-track-recovery').glob('*/inventory.json'))
    inv = read(inv_path)
    annotation = read(ROOT / TID / 'annotation/result.json')
    d = context(inv)
    p0, _ = d['problems']['c0']
    target = next(r for r in inv['tracks'] if r['track_id'] == TID)
    target_times = d['scan'].tracks[target['track_index']]['times']
    full_times = np.r_[p0.flat_times, target_times]
    means, receipts = prior_means(d, d['node'])
    factory = training_factory(d)
    powers = np.ones(len(d['powers']))
    contexts = []
    for fold in annotation['folds']:
        train, held = replay_split(full_times, fold['split'])
        keep = d['keep'] & train[:len(p0.flat_times)]
        mask_hash = hashlib.sha256(keep.astype(np.uint8).tobytes()).hexdigest()
        for arm in ('c0', 'fitted_c'):
            original = fold['proposals'][0]['arms'][arm]
            reference = np.zeros(len(means))
            row = dict(seed=fold['seed'], arm=arm, training_mask_sha256=mask_hash,
                training_points=int(keep.sum()), target_calibrates_training_graph=False,
                original_rounds=[], continuation=[])
            result['rows'].append(row)
            for k, saved in enumerate(original['history']):
                p = make_event_problem(d['scan'], d['node'], keep, arm, reference, powers, means, d['model'], [], base_problem_factory=factory)
                cached(p)
                x = np.asarray(saved['endpoint'])
                reference, check = phase_record(p, x, reference)
                if abs(check['phase_change_s'] - saved['phase_change_s']) > 1e-6:
                    raise ValueError(f'Frozen phase replay mismatch seed={fold["seed"]} arm={arm} round={k+1}')
                row['original_rounds'].append(dict(round=k+1, endpoint_east_north_km=x.tolist(), **check))
            objective = float(p.calculate(x)['negative_twice_elbo'])
            row['original_objective_replay_difference'] = objective - original['training_objective']
            if abs(row['original_objective_replay_difference']) > 1e-4:
                raise ValueError('Frozen training objective failed exact replay')
            contexts.append(dict(row=row, keep=keep, arm=arm, x=x, reference=reference))
            print(f'replayed seed={fold["seed"]} arm={arm} offender={check["largest_phase_movements"][0]}', flush=True)
            save()
    # Round-robin every identical budget, retaining paired c arms even if one
    # graph converges earlier. There are no target fits or candidate changes.
    for epoch in range(10):
        for c in contexts:
            p = make_event_problem(d['scan'], d['node'], c['keep'], c['arm'], c['reference'], powers, means, d['model'], [], base_problem_factory=factory)
            cached(p)
            f = fit(p, c['x'], iterations=48)
            c['x'] = np.asarray(f['parameters'])
            c['reference'], check = phase_record(p, c['x'], c['reference'])
            c['row']['continuation'].append(dict(round=epoch+6, endpoint_east_north_km=c['x'].tolist(),
                training_objective=float(p.calculate(c['x'])['negative_twice_elbo']),
                fit_stopped=f.get('stopped'), fit_evaluations=f.get('evaluations'), **check))
            save()
        print(f'extra_round={epoch+1} deltas={[round(c["row"]["continuation"][-1]["phase_change_s"], 9) for c in contexts]}', flush=True)
    result['completed'] = True


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(590)
    try:
        run()
    except Exception as exc:
        result['completed'] = False
        result['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        save()
