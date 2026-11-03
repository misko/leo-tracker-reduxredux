"""Measure diagnostic ellipse coverage without fitting an inflation factor."""
import importlib.util
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'deletion-spread-v1-predictions.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    predictions = json.loads(path.read_text())
    assert predictions['source_sha256'] == digest(HERE/'prepare_deletion_spread.py')
    assert predictions['kernel_sha256'] == digest(
        HERE.parents[1]/'src/leo/analysis/localization_deletion_spread.py')
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == predictions['original_freeze_sha256']
    assert [r['unit'] for r in predictions['rows']] == json.loads(
        freeze_path.read_text())['ordered_units']
    for row in predictions['rows']:
        for folder, binding in [('group-influence-v1', 'influence_sha256'),
                                ('curvature-v1', 'curvature_sha256')]:
            assert digest(HERE/folder/(row['unit']+'.json')) == row[binding]
        parent = next((HERE/'regression-v1').glob('batch-*/'+row['unit']+'.json'))
        assert digest(parent) == row['parent_sha256']
        assert json.loads(parent.read_text())['best']['mean'][:2] == row['position_km']
    # All reference-free shapes and their parent positions are sealed/audited.
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('deletion_reference', helper)
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
    arms, summaries = {}, {}
    for arm in ['curvature', 'deletion', 'sum']:
        rows = []
        for row in predictions['rows']:
            valid = arm in row['matrices_km2']
            result = dict(unit=row['unit'], valid=valid, mahalanobis_squared=None)
            if valid:
                c = np.asarray(row['matrices_km2'][arm])
                np.linalg.cholesky(c)
                delta = np.asarray(row['position_km'])-truth
                result.update(mahalanobis_squared=float(delta@np.linalg.solve(c, delta)),
                              major95_m=float(1000*np.sqrt(-2*np.log(.05)*np.linalg.eigvalsh(c)[-1])),
                              area_ratio_to_curvature=float(np.sqrt(np.linalg.det(c)/np.linalg.det(
                                  row['matrices_km2']['curvature']))))
            result['covered'] = {
                str(p): bool(valid and result['mahalanobis_squared'] <= -2*np.log(1-p))
                for p in [.5, .9, .95]}
            rows.append(result)
        arms[arm] = rows
        valid = [r for r in rows if r['valid']]
        summaries[arm] = dict(
            valid=len(valid), denominator=64,
            covered={str(p): sum(r['covered'][str(p)] for r in rows) for p in [.5, .9, .95]},
            median_major95_m=float(np.median([r['major95_m'] for r in valid])),
            median_area_ratio_to_curvature=float(np.median(
                [r['area_ratio_to_curvature'] for r in valid])))
    result = dict(
        prediction_sha256=digest(path), evaluator_sha256=digest(__file__), summaries=summaries,
        qualification='Empirical Gaussian-threshold ellipse diagnostic on64 exposed single-site '
        'regression scans, not held-out calibration. No scale fitted. Positions unchanged. '
        'Deletion matrix is an approximate sensitivity measure; sum may double-count uncertainty.',
        rows=arms)
    with (HERE/'deletion-spread-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    levels = np.linspace(.01, .99, 99)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    labels = {'curvature': 'Local curvature', 'deletion': 'Deletion spread', 'sum': 'Heuristic sum'}
    colors = {'curvature': '#6b798b', 'deletion': '#2c8291', 'sum': '#bb8745'}
    for arm, rows in arms.items():
        coverage = [sum(r['valid'] and r['mahalanobis_squared'] <= -2*np.log(1-p)
                        for r in rows)/64 for p in levels]
        axes[0].plot(levels, coverage, color=colors[arm], label=labels[arm])
    axes[0].plot([0, 1], [0, 1], '--', color='gray', linewidth=1)
    axes[0].set(xlabel='Nominal Gaussian ellipse probability',
                ylabel='Fraction containing reference',
                xlim=(0, 1), ylim=(0, 1), title='All64 scans retained in denominator')
    axes[0].legend(fontsize=8)
    bars = axes[1].bar(list(labels.values()), [summaries[a]['median_major95_m'] for a in labels],
                       color=list(colors.values()))
    axes[1].bar_label(bars, fmt='%.0f m', padding=3)
    axes[1].set(ylabel='Median nominal95% ellipse major radius (m)',
                title='Wider does not mean calibrated')
    axes[1].margins(y=.2)
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(alpha=.15)
        axis.set_axisbelow(True)
    fig.suptitle('Unchanged position estimates: curvature versus group-deletion sensitivity')
    fig.savefig(HERE/'deletion-spread-v1.png', dpi=160)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
