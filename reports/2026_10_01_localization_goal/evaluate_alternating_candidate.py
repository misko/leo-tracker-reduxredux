"""Audit alternating search receipts and independent stationarity before geography."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_reassociation_joint import CandidateJointObjective
from diagnose_candidate_reassociation import training_information
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'alternating-candidate-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit, arm in frozen['pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, discrepancy = [], {}, None
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30
            assert launch['freeze_sha256'] == digest(freeze)
            assert launch['receipt_sha256'] == digest(path)
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['arm'] == arm
            assert receipt['converged'], receipt['reason']
            assert receipt['seconds'] < 30
            for name, expected in receipt['sources'].items():
                assert frozen['source_sha256'][name] == expected
            verify_sources(receipt['inputs'])
            parent_path = HERE/'candidate-joint-expansion-v1'/(unit+'-candidate.json')
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            assert receipt['height'] == parent['height']
            assert receipt['inputs'] == parent['inputs']
            assignments = receipt['assignments']
            state = np.asarray(receipt['full_state'])
            clean, prior_gain = profile_unused_epochs(state, assignments, len(state)-5)
            assert prior_gain == 0 and np.array_equal(clean, state)
            assert np.linalg.norm(state[:2]) <= 250
            model = CandidateJointObjective(unit, state=receipt['metric_state'],
                                            assignments=assignments)
            assert model.columns.tolist() == receipt['columns']
            metric = training_information(model)
            assert np.allclose(metric, receipt['metric'], atol=1e-10, rtol=1e-10)
            point = state[model.columns]
            value, gradient = model.evaluate(point)
            assert abs(value-receipt['final_objective']) < 1e-7
            assert np.all(np.diff(receipt['history']) <= 1e-7)
            assert abs(value-receipt['history'][-1]) < 1e-7
            for fit in receipt['fits']:
                assert fit['converged'] and np.all(np.diff(fit['objectives']) <= 1e-7)
            assert all(abs(p['discrepancy']) < 1e-7 for p in receipt['profiles'])
            assert gradient@np.linalg.solve(metric, gradient) <= 1e-6
            finite = []
            for direction in np.eye(len(point))*.0005:
                a = model.evaluate(point+direction, gradient=False)[0]
                b = model.evaluate(point-direction, gradient=False)[0]
                finite.append((a-b)/.001)
            finite = np.asarray(finite)
            discrepancy = float(np.max(np.abs(finite-gradient)))
            assert discrepancy < .005 and finite@np.linalg.solve(metric, finite) < 1e-5
            if arm == 'control':
                assert assignments == parent['assignments']
                assert np.linalg.norm(state[:2]-np.asarray(parent['mean'][:2]))*1000 < .1
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
            reason=receipt.get('reason'), state=receipt.get('full_state'),
            initial=receipt.get('initial_full_state'), runtime_s=launch['elapsed_seconds'],
            cpu_s=receipt.get('cpu_s'), gradient_discrepancy=discrepancy,
            fit_rounds=len(receipt.get('fits', [])), trials=len(receipt.get('trials', [])),
            error_m=None, parent_error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('alternating_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            for key, point in [('error_m', row['state']), ('parent_error_m', row['initial'])]:
                row[key] = reference.distance_m(
                    reference.latlon_from_enu(*point[:2]), reference.REFERENCE)
        del row['state'], row['initial']
    result = dict(rows=rows, planned=len(rows), valid=sum(r['valid'] for r in rows),
        freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
        qualification='Warm four-scan development diagnostic; exact unused epoch profiling. '
        'No-improvement means only tested training-best single swaps, not all catalogue '
        'assignments. Failures retained; no cold64, independent validation or calibration claim.')
    output = HERE/'alternating-candidate-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
