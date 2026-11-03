"""Seal three diagnostic ellipse shapes before reading the geographic reference."""
import json
import time
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

from leo.analysis.localization_deletion_spread import deletion_spread

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    for directory in ['group-influence-v1', 'curvature-v1']:
        verify_sources(json.loads((HERE/directory/'sources.json').read_text()))
    rows = []
    for unit in freeze['ordered_units']:
        influence_path = HERE/'group-influence-v1'/(unit+'.json')
        curvature_path = HERE/'curvature-v1'/(unit+'.json')
        values = []
        for path in [influence_path, curvature_path]:
            launch = json.loads(path.with_suffix('.launch.json').read_text())
            assert launch['returncode'] == 0 and not launch['timed_out']
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            values.append(json.loads(path.read_text()))
        influence, curvature = values
        assert influence['parent_sha256'] == curvature['receipt_sha256']
        parents = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert len(parents) == 1 and digest(parents[0]) == influence['parent_sha256']
        parent = json.loads(parents[0].read_text())
        assert curvature['position_km'] == parent['best']['mean'][:2]
        assert influence['invalid_deletions'] == 0
        assert influence['source_sha256'] == digest(HERE/'diagnose_group_influence.py')
        assert influence['kernel_sha256'] == digest(
            HERE.parents[1]/'src/leo/analysis/localization_influence.py')
        assert curvature['source_sha256'] == digest(HERE/'local_curvature.py')
        assert curvature['kernel_sha256'] == digest(
            HERE.parents[1]/'src/leo/analysis/localization_uncertainty.py')
        c = np.asarray(curvature['covariance_km2'])
        shifts = np.asarray([g['position_step_km'] for g in influence['groups']])
        assert len(shifts) == influence['group_count']
        spread = deletion_spread(shifts)
        matrices, failures = {}, {}
        # The sum is explicitly a sensitivity heuristic; these two terms are
        # not established independent sources of variance.
        for arm, matrix in [('curvature', c), ('deletion', spread), ('sum', c+spread)]:
            try:
                assert matrix.shape == (2, 2) and np.all(np.isfinite(matrix))
                np.linalg.cholesky(matrix)
            except (AssertionError, np.linalg.LinAlgError) as error:
                failures[arm] = type(error).__name__
            else:
                matrices[arm] = matrix.tolist()
        rows.append(dict(unit=unit, parent_sha256=digest(parents[0]),
                         influence_sha256=digest(influence_path),
                         curvature_sha256=digest(curvature_path),
                         position_km=curvature['position_km'], group_count=len(shifts),
                         matrices_km2=matrices, failures=failures))
    result = dict(
        planned=64, rows=rows, source_sha256=digest(__file__),
        kernel_sha256=digest(HERE.parents[1]/'src/leo/analysis/localization_deletion_spread.py'),
        original_freeze_sha256=digest(freeze_path), preparation_seconds=time.monotonic()-start,
        qualification='Reference-blind shape construction at unchanged sealed positions. '
        'Deletion shape uses(G-1)/G centered outer-product sum of approximate deletion shifts. '
        'Unequal, inferred groups and frozen IRLS weights do not guarantee jackknife calibration. '
        'Sum is a heuristic, not an independence claim. No parameter fitted to reference errors.')
    path = HERE/'deletion-spread-v1-predictions.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')
    print(json.dumps(dict(planned=64, preparation_seconds=result['preparation_seconds'],
                          rows_with_matrix_failure=sum(bool(r['failures']) for r in rows))))


if __name__ == '__main__':
    main()
