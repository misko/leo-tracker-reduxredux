"""Audit sealed reassociation fits before admitting geographic diagnostics."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_reassociation_joint import CandidateJointObjective
from diagnose_candidate_reassociation import training_information
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'candidate-reassociation-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    audit_path = HERE/'candidate-reassociation-audit-v1.json'
    audit = json.loads(audit_path.read_text())
    audits = {r['unit']: r for r in audit['rows']}
    rows = []
    for unit, arm in frozen['pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt = [], {}
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30
            assert launch['freeze_sha256'] == digest(freeze)
            assert launch['receipt_sha256'] == digest(path)
            assert path.with_suffix('.sha256').read_text().strip() == digest(path)
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['arm'] == arm
            assert receipt['converged'], receipt['reason']
            assert receipt['reassociation_audit_sha256'] == digest(audit_path)
            for filename, expected in receipt['sources'].items():
                assert frozen['source_sha256'][filename] == expected
            verify_sources(receipt['inputs'])
            parent_path = HERE/'candidate-joint-expansion-v1'/(unit+'-candidate.json')
            assert digest(parent_path) == receipt['joint_parent_sha256']
            parent = json.loads(parent_path.read_text())
            proposal = max(audits[unit]['proposals'], key=lambda p: p['joint_objective_gain'])
            assert proposal == receipt['proposal'] and proposal['joint_objective_gain'] > 0
            assignments = parent['assignments'].copy()
            if arm == 'candidate':
                assignments[proposal['track_index']] = proposal['best_index']
            assert assignments == receipt['assignments']
            state = np.asarray(receipt['inherited_full_state'])
            assert np.array_equal(state[parent['columns']], parent['mean'])
            model = CandidateJointObjective(unit, state=state, assignments=assignments)
            assert receipt['height'] == model.base.parent['height']
            assert receipt['inputs'] == model.base.parent['inputs']
            assert model.columns.tolist() == receipt['columns']
            assert model.initial.tolist() == receipt['initial']
            metric = training_information(model)
            assert np.allclose(metric, receipt['information'], atol=1e-10, rtol=1e-10)
            point = np.asarray(receipt['mean'])
            assert np.all(np.isfinite(point)) and np.linalg.norm(point[:2]) <= 250
            value, gradient = model.evaluate(point)
            assert abs(value-receipt['final_objective']) < 1e-7
            assert np.all(np.diff(receipt['objectives']) <= 1e-9)
            assert value <= parent['final_objective']+1e-7
            assert gradient@np.linalg.solve(metric, gradient) <= 1e-6
            finite = []
            for direction in np.eye(len(point))*.0005:
                a = model.evaluate(point+direction, gradient=False)[0]
                b = model.evaluate(point-direction, gradient=False)[0]
                finite.append((a-b)/.001)
            finite = np.asarray(finite)
            assert np.max(np.abs(finite-gradient)) < .005
            assert finite@np.linalg.solve(metric, finite) < 1e-5
            if arm == 'control':
                assert receipt['position_change_m'] < .1
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
            mean=receipt.get('mean'), initial=receipt.get('initial'),
            runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_s'),
            final_objective=receipt.get('final_objective'),
            parent_objective=receipt.get('parent_joint_objective'),
            error_m=None, parent_error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('reassociation_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            for key, position in [('error_m', row['mean']), ('parent_error_m', row['initial'])]:
                row[key] = reference.distance_m(
                    reference.latlon_from_enu(*position[:2]), reference.REFERENCE)
    result = dict(rows=rows, planned=len(rows), valid=sum(r['valid'] for r in rows),
        freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
        qualification='Four development scans selected by positive full-objective swap gain, '
        'without GPS. One swap per scan; warm conditional fitting with unused epochs fixed. '
        'No full-panel, cold-runtime, held-out or uncertainty-calibration claim.')
    output = HERE/'candidate-reassociation-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
