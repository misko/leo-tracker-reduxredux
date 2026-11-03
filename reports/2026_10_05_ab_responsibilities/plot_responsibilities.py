"""Replay saved A/B all-window position fits; no optimization or new associations.

The population is previously assigned top-one receiver/channel/probe windows,
not every passing GLRT window. Compare saved fitted-c and zero-c fits using
identical observations and selected satellite banks. Absolute responsibilities
include the clutter alternative; do not renormalize conditional on signal.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOURCE = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
ARMS = ('fitted-c', 'zero-c')
COLORS = {'fitted-c': '#0072B2', 'zero-c': '#D55E00'}
LABELS = {'fitted-c': 'Fitted c', 'zero-c': 'c = 0'}
THRESHOLDS = (0., 1e-6, .001, .01, .05, .1, .5)


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def counts_above(probability, threshold):
    """Strictly positive at zero; inclusive threshold elsewhere."""
    p = np.asarray(probability, dtype=float)
    if p.ndim != 2 or not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('Expected a finite window-by-satellite probability matrix')
    if not 0 <= threshold <= 1:
        raise ValueError('Threshold must be a probability')
    return np.sum(p > 0 if threshold == 0 else p >= threshold, axis=1)


def summarize(p, clutter):
    p = np.asarray(p)
    if not np.allclose(p.sum(axis=1) + clutter, 1., atol=2e-12, rtol=0):
        raise ValueError('Satellite and clutter responsibilities must sum to one')
    n, k = p.shape
    result = dict(windows=n, selected_satellites=k,
                  positive_pairs=int(np.count_nonzero(p)),
                  exact_zero_pairs=int(np.sum(p == 0)),
                  minimum_positive_probability=float(p[p > 0].min()),
                  maximum_probability=float(p.max()),
                  mean_clutter_probability=float(np.mean(clutter)),
                  clutter_winner_windows=int(np.sum(clutter > p.max(axis=1))),
                  thresholds={})
    for threshold in THRESHOLDS:
        counts = counts_above(p, threshold)
        histogram = np.bincount(counts, minlength=k+1)
        result['thresholds'][str(threshold)] = dict(
            histogram=histogram.tolist(), mean_satellites=float(counts.mean()),
            median_satellites=float(np.median(counts)), maximum_satellites=int(counts.max()),
            zero=int(np.sum(counts == 0)), one=int(np.sum(counts == 1)),
            multiple=int(np.sum(counts >= 2)), multiple_percent=float(100*np.mean(counts >= 2)))
    return result


def manual_responsibilities(measured, predicted, visible, sigma, q, clutter, alias):
    """Independent one-observation formula check against the saved-model engine."""
    residual = (measured[:, None] - predicted + alias/2) % alias - alias/2
    log_density = logsumexp(np.stack([
        -.5*((residual + shift*alias)/sigma)**2 - np.log(sigma*np.sqrt(2*np.pi))
        for shift in (-1, 0, 1)]), axis=0)
    log_signal = np.where(visible, np.log(q/(1-q)) + log_density, -np.inf)
    normalizer = np.logaddexp(np.log(clutter/alias), logsumexp(log_signal, axis=1))
    return np.exp(log_signal - normalizer[:, None]), np.exp(np.log(clutter/alias)-normalizer)


def load_case(scan, arm):
    for name in ('2026_10_02_localization_benchmark', '2026_10_02_multiscan_localization',
                 '2026_10_02_ds13_timing_em'):
        path = str(REPO/'reports'/name)
        if path not in sys.path:
            sys.path.insert(0, path)
    from rf_calibration_diagnostic import CalibrationObjective
    folder = SOURCE/scan
    meta = json.loads((folder/'input.json').read_text())
    saved = json.loads((folder/'all-100.json').read_text())
    if digest(folder/'input.npz') != meta['input_sha256']:
        raise ValueError('Input hash mismatch')
    if saved['input_metadata']['input_sha256'] != meta['input_sha256']:
        raise ValueError('Fit/input provenance mismatch')
    with np.load(folder/'input.npz', allow_pickle=False) as z:
        data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
    if len(np.unique(data.group)) != len(data.times):
        raise ValueError('Expected exactly one selected candidate per window')
    if saved['numbers'] != data.numbers.tolist() or saved['original_rows'] != data.original_rows.tolist():
        raise ValueError('Saved satellite or observation order changed')
    obj = CalibrationObjective(data, data.initial, np.arange(len(data.numbers)), False, 120.)
    obj.center = meta['rf_center_hz']
    obj.features = ((data.rf - obj.center)/1e9)[:, None]
    obj.likelihood.features = obj.features
    obj.base.minimum_shift_s = max(obj.base.minimum_shift_s, -20.)
    obj.base.maximum_shift_s = min(obj.base.maximum_shift_s, 20.)
    obj.base.deadline = float('inf')
    if arm == 'zero-c':
        obj.bounds[-1] = (0., 0.)
    best = saved['arms'][arm]['best']
    vector = np.asarray(best['vector'])
    if arm == 'zero-c' and vector[-1] != 0:
        raise ValueError('Nonzero c in c=0 arm')
    value, _ = obj.evaluate(vector)
    if abs(value-best['objective']) > 1e-7:
        raise ValueError('Saved objective does not reproduce')
    result = obj.likelihood.last_result
    p = np.asarray(result['row_association_probability'])
    clutter = 1-p.sum(axis=1)
    predicted, visible = obj.base.predict(vector[:obj.size])
    predicted += (obj.features @ obj.likelihood.coefficients)[:, None]
    check, check_clutter = manual_responsibilities(
        data.measured, predicted, visible, obj.base.sigma_hz,
        obj.likelihood.detection_probability, obj.likelihood.clutter_rate, obj.likelihood.alias_hz)
    np.testing.assert_allclose(p, check, atol=2e-12, rtol=2e-12)
    np.testing.assert_allclose(clutter, check_clutter, atol=2e-12, rtol=2e-12)
    stats = summarize(p, clutter)
    stats.update(scan=scan, arm=arm, evaluation='saved best all-100 position fit',
                 sigma_hz=obj.base.sigma_hz, detection_probability=obj.likelihood.detection_probability,
                 clutter_rate=obj.likelihood.clutter_rate, alias_hz=obj.likelihood.alias_hz,
                 saved_position_error_m=1000*float(np.linalg.norm(best['point_km'])),
                 converged=bool(best['success'] and not best['fixed_location']),
                 objective=value, objective_reconstruction_error=value-best['objective'],
                 formula_max_error=float(np.max(abs(p-check))),
                 sources={str(folder/name): digest(folder/name)
                          for name in ('input.npz', 'input.json', 'all-100.json')})
    return data, p, clutter, stats


def plot_counts(cases):
    fig, axes = plt.subplots(2, 3, figsize=(18, 9))
    for row, scan in enumerate(('A', 'B')):
        n, k = cases[scan, 'fitted-c'][1].shape
        for col, threshold in enumerate((0., .01, .05)):
            ax = axes[row, col]
            maximum = max(int(counts_above(cases[scan, arm][1], threshold).max()) for arm in ARMS)
            x = np.arange(maximum+1)
            for j, arm in enumerate(ARMS):
                counts = np.bincount(counts_above(cases[scan, arm][1], threshold), minlength=len(x))
                bars = ax.bar(x+(j-.5)*.38, counts/n*100, width=.36, color=COLORS[arm], label=LABELS[arm])
                if threshold:
                    for bar, count in zip(bars, counts):
                        if count:
                            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1.1,
                                    f'{100*count/n:.1f}', ha='center', va='bottom', fontsize=8)
            title = 'Strictly nonzero: probability > 0' if threshold == 0 else f'Responsibility ≥ {100*threshold:g}%'
            ax.set_title(f'Scan {scan} · {title}\n{n:,} fitted windows · {k} selected satellites', fontsize=12)
            ax.set_xlabel('Number of satellites for one GLRT window')
            ax.set_ylabel('Share of fitted windows (%)')
            ax.set_xticks(x if maximum < 10 else x[::2])
            ax.set_ylim(0, 100 if threshold else 40)
            ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    axes[0, 0].legend(frameon=False)
    fig.suptitle('Scan A + B · how many satellites share responsibility for one GLRT?', fontsize=19, y=.99)
    fig.text(.5, .045, 'Same assigned top-one 20 ms receiver/channel windows and selected bank in both RF arms; each arm at its saved fitted position.\n'
             'Clutter remains in the probability denominator, but is not counted as a satellite. Thresholds are display-only: no fits changed.\n'
             'Strictly nonzero includes negligible floating-point tails; exact zero may mean invisibility or numerical underflow. Unassigned input windows are excluded.',
             ha='center', va='center', fontsize=10)
    fig.tight_layout(rect=(0, .11, 1, .94))
    fig.savefig(HERE/'satellites-per-window.png', dpi=160)
    plt.close(fig)


def plot_values(cases):
    bins = np.array([0, 1e-6, .001, .01, .05, .25, .5, .75, 1.])
    labels = ['<0.0001%', '0.0001–0.1%', '0.1–1%', '1–5%', '5–25%', '25–50%', '50–75%', '75–100%']
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), sharey=True)
    for ax, scan in zip(axes, ('A', 'B')):
        for j, arm in enumerate(ARMS):
            p = cases[scan, arm][1]
            positive = p[p > 0]
            hist, _ = np.histogram(positive, bins)
            ax.bar(np.arange(len(labels))+(j-.5)*.38, 100*hist/len(positive), width=.36,
                   color=COLORS[arm], label=f'{LABELS[arm]}: {len(positive):,} positive pairs')
        ax.set_title(f'Scan {scan} · positive satellite/window responsibilities')
        ax.set_xticks(np.arange(len(labels)), labels, rotation=28, ha='right')
        ax.set_xlabel('Absolute responsibility (unequal-width bins)')
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True); ax.legend(frameon=False, fontsize=10)
    axes[0].set_ylabel('Share of positive satellite/window pairs (%)')
    fig.suptitle('A numerical nonzero is often only a negligible Gaussian tail', fontsize=19)
    fig.text(.5, .035, 'Each satellite/window pair is counted once; one window can contribute several pairs. Exact zeros excluded.\n'
             'Probabilities include clutter competition; these are not independent detections or confirmed satellite identities.',
             ha='center', va='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .92))
    fig.savefig(HERE/'responsibility-values.png', dpi=160)
    plt.close(fig)


def main():
    cases, all_stats, windows, thresholds = {}, [], [], []
    for scan in ('A', 'B'):
        for arm in ARMS:
            data, p, clutter, stats = load_case(scan, arm)
            cases[scan, arm] = (data, p, clutter, stats)
            all_stats.append(stats)
            np.savez_compressed(HERE/f'{scan}-{arm}-responsibilities.npz',
                                responsibility=p, clutter=clutter, numbers=data.numbers,
                                original_rows=data.original_rows, group=data.group,
                                times=data.times, receiver=data.receiver, channel=data.channel)
            order = np.argsort(p, axis=1)
            for i in range(len(p)):
                windows.append(dict(scan=scan, arm=arm, original_row=int(data.original_rows[i]),
                    group=int(data.group[i]), time_s=float(data.times[i]), receiver=int(data.receiver[i]),
                    channel=int(data.channel[i]), original_owner=int(data.owners[i]),
                    best_satellite=int(data.numbers[order[i, -1]]), best_probability=float(p[i, order[i, -1]]),
                    second_satellite=int(data.numbers[order[i, -2]]), second_probability=float(p[i, order[i, -2]]),
                    clutter_probability=float(clutter[i]), positive_satellites=int(np.sum(p[i] > 0)),
                    satellites_ge_1pct=int(np.sum(p[i] >= .01)), satellites_ge_5pct=int(np.sum(p[i] >= .05))))
            for threshold, values in stats['thresholds'].items():
                thresholds.append(dict(scan=scan, arm=arm, threshold=float(threshold),
                                       windows=len(p), **{k:v for k,v in values.items() if k != 'histogram'}))
            print(scan, arm, stats['thresholds']['0.01'], flush=True)
        a, b = cases[scan, 'fitted-c'][0], cases[scan, 'zero-c'][0]
        for key in ('original_rows', 'numbers', 'measured', 'times'):
            np.testing.assert_array_equal(getattr(a, key), getattr(b, key))
    for name, rows in (('windows.csv', windows), ('threshold-summary.csv', thresholds)):
        with (HERE/name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    (HERE/'summary.json').write_text(json.dumps(dict(scope=__doc__, cases=all_stats,
        script_sha256=digest(Path(__file__)), notes=[
        'Saved independent 2 km all-100 fits. No cone weighting in these historical A/B fits.',
        'Both c arms retain the same fitted-c upstream calibration baseline and input bank.',
        'Absolute responsibilities, with clutter. Not normalized conditional on a satellite.',
        'Positive counts are numerical, not a defensible-association criterion.',
        'Only previously assigned top-one windows were fitted; no claim about all passing GLRT.']), indent=2))
    plot_counts(cases)
    plot_values(cases)


if __name__ == '__main__':
    main()
