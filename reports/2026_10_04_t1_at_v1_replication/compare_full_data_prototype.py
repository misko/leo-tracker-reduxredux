"""Compare audited fold-based and full-data prototypes, without refitting."""
import csv
import json
from pathlib import Path

import numpy as np

from timing_bound_comparison import digest

HERE = Path(__file__).resolve().parent
OUT = HERE / 'full-scan-seed-restart'
SCANS = tuple(f'N{i:02d}' for i in range(1, 17))
ARMS = ('fitted-c', 'zero-c')
VARIANTS = ('fold-based', 'full-data-initial', 'full-data-multistart')


def comparison_rows(old, new):
    if old['status'] != 'passed' or new['status'] != 'passed':
        raise ValueError('Only audited results may be compared')
    rows = []
    for scan in SCANS:
        for arm in ARMS:
            denominator = None
            for variant, report, field, name in [
                ('fold-based', old, 'case', 'fold-control'),
                ('full-data-initial', old, 'case', 'full-rebuilt-members'),
                ('full-data-multistart', new, 'variant', 'restarted-full-scan'),
            ]:
                def select(source):
                    matches = [r for r in report[source]
                               if (r['scan'], r['arm'], r[field]) == (scan, arm, name)]
                    if len(matches) != 1:
                        raise ValueError('Missing or duplicate scan/arm/variant')
                    return matches[0]
                position, association = select('rows'), select('coverage')
                if denominator is not None and denominator != association['denominator']:
                    raise ValueError('Coverage denominators changed')
                denominator = association['denominator']
                rows.append(dict(scan=scan, arm=arm, variant=variant,
                    windows_total=denominator, windows_assigned=association['assigned'],
                    coverage=association['coverage'], association_satellites=association['satellites'],
                    position_windows=position['windows'], position_satellites=position['satellites'],
                    position_error_m=position['distance_m'], converged=position['converged'],
                    boundary=position['boundary'],
                    posterior_weighted_rms_hz=position['posterior_weighted_residual_rms_hz']))
    return rows


def summarize(rows):
    result = []
    for arm in ARMS:
        for variant in VARIANTS:
            selected = [r for r in rows if (r['arm'], r['variant']) == (arm, variant)]
            result.append(dict(arm=arm, variant=variant, scans=len(selected),
                median_coverage_pct=100*float(np.median([r['coverage'] for r in selected])),
                pooled_coverage_pct=100*sum(r['windows_assigned'] for r in selected)/sum(r['windows_total'] for r in selected),
                median_position_error_m=float(np.median([r['position_error_m'] for r in selected])),
                median_posterior_weighted_rms_hz=float(np.median([r['posterior_weighted_rms_hz'] for r in selected])),
                below_1km=sum(r['position_error_m'] < 1000 for r in selected),
                converged=sum(r['converged'] for r in selected), boundary=sum(r['boundary'] for r in selected)))
    return result


def render(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    variants = ('fold-based', 'full-data-multistart')
    colors = ('#999999', '#0072b2')
    for column, arm in enumerate(ARMS):
        for i, scan in enumerate(SCANS):
            pair = [next(r for r in rows if (r['scan'], r['arm'], r['variant']) == (scan, arm, v)) for v in variants]
            for row, key, scale in [(0, 'coverage', 100), (1, 'position_error_m', 1)]:
                ax = axes[row, column]
                ys = [r[key]*scale for r in pair]
                ax.plot([i-.14, i+.14], ys, color='.75', lw=1)
                for j, r in enumerate(pair):
                    x = i + (-.14 if j == 0 else .14)
                    ax.scatter(x, ys[j], color=colors[j], s=42,
                        marker='^' if row == 1 and r['boundary'] else 'o',
                        label=('Earlier fold-based', 'Full-data prototype')[j] if i == 0 and row == 0 else None)
                    if row == 1 and not r['converged']:
                        ax.scatter(x, ys[j], marker='x', color='black', s=46)
                if row == 1:
                    ax.annotate(f'{ys[1]:.0f}', (i+.14, ys[1]), xytext=(0, 7),
                                textcoords='offset points', ha='center', fontsize=8)
        axes[0, column].set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
        axes[0, column].set_ylabel('Associated top-candidate windows (%)')
        axes[0, column].set_ylim(55, 102)
        axes[0, column].axhline(90, color='.5', ls=':')
        axes[1, column].set_ylabel('Best-found position error (m)')
        axes[1, column].set_ylim(0, 4500)
        axes[1, column].axhline(1000, color='.4', ls='--')
        axes[1, column].axhline(4000, color='.5', ls=':')
        axes[1, column].set_xticks(range(len(SCANS)), SCANS, rotation=45)
    for ax in axes.ravel():
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
    axes[0, 0].legend(loc='lower left', fontsize=9)
    fig.suptitle('N01–N16 · fold-based calibration versus the full-data prototype', fontsize=18)
    fig.text(.5, .025,
        'Same refined top-one GLRT input and TLE bank; independent 4 km searches. Calibration uses the known roof.\n'
        'Full data: no temporal holdouts; nonlinear RX correction retains its quality gate; localization uses assigned windows.\n'
        'Position RF arms share fitted-c-selected observations and candidates. Triangles: boundary; ×: unconverged.\n'
        'Multistart prototype changes calibration initialization as well as data scope; this is not blind localization.',
        ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .135, 1, .95))
    fig.savefig(OUT/'fold-versus-full-data.png', dpi=165)
    plt.close(fig)


def main():
    paths = [HERE/'full-scan-cohort/audit.json', OUT/'audit.json']
    rows = comparison_rows(*(json.loads(p.read_text()) for p in paths))
    report = dict(sources={str(p): digest(p) for p in paths},
                  implementation_sha256=digest(Path(__file__)), summaries=summarize(rows), rows=rows)
    (OUT/'fold-versus-full-data.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    with (OUT/'fold-versus-full-data.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render(rows)
    print(json.dumps(report['summaries'], indent=2))


if __name__ == '__main__':
    main()
