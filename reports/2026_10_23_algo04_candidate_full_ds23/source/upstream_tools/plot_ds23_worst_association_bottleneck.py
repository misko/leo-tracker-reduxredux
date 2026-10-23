"""Render graph membership in the original GLRT CFO coordinate system.

Numerical graph values are dealiased; raw GLRT may differ by integer periods.
Join explicit observation IDs rather than overlaying these incompatible gauges.
"""

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from probe_ds23_worst_association_bottleneck import OUT, setup
from run_algo01_ds23_sample import ROOT, read, sha, write


def raw_track_values(track, indices, by_id):
    indices = np.asarray(indices, int)
    ids = [track['observation_ids'][i] for i in indices]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate graph observation ID')
    rows = [by_id[oid] for oid in ids]
    times = np.array([r['time_s'] for r in rows])
    if not np.allclose(times, np.asarray(track['times'])[indices], rtol=0., atol=1e-8):
        raise ValueError('physical observation time differs from graph membership')
    return times, np.array([r['measured_cfo_hz'] for r in rows])


def one(case):
    d = setup(case)
    inv = read(OUT/case/'inventory.json')['arms']['fitted_c']
    by_id = {o['observation_id']: o for o in d['observations']}
    channels = sorted({o['channel'] for o in d['observations']})
    fig, axes = plt.subplots(2, len(channels), figsize=(4*len(channels), 7), squeeze=False)
    owned = set(inv['accepted_observation_ids'])
    cmap = plt.get_cmap('tab20')
    for rx in [1, 2]:
        for col, ch in enumerate(channels):
            ax = axes[rx-1, col]
            rows = [r for r in d['observations'] if r['receiver'] == rx and r['channel'] == ch]
            missing = [r for r in rows if r['observation_id'] not in owned]
            ax.scatter([r['time_s'] for r in rows], [r['measured_cfo_hz']/1000 for r in rows], c='0.85', s=8)
            ax.scatter([r['time_s'] for r in missing], [r['measured_cfo_hz']/1000 for r in missing], c='crimson', s=10)
            for k, r in enumerate(inv['ranking']):
                if (r['receiver'], r['channel']) != (rx, ch):
                    continue
                times, values = raw_track_values(d['scan'].tracks[r['track_index']], r['indices'], by_id)
                cuts = np.flatnonzero((np.diff(times) > 10.) | (abs(np.diff(values)) > .5/4.4e-6))+1
                for part in np.split(np.arange(len(times)), cuts):
                    ax.plot(times[part], values[part]/1000, c=cmap(k % 20), lw=1.5)
            ax.set_title(f'RX{rx} CH{ch}')
            ax.set_xlabel('Time in scan (s)')
            ax.set_ylabel('Raw GLRT CFO (kHz)')
            ax.grid(alpha=.2)
    fig.suptitle(f"{case}: {inv['associated']}/{inv['total_GLRT']} associated ({inv['percent']:.2f}%)\n"
                 'Gray: all GLRT · red: unassociated GLRT · colors: unassociated graph-track point sequences')
    fig.tight_layout()
    target = OUT/case/'unassociated_GLRT_raw_CFO.png'
    fig.savefig(target, dpi=160)
    plt.close(fig)
    return dict(case=case, figure=str(target), figure_sha256=sha(target),
                all_graph_coordinates_joined_to_explicit_raw_observation_IDs=True,
                original_dealiased_numerical_inputs_unchanged=True)


def main():
    rows = [one(c) for c in read(OUT/'protocol.json')['cases']]
    write(OUT/'raw_CFO_figure_receipt.json', dict(rows=rows, source_sha256=sha(Path(__file__)),
          replaces_initial_misaligned_canonical_graph_overlays=True,
          test_source_sha256=sha(ROOT/'tests/analysis/test_ds23_worst_association_bottleneck.py')))


if __name__ == '__main__':
    main()
