"""Frozen equal-weight aggregation of audited baseline single locations."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def aggregate(points):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0 or not np.all(np.isfinite(points)):
        raise ValueError('Expected finite nonempty E/N positions')
    center = points.mean(axis=0)
    scatter = float(np.sqrt(np.mean(np.sum((points-center)**2, axis=1))))
    return center, scatter


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE/'centroid-ablation-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs = {}

    def read(path):
        assert digest(path) == path.with_suffix('.sha256').read_text().strip(), path
        inputs[str(path)] = digest(path)
        return json.loads(path.read_text())

    selection = read(HERE/'selection.json')
    units = selection['evaluation_units']
    blocks = list(dict.fromkeys(u['block_id'] for u in units))
    assert len(blocks) == 16 and len(units) == 112
    rows = []
    for block in blocks:
        directory = HERE/'independent-v2'/block
        audited = {r['unit']: r for r in read(directory/'evaluation.json')['rows']}
        singles = {}
        for k in range(1, 5):
            unit = block+f'-S{k}'
            row = audited[unit]
            if row['accepted']:
                path = directory/(unit+'.json')
                receipt = read(path)
                assert digest(path) == row['receipt_sha256']
                assert len(row['scans']) == 1
                singles[row['scans'][0]] = (receipt['best']['mean'][:2], row['runtime_s'])
        for unit in [u for u in units if u['block_id'] == block]:
            original = audited[unit['unit_id']]
            assert original['scans'] == unit['scans'] and original['size'] == unit['size']
            missing = [s for s in unit['scans'] if s not in singles]
            row = dict(unit=unit['unit_id'], block=block, dataset=block.split('-')[0],
                       size=unit['size'], scans=unit['scans'], available=not missing,
                       unavailable_constituents=missing, joint_accepted=original['accepted'],
                       joint_error_m=original['error_m'], joint_runtime_s=original['runtime_s'])
            if not missing:
                center, scatter = aggregate([singles[s][0] for s in unit['scans']])
                row.update(center_km=center.tolist(), scatter_m=1000*scatter,
                           constituent_inference_s=sum(singles[s][1] for s in unit['scans']))
            rows.append(row)

    # All locations/admission decisions fixed before reference scoring.
    references = read(HERE/'reference-admission-v1.json')
    for p, expected in references['source_sha256'].items():
        assert digest(p) == expected
        inputs[p] = expected
    reference = {r['unit']:r['reference_latlon'] for r in references['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    inputs[str(helper)] = digest(helper)
    spec = importlib.util.spec_from_file_location('centroid_geo', helper)
    geo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geo)
    for row in rows:
        locations = [reference[s] for s in row['scans']]
        assert all(p == locations[0] for p in locations)
        row['centroid_error_m'] = geo.distance_m(geo.latlon_from_enu(*row['center_km']), locations[0]) if row['available'] else None
        if row['size'] == 1 and row['available']:
            assert abs(row['centroid_error_m']-row['joint_error_m']) < 1e-7
    summary = {}
    for size in (1, 2, 4):
        selected = [r for r in rows if r['size'] == size]
        common = [r for r in selected if r['available'] and r['joint_accepted']]
        changes = [r['centroid_error_m']-r['joint_error_m'] for r in common]
        summary[str(size)] = dict(planned=len(selected), available=sum(r['available'] for r in selected),
            joint_accepted=sum(r['joint_accepted'] for r in selected), matched=len(common),
            centroid_median_m=float(np.median([r['centroid_error_m'] for r in common])),
            joint_median_m=float(np.median([r['joint_error_m'] for r in common])),
            centroid_p90_m=float(np.percentile([r['centroid_error_m'] for r in common],90)),
            joint_p90_m=float(np.percentile([r['joint_error_m'] for r in common],90)),
            improved=sum(c < -1 for c in changes), worsened=sum(c > 1 for c in changes),
            tied_within_1m=sum(abs(c) <= 1 for c in changes),
            median_change_m=float(np.median(changes)),
            median_scatter_m=float(np.median([r['scatter_m'] for r in common])),
            median_constituent_inference_s=float(np.median([r['constituent_inference_s'] for r in common])),
            median_joint_inference_s=float(np.median([r['joint_runtime_s'] for r in common])))
    result = dict(rows=rows, summary=summary, inputs=inputs,
        sources={str(p):digest(p) for p in (Path(__file__).resolve(), HERE/'CENTROID_ABLATION_PLAN.md', HERE/'test_centroid_ablation.py')},
        qualification='No-refit development ablation. Arithmetic mean of all audited constituent singles; unavailable on any failed constituent. Matched quantiles; historical constituent costs exclude aggregation/audit. Scatter is not uncertainty. No new joint-fit acceptance claim.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
    for size, marker in ((2,'o'),(4,'s')):
        common = [r for r in rows if r['size']==size and r['available'] and r['joint_accepted']]
        axes[0].scatter([r['joint_error_m'] for r in common], [r['centroid_error_m'] for r in common], marker=marker,label=f'{size} scans')
        axes[1].scatter([r['scatter_m'] for r in common], [r['centroid_error_m'] for r in common], marker=marker,label=f'{size} scans')
    limit=max(max(r['joint_error_m'],r['centroid_error_m']) for r in rows if r['size']>1 and r['available'] and r['joint_accepted'])*1.05
    axes[0].plot([0,limit],[0,limit],'k--',alpha=.4)
    axes[0].set(xlabel='Joint error (m)',ylabel='Centroid error (m)', title='Matched available windows')
    axes[1].set(xlabel='Constituent RMS scatter (m)',ylabel='Centroid error (m)',title='Agreement does not establish accuracy')
    for ax in axes:
        ax.grid(alpha=.2); ax.legend()
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
