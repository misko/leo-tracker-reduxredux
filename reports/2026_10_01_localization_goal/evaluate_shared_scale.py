"""Audit grouped residual pilots and singleton parity before geographic scoring."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'shared-scale-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    baseline_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(baseline_path) == freeze['baseline_sha256']
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    rows, states, receipts = [], {}, {}
    for unit, arm in freeze['ordered_pairs']:
        expected = dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                        iterations_per_seed=64, acquisition_limit_s=50.,
                        initializer_deadline_s=60., internal_deadline_s=85., external_limit_s=90.,
                        scale_multiplier=1., degrees_of_freedom=4., grouping=arm,
                        assignments='fixed_from_initializer', nuisance_model='nonlinear')
        path = HERE/'shared-scale-v1'/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        receipt, errors, displacement, objective_change = {}, [], None, None
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
                    signal_indices = [i for i, a in enumerate(receipt['assignments']) if a < count]
                    members = receipt['group_members']
                    assert sorted(i for g in members for i in g) == signal_indices
                    original_ids = [i for p in receipt['observations'] for i in p]
                    grouped_ids = [i for p in receipt['grouped_observations'] for i in p]
                    assert sorted(original_ids) == sorted(grouped_ids)
                    assert len(set(grouped_ids)) == len(grouped_ids)
                    if arm == 'singleton':
                        assert all(len(g) == 1 for g in members)
                    else:
                        labels = [{receipt['assignments'][i] for i in g} for g in members]
                        assert all(len(label) == 1 for label in labels)
                        assert len(set(next(iter(label)) for label in labels)) == len(labels)
                    displacement = float(1000*np.linalg.norm(
                        np.asarray(receipt['best']['mean'][:2])-np.asarray(initial['mean'][:2])))
                    if arm == 'singleton':
                        objective_change = (receipt['best']['objectives'][-1]
                                            -initial['objectives'][-1])
            except (AssertionError, KeyError, ValueError, OSError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, arm=arm, accepted=not failures, audit_errors=errors,
                         acceptance_failures=failures, runtime_s=launch['elapsed_seconds'],
                         cpu_s=receipt.get('cpu_seconds'), error_m=None,
                         receipt_sha256=launch.get('receipt_sha256'),
                         reason=(receipt.get('best') or {}).get('reason'),
                         signal_group_count=len(receipt.get('group_members', [])),
                         group_track_counts=[len(g) for g in receipt.get('group_members', [])],
                         displacement_from_initializer_m=displacement,
                         singleton_objective_change=objective_change))
        receipts[(unit, arm)] = receipt
        if not failures:
            states[(unit, arm)] = np.asarray(receipt['best']['mean'][:2])
    matching = []
    for unit in dict.fromkeys(u for u, _ in freeze['ordered_pairs']):
        a, b = receipts[(unit, 'singleton')], receipts[(unit, 'satellite')]
        matching.append(dict(unit=unit, initial_fits=a.get('initial_fits') == b.get('initial_fits'),
                             assignments=a.get('assignments') == b.get('assignments')))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('shared_scale_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[(row['unit'], row['arm'])]), reference.REFERENCE)
            row['baseline_error_m'] = baseline[row['unit']]['error_m']
    result = dict(freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
                  planned=6, accepted=sum(r['accepted'] for r in rows), rows=rows,
                  matching=matching,
                  qualification='Three exposed development scans; fixed identity groups. '
                  'Normalized shared amplitude scale, not signed coherent orbit discrepancy. '
                  'No held-out accuracy or calibrated uncertainty claim.')
    with (HERE/'shared-scale-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
