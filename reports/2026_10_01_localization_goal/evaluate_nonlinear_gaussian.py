"""Audit nonlinear controls and matched initializations before reference scoring."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'nonlinear-gaussian-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    linear_path = HERE/'marginal-position-v1-evaluation.json'
    assert digest(linear_path) == freeze['linear_comparison_sha256']
    linear = {r['unit']: r for r in json.loads(linear_path.read_text())['rows']
              if r['arm'] == 'profile'}
    linear_freeze = HERE/'marginal-position-v1-freeze.json'
    assert digest(linear_freeze) == linear_freeze.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(linear_freeze.read_text())['source_sha256'])
    expected_config = dict(
        prior_radius_km=250., height_m_msl=30.48, seed_limit=3, iterations_per_seed=64,
        acquisition_limit_s=50., initializer_deadline_s=60., internal_deadline_s=85.,
        external_limit_s=90., gaussian_covariance_scale=2.,
        assignments='fixed_from_initializer', nuisance_model='nonlinear')
    rows, states = [], {}
    for unit in freeze['ordered_units']:
        path = HERE/'nonlinear-gaussian-v1'/(unit+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        receipt, errors, match = {}, [], {}
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == 'nonlinear_gaussian'
                assert receipt['config'] == expected_config
                for filename, expected in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == expected
                previous = HERE/'marginal-position-v1'/(unit+'-profile.json')
                assert digest(previous) == linear[unit]['receipt_sha256']
                control = json.loads(previous.read_text())
                for key in ['inputs', 'height', 'observations']:
                    assert receipt[key] == control[key]
                for filename, expected in receipt['inputs'].items():
                    assert digest(filename) == expected
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
        rows.append(dict(unit=unit, accepted=not failures, audit_errors=errors,
                         acceptance_failures=failures, matched_control=match,
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         error_m=None, receipt_sha256=launch.get('receipt_sha256'),
                         reason=(receipt.get('best') or {}).get('reason')))
        if not failures:
            states[unit] = np.asarray(receipt['best']['mean'][:2])
            rows[-1]['position_displacement_from_linear_m'] = float(
                1000*np.linalg.norm(states[unit]-np.asarray(control['best']['mean'][:2])))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('nonlinear_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[row['unit']]), reference.REFERENCE)
            row['linear_profile_error_m'] = linear[row['unit']]['error_m']
    result = dict(freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
                  planned=3, accepted=sum(r['accepted'] for r in rows), rows=rows,
                  qualification='Three exposed development scans. Full nonlinear signal fit with '
                  'Gaussian2C noise, fixed identities and original priors. No held-out accuracy '
                  'or uncertainty calibration claim.')
    with (HERE/'nonlinear-gaussian-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
