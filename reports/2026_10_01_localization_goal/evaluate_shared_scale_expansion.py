"""Audit the exact12-scan shared-scale expansion before reference scoring."""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze_path = HERE/'shared-scale-expansion-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    selection = HERE/'student-scale-expansion-v1-freeze.json'
    assert digest(selection) == freeze['selection_sha256']
    assert json.loads(selection.read_text())['ordered_units'] == freeze['ordered_units']
    baseline_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(baseline_path) == freeze['baseline_sha256']
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    expected = dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                    iterations_per_seed=64, acquisition_limit_s=50.,
                    initializer_deadline_s=60., internal_deadline_s=85., external_limit_s=90.,
                    scale_multiplier=1., degrees_of_freedom=4., grouping='satellite',
                    assignments='fixed_from_initializer', nuisance_model='nonlinear')
    rows, states = [], {}
    for unit in freeze['ordered_units']:
        paths = list((HERE/'shared-scale-expansion-v1').glob('batch-*/'+unit+'.launch.json'))
        if not paths:
            rows.append(dict(unit=unit, accepted=False, status='not_finished', error_m=None))
            continue
        assert len(paths) == 1
        launch = json.loads(paths[0].read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        path = paths[0].with_name(unit+'.json')
        receipt, errors = {}, []
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == 'satellite'
                assert receipt['config'] == expected
                for filename, value in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == value
                controls = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
                assert len(controls) == 1
                assert digest(controls[0]) == baseline[unit]['receipt_sha256']
                control = json.loads(controls[0].read_text())
                for key in ['inputs', 'height', 'observations']:
                    assert receipt[key] == control[key]
                for filename, value in receipt['inputs'].items():
                    assert digest(filename) == value
                if receipt.get('best'):
                    initial = min((f for f in receipt['initial_fits'] if f['objectives']),
                                  key=lambda f: f['objectives'][-1])
                    assert initial['converged']
                    assert receipt['initializer_seed'] == initial['seed_index']
                    assert initial['mean'] == control['best']['mean']
                    count = len(initial['mean'])-5
                    signal = [i for i, a in enumerate(receipt['assignments']) if a < count]
                    members = receipt['group_members']
                    assert sorted(i for g in members for i in g) == signal
                    original_ids = [i for p in receipt['observations'] for i in p]
                    grouped_ids = [i for p in receipt['grouped_observations'] for i in p]
                    assert sorted(original_ids) == sorted(grouped_ids)
                    assert len(set(grouped_ids)) == len(grouped_ids)
                    labels = [{receipt['assignments'][i] for i in g} for g in members]
                    assert all(len(label) == 1 for label in labels)
                    assert len(set(next(iter(label)) for label in labels)) == len(labels)
            except (AssertionError, KeyError, ValueError, OSError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, accepted=not failures, audit_errors=errors,
                         acceptance_failures=failures, status=receipt.get('status', 'missing'),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         error_m=None, receipt_sha256=launch.get('receipt_sha256'),
                         reason=(receipt.get('best') or {}).get('reason'),
                         group_count=len(receipt.get('group_members', []))))
        if not failures:
            states[unit] = np.asarray(receipt['best']['mean'][:2])
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('shared_expansion_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[row['unit']]), reference.REFERENCE)
            row['baseline_error_m'] = baseline[row['unit']]['error_m']
            row['change_m'] = row['error_m']-row['baseline_error_m']
    accepted = [r for r in rows if r['accepted']]
    times = [r['runtime_s'] for r in rows if 'runtime_s' in r]
    errors = [r['error_m'] for r in accepted]
    old_errors = [r['baseline_error_m'] for r in accepted]
    result = dict(
        freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
        planned=len(rows), finished=len(times), accepted=len(accepted),
        improved=sum(r['change_m'] < 0 for r in accepted),
        within_1000_m=sum(e <= 1000 for e in errors), within_3000_m=sum(e <= 3000 for e in errors),
        median_error_m=float(np.median(errors)) if errors else None,
        p90_error_m=float(np.percentile(errors, 90)) if errors else None,
        paired_baseline_median_error_m=float(np.median(old_errors)) if old_errors else None,
        paired_baseline_p90_error_m=float(np.percentile(old_errors, 90)) if old_errors else None,
        median_change_m=float(np.median([r['change_m'] for r in accepted])) if accepted else None,
        median_runtime_s=float(np.median(times)) if times else None,
        maximum_runtime_s=max(times) if times else None,
        qualification='Same12 additional scans as the scale expansion, no replacements. '
        'Error quantiles conditional on acceptance; threshold counts retain all12 denominator. '
        'No held-out accuracy or calibrated uncertainty claim.', rows=rows)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
