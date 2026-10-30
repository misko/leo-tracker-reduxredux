"""Describe target residual scale without changing observations or position fits."""
import argparse
import hashlib
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context


def scale_rows(times, residual, sigma):
    times, residual, sigma = [np.asarray(x, float) for x in (times, residual, sigma)]
    if not (times.ndim == 1 and times.shape == residual.shape == sigma.shape
            and len(times) >= 4 and np.isfinite([times, residual, sigma]).all()
            and (sigma > 0).all()):
        raise ValueError('finite matching vectors and positive noise scales required')
    midpoint = (times.min() + times.max()) / 2
    groups = [('first_half', times < midpoint), ('second_half', times >= midpoint)]
    block = np.floor(times / 12).astype(int)
    groups += [(f'scan_block_{b}', block == b) for b in np.unique(block)]
    rows = []
    for name, mask in groups:
        r = residual[mask]
        rows.append(dict(group=name, points=len(r),
            first_s=float(times[mask].min()), last_s=float(times[mask].max()),
            residual_mean_hz=float(r.mean()), residual_RMS_hz=float(np.sqrt(np.mean(r*r))),
            residual_scatter_hz=float(np.std(r, ddof=1)) if len(r) > 1 else None,
            median_radio_sigma_hz=float(np.median(sigma[mask])),
            scaled_RMS=float(np.sqrt(np.mean((r/sigma[mask])**2)))))
    return rows


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = read(args.trial/'protocol.json')
    inventory = args.study/'all-large-track-recovery'/protocol['job']['job_id']/'inventory.json'
    d = context(read(inventory))
    if len(protocol['targets']) != 1:
        raise ValueError('single native target required for this diagnostic')
    target = protocol['targets'][0]
    track = d['scan'].tracks[target['track_index']]
    if track['observation_ids'] != target['observation_ids']:
        raise ValueError('target observation order differs from native graph')
    trial = read(args.trial/'new_family.json')
    meta = d['scan'].fixed_window_noise
    sigma = np.array([meta['per_observation_noise_sigma_hz'][o]
        if meta['extra_parameter_BIC_gain'] > 0 else d['scan'].radio_sigma_hz
        for o in track['observation_ids']])
    rows = []; points = []; fig, axes = plt.subplots(1, 2, figsize=(13, 4), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        diagnostic = trial['arms'][arm]['family']['diagnostics'][0]
        times = np.asarray(diagnostic['times_s'])
        if not np.array_equal(times, track['times']):
            raise ValueError('diagnostic timestamps differ from native target')
        residual = np.asarray(diagnostic['raw_residual_hz']) - diagnostic['profile_bias_hz']
        rows.extend(dict(arm=arm, **r) for r in scale_rows(times, residual, sigma))
        points.append(dict(arm=arm, times_s=times, residual_hz=residual, radio_sigma_hz=sigma))
        ax.plot(times, residual, '.-', lw=.6, label='Satellite residual')
        ax.fill_between(times, -sigma, sigma, alpha=.2, label='± radio sigma (uncertainty proxy)')
        ax.axvline((times.min()+times.max())/2, color='k', ls=':', lw=.8)
        ax.axhline(0, color='k', lw=.5)
        ax.set(title=arm, xlabel='Scan time (s)', ylabel='Hz'); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.savefig(args.output/'residual_scale.png', dpi=140); plt.close(fig)
    sources = [inventory, args.trial/'protocol.json', args.trial/'new_family.json']
    write(args.output/'result.json', dict(job=protocol['job'], target=target, rows=rows, points=points,
        radio_noise_metadata={k:v for k,v in meta.items() if k!='per_observation_noise_sigma_hz'},
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        changes_to_fit=False, GPS_used=False, grouping='timestamp midpoint and fixed scanwide 12-second blocks',
        caveat='Descriptive fitted residuals; scatter includes model mismatch and is not an independent measurement-noise estimate. Radio sigma excludes shared receiver/orbit uncertainty. No acceptance rule or corrected position is inferred.'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'trial', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    run(p.parse_args())
