"""Score sealed DS12 predictions using separately admitted capture-bound references."""
import importlib.util
import json
from pathlib import Path

import matplotlib
import numpy as np
from regression_batch import digest, verify_sources

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    paths = {key: HERE/name for key, name in dict(
        reference='ds12-reference-admission-v1.json',
        uncertainty='heldout-uncertainty-v1-evaluation.json',
        runtime='heldout-baseline-v1-runtime-16.json',
        freeze='heldout-uncertainty-v1-freeze.json',
        thresholds='uncertainty-thresholds-v1-freeze.json').items()}
    data = {k: json.loads(p.read_text()) for k, p in paths.items()}
    for key in ['reference', 'freeze', 'thresholds']:
        assert digest(paths[key]) == paths[key].with_suffix('.sha256').read_text().strip()
        verify_sources(data[key]['source_sha256'])
    assert data['uncertainty']['freeze_sha256'] == digest(paths['freeze'])
    assert data['uncertainty']['evaluator_sha256'] == digest(
        HERE/'evaluate_heldout_uncertainty.py')
    assert data['runtime']['evaluator_sha256'] == digest(HERE/'evaluate_heldout_runtime.py')
    assert data['runtime']['freeze_sha256'] == data['freeze']['baseline_freeze_sha256']
    assert data['freeze']['threshold_freeze_sha256'] == digest(paths['thresholds'])
    units = data['freeze']['ordered_units']
    for key in ['reference', 'uncertainty', 'runtime']:
        assert [r['unit'] for r in data[key]['rows']] == units
    assert len(units) == 16
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('coordinate_helper', helper)
    geo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geo)
    rules = data['thresholds']['thresholds']
    rows = []
    for reference, audit, timing in zip(data['reference']['rows'], data['uncertainty']['rows'],
                                      data['runtime']['rows'], strict=True):
        unit = reference['unit']
        assert audit['valid'] and timing['accepted']
        path = HERE/'heldout-uncertainty-v1'/(unit+'.json')
        assert digest(path) == audit['receipt_sha256']
        receipt = json.loads(path.read_text())
        parents = list((HERE/'heldout-baseline-v1').glob('batch-*/'+unit+'.json'))
        assert len(parents) == 1
        assert digest(parents[0]) == receipt['parent_sha256'] == timing['receipt_sha256']
        parent = json.loads(parents[0].read_text())
        assert parent['best']['mean'][:2] == receipt['position_km']
        position = np.asarray(receipt['position_km'])
        latlon = geo.latlon_from_enu(*position)
        ref = reference['reference_latlon']
        error = geo.distance_m(latlon, ref)
        lat0, lon0 = np.radians(geo.CENTER)
        lat, lon = np.radians(ref)
        east = np.cos(lat)*np.sin(lon-lon0)
        north = np.cos(lat0)*np.sin(lat)-np.sin(lat0)*np.cos(lat)*np.cos(lon-lon0)
        dot = np.sin(lat0)*np.sin(lat)+np.cos(lat0)*np.cos(lat)*np.cos(lon-lon0)
        length = np.hypot(east, north)
        truth = (geo.EARTH_RADIUS_KM*np.arctan2(length, dot)*np.array([east, north])/length
                 if length else np.zeros(2))
        assert geo.distance_m(geo.latlon_from_enu(*truth), ref) < .001
        delta = position-truth
        arms = {}
        for arm, rule in rules.items():
            matrix = np.asarray(receipt['arms'][arm]['matrix_km2'])
            np.linalg.cholesky(matrix)
            score = float(delta@np.linalg.solve(matrix, delta))
            arms[arm] = dict(squared_distance=score,
                             covered={p: score <= v['squared_distance_cutoff']
                                      for p, v in rule.items()},
                             nominal95_covered=bool(score <= -2*np.log(.05)))
        rows.append(dict(unit=unit, accepted=True, error_m=error,
                         east_north_error_m=(1000*delta).tolist(), arms=arms,
                         runtime_s=timing['runtime_s'], cpu_s=timing['cpu_s']))
    errors = [r['error_m'] for r in rows]
    result = dict(
        planned=16, accepted=16, median_error_m=float(np.median(errors)),
        p90_error_m=float(np.percentile(errors, 90)), maximum_error_m=max(errors),
        within_1000_m=sum(e <= 1000 for e in errors),
        within_3000_m=sum(e <= 3000 for e in errors), denominator=16,
        median_runtime_s=float(np.median([r['runtime_s'] for r in rows])),
        maximum_runtime_s=max(r['runtime_s'] for r in rows),
        median_cpu_s=float(np.median([r['cpu_s'] for r in rows])),
        coverage={arm: {p: sum(r['arms'][arm]['covered'][p] for r in rows)
                        for p in rule} for arm, rule in rules.items()},
        nominal95_coverage={arm: sum(r['arms'][arm]['nominal95_covered'] for r in rows)
                            for arm in rules},
        source_sha256={str(p): digest(p) for p in [*paths.values(), Path(__file__), helper]},
        qualification='Unchanged sealed point estimates and previously frozen uncertainty '
        'thresholds, now scored against capture-bound operator reference. Reference is unsurveyed, '
        'WGS84 assumed. Sixteen temporally related scans at one site do not establish general '
        'calibration; prior production-analysis exposure acknowledged. No held-out tuning or '
        'arm selection. Inference runtimes exclude separately measured uncertainty diagnostics.',
        rows=rows)
    output = HERE/'ds12-geography-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].bar(np.arange(1, 17), errors, color='#367c94')
    axes[0].axhline(1000, color='#56975a', linestyle='--', label='1,000 m')
    axes[0].axhline(3000, color='#bb8745', linestyle='--', label='3,000 m')
    axes[0].set(xlabel='Frozen held-out scan index', ylabel='Horizontal reference error (m)',
                title=f'Median {np.median(errors):,.0f} m; p90 {np.percentile(errors, 90):,.0f} m')
    axes[0].legend()
    for arm, values in result['coverage'].items():
        axes[1].plot([float(p) for p in values], [n/16 for n in values.values()],
                     marker='o', label=arm)
    axes[1].plot([.5, 1], [.5, 1], '--', color='gray')
    axes[1].set(xlabel='Frozen empirical ellipse level', ylabel='Fraction containing reference',
                ylim=(0, 1.05), title='All 16 scans; thresholds fixed before reference admission')
    axes[1].legend()
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
    fig.suptitle('DS12: unchanged baseline, operator reference (unsurveyed)')
    fig.savefig(HERE/'ds12-geography-v1.png', dpi=160)
    print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256']},
                     indent=2))


if __name__ == '__main__':
    main()
