"""Sum first-to-last spans per (satellite, receiver), pooling channels.

These are track-span seconds, not continuous detected time or IQ exposure.
Gaps count in spans; simultaneous satellites and receivers count separately.
Uses frozen hard owners in the actual all-100 localization input for both arms.
"""
import csv
import hashlib
from pathlib import Path

import numpy as np

from plot_assigned_vs_position import ARMS, HERE, SCANS, read_points

INPUTS = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')


def track_spans(times, owners, receivers):
    assert len(times) == len(owners) == len(receivers)
    assert np.isfinite(times).all()
    rows = []
    for sat, rx in sorted(set(zip(map(int, owners), map(int, receivers)))):
        selected = times[(owners == sat) & (receivers == rx)]
        rows.append(dict(satellite=sat, receiver=rx, windows=len(selected),
                         start_s=float(selected.min()), end_s=float(selected.max()),
                         span_s=float(np.ptp(selected))))
    return rows


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import StrMethodFormatter

    positions = read_points(HERE / 'cohort-positions.csv')
    track_rows, totals = [], {}
    for scan in SCANS:
        source = INPUTS / scan / 'input.npz'
        with np.load(source, allow_pickle=False) as data:
            tracks = track_spans(data['times'], data['owners'], data['receiver'])
            expected = {int(r['windows']) for r in positions if r['scan'] == scan}
            assert expected == {len(data['times'])}
            assert len(np.unique(data['group'])) == len(data['times'])
            assert sum(r['windows'] for r in tracks) == len(data['times'])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        track_rows.extend(dict(scan=scan, **r, source=str(source),
                               source_sha256=digest) for r in tracks)
        totals[scan] = (sum(r['span_s'] for r in tracks), len(tracks))
    write_csv(HERE / 'associated-track-spans.csv', track_rows)
    points = [dict(scan=r['scan'], arm=r['arm'],
                   total_track_span_s=totals[r['scan']][0], tracks=totals[r['scan']][1],
                   associated_windows=int(r['windows']), distance_m=float(r['distance_m']),
                   boundary=r['boundary'], converged=r['converged'], ambiguous=r['ambiguous'])
              for r in positions]
    write_csv(HERE / 'track-seconds-vs-position.csv', points)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7.2), sharex=True, sharey=True)
    for ax, (arm, (title, color)) in zip(axes, ARMS.items()):
        rows = [r for r in points if r['arm'] == arm]
        for r in rows:
            x, y = r['total_track_span_s'], r['distance_m']
            boundary, converged = r['boundary'] == 'True', r['converged'] == 'True'
            ax.scatter(x, y, marker='^' if boundary else 'o', s=105 if boundary else 72,
                       facecolors=color if converged else 'white', edgecolors=color,
                       linewidths=1.7, zorder=4)
            if not converged:
                ax.scatter(x, y, marker='x', s=32, color='#292929', linewidths=1.3, zorder=5)
            if r['ambiguous'] == 'True':
                ax.scatter(x, y, marker='o', s=190, facecolors='none', edgecolors='.4', zorder=3)
            offset = (7, 9)
            if boundary:
                rank = sorted([q['total_track_span_s'] for q in rows if q['boundary'] == 'True']).index(x)
                offset = (0, 12 if rank % 2 == 0 else 29)
            overrides = {
                'fitted-c': {'A': (8, 12), 'N07': (-8, -13)},
                'zero-c': {'B': (-12, -12), 'N12': (8, -13),
                           'N02': (-8, 9), 'N03': (7, -14), 'N11': (-8, -13),
                           'N10': (-14, 14), 'N16': (-5, 32), 'N14': (10, 14)},
            }
            offset = overrides.get(arm, {}).get(r['scan'], offset)
            ax.annotate(r['scan'], (x, y), xytext=offset, textcoords='offset points',
                        fontsize=9, ha='right' if offset[0] < 0 else
                        'center' if offset[0] == 0 else 'left', color='#252525')
        ax.set_title(f'{title}\n18 scans · '
                     f'{sum(r["boundary"] == "True" for r in rows)} boundary hits · '
                     f'{sum(r["converged"] == "False" for r in rows)} unconverged', fontsize=13)
        ax.axhline(2000, color='.4', ls=':', lw=1.2)
        ax.grid(alpha=.18)
        ax.set_axisbelow(True)
        ax.set_ylim(0, 2320)
        ax.set_yticks([0, 500, 1000, 1500, 2000])
        ax.margins(x=.16)
        ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
        ax.set_xlabel('Total associated track span (satellite–receiver seconds)', fontsize=11)
    axes[0].set_ylabel('Best-found distance from correct roof (m)', fontsize=11)
    fig.suptitle('T1-AT v1 · total associated track seconds vs position error', fontsize=18, y=.97)
    handles = [
        Line2D([], [], marker='o', color='none', markerfacecolor='.4', markeredgecolor='.4', label='Converged interior'),
        Line2D([], [], marker='^', color='none', markerfacecolor='.4', markeredgecolor='.4', label='Search boundary'),
        Line2D([], [], marker='x', color='.2', ls='none', label='Unconverged (× overlay)'),
        Line2D([], [], marker='o', color='none', markerfacecolor='none', markeredgecolor='.4', markersize=10, label='Outer ring: search ambiguity'),
    ]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .105), ncol=4, frameon=False, fontsize=9)
    fig.text(.5, .027,
             'Duration = sum of (last − first associated observation) for each satellite/receiver pair; channels pooled.\n'
             'Gaps are included. Concurrent satellites and receivers count separately; this is not continuous detected time or 20 ms × window count.\n'
             'All assigned windows; frozen owners and identical inputs in both arms. Independent 2 km searches; boundary points are not established unconstrained minima.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .17, 1, .92))
    fig.savefig(HERE / 'track-seconds-vs-position.png', dpi=180)
    plt.close(fig)
    for scan, (span, tracks) in totals.items():
        print(f'{scan}: {span:.1f} track-span seconds, {tracks} satellite/receiver tracks')


if __name__ == '__main__':
    main()
