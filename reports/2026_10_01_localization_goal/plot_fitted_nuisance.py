"""Empirical fitted MAP nuisance distributions from sealed64baseline fits."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
evaluation_path = HERE/'regression-v1-evaluation-64.json'
assert digest(evaluation_path) == 'sha256:97be104787783e3bb81d851ba8664f3a26ac93fe10b617aae605ad8b13372bd7'
evaluation = json.loads(evaluation_path.read_text())
assert evaluation['accepted_count'] == 64
inputs = {str(evaluation_path): digest(evaluation_path)}
scans, satellites = [], []
for row in evaluation['rows']:
    unit = row['unit']
    paths = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == row['receipt_sha256']
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
    parent = json.loads(path.read_text())
    assert parent['best']['converged']
    state = np.asarray(parent['best']['mean'])
    group_path = HERE/'group-influence-v1'/f'{unit}.json'
    assert digest(group_path) == group_path.with_suffix('.sha256').read_text().strip()
    groups = json.loads(group_path.read_text())
    assert groups['parent_sha256'] == digest(path)
    assert groups['source_sha256'] == digest(HERE/'diagnose_group_influence.py')
    assert groups['group_count'] == len(groups['groups'])
    inputs.update({str(p): digest(p) for p in [path, group_path]})
    active = [5+g['candidate_index'] for g in groups['groups']]
    assert len(active) == len(set(active))
    scans.append(dict(unit=unit, dataset=unit.split('-')[0], clock_s=float(state[2]),
        drift_rx0_hz_s=float(state[3]), drift_rx1_hz_s=float(state[4]), active_satellites=len(active)))
    for group in groups['groups']:
        epoch = float(state[5+group['candidate_index']])
        satellites.append(dict(unit=unit, dataset=unit.split('-')[0], norad_id=group['norad_id'],
            tracks=group['track_count'], clock_s=float(state[2]), epoch_s=epoch,
            effective_time_s=float(state[2]+epoch)))


def stats(values, sigma):
    x = np.asarray(values)
    return dict(count=len(x), mean=float(x.mean()), median=float(np.median(x)),
        std=float(x.std(ddof=1)), p05=float(np.percentile(x, 5)), p95=float(np.percentile(x, 95)),
        minimum=float(x.min()), maximum=float(x.max()), prior_sigma=sigma,
        outside2sigma=int(np.sum(abs(x) > 2*sigma)), outside3sigma=int(np.sum(abs(x) > 3*sigma)))


series = {
    'clock': ([r['clock_s'] for r in scans], 1.),
    'drift_rx0': ([r['drift_rx0_hz_s'] for r in scans], .5),
    'drift_rx1': ([r['drift_rx1_hz_s'] for r in scans], .5),
    'satellite_epoch': ([r['epoch_s'] for r in satellites], .5),
    'effective_time': ([r['effective_time_s'] for r in satellites], np.sqrt(1.25)),
}
summaries = {k: stats(v, sigma) for k, (v, sigma) in series.items()}
result = dict(summary=summaries, scans=scans, satellites=satellites, inputs=inputs,
    source_sha256={str(Path(__file__)): digest(__file__)},
    qualification='Empirical distributions of fitted MAP values, not posterior samples or measured '
    'hardware errors. One clock/drift per scan, one epoch per active inferred satellite per scan; '
    'unused catalogue epochs excluded. Repeated satellites and nearby scans are dependent. '
    'Gaussian overlays are model priors; effective-time marginal sigma=sqrt(1²+.5²), '
    'with shared-clock correlation across satellites. Frequency constants are projected out and '
    'are not retained fitted state coordinates; no histogram of fictitious zero offsets.')
output = HERE/'fitted-nuisance-distributions-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
for name, data in [('scans', scans), ('satellites', satellites)]:
    with (HERE/f'fitted-nuisance-{name}-v1.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
panels = [(['clock'], 'Shared clock correction', 'seconds'),
          (['drift_rx0', 'drift_rx1'], 'Receiver frequency drift', 'Hz / second'),
          (['satellite_epoch'], 'Active satellite timing correction', 'seconds'),
          (['effective_time'], 'Combined timing: clock + satellite correction', 'seconds')]
colors = ['#2879ad', '#e58a32']
for ax, (keys, title, unit) in zip(axes.ravel(), panels, strict=True):
    sigma = series[keys[0]][1]
    values = np.concatenate([series[k][0] for k in keys])
    lo, hi = min(values.min(), -3*sigma), max(values.max(), 3*sigma)
    padding = .04*(hi-lo)
    lo, hi = lo-padding, hi+padding
    bins = np.linspace(lo, hi, 36 if len(values) > 200 else 23)
    for k, color in zip(keys, colors):
        label = k.replace('drift_', '').upper() if len(keys) > 1 else f'Fitted values (n={len(series[k][0]):,})'
        ax.hist(series[k][0], bins=bins, density=True, histtype='stepfilled',
                alpha=.45, color=color, label=label)
        ax.axvline(np.median(series[k][0]), color=color, ls=':', lw=1.6)
    grid = np.linspace(lo, hi, 800)
    prior = np.exp(-.5*(grid/sigma)**2)/(sigma*np.sqrt(2*np.pi))
    ax.plot(grid, prior, color='#303030', ls='--', lw=1.6, label=f'Prior: σ={sigma:.3g}')
    ax.axvline(0, color='#888888', lw=.7)
    ax.set(xlabel=unit, ylabel='Density', title=title, xlim=(lo, hi))
    ax.legend(fontsize=8)
fig.suptitle('Fitted nuisance parameters — original 64-scan joint baseline\n'
             'Histograms are fitted point estimates; dashed curves are priors, dotted lines are medians', fontsize=13)
fig.savefig(HERE/'fitted-nuisance-distributions-v1.png', dpi=170)

fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), layout='constrained')
for ds, color in zip(['DS9', 'DS10', 'DS11'], ['#2879ad', '#e58a32', '#41905c']):
    subset = [r for r in scans if r['dataset'] == ds]
    for ax, field in zip(axes, ['clock_s', 'drift_rx0_hz_s', 'drift_rx1_hz_s'], strict=True):
        values = np.sort([r[field] for r in subset])
        ax.step(values, np.arange(1, len(values)+1)/len(values), where='post', label=ds, color=color)
for ax, title, unit in zip(axes, ['Clock correction', 'RX0 drift', 'RX1 drift'],
                           ['seconds', 'Hz / second', 'Hz / second'], strict=True):
    ax.set(title=title, xlabel=unit, ylabel='Fraction of scans', ylim=(0, 1.03))
    ax.axvline(0, color='gray', lw=.7)
    ax.legend()
fig.suptitle('Dataset breakdown of fitted nuisance parameters (not independent posterior samples)')
fig.savefig(HERE/'fitted-nuisance-by-dataset-v1.png', dpi=160)
print(json.dumps(summaries, indent=2))
