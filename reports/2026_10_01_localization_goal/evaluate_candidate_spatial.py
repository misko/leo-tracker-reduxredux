"""Audit composite spatial optima before reading the geographic reference."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_spatial_adapter import CandidateSpatialObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'candidate-spatial-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit, arm in frozen['pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, decrement = [], {}, None
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30.
            assert launch['freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['arm'] == arm
            for filename, expected in receipt['sources'].items():
                assert frozen['source_sha256'][filename] == expected
            model = CandidateSpatialObjective(unit)
            assert receipt['parent_sha256'] == digest(model.parent_path)
            assert receipt['inputs'] == model.parent['inputs']
            assert receipt['height'] == model.parent['height']
            assert receipt['assignments'] == model.assignments
            verify_sources(receipt['inputs'])
            point = np.asarray(receipt['point'])
            assert receipt['converged'] and np.linalg.norm(point) <= 250.
            weight = float(arm == 'candidate')

            def objective(x, model=model, weight=weight):
                train, extra = model.components(x)
                return train-weight*extra

            value = objective(point)
            assert abs(value-receipt['objectives'][-1]) < 1e-7
            h, basis = .01, np.eye(2)*.01
            plus = np.array([objective(point+b) for b in basis])
            minus = np.array([objective(point-b) for b in basis])
            gradient = (plus-minus)/(2*h)
            hessian = np.diag((plus+minus-2*value)/h**2)
            corners = [objective(point+a*basis[0]+b*basis[1])
                       for a, b in [(1, 1), (1, -1), (-1, 1), (-1, -1)]]
            hessian[0, 1] = hessian[1, 0] = (
                corners[0]-corners[1]-corners[2]+corners[3])/(4*h*h)
            assert np.linalg.eigvalsh(hessian).min() > 0
            decrement = float(gradient@np.linalg.solve(hessian, gradient))
            assert decrement < 1e-5
            if arm == 'control':
                assert receipt['position_change_m'] < .1
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
                         decrement_squared=decrement, initial=receipt.get('initial_point'),
                         point=receipt.get('point'), runtime_s=launch['elapsed_seconds'],
                         cpu_s=receipt.get('cpu_s'), baseline_error_m=None, error_m=None,
                         position_change_m=receipt.get('position_change_m')))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('candidate_spatial_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*row['initial']), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*row['point']), reference.REFERENCE)
    result = dict(planned=6, valid=sum(r['valid'] for r in rows), rows=rows,
                  source_freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
                  qualification='Warm fixed-nuisance spatial pilot. Former checking evidence is '
                  'now fitted data, not validation. Controls use same training-only parents. '
                  'No cold90s, full64, independent recording or uncertainty calibration claim.')
    output = HERE/'candidate-spatial-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
