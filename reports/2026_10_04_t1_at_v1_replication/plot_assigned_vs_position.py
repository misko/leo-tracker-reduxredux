"""Plot actual localization-input window counts, not separate association arms."""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCANS = ['A', 'B'] + [f'N{i:02}' for i in range(1, 17)]
ARMS = {'fitted-c': ('Fitted c', '#0077ad'), 'zero-c': ('c = 0', '#df6900')}


def read_points(path):
    with path.open(newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r['case'] == 'all-100']
    expected = {(s, a) for s in SCANS for a in ARMS}
    assert len(rows) == len(expected)
    assert {(r['scan'], r['arm']) for r in rows} == expected
    for scan in SCANS:
        pair = [r for r in rows if r['scan'] == scan]
        assert len({r['windows'] for r in pair}) == 1
    for row in rows:
        assert row['state'] == 'complete'
        assert int(row['windows']) > 0
        assert 0 <= float(row['distance_m']) <= 2000.01
        for flag in ('boundary', 'converged', 'ambiguous'):
            assert row[flag] in ('True', 'False')
    return rows


def main(source=None, output_prefix=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import StrMethodFormatter

    rows = read_points(Path(source) if source else HERE / 'cohort-positions.csv')
    prefix = Path(output_prefix) if output_prefix else HERE / 'assigned-windows-vs-position'
    fields = ['scan', 'arm', 'windows', 'distance_m', 'boundary', 'converged',
              'ambiguous', 'source_sha256']
    with prefix.with_suffix('.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7.2), sharex=True, sharey=True)
    label_offsets = {
        'fitted-c': {'N04': (7, -15), 'N13': (-7, 9), 'N12': (-8, 11),
                     'N16': (8, 11), 'N11': (-8, -15)},
        'zero-c': {'N05': (-8, -20), 'B': (8, -23), 'N09': (-6, 24),
                   'N04': (6, -25), 'N10': (6, 23), 'N12': (7, -15),
                   'N15': (0, 24), 'N06': (0, 11), 'N07': (0, 24)},
    }
    for ax, (arm, (title, color)) in zip(axes, ARMS.items()):
        subset = [r for r in rows if r['arm'] == arm]
        for row in subset:
            x, y = int(row['windows']), float(row['distance_m'])
            boundary, converged = row['boundary'] == 'True', row['converged'] == 'True'
            marker = '^' if boundary else 'o'
            ax.scatter(x, y, marker=marker, s=105 if boundary else 72,
                       facecolors=color if converged else 'white',
                       edgecolors=color, linewidths=1.7, zorder=4)
            if not converged:
                ax.scatter(x, y, marker='x', s=32, color='#292929', linewidths=1.3, zorder=5)
            if row['ambiguous'] == 'True':
                ax.scatter(x, y, marker='o', s=190, facecolors='none',
                           edgecolors='#555555', linewidths=.8, zorder=3)
            offset = label_offsets.get(arm, {}).get(row['scan'], (7, 9))
            ax.annotate(row['scan'], (x, y), xytext=offset,
                        textcoords='offset points', fontsize=9,
                        ha='right' if offset[0] < 0 else 'left', color='#252525')
        boundary_count = sum(r['boundary'] == 'True' for r in subset)
        failed_count = sum(r['converged'] == 'False' for r in subset)
        ax.set_title(f'{title}\n18 scans · {boundary_count} boundary hits · '
                     f'{failed_count} unconverged', fontsize=13)
        ax.axhline(2000, color='.4', ls=':', lw=1.2)
        ax.grid(alpha=.18)
        ax.set_axisbelow(True)
        ax.set_xlim(1650, 3900)
        ax.set_ylim(0, 2280)
        ax.set_yticks([0, 500, 1000, 1500, 2000])
        ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
        ax.set_xlabel('Associated GLRT windows used in position fit', fontsize=11)
    axes[0].set_ylabel('Best-found distance from correct roof (m)', fontsize=11)
    fig.suptitle('T1-AT v1 · associated GLRT windows vs position error' +
                 (' · after continuation' if source else ''), fontsize=16 if source else 18, y=.97)
    handles = [
        Line2D([], [], marker='o', color='none', markerfacecolor='.4', markeredgecolor='.4', label='Converged interior'),
        Line2D([], [], marker='^', color='none', markerfacecolor='.4', markeredgecolor='.4', label='Search boundary'),
        Line2D([], [], marker='x', color='.2', ls='none', label='Unconverged (× overlay)'),
        Line2D([], [], marker='o', color='none', markerfacecolor='none', markeredgecolor='.4', markersize=10, label='Outer ring: search ambiguity'),
    ]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .105), ncol=4, frameon=False, fontsize=9)
    fig.text(.5, .035,
             'One point per scan per calibration variant; all assigned windows, no subset filtering. Same windows in both panels.\n'
             'One highest-refined-margin candidate per passing 20 ms receiver/channel window. Independent 2 km searches.\n'
             '2,000 m marks the imposed search boundary, not an established unconstrained minimum. ' +
             ('Optimizer-only continuation; original model and tolerance retained.' if source else 'Saved best-found results; no new fits.'),
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .17, 1, .92))
    fig.savefig(prefix.with_suffix('.png'), dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output-prefix', type=Path)
    args = parser.parse_args()
    main(args.source, args.output_prefix)
