"""Audit joint optima and independent scalar finite differences before geography."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_calibrated_joint import CandidateJointObjective
from diagnose_calibrated_joint import training_information
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'calibrated-joint-expansion-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit, arm in frozen['pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, numeric_decrement, gradient_error = [], {}, None, None
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30.
            assert launch['freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            for filename, expected in receipt['sources'].items():
                assert frozen['source_sha256'][filename] == expected
            assert receipt['unit'] == unit and receipt['arm'] == arm
            model = CandidateJointObjective(unit)
            assert receipt['parent_sha256'] == digest(model.base.parent_path)
            assert receipt['inputs'] == model.base.parent['inputs']
            assert receipt['height'] == model.base.parent['height']
            assert receipt['columns'] == model.columns.tolist()
            assert receipt['initial'] == model.initial.tolist()
            assert receipt['assignments'] == model.base.assignments
            verify_sources(receipt['inputs'])
            assert receipt['converged'], receipt['reason']
            mean = np.asarray(receipt['mean'])
            assert np.all(np.isfinite(mean)) and np.linalg.norm(mean[:2]) <= 250.
            information = training_information(model)
            assert np.allclose(information, receipt['information'], atol=1e-10, rtol=1e-10)
            weight = float(arm == 'candidate')
            value, gradient = model.evaluate(mean, candidate_weight=weight)
            assert abs(value-receipt['final_objective']) < 1e-7
            assert abs(value-receipt['objectives'][-1]) < 1e-7
            assert np.all(np.diff(receipt['objectives']) <= 1e-9)
            decrement = float(gradient@np.linalg.solve(information, gradient))
            assert decrement <= 1e-6
            finite = []
            for direction in np.eye(len(mean))*.0005:
                a = model.evaluate(mean+direction, gradient=False, candidate_weight=weight)[0]
                b = model.evaluate(mean-direction, gradient=False, candidate_weight=weight)[0]
                finite.append((a-b)/.001)
            finite = np.asarray(finite)
            gradient_error = float(np.max(np.abs(finite-gradient)))
            numeric_decrement = float(finite@np.linalg.solve(information, finite))
            assert gradient_error < .005 and numeric_decrement < 1e-5
            if arm == 'control':
                assert receipt['position_change_m'] < .1
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
                         numeric_decrement_squared=numeric_decrement,
                         maximum_gradient_error=gradient_error, initial=receipt.get('initial'),
                         mean=receipt.get('mean'), reason=receipt.get('reason'),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_s'),
                         baseline_error_m=None, error_m=None,
                         position_change_m=receipt.get('position_change_m')))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('joint_reference', helper)
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
                reference.latlon_from_enu(*row['initial'][:2]), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*row['mean'][:2]), reference.REFERENCE)
    spatial_path = HERE/'candidate-spatial-expansion-v1-evaluation.json'
    assert digest(spatial_path) == spatial_path.with_suffix('.sha256').read_text().strip()
    spatial = {r['unit']: r for r in json.loads(spatial_path.read_text())['rows']
               if r['arm'] == 'candidate' and r['valid']}
    candidates = [r for r in rows if r['arm'] == 'candidate']
    valid = [r for r in candidates if r['valid']]
    common = [r for r in valid if r['unit'] in spatial]
    comparisons = {}
    for label, values in [
        ('original_all_data', [r['all_data_baseline_error_m'] for r in common]),
        ('split_training', [r['baseline_error_m'] for r in common]),
        ('spatial_candidate', [spatial[r['unit']]['error_m'] for r in common]),
        ('joint_candidate', [r['error_m'] for r in common]),
    ]:
        comparisons[label] = dict(median_error_m=float(np.median(values)) if values else None,
            p90_error_m=float(np.percentile(values, 90)) if values else None)
    result = dict(planned=18, valid=sum(r['valid'] for r in rows), rows=rows,
                  candidate_valid_of_9=len(valid),
                  candidate_median_error_m=float(np.median(
                      [r['error_m'] for r in valid])) if valid else None,
                  candidate_p90_error_m=float(np.percentile(
                      [r['error_m'] for r in valid], 90)) if valid else None,
                  candidate_within_1000m_of_9=sum(r['error_m'] <= 1000 for r in valid),
                  candidate_within_3000m_of_9=sum(r['error_m'] <= 3000 for r in valid),
                  candidate_improved_over_split=sum(
                      r['error_m'] < r['baseline_error_m'] for r in valid),
                  matched_comparison_units=[r['unit'] for r in common],
                  matched_comparisons=comparisons,
                  spatial_evaluation_sha256=digest(spatial_path),
                  freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
                  qualification='Warm joint pilot, fixed identities, original nuisance priors. '
                  'Former checking data now fitted; no cold90s or independent-recording claim. '
                  'Stationarity verified in fixed training metric by complete scalar finite '
                  'differences, not proof of global optimum or positive observed curvature. '
                  'Failures retained in denominators; quantiles conditional on acceptance. '
                  'Four-way comparisons use identical units accepted by both candidate models.')
    output = HERE/'calibrated-joint-expansion-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
