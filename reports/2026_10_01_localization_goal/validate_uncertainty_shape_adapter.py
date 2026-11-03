"""Replay three original controls against separately sealed shape calculations."""
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources
from uncertainty_shape_adapter import build_shapes

HERE = Path(__file__).resolve().parent


def main():
    frozen = HERE/'regression-v1-freeze.json'
    assert digest(frozen) == frozen.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(frozen.read_text())['source_sha256'])
    prepared_path = HERE/'deletion-spread-v1-predictions.json'
    assert digest(prepared_path) == prepared_path.with_suffix('.sha256').read_text().strip()
    prepared = {r['unit']: r for r in json.loads(prepared_path.read_text())['rows']}
    rows = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(parent_path) == prepared[unit]['parent_sha256']
        parent = json.loads(parent_path.read_text())
        scan, height, ports = prepare(unit)
        assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
        assert [list(p.observation_ids) for p in ports] == parent['observations']
        matrices, labels, shifts = build_shapes(ports, np.asarray(parent['best']['mean']))
        largest = 0.
        for arm, matrix in matrices.items():
            expected = np.asarray(prepared[unit]['matrices_km2'][arm])
            np.testing.assert_allclose(matrix, expected, rtol=1e-10, atol=1e-12)
            largest = max(largest, float(np.max(np.abs(matrix-expected))))
        influence_path = HERE/'group-influence-v1'/(unit+'.json')
        assert digest(influence_path) == prepared[unit]['influence_sha256']
        groups = json.loads(influence_path.read_text())['groups']
        assert labels == [g['candidate_index'] for g in groups]
        np.testing.assert_allclose(shifts, [g['position_step_km'] for g in groups],
                                   rtol=1e-10, atol=1e-12)
        rows.append(dict(unit=unit, maximum_matrix_difference_km2=largest,
                         parent_sha256=digest(parent_path)))
    result = dict(rows=rows, all_passed=True, source_sha256=digest(__file__),
                  adapter_sha256=digest(HERE/'uncertainty_shape_adapter.py'),
                  reference_loaded=False)
    with (HERE/'uncertainty-shape-adapter-validation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
