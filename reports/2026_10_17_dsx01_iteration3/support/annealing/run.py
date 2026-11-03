"""Two-source fixed-bank matched annealing pilot with a pre-evaluation seal."""

import argparse
import hashlib
import importlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = ROOT/'reports/2026_10_16_dsx01_models'
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
sys.path.insert(0, str(OLD))
common = importlib.import_module('common')
spec = importlib.util.spec_from_file_location('support_annealing_model', HERE/'model.py')
annealing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(annealing)
LABELS = ('S01', 'S04')


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(label):
    source_paths = [HERE/'model.py', HERE/'test_model.py', Path(__file__), OLD/'common.py',
                    PREVIOUS/'results'/f'{label}-fitted-c-profile.json',
                    PREVIOUS/'results'/f'{label}-zero-c-profile.json']
    authority = {str(path): digest(path) for path in source_paths}
    with (HERE/f'launch_{label}.json').open('x') as stream:
        json.dump(dict(source_sha256=authority, max_evaluations=1000, max_seconds=120,
            schedule=[[1000, 149], [500, 150], [250, 150], [125, 550]],
            labels='two-source original fixed banks; no new position seeds',
            source='paired fitted-c fixed-profile complete seed; c0 changes onlyc'),
            stream, indent=2)
    context = common.load_context(label)
    seed = json.loads((PREVIOUS/'results'/f'{label}-fitted-c-profile.json').read_text())
    v, n = np.array(seed['vector']), np.array(seed['nuisance'])
    baseline = context.model.evaluate_joint(v, n)
    same = annealing.WidthModel(context.model, 125).evaluate_joint(v, n)
    for a, b in zip(baseline[:3], same[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(baseline[3].responsibilities, same[3].responsibilities)
    common.save_json(HERE/f'qualification_{label}.json', dict(source=authority,
        objectives=2, localization_fits=0, sigma125_nesting='bit exact',
        objective=float(same[0]), base_prior='same', candidate_count=len(context.bank.numbers)))
    outcomes = []
    for arm in ('fitted-c', 'zero-c'):
        incumbent = json.loads((PREVIOUS/'results'/f'{label}-{arm}-profile.json').read_text())
        for name in ('continuation', 'annealing'):
            ctx = replace(context, fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
            result = annealing.fit(ctx, seed, incumbent, anneal=name == 'annealing',
                                    max_evaluations=1000, max_seconds=120)
            path = HERE/f'fit_{label}_{arm}_{name}.json'
            common.save_json(path, dict(source_id=label, arm=arm, method=name,
                vector=result['vector'], nuisance=result['nuisance'],
                diagnostics=result['diagnostics'], source_sha256=authority,
                original_candidate_numbers=context.bank.numbers,
                policy='fixed-bank profile seed; final125J only; own-arm125 incumbent retained'))
            outcomes.append(dict(path=str(path), sha256=digest(path)))
            print(label, arm, name, result['diagnostics']['objective'],
                  result['diagnostics']['selected_origin'], result['diagnostics']['evaluations'],
                  flush=True)
    if any(digest(path) != value for path, value in authority.items()):
        raise ValueError('frozen source changed')
    common.save_json(HERE/f'seal_{label}.json', dict(outcomes=outcomes, source_sha256=authority))


def evaluate():
    for label in LABELS:
        seal = json.loads((HERE/f'seal_{label}.json').read_text())
        for row in seal['outcomes']:
            if digest(row['path']) != row['sha256']:
                raise ValueError('all eight outcomes must seal before evaluation')
    rows = []
    for label in LABELS:
        context = common.load_context(label)
        for arm in ('fitted-c', 'zero-c'):
            incumbent = json.loads((PREVIOUS/'results'/f'{label}-{arm}-profile.json').read_text())
            original = np.array(incumbent['vector']), np.array(incumbent['nuisance'])
            ctx = replace(context, fixed_c=arm == 'zero-c')
            for name in ('continuation', 'annealing'):
                path = HERE/f'fit_{label}_{arm}_{name}.json'
                result = json.loads(path.read_text())
                v, n = np.array(result['vector']), np.array(result['nuisance'])
                mask = common.challenge_mask(ctx)
                row = dict(source_id=label, arm=arm, method=name, outcome_sha256=digest(path),
                    diagnostics=result['diagnostics'], audit=common.endpoint_status(ctx, v, n),
                    full=common.measure(ctx, v, n, original=original),
                    challenge=common.measure(ctx, v, n, original=original, mask=mask),
                    outside=common.measure(ctx, v, n, original=original, mask=~mask))
                _, _, best, assigned, residual = common.point_state(ctx.full_model, v, n)
                np.savez_compressed(HERE/f'eval_{label}_{arm}_{name}.npz', associated=assigned,
                    residual_hz=residual, satellite_number=ctx.bank.numbers[best],
                    times_s=ctx.observations.times_s)
                rows.append(row)
    common.save_json(HERE/'evaluation.json', dict(scope='two-source pilot; final scoring sigma125',
        rows=rows, postseal_objectives_per_result=8, original_source_replays_per_case=2,
        promotion=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'evaluate'))
    parser.add_argument('--source', choices=LABELS)
    args = parser.parse_args()
    run(args.source) if args.action == 'run' else evaluate()
