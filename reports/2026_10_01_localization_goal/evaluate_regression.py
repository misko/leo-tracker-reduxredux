"""Audit available frozen regression attempts before accessing position truth."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualification(receipt, launch, audit_passed):
    failures = []
    if not audit_passed:
        failures.append('audit_failed')
    if (launch.get('timed_out') or launch.get('returncode') != 0
            or not launch.get('within_budget') or launch.get('elapsed_seconds', np.inf) > 90.):
        failures.append('worker_failed_or_over_budget')
    fits = [f for f in receipt.get('fits', []) if f.get('objectives')]
    best = min(fits, key=lambda f: f['objectives'][-1]) if fits else None
    if (best is None or not best.get('converged') or receipt.get('best') != best
            or receipt.get('status') != 'converged_local_mode'):
        failures.append('winning_mode_not_converged')
    if best:
        point = np.asarray(best.get('mean', []))
        if (point.ndim != 1 or point.size < 5 or not np.all(np.isfinite(point))
                or np.linalg.norm(point[:2]) > 250.):
            failures.append('invalid_state')
        if not all(np.all(np.isfinite(f['objectives'])) for f in fits):
            failures.append('invalid_objective')
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    for filename, expected in freeze['source_sha256'].items():
        assert digest(filename) == expected, filename
    plan = json.loads((ROOT/'plans/localization-approaches-2026-10-01/benchmark.json').read_text())
    authorities = {r['unit_id']: r for r in plan['historical_primary_receipts']}
    rows, points = [], {}
    for unit in freeze['ordered_units']:
        paths = list((HERE/'regression-v1').glob('batch-*/'+unit+'.launch.json'))
        if not paths:
            rows.append(dict(unit=unit, status='not_finished', accepted=False, error_m=None))
            continue
        assert len(paths) == 1
        launch = json.loads(paths[0].read_text())
        path = paths[0].with_name(unit+'.json')
        audit_errors, receipt = [], {}
        try:
            assert launch['freeze_sha256'] == digest(freeze_path)
            assert launch['unit_id'] == unit
            if path.exists():
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == 'hard'
                expected_config = dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                                       iterations_per_seed=64, acquisition_limit_s=50.,
                                       internal_deadline_s=85., external_limit_s=90.)
                assert receipt['config'] == expected_config
                for filename, expected in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == expected
                binding = authorities[unit]
                baseline_path = ROOT/binding['path']
                assert digest(baseline_path) == binding['sha256']
                baseline = json.loads(baseline_path.read_text())
                assert receipt['inputs'] == baseline['inputs']
                assert receipt['height'] == baseline['height_input_bindings']
                for filename, expected in receipt['inputs'].items():
                    assert digest(filename) == expected
                assert len(receipt['observations']) == baseline['planned_factors']
                ids = [i for track in receipt['observations'] for i in track]
                assert len(ids) == len(set(ids))
            elif launch['returncode'] == 0:
                raise ValueError('successful worker missing receipt')
        except (AssertionError, KeyError, ValueError, FileNotFoundError) as error:
            audit_errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not audit_errors)
        accepted = not failures
        rows.append(dict(unit=unit, status=receipt.get('status', 'missing_receipt'),
                         accepted=accepted, acceptance_failures=failures,
                         audit_errors=audit_errors, runtime_s=launch['elapsed_seconds'],
                         started_seeds=len(receipt.get('fits', [])), error_m=None,
                         receipt_sha256=launch.get('receipt_sha256')))
        if accepted:
            points[unit] = receipt['best']['mean'][:2]
    # Only after every available attempt has been audited, load the evaluator reference.
    helper = ROOT/'reports/2026_10_01_fixed_height_greedy/evaluate.py'
    expected = 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    assert digest(helper) == expected
    spec = importlib.util.spec_from_file_location('regression_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*points[row['unit']]), reference.REFERENCE,
            )
    errors = [r['error_m'] for r in rows if r['accepted']]
    runtimes = [r['runtime_s'] for r in rows if 'runtime_s' in r]
    result = dict(planned_count=64, finished_count=len(runtimes), accepted_count=len(errors),
                  median_error_m=float(np.median(errors)) if errors else None,
                  p90_error_m=float(np.percentile(errors, 90)) if errors else None,
                  median_runtime_s=float(np.median(runtimes)) if runtimes else None,
                  qualification='conditional errors; incomplete panels are not final results',
                  freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__), rows=rows)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
