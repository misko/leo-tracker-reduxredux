"""Report-only matched c-arm control; geographic truth is used only here."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from algo02_scan import pair_passes
from report_algo02_ds23 import position_error
from review_ds23_0268_geometry import OUT, PROPOSAL, SOURCE_OUT, csv_write
from run_algo01_ds23_sample import read, write, sha


def main():
    audit = read(OUT / 'phase_exclusion_independent_audit.json')
    retained = read(SOURCE_OUT / (PROPOSAL + '.json'))
    cover = read(SOURCE_OUT / 'accepted_identity_split_coverage.json')[PROPOSAL]
    excluded = {a: read(OUT / ('phase_exclusion_' + a + '.json')) for a in ('c0', 'fitted_c')}
    if not pair_passes({a: r['arms'][a] for a, r in excluded.items()}, include_linear=True):
        raise ValueError('exclusion control fails original paired gates')
    rows = []
    for arm in ('c0', 'fitted_c'):
        path = OUT / ('phase_exclusion_' + arm + '.json')
        if audit['checks'][arm]['fit_sha256'] != sha(path):
            raise ValueError('independent replay is stale')
        for name, result, coverage in (('Retained prototype', retained['arms'][arm], cover[arm]),
                ('Exclude largest sky correction', excluded[arm]['arms'][arm], excluded[arm]['coverage'])):
            rows.append(dict(method=name, arm=arm,
                associated_points=coverage['associated_original_winners'],
                associated_percent=coverage['associated_original_percent'],
                tracks=coverage['associated_tracks'],
                position_error_km=position_error(result['endpoint_latlon']),
                original_gates_pass=True))
    csv_write(OUT / 'phase_exclusion_comparison.csv', rows)
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    names = list(dict.fromkeys(r['method'] for r in rows))
    for arm, shift, color in (('c0', -.16, '#6286b0'), ('fitted_c', .16, '#bd7187')):
        selected = [next(r for r in rows if r['method'] == name and r['arm'] == arm) for name in names]
        for ax, field in zip(axes, ('associated_percent', 'position_error_km')):
            bars = ax.bar([k + shift for k in range(2)], [r[field] for r in selected], width=.3,
                color=color, label=arm)
            ax.bar_label(bars, fmt='%.2f', padding=3, fontsize=9)
    axes[0].axhline(70, color='black', ls='--', lw=.8, label='70% target')
    axes[0].set_ylabel('Original winning GLRT observations associated (%)')
    axes[0].set_ylim(0, 85)
    axes[1].set_ylabel('Position error (km; evaluation only)')
    axes[1].set_ylim(0, 2.)
    for ax in axes:
        ax.set_xticks([0, 1], ['Retained 17-label\nprototype', 'Exclude 69445\n16 labels'])
        ax.grid(axis='y', alpha=.15)
        ax.legend(loc='lower left', fontsize=8)
    figure.suptitle('DS23-0268 · association target survives exclusion of the largest sky correction\n'
        'Fresh regional cold starts · causal catalogue · original residual gates · single-scan diagnostic')
    figure.tight_layout(rect=(0, 0, 1, .89))
    figure.savefig(OUT / 'phase_exclusion_comparison.png', dpi=175)
    plt.close(figure)
    write(OUT / 'report_receipt.json', dict(rows=rows, evaluation_coordinate_used_only_for_reporting=True,
        no_RF_objective_comparison_across_changed_masks=True,
        independent_audit_sha256=sha(OUT / 'phase_exclusion_independent_audit.json')))
    print(rows, flush=True)


if __name__ == '__main__':
    main()
