"""Measure coverage of a candidate local-IRLS ellipse on the frozen panel."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'curvature-v1'
    verify_sources(json.loads((directory/'sources.json').read_text()))
    panel_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(panel_path) == (
        'sha256:97be104787783e3bb81d851ba8664f3a26ac93fe10b617aae605ad8b13372bd7')
    panel = json.loads(panel_path.read_text())
    rows, matrices, positions = [], {}, {}
    for prior in panel['rows']:
        unit = prior['unit']
        path = directory/(unit+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, result = [], {}
        try:
            assert launch['returncode'] == 0 and not launch['timed_out']
            assert launch['within_budget']
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            result = json.loads(path.read_text())
            assert result['receipt_sha256'] == prior['receipt_sha256']
            assert result['source_sha256'] == digest(HERE/'local_curvature.py')
            assert result['kernel_sha256'] == digest(
                HERE.parents[1]/'src/leo/analysis/localization_uncertainty.py')
            covariance = np.asarray(result['covariance_km2'])
            assert covariance.shape == (2, 2) and np.all(np.isfinite(covariance))
            np.linalg.cholesky(covariance)
            prediction = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(prediction) == prior['receipt_sha256']
            assert result['position_km'] == json.loads(prediction.read_text())['best']['mean'][:2]
            matrices[unit], positions[unit] = covariance, np.asarray(result['position_km'])
        except (AssertionError, KeyError, ValueError, OSError, np.linalg.LinAlgError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, valid=not errors, audit_errors=errors,
                         diagnostic_runtime_s=launch['elapsed_seconds'],
                         axis_scales_m=result.get('axis_scales_m'), mahalanobis_squared=None))
    # Reference coordinates are used only after every covariance has been audited.
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('curvature_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    lat0, lon0 = np.radians(reference.CENTER)
    lat, lon = np.radians(reference.REFERENCE)
    east = np.cos(lat)*np.sin(lon-lon0)
    north = np.cos(lat0)*np.sin(lat)-np.sin(lat0)*np.cos(lat)*np.cos(lon-lon0)
    dot = np.sin(lat0)*np.sin(lat)+np.cos(lat0)*np.cos(lat)*np.cos(lon-lon0)
    length = np.hypot(east, north)
    truth = reference.EARTH_RADIUS_KM*np.arctan2(length, dot)*np.array([east, north])/length
    assert reference.distance_m(reference.latlon_from_enu(*truth), reference.REFERENCE) < .001
    levels = [.5, .9, .95]
    for row in rows:
        if row['valid']:
            delta = positions[row['unit']]-truth
            row['mahalanobis_squared'] = float(delta@np.linalg.solve(matrices[row['unit']], delta))
        row['covered'] = {
            str(p): bool(row['valid'] and row['mahalanobis_squared'] <= -2*np.log(1-p))
            for p in levels}
    coverage = {str(p): dict(nominal=p, count=sum(r['covered'][str(p)] for r in rows),
                             denominator=64,
                             fraction=sum(r['covered'][str(p)] for r in rows)/64)
                for p in levels}
    result = dict(
        qualification=('Empirical coverage diagnostic for conditional inverse IRLS curvature, '
                       'not an exact or calibrated posterior. All64 scans retained in denominator. '
                       'Single-site exposed regression data, not held-out calibration. '
                       'Posthoc diagnostic runtime is separate from the original fitter runtime.'),
        valid_count=sum(r['valid'] for r in rows), planned_count=64, coverage=coverage,
        median_diagnostic_seconds=float(np.median([r['diagnostic_runtime_s'] for r in rows])),
        evaluator_sha256=digest(__file__), rows=rows,
    )
    with (HERE/'curvature-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
