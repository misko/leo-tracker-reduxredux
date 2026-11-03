"""Separate, uniformly budgeted numerical polish of sealed raw pilot outcomes."""

import argparse
import importlib.util
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('annealing_pilot', HERE/'run.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
spec = importlib.util.spec_from_file_location('same_endpoint_polish',
    pilot.PREVIOUS/'endpoint_polish.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def allowance(diagnostics, audit):
    """Same rule for every case/arm/method, without position or membership inputs."""
    if audit['accepted'] or not audit['feasible']:
        return None
    calls = min(134, 1000-int(diagnostics['evaluations']))
    seconds = min(78., 120.-float(diagnostics['elapsed_seconds']))
    return (calls, seconds) if calls >= 1 and seconds > 0 else None


def run(label):
    evaluation = HERE/'evaluation.json'
    rows = json.loads(evaluation.read_text())['rows']
    sources = [Path(__file__), HERE/'test_polish.py', HERE/'run.py',
        pilot.PREVIOUS/'endpoint_polish.py', pilot.OLD/'common.py', evaluation,
        HERE/f'seal_{label}.json']
    sources += [HERE/f'fit_{label}_{arm}_{method}.json'
        for arm in ('fitted-c', 'zero-c') for method in ('continuation', 'annealing')]
    authority = {str(path): pilot.digest(path) for path in sources}
    with (HERE/f'polish_launch_{label}.json').open('x') as stream:
        json.dump(dict(source_sha256=authority,
            policy='all feasible rejected selected endpoints with remaining budget',
            budget='<=1000 cumulative fit objectives and <=120 cumulative active seconds; '
                   'separate later wall run; independent audits outside fit budget',
            engine_caps=dict(evaluations=134, seconds=78)), stream, indent=2)
    context = pilot.common.load_context(label)
    outputs = []
    for row in rows:
        if row['source_id'] != label:
            continue
        arm, method = row['arm'], row['method']
        raw_path = HERE/f'fit_{label}_{arm}_{method}.json'
        raw = json.loads(raw_path.read_text())
        limits = allowance(raw['diagnostics'], row['audit'])
        output = dict(source_id=label, arm=arm, method=method,
            raw_parent_sha256=pilot.digest(raw_path), source_sha256=authority,
            policy='separate cumulative-active-budget numerical evidence; raw outcome immutable',
            independent_audits_outside_inference=1 if limits else 0)
        if limits:
            calls, seconds = limits
            ctx = replace(context, fixed_c=arm == 'zero-c', deadline=time.monotonic()+seconds)
            result = engine.polish(ctx, raw['vector'], raw['nuisance'],
                max_evaluations=calls, max_seconds=seconds,
                expected_objective=raw['diagnostics']['objective'])
            audit = pilot.common.endpoint_status(ctx, result['vector'], result['nuisance'])
            if audit['training_objective'] > row['audit']['training_objective']+1e-7:
                raise ValueError('same-target polish worsened source score')
            output.update(result, audit=audit, attempted=True,
                cumulative_evaluations=raw['diagnostics']['evaluations']+
                    result['diagnostics']['evaluations'],
                cumulative_active_seconds=raw['diagnostics']['elapsed_seconds']+
                    result['diagnostics']['total_elapsed_seconds'])
        else:
            output.update(attempted=False,
                          reason='already accepted, infeasible, or no remaining budget')
        path = HERE/f'polish_{label}_{arm}_{method}.json'
        pilot.common.save_json(path, output)
        outputs.append(dict(path=str(path), sha256=pilot.digest(path)))
        print(label, arm, method, output.get('audit', {}).get('accepted'), flush=True)
    if any(pilot.digest(path) != value for path, value in authority.items()):
        raise ValueError('polish authority changed')
    pilot.common.save_json(HERE/f'polish_seal_{label}.json', dict(outcomes=outputs,
        source_sha256=authority))


def evaluate():
    # All supplementary outcomes seal before observing support/position changes.
    for label in pilot.LABELS:
        seal = json.loads((HERE/f'polish_seal_{label}.json').read_text())
        if any(pilot.digest(row['path']) != row['sha256'] for row in seal['outcomes']):
            raise ValueError('supplementary seal mismatch')
    rows = []
    for label in pilot.LABELS:
        context = pilot.common.load_context(label)
        for arm in ('fitted-c', 'zero-c'):
            ctx = replace(context, fixed_c=arm == 'zero-c')
            for method in ('continuation', 'annealing'):
                path = HERE/f'polish_{label}_{arm}_{method}.json'
                outcome = json.loads(path.read_text())
                if not outcome['attempted']:
                    continue
                raw = json.loads((HERE/f'fit_{label}_{arm}_{method}.json').read_text())
                v, n = np.array(outcome['vector']), np.array(outcome['nuisance'])
                original = np.array(raw['vector']), np.array(raw['nuisance'])
                _, _, best, assigned, residual = pilot.common.point_state(ctx.full_model, v, n)
                old = np.load(HERE/f'eval_{label}_{arm}_{method}.npz')
                same_support = bool(np.array_equal(old['associated'], assigned))
                same_labels = bool(np.array_equal(old['satellite_number'], ctx.bank.numbers[best]))
                np.savez_compressed(HERE/f'polish_eval_{label}_{arm}_{method}.npz',
                    associated=assigned, residual_hz=residual,
                    satellite_number=ctx.bank.numbers[best], times_s=ctx.observations.times_s)
                rows.append(dict(source_id=label, arm=arm, method=method,
                    outcome_sha256=pilot.digest(path), audit=outcome['audit'],
                    support_unchanged=same_support, all_best_candidate_labels_unchanged=same_labels,
                    full=pilot.common.measure(ctx, v, n, original=original),
                    challenge=pilot.common.measure(ctx, v, n, original=original,
                        mask=pilot.common.challenge_mask(ctx))))
    pilot.common.save_json(HERE/'polish_evaluation.json', dict(rows=rows,
        promotion=False, raw_primary_unchanged=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'evaluate'))
    parser.add_argument('--source', choices=pilot.LABELS)
    args = parser.parse_args()
    run(args.source) if args.action == 'run' else evaluate()
