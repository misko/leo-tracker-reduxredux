"""Audit held-out uncertainty construction without loading geographic truth."""
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    frozen_path = HERE/'heldout-uncertainty-v1-freeze.json'
    assert digest(frozen_path) == frozen_path.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(frozen_path.read_text())
    verify_sources(frozen['source_sha256'])
    threshold_path = HERE/'uncertainty-thresholds-v1-freeze.json'
    assert digest(threshold_path) == frozen['threshold_freeze_sha256']
    rules = json.loads(threshold_path.read_text())['thresholds']
    assert digest(HERE/'uncertainty-shape-adapter-validation.json') == frozen[
        'adapter_validation_sha256']
    batch = json.loads((HERE/'heldout-uncertainty-v1/batch.json').read_text())
    assert batch['freeze_sha256'] == digest(frozen_path)
    assert [r['unit_id'] for r in batch['launches']] == frozen['ordered_units']
    rows = []
    for launch in batch['launches']:
        unit = launch['unit_id']
        path = HERE/'heldout-uncertainty-v1'/(unit+'.json')
        receipt, errors = {}, []
        try:
            assert launch['freeze_sha256'] == digest(frozen_path)
            assert launch['returncode'] == 0 and not launch['timed_out']
            assert launch['within_budget'] and launch['elapsed_seconds'] <= 30.
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['status'] == 'shapes_prepared'
            assert receipt['error_m'] is None and receipt['geographic_coverage'] is None
            assert receipt['threshold_freeze_sha256'] == digest(threshold_path)
            for filename, value in receipt['source_sha256'].items():
                assert frozen['source_sha256'][filename] == value
            parents = list((HERE/'heldout-baseline-v1').glob('batch-*/'+unit+'.json'))
            assert len(parents) == 1 and digest(parents[0]) == receipt['parent_sha256']
            parent = json.loads(parents[0].read_text())
            parent_launch = json.loads(parents[0].with_suffix('.launch.json').read_text())
            assert parent_launch['freeze_sha256'] == frozen['baseline_freeze_sha256']
            assert parent_launch['receipt_sha256'] == digest(parents[0])
            assert not qualification(parent, parent_launch, True)
            assert parent['best']['mean'][:2] == receipt['position_km']
            for key in ['inputs', 'height']:
                assert receipt[key] == parent[key]
            assert set(receipt['arms']) == set(rules)
            for arm, result in receipt['arms'].items():
                matrix = np.asarray(result['matrix_km2'])
                assert matrix.shape == (2, 2) and np.all(np.isfinite(matrix))
                np.linalg.cholesky(matrix)
                assert set(result['ellipse_minor_major_axes_m']) == set(rules[arm])
                for p, rule in rules[arm].items():
                    axes = 1000*np.sqrt(rule['squared_distance_cutoff']*np.linalg.eigvalsh(matrix))
                    np.testing.assert_allclose(result['ellipse_minor_major_axes_m'][p], axes,
                                               rtol=1e-12, atol=1e-9)
        except (AssertionError, KeyError, ValueError, OSError, np.linalg.LinAlgError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, valid=not errors, audit_errors=errors,
                         diagnostic_runtime_s=launch['elapsed_seconds'],
                         diagnostic_cpu_s=receipt.get('cpu_seconds'),
                         geographic_error_m=None, geographic_coverage=None,
                         major95_m={a: r['ellipse_minor_major_axes_m']['0.95'][1]
                                    for a, r in receipt.get('arms', {}).items()},
                         receipt_sha256=launch.get('receipt_sha256')))
    valid = [r for r in rows if r['valid']]
    result = dict(
        planned=16, valid=len(valid), failed=16-len(valid),
        median_diagnostic_runtime_s=float(np.median([r['diagnostic_runtime_s'] for r in rows])),
        maximum_diagnostic_runtime_s=max(r['diagnostic_runtime_s'] for r in rows),
        median_diagnostic_cpu_s=float(np.median([r['diagnostic_cpu_s'] for r in valid])),
        median_major95_m={arm: float(np.median([r['major95_m'][arm] for r in valid]))
                          for arm in rules},
        freeze_sha256=digest(frozen_path), evaluator_sha256=digest(__file__),
        geographic_error_m=None, geographic_coverage=None,
        qualification='Reference-blind held-out shape and threshold application audit. '
        'Development-derived empirical95 cutoffs are unvalidated on DS12. No GPS read, no point '
        'changes, no accuracy or coverage claim. Diagnostic CPU/runtime separate from inference.',
        rows=rows)
    with (HERE/'heldout-uncertainty-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
