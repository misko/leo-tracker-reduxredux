"""Reference-informed diagnosis only; never selects benchmark predictions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe(receipt, error_fn):
    """Compare converged starts after inference, without replacing the winner."""
    best = receipt['best']
    modes = [dict(seed_index=f['seed_index'], error_m=error_fn(f['mean'][:2]),
                  objective_gap=f['objectives'][-1]-best['objectives'][-1])
             for f in receipt['fits'] if f['converged'] and f['objectives']]
    winner = next(m for m in modes if m['seed_index'] == best['seed_index'])
    oracle = min(modes, key=lambda m: m['error_m'])
    return dict(winner=winner, reference_best_sampled_mode=oracle, modes=modes,
                winner_over_3km=winner['error_m'] > 3000,
                sampled_alternative_within_3km=(winner['error_m'] > 3000
                                                and oracle['error_m'] <= 3000))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_text())
    receipts = []
    for row in evaluation['rows']:
        if not row['accepted']:
            continue
        paths = list((HERE/'regression-v1').glob('batch-*/'+row['unit']+'.json'))
        assert len(paths) == 1 and digest(paths[0]) == row['receipt_sha256']
        receipts.append((row, json.loads(paths[0].read_text())))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('mode_diagnostic_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    def error_fn(point):
        return reference.distance_m(reference.latlon_from_enu(*point), reference.REFERENCE)
    rows = []
    for audited, receipt in receipts:
        description = describe(receipt, error_fn)
        assert abs(description['winner']['error_m']-audited['error_m']) < 1e-6
        rows.append(dict(unit=audited['unit'], **description))
    oracle_errors = [r['reference_best_sampled_mode']['error_m'] for r in rows]
    result = dict(
        qualification=('REFERENCE-INFORMED DIAGNOSTIC ONLY. Best distance among converged '
                       'sampled starts is an unattainable oracle, not a deployable selector '
                       'or a global search bound. No benchmark predictions changed.'),
        evaluation_sha256=digest(args.evaluation), source_sha256=digest(__file__),
        planned_count=64, finished_count=evaluation['finished_count'], accepted_count=len(rows),
        winners_over_3km=sum(r['winner_over_3km'] for r in rows),
        over_3km_winners_with_sampled_alternative_within_3km=sum(
            r['sampled_alternative_within_3km'] for r in rows),
        oracle_median_error_m=float(np.median(oracle_errors)) if rows else None,
        oracle_p90_error_m=float(np.percentile(oracle_errors, 90)) if rows else None,
        rows=rows,
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
