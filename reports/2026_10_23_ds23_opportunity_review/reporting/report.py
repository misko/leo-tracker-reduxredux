"""Frozen-input descriptive reporting; no fitting or policy selection."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STAGES = Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/tables/stage_changes.csv')


def summarize(rows):
    out = []
    for arm in ('c0', 'fitted_c'):
        rr = [r for r in rows if r['arm'] == arm]
        assert len(rr) == 410 and len({r['case'] for r in rr}) == 410
        for stage, error, count, delta in (
            ('reference', 'reference_error_km', 'reference_associated_points', None),
            ('graph', 'ordinary_graph_error_km', 'ordinary_graph_associated_points', 'graph_minus_reference'),
            ('final_native_policy', 'final_error_km', 'final_associated_points', 'native_minus_graph'),
        ):
            e = np.array([float(r[error]) for r in rr])
            d = np.array([float(r[delta + '_error_km']) for r in rr]) if delta else np.zeros(len(rr))
            inc = np.array([int(r[delta + '_associated_points']) for r in rr]) if delta else np.zeros(len(rr), dtype=int)
            out.append(dict(arm=arm, stage=stage, scans=len(rr), mean_error_km=float(e.mean()), median_error_km=float(np.median(e)), p95_error_km=float(np.percentile(e, 95)), associated_points=sum(int(r[count]) for r in rr), incremental_points=int(inc.sum()), scans_gaining_points=int((inc > 0).sum()), scans_losing_points=int((inc < 0).sum()), regressions_gt_0_5km=int((d > .5).sum()), improvements_gt_0_5km=int((d < -.5).sum()), mean_incremental_error_km=float(d.mean())))
    return out


def decompose(rows):
    out = []
    for case in ('DS23-0259', 'DS23-0353'):
        for arm in ('c0', 'fitted_c'):
            pair = {r['endpoint']: r for r in rows if r['case'] == case and r['arm'] == arm}
            g, n = pair['graph_parent'], pair['ordinary_native']
            curved = n['curved_objective'] - g['curved_objective']
            contrasts = n['parts']['contrasts']['total'] - g['parts']['contrasts']['total']
            levels = n['parts']['levels_given_contrasts']['total'] - g['parts']['levels_given_contrasts']['total']
            total = n['total_objective'] - g['total_objective']
            assert abs(curved + contrasts + levels - total) < 1e-8
            out.append(dict(case=case, arm=arm, curved_delta=curved, contrasts_delta=contrasts, conditional_levels_delta=levels, full_score_delta=total, contrast_only_endpoint_delta=curved + contrasts))
    return out


def write_csv(name, rows):
    with (ROOT / 'tables' / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def main():
    stages = list(csv.DictReader(STAGES.open()))
    summary = summarize(stages)
    parts = decompose(json.loads((ROOT / 'mean_shape.json').read_text())['rows'])
    write_csv('stage_summary.csv', summary)
    write_csv('endpoint_score_changes.csv', parts)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for col, arm in enumerate(('c0', 'fitted_c')):
        rr = [r for r in summary if r['arm'] == arm]
        x = np.arange(3)
        axes[0, col].bar(x, [r['associated_points'] for r in rr], color=['#888', '#397eb7', '#db8b35'])
        axes[0, col].set(title=arm, ylabel='Associated points (410 scans)', xticks=x, xticklabels=['Reference', 'Graph', 'Final policy'])
        for key, label in [('mean_error_km', 'Mean'), ('median_error_km', 'Median'), ('p95_error_km', '95th percentile')]:
            axes[1, col].plot(x, [r[key] for r in rr], marker='o', label=label)
        axes[1, col].set(ylabel='Position error (km)', xticks=x, xticklabels=['Reference', 'Graph', 'Final policy'])
        axes[1, col].legend()
    fig.suptitle('Frozen DS23 stage outcomes; final policy includes rescue/fallback decisions')
    fig.savefig(ROOT / 'figures' / 'stage_counts_accuracy.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    keys = [('curved_delta', 'Curved penalty'), ('contrasts_delta', 'Native temporal contrasts'), ('conditional_levels_delta', 'Native conditional levels')]
    for ax, case in zip(axes, ('DS23-0259', 'DS23-0353')):
        rr = [r for r in parts if r['case'] == case]
        for i, (key, label) in enumerate(keys):
            ax.bar(np.arange(2) + (i - 1) * .24, [r[key] for r in rr], .24, label=label)
        ax.axhline(0, color='black', linewidth=.7)
        ax.set(title=case, ylabel='Score change: ordinary native − graph', xticks=[0, 1], xticklabels=['c=0', 'Fitted c'])
    axes[0].legend(fontsize=8)
    fig.suptitle('Exact shared Gaussian factorization at frozen endpoints; lower score favored')
    fig.savefig(ROOT / 'figures' / 'endpoint_score_components.png', dpi=160); plt.close(fig)
    inputs = [STAGES, ROOT / 'mean_shape.json', ROOT / 'protocol.json', ROOT / 'source' / 'mean_shape.py', ROOT / 'source' / 'test_mean_shape.py', Path(__file__), Path(__file__).with_name('test_report.py')]
    receipt = dict(status='complete', stage_rows=len(stages), matched_scans_per_arm=410, endpoint_evaluations=8, no_new_fit=True, interpretation='Contrast-only score is an alternative-model endpoint difference only; no fit or localization improvement claim.', input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    (ROOT / 'reporting' / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
