"""Verify residual-family controls before opening the geographic reference."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'residual-factorial-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    previous_path = HERE/'nonlinear-gaussian-v1-evaluation.json'
    assert digest(previous_path) == freeze['nonlinear_comparison_sha256']
    previous = {r['unit']: r for r in json.loads(previous_path.read_text())['rows']}
    baseline_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(baseline_path) == freeze['baseline_sha256']
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    rows, states = [], {}
    for unit, arm in freeze['ordered_pairs']:
        family, scale, degrees = (
            ('student', 2., 4.) if arm == 'student2' else ('gaussian', 1., None))
        expected = dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                        iterations_per_seed=64, acquisition_limit_s=50.,
                        initializer_deadline_s=60., internal_deadline_s=85., external_limit_s=90.,
                        scale_multiplier=scale, residual_family=family, degrees_of_freedom=degrees,
                        assignments='fixed_from_initializer', nuisance_model='nonlinear')
        path = HERE/'residual-factorial-v1'/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        receipt, errors, match = {}, [], {}
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == arm
                assert receipt['config'] == expected
                for filename, value in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == value
                control_path = HERE/'nonlinear-gaussian-v1'/(unit+'.json')
                assert digest(control_path) == previous[unit]['receipt_sha256']
                control = json.loads(control_path.read_text())
                for key in ['inputs', 'height', 'observations']:
                    assert receipt[key] == control[key]
                for filename, value in receipt['inputs'].items():
                    assert digest(filename) == value
                match = dict(initial_fits=receipt['initial_fits'] == control['initial_fits'],
                             assignments=receipt.get('assignments') == control['assignments'],
                             acquisition_seeds=receipt['proposal']['seeds'] ==
                             control['proposal']['seeds'])
                if receipt.get('best'):
                    initial = min((f for f in receipt['initial_fits'] if f['objectives']),
                                  key=lambda f: f['objectives'][-1])
                    assert initial['converged']
                    assert receipt['initializer_seed'] == initial['seed_index']
            except (AssertionError, KeyError, ValueError, OSError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, arm=arm, accepted=not failures, audit_errors=errors,
                         acceptance_failures=failures, matched_control=match,
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         error_m=None, receipt_sha256=launch.get('receipt_sha256'),
                         reason=(receipt.get('best') or {}).get('reason')))
        if not failures:
            states[(unit, arm)] = np.asarray(receipt['best']['mean'][:2])
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('factorial_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[(row['unit'], row['arm'])]), reference.REFERENCE)
    table = []
    for unit in dict.fromkeys(u for u, _ in freeze['ordered_pairs']):
        selected = {r['arm']: r for r in rows if r['unit'] == unit}
        table.append(dict(unit=unit, student1_error_m=baseline[unit]['error_m'],
                          student2_error_m=selected['student2']['error_m'],
                          gaussian1_error_m=selected['gaussian1']['error_m'],
                          gaussian2_error_m=previous[unit]['error_m']))
    result = dict(freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
                  planned=6, accepted=sum(r['accepted'] for r in rows), rows=rows, table=table,
                  qualification='Three exposed development scans; fixed identities. C is the '
                  'Student-t scale, not its covariance. Existing robustC and Gaussian2C controls '
                  'are included alongside new runs. No held-out accuracy or uncertainty claim.')
    with (HERE/'residual-factorial-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
