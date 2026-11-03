"""Uniform remaining-three replication, with within-deadline numerical finishing."""

import argparse
import importlib.util
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('annealing_remaining_polish', HERE/'polish.py')
finishing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finishing)
pilot = finishing.pilot
LABELS = ('S02', 'S03', 'S05')


def execute(context, seed, incumbent, *, anneal, fit=None, polish=None, auditor=None):
    fit = fit or pilot.annealing.fit
    polish = polish or finishing.engine.polish
    auditor = auditor or pilot.common.endpoint_status
    begun = time.monotonic()
    ctx = replace(context, deadline=min(context.deadline, begun+120))
    raw = fit(ctx, seed, incumbent, anneal=anneal, max_evaluations=1000, max_seconds=120)
    audit = auditor(ctx, raw['vector'], raw['nuisance'])
    result = dict(vector=raw['vector'], nuisance=raw['nuisance'], audit=audit)
    limits = finishing.allowance(raw['diagnostics'], audit)
    supplement = None
    if limits:
        calls, seconds = limits
        seconds = min(seconds, ctx.deadline-time.monotonic())
        if seconds > 0:
            supplement = polish(ctx, raw['vector'], raw['nuisance'],
                max_evaluations=calls, max_seconds=seconds,
                expected_objective=raw['diagnostics']['objective'])
            final_audit = auditor(ctx, supplement['vector'], supplement['nuisance'])
            if final_audit['training_objective'] > audit['training_objective']+1e-7:
                raise ValueError('same-target finishing must not worsen source score')
            result.update(vector=supplement['vector'], nuisance=supplement['nuisance'],
                          audit=final_audit)
    calls = raw['diagnostics']['evaluations']
    if supplement:
        calls += supplement['diagnostics']['evaluations']
    if calls > 1000:
        raise RuntimeError('whole-unit objective cap exceeded')
    result.update(raw=raw, supplement=supplement, diagnostics=dict(evaluations=calls,
        elapsed_seconds=time.monotonic()-begun, accepted=result['audit']['accepted'],
        objective=result['audit']['training_objective'],
        stationarity=result['audit']['stationarity'],
        independent_audit_calls=2 if supplement else 1,
        maximum_evaluations=1000, maximum_seconds=120,
        numerical_policy='one same-target finish of feasible rejected endpoint only, '
            'within original remaining deadline/calls; source raw result retained'))
    return result


def run(label):
    sources = [Path(__file__), HERE/'test_remaining.py', HERE/'polish.py', HERE/'model.py',
        HERE/'run.py', pilot.PREVIOUS/'endpoint_polish.py', pilot.OLD/'common.py']
    sources += [pilot.PREVIOUS/'results'/f'{label}-{arm}-profile.json'
        for arm in ('fitted-c', 'zero-c')]
    authority = {str(path): pilot.digest(path) for path in sources}
    with (HERE/f'remaining_launch_{label}.json').open('x') as stream:
        json.dump(dict(source_sha256=authority, predeclared_sources=list(LABELS),
            same_pair_policy='original fixed bank; same fitted-c complete profile seed for bothc',
            width_schedule=[[1000, 149], [500, 150], [250, 150], [125, 550]],
            unit_caps=dict(actual_fit_objectives=1000, seconds=120),
            audits='independent replay calls outside fit-objective budget, within unit wall time',
            extension='remaining-three replication; pilot finishing was separate '
                      'cumulative-active run'),
            stream, indent=2)
    context = pilot.common.load_context(label)
    seed = json.loads((pilot.PREVIOUS/'results'/f'{label}-fitted-c-profile.json').read_text())
    v, n = np.array(seed['vector']), np.array(seed['nuisance'])
    original = context.model.evaluate_joint(v, n)
    nested = pilot.annealing.WidthModel(context.model, 125).evaluate_joint(v, n)
    for a, b in zip(original[:3], nested[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(original[3].responsibilities, nested[3].responsibilities)
    pilot.common.save_json(HERE/f'remaining_qualification_{label}.json', dict(
        source_sha256=authority, sigma125_nesting='bit exact', objectives=2,
        localization_fits=0, candidate_count=len(context.bank.numbers)))
    outputs = []
    for arm in ('fitted-c', 'zero-c'):
        incumbent = json.loads((pilot.PREVIOUS/'results'/f'{label}-{arm}-profile.json').read_text())
        for method in ('continuation', 'annealing'):
            ctx = replace(context, fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
            result = execute(ctx, seed, incumbent, anneal=method == 'annealing')
            path = HERE/f'remaining_fit_{label}_{arm}_{method}.json'
            pilot.common.save_json(path, dict(result, source_id=label, arm=arm, method=method,
                source_sha256=authority, original_candidate_numbers=context.bank.numbers))
            outputs.append(dict(path=str(path), sha256=pilot.digest(path)))
            print(label, arm, method, result['diagnostics'], flush=True)
    if any(pilot.digest(path) != value for path, value in authority.items()):
        raise ValueError('frozen remaining source changed')
    pilot.common.save_json(HERE/f'remaining_seal_{label}.json', dict(outcomes=outputs,
        source_sha256=authority))


def evaluate():
    for label in LABELS:
        seal = json.loads((HERE/f'remaining_seal_{label}.json').read_text())
        if any(pilot.digest(row['path']) != row['sha256'] for row in seal['outcomes']):
            raise ValueError('all remaining12 outcomes must seal before evaluation')
    rows = []
    for label in LABELS:
        context = pilot.common.load_context(label)
        for arm in ('fitted-c', 'zero-c'):
            incumbent_path = pilot.PREVIOUS/'results'/f'{label}-{arm}-profile.json'
            incumbent = json.loads(incumbent_path.read_text())
            original = np.array(incumbent['vector']), np.array(incumbent['nuisance'])
            ctx = replace(context, fixed_c=arm == 'zero-c')
            for method in ('continuation', 'annealing'):
                path = HERE/f'remaining_fit_{label}_{arm}_{method}.json'
                outcome = json.loads(path.read_text())
                v, n = np.array(outcome['vector']), np.array(outcome['nuisance'])
                _, _, best, assigned, residual = pilot.common.point_state(ctx.full_model, v, n)
                np.savez_compressed(HERE/f'remaining_eval_{label}_{arm}_{method}.npz',
                    associated=assigned, residual_hz=residual,
                    satellite_number=ctx.bank.numbers[best], times_s=ctx.observations.times_s)
                rows.append(dict(source_id=label, arm=arm, method=method,
                    outcome_sha256=pilot.digest(path), diagnostics=outcome['diagnostics'],
                    audit=pilot.common.endpoint_status(ctx, v, n),
                    full=pilot.common.measure(ctx, v, n, original=original),
                    challenge=pilot.common.measure(ctx, v, n, original=original,
                        mask=pilot.common.challenge_mask(ctx))))
    pilot.common.save_json(HERE/'remaining_evaluation.json', dict(rows=rows,
        scope='remaining-three uniform replication; raw pilot receipts remain separate',
        promotion=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'evaluate'))
    parser.add_argument('--source', choices=LABELS)
    args = parser.parse_args()
    run(args.source) if args.action == 'run' else evaluate()
