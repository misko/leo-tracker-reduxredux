"""Verify and visualize the completed conditional curvature diagnostic."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from screen_seed_prefix import sealed, digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    rows = []; inputs = {}
    for dataset in ('DS9', 'DS10', 'DS11'):
        directory = HERE/'receiver-curvature-v1'/(dataset+'-B01-S1')
        frozen = sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
        assert process_ok(sealed(directory/'launch.json'))
        result = sealed(directory/'result.json')
        for name in ('sources.json', 'result.json', 'launch.json'):
            inputs[str(directory/name)] = digest(directory/name)
        assert result['all_folds_valid']
        count = sum(f['contrasts'] for f in result['folds'])
        gains = [(f['scores']['quadratic']-f['scores']['linear'])/f['contrasts'] for f in result['folds']]
        coefficient = np.asarray([f['quadratic']['beta'] for f in result['folds']])
        row = dict(dataset=dataset, groups=len(gains), contrasts=count,
            signal_tracks=result['signal_tracks'], background_tracks=result['background_tracks'],
            pooled_gain=result['pooled_quadratic_minus_linear_per_contrast'],
            median_gain=float(np.median(gains)), positive_groups=sum(g > 0 for g in gains), group_gains=gains,
            gain_over_zero={arm: sum(f['scores'][arm]-f['scores']['zero'] for f in result['folds'])/count for arm in ('linear', 'quadratic')},
            quadratic_coefficients_hz_min=coefficient[:, 2:].min(axis=0).tolist(),
            quadratic_coefficients_hz_max=coefficient[:, 2:].max(axis=0).tolist(),
            acceleration_hz_per_s2_min=(2*coefficient[:, 2:].min(axis=0)/result['scale_seconds']**2).tolist(),
            acceleration_hz_per_s2_max=(2*coefficient[:, 2:].max(axis=0)/result['scale_seconds']**2).tolist(),
            gate_passed=result['gate_passed'])
        rows.append(row)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    x = np.arange(3)
    for offset, arm, color in ((-.18, 'linear', '#517fa4'), (.18, 'quadratic', '#cf8832')):
        axes[0].bar(x+offset, [r['gain_over_zero'][arm] for r in rows], width=.36, label=arm, color=color)
    axes[0].set_xticks(x, [r['dataset'] for r in rows]); axes[0].legend()
    axes[0].set_ylabel('Held-group log-score gain / contrast')
    axes[0].set_title('Corrections versus frozen baseline')
    for i, row in enumerate(rows):
        axes[1].scatter(i+np.linspace(-.12, .12, row['groups']), row['group_gains'], s=18, alpha=.65)
    axes[1].scatter(x, [r['pooled_gain'] for r in rows], marker='D', color='black', label='Pooled / contrast')
    axes[1].set_xticks(x, [r['dataset'] for r in rows]); axes[1].legend()
    axes[1].set_title('Quadratic versus linear control')
    for ax in axes: ax.axhline(0, color='gray', linewidth=.8); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Conditional residual prediction; fixed data-fitted locations and identities')
    figure = HERE/'receiver-curvature-summary-v1.png'; fig.savefig(figure, dpi=160); plt.close(fig)
    output = HERE/'receiver-curvature-summary-v1.json'
    value = dict(rows=rows, gate_passed=all(r['gate_passed'] for r in rows), inputs=inputs,
        sources={str(Path(__file__).resolve()): digest(__file__)}, figure_sha256=digest(figure))
    with output.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__': main()
