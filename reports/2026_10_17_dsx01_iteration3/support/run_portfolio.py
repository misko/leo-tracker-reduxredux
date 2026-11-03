"""Bounded paired pilot; seal all inference outcomes before geographic evaluation."""

import argparse
import hashlib
import importlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'reports/2026_10_16_dsx01_models'
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(PREVIOUS))
common = importlib.import_module('common')
expansion = importlib.import_module('bank_expansion')
portfolio = importlib.import_module('portfolio')
LABELS = ('S01', 'S04')


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(label):
    original = common.load_context(label)
    selection = json.loads((PREVIOUS/f'candidate_screen_{label}.json').read_text())
    regional = expansion.regional_bank(original)
    expanded, _ = expansion.expandable_context(original, selection['selected_ids'],
                                               regional=regional)
    fixed_path = PREVIOUS/'results'/f'{label}-fitted-c-profile.json'
    fixed = json.loads(fixed_path.read_text())
    lifted, transfer = expansion.expandable_context(common.with_state(original,
        fixed['vector'], fixed['nuisance']), selection['selected_ids'], regional=regional)
    for name in ('baseline', 'design', 'clock_design'):
        np.testing.assert_array_equal(getattr(lifted.model.original, name),
                                      getattr(expanded.model.original, name))
    fitted_path = PREVIOUS/'expanded-results'/f'{label}-fitted-c-profile.json'
    fitted = json.loads(fitted_path.read_text())
    return expanded, dict(vector=lifted.vector, nuisance=lifted.nuisance), fitted, transfer


def run(label):
    paths = [HERE/'portfolio.py', HERE/'test_portfolio.py', Path(__file__),
             PREVIOUS/'bank_expansion.py', OLD/'common.py',
             PREVIOUS/'results'/f'{label}-fitted-c-profile.json',
             PREVIOUS/'expanded-results'/f'{label}-fitted-c-profile.json',
             PREVIOUS/'expanded-results'/f'{label}-zero-c-profile.json',
             PREVIOUS/f'candidate_screen_{label}.json']
    authority = {str(path): digest(path) for path in paths}
    launch = HERE/f'launch_{label}.json'
    with launch.open('x') as stream:
        json.dump(dict(sources=authority, policy='five paired seeds; own-arm incumbent',
                       max_evaluations=1000, maximum_seconds=120), stream, indent=2)
    ctx, fixed, expanded, transfer = prepare(label)
    outputs = []
    for arm in ('fitted-c', 'zero-c'):
        incumbent_path = PREVIOUS/'expanded-results'/f'{label}-{arm}-profile.json'
        incumbent = json.loads(incumbent_path.read_text())
        for method in ('continuation', 'portfolio'):
            context = replace(ctx, fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
            result = portfolio.fit(context, fixed, expanded, incumbent, method=method,
                                   max_evaluations=1000, max_seconds=120)
            output = HERE/f'fit_{label}_{arm}_{method}.json'
            common.save_json(output, dict(source_id=label, arm=arm, method=method,
                vector=result['vector'], nuisance=result['nuisance'],
                diagnostics=result['diagnostics'], lift=transfer, sources=authority,
                qualification='paired fitted-c five source states; zero-c only coefficient6; '
                    'retained own-arm incumbent; expanded original bank unchanged'))
            outputs.append(dict(path=str(output), sha256=digest(output)))
            print(label, arm, method, result['diagnostics']['selected_origin'],
                  result['diagnostics']['objective'], result['diagnostics']['evaluations'],
                  flush=True)
    for path, expected in authority.items():
        if digest(path) != expected:
            raise ValueError('frozen pilot authority changed')
    common.save_json(HERE/f'seal_{label}.json', dict(outcomes=outputs, sources=authority))


def evaluate():
    seals = {}
    for label in LABELS:
        seal = json.loads((HERE/f'seal_{label}.json').read_text())
        for row in seal['outcomes']:
            if digest(row['path']) != row['sha256']:
                raise ValueError('all eight outcomes must seal before evaluation')
        seals[label] = digest(HERE/f'seal_{label}.json')
    rows = []
    for label in LABELS:
        ctx, _, _, _ = prepare(label)
        for arm in ('fitted-c', 'zero-c'):
            incumbent = json.loads((PREVIOUS/'expanded-results'/
                f'{label}-{arm}-profile.json').read_text())
            context = replace(ctx, fixed_c=arm == 'zero-c')
            baseline = np.array(incumbent['vector']), np.array(incumbent['nuisance'])
            for method in ('continuation', 'portfolio'):
                path = HERE/f'fit_{label}_{arm}_{method}.json'
                r = json.loads(path.read_text())
                v, n = np.array(r['vector']), np.array(r['nuisance'])
                audit = common.endpoint_status(context, v, n)
                full = common.measure(context, v, n, original=baseline)
                mask = common.challenge_mask(context)
                challenge = common.measure(context, v, n, original=baseline, mask=mask)
                outside = common.measure(context, v, n, original=baseline, mask=~mask)
                _, _, best, assigned, residual = common.point_state(context.full_model, v, n)
                np.savez_compressed(HERE/f'eval_{label}_{arm}_{method}.npz',
                    associated=assigned, residual_hz=residual,
                    satellite_number=context.bank.numbers[best],
                    times_s=context.observations.times_s)
                rows.append(dict(source_id=label, arm=arm, method=method,
                    diagnostics=r['diagnostics'], audit=audit, full=full,
                    challenge=challenge, outside=outside, outcome_sha256=digest(path)))
    common.save_json(HERE/'evaluation.json', dict(scope='two-source pilot, no all-five aggregate',
        seals=seals, rows=rows, evaluation_objectives_per_result=8,
        qualification='reference evaluation only; unchanged classification and all rows'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'evaluate'))
    parser.add_argument('--source', choices=LABELS)
    args = parser.parse_args()
    run(args.source) if args.action == 'run' else evaluate()
