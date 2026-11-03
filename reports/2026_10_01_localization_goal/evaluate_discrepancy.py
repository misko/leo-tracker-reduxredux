"""Audit all six prespecified pilot attempts before loading the reference."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'discrepancy-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    baseline_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(baseline_path) == (
        'sha256:97be104787783e3bb81d851ba8664f3a26ac93fe10b617aae605ad8b13372bd7')
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    rows = []
    states = {}
    for unit, arm in freeze['ordered_pairs']:
        path = HERE/'discrepancy-v1'/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        receipt, errors = {}, []
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == arm
                assert receipt['config'] == dict(
                    prior_radius_km=250., height_m_msl=30.48,
                    track_slope_sigma_hz_s=0. if arm == 'zero' else .5,
                    isotropic_control=arm == 'isotropic', seed_limit=3,
                    iterations_per_seed=64, acquisition_limit_s=50.,
                    internal_deadline_s=85., external_limit_s=90.)
                for filename, expected in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == expected
                previous = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
                assert digest(previous) == baseline[unit]['receipt_sha256']
                control = json.loads(previous.read_text())
                for key in ['inputs', 'height', 'observations']:
                    assert receipt[key] == control[key]
                for filename, expected in receipt['inputs'].items():
                    assert digest(filename) == expected
            except (AssertionError, KeyError, ValueError, FileNotFoundError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        accepted = not failures
        row = dict(unit=unit, arm=arm, accepted=accepted, audit_errors=errors,
                   acceptance_failures=failures, status=receipt.get('status', 'missing'),
                   runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                   error_m=None, receipt_sha256=launch.get('receipt_sha256'))
        rows.append(row)
        if accepted:
            states[(unit, arm)] = receipt['best']['mean'][:2]
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('discrepancy_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[(row['unit'], row['arm'])]), reference.REFERENCE)
            row['change_from_frozen_baseline_m'] = row['error_m']-baseline[row['unit']]['error_m']
    summaries = {}
    for arm in ['zero', 'slope', 'isotropic']:
        selected = [r for r in rows if r['arm'] == arm]
        errors = [r['error_m'] for r in selected if r['accepted']]
        summaries[arm] = dict(planned=2, accepted=len(errors),
                              median_error_m=float(np.median(errors)) if errors else None,
                              median_runtime_s=float(np.median([r['runtime_s'] for r in selected])))
    result = dict(freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
                  qualification='Two-scan development pilots only; no generalization claim.',
                  summaries=summaries, rows=rows)
    output = HERE/'discrepancy-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
