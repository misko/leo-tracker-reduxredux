"""Retain every conditional result and summarize excluded predictive loss."""
import csv
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    records = [r for path in sorted((HERE/'conditional_results').glob('*.json'))
        for r in json.loads(path.read_text())['records']]
    rows = []
    for r in records:
        row = {key:r[key] for key in ['source_id', 'arm', 'direction', 'sigma_hz',
            'train_observations', 'held_observations', 'held_nll_b0', 'held_nll_learned',
            'held_nll_delta', 'held_new', 'held_lost', 'held_retained',
            'held_intersection_b0_rms_hz', 'held_intersection_learned_rms_hz',
            'configured_reference_distance_km']}
        row.update(r['diagnostics'])
        for key in ['all_held_b0', 'all_held_learned', 'challenge_held_b0', 'challenge_held_learned']:
            row.update({key+'_'+k:v for k, v in r[key].items()})
        rows.append(row)
    with (HERE/'conditional-comparison.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    aggregates = []
    for arm in ['fitted-c', 'zero-c']:
        for sigma in [300., 1000.]:
            selected = [r for r in records if r['arm'] == arm and r['sigma_hz'] == sigma]
            # Both directions together count every original observation once.
            metrics = {key:dict(denominator=sum(r[key]['denominator'] for r in selected),
                associated=sum(r[key]['associated'] for r in selected))
                for key in ['all_held_b0', 'all_held_learned', 'challenge_held_b0', 'challenge_held_learned']}
            aggregates.append(dict(arm=arm, sigma_hz=sigma, fits=len(selected),
                held_nll_delta=sum(r['held_nll_delta'] for r in selected),
                held_nll_improved_fits=sum(r['held_nll_delta'] < 0 for r in selected),
                strict_bias_endpoints=sum(r['diagnostics']['accepted'] for r in selected),
                new=sum(r['held_new'] for r in selected), lost=sum(r['held_lost'] for r in selected),
                density_evaluations=sum(r['diagnostics']['density_evaluations'] for r in selected),
                surrogate_profile_calls=sum(r['diagnostics']['surrogate_profile_calls'] for r in selected),
                **metrics))
    summary = dict(fits=len(records), expected_fits=40, aggregates=aggregates,
        qualification='Conditional residual prediction only. Full-data-conditioned physical/calibration/q baseline unchanged; biases selected on training halves only. Each direction has a distinct train fit. Both directions pooled cover all 20084 original observations and all693 challenge observations once per arm/width. These are not cold-pipeline, geographic or identity validation results.')
    (HERE/'conditional-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for axis, arm in zip(axes, ['fitted-c', 'zero-c']):
        labels = [(s, d) for s in ['S01', 'S02', 'S03', 'S04', 'S05'] for d in ['early_to_late', 'late_to_early']]
        x = np.arange(len(labels))
        for delta, sigma, color in [(-.18, 300., '#1876a8'), (.18, 1000., '#bf6512')]:
            values = [next(r['held_nll_delta'] for r in records if r['arm'] == arm
                and r['sigma_hz'] == sigma and r['source_id'] == s and r['direction'] == d) for s, d in labels]
            axis.bar(x+delta, values, .35, color=color, label=f'σ{int(sigma)}')
        axis.set_xticks(x, [s+' '+('E→L' if d == 'early_to_late' else 'L→E') for s, d in labels], rotation=55, ha='right')
        axis.axhline(0., color='black', linewidth=.8)
        axis.set(title=arm, ylabel='Excluded-half NLL change (positive is worse)')
        axis.grid(axis='y', alpha=.2)
        axis.legend()
    fig.suptitle('Bias-only conditional residual prediction; full-data-conditioned physical/calibration/q fixed')
    fig.savefig(HERE/'conditional-excluded-nll.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
