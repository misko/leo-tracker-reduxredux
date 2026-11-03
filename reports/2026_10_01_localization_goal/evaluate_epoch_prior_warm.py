"""Audit conditional timing-prior ablations before loading reference coordinates."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'epoch-prior-warm-v1'
    freeze_path = directory/'sources.json'
    frozen = json.loads(freeze_path.read_text())
    verify_sources(frozen['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    rows, states = [], {}
    for unit, arm in frozen['ordered_pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, parent = [], {}, {}
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30.
            assert launch['source_freeze_sha256'] == digest(freeze_path)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['source_freeze_sha256'] == digest(freeze_path)
            assert receipt['unit'] == unit and receipt['arm'] == arm
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == frozen['parent_sha256'][unit] == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            for key in ['inputs', 'height', 'observations']:
                assert receipt[key] == parent[key]
            verify_sources(receipt['inputs'])
            assert receipt['converged'] and np.all(np.isfinite(receipt['mean']))
            assert np.linalg.norm(receipt['mean'][:2]) <= 250.
            assert receipt['variance_s2'] == .25
            count = len(parent['best']['mean'])-5
            labels = sorted({i for i in receipt['assignments'] if i < count})
            assert receipt['labels'] == labels
            assert len(receipt['assignments']) == len(receipt['observations'])
            expected_factors = [['prior:satellite-epoch:'+str(i)] for i in labels]
            assert receipt['prior_factors'] == (expected_factors if arm == 'student' else [])
            np.testing.assert_allclose(receipt['initial_epoch_s'],
                                       np.asarray(parent['best']['mean'])[5+np.asarray(labels)])
            assert np.max(np.diff(receipt['objectives'])) <= 1e-6
            if arm == 'gaussian':
                assert receipt['position_shift_m'] < .1
                assert abs(receipt['objectives'][-1]-receipt['initial_objective']) < 1e-6
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
                         error_m=None, original_error_m=None,
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         position_shift_m=receipt.get('position_shift_m'),
                         largest_initial_epoch_s=max(map(abs, receipt.get('initial_epoch_s', [0]))),
                         largest_final_epoch_s=max(map(abs, receipt.get('final_epoch_s', [0])))))
        if not errors:
            states[(unit, arm)] = (receipt['mean'][:2], parent['best']['mean'][:2])
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('epoch_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            position, original_position = states[(row['unit'], row['arm'])]
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*position), reference.REFERENCE)
            row['original_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*original_position), reference.REFERENCE)
    result = dict(
        planned=6, valid=sum(r['valid'] for r in rows), rows=rows,
        source_freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
        qualification='Three reference-exposed development pilots with Gaussian parity controls. '
        'Warm fixed-identity ablation, not cold90s or held-out performance. Same timing prior '
        'variance; Student-t has heavier tails and stronger central shrinkage. No cross-arm '
        'objective-based model selection. No calibrated uncertainty claim.')
    output = HERE/'epoch-prior-warm-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
