"""Audit composite spatial optima before reading the geographic reference."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_spatial_expansion_adapter import CandidateSpatialObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'candidate-spatial-expansion-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    # Unlike the pilot, this expansion binds lazy third-party imports beforehand.
    numpy_ma = HERE.parents[1]/'.venv/lib/python3.12/site-packages/numpy/ma'
    dependency_hashes = dict(
        core='sha256:f7a05895d83965d6f48f9f858f59f7793c30e1ebcc98ce5a88f80de7a484c828',
        extras='sha256:ffe5314b5364a723057ecf51d1da2ee21e0473eec10a982e03bf6bef70539417',
        __init__='sha256:5e90d6617c1ab83738f7e20db24e39e43d37530e29eb115db1d58e9f6aedf3b5')
    supplemental = {str(numpy_ma/(name+'.py')): value
                    for name, value in dependency_hashes.items()}
    verify_sources(supplemental)
    assert all(frozen['source_sha256'][p] == v for p, v in supplemental.items())
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
                known = frozen['source_sha256'][filename]
                assert known == expected
            assert all(receipt['sources'].get(p) == v for p, v in supplemental.items())
            model = CandidateSpatialObjective(unit)
            assert receipt['parent_sha256'] == digest(model.parent_path)
            assert receipt['inputs'] == model.parent['inputs']
            assert receipt['height'] == model.parent['height']
            assert receipt['assignments'] == model.assignments
            assert receipt['initial_point'] == model.initial[:2].tolist()
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
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+row['unit']+'.json'))
        parent_seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
        assert digest(parent_path) == parent_seal['prediction_sha256']
        parent = json.loads(parent_path.read_text())
        row['all_data_baseline_error_m'] = reference.distance_m(
            reference.latlon_from_enu(*parent['best']['mean'][:2]), reference.REFERENCE)
        if row['valid']:
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*row['initial']), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*row['point']), reference.REFERENCE)
    candidates = [r for r in rows if r['arm'] == 'candidate']
    valid = [r for r in candidates if r['valid']]
    summary = {}
    for label, field, subset in [('candidate', 'error_m', valid),
                                  ('split_training', 'baseline_error_m', valid),
                                  ('all_data_baseline', 'all_data_baseline_error_m', candidates)]:
        values = [r[field] for r in subset]
        summary[label+'_median_error_m'] = float(np.median(values)) if values else None
        summary[label+'_p90_error_m'] = float(np.percentile(values, 90)) if values else None
    result = dict(planned=24, valid=sum(r['valid'] for r in rows), rows=rows, **summary,
                  candidate_valid_of_12=len(valid),
                  candidate_improved_over_split_training=sum(
                      r['error_m'] < r['baseline_error_m'] for r in valid),
                  candidate_within_1000m_of_12=sum(r['error_m'] <= 1000 for r in valid),
                  candidate_within_3000m_of_12=sum(r['error_m'] <= 3000 for r in valid),
                  prebound_audited_dependencies=supplemental,
                  source_freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
                  qualification='Warm fixed-nuisance spatial pilot. Former checking evidence is '
                  'now fitted data, not validation. Controls use same training-only parents. '
                  'No cold90s, full64, independent recording or uncertainty calibration claim. '
                  'All project and NumPy masked-array sources bound before this expansion. '
                  'Failures retained in denominators; candidate/split quantiles conditional '
                  'on candidate acceptance.')
    output = HERE/'candidate-spatial-expansion-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
