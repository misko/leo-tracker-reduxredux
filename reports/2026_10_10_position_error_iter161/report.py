"""Postseal descriptive aggregation; no fitting or operational selection."""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODES = ('full', 'train0', 'train1')
ARMS = ('zero-c', 'fitted-c')


def stats(values):
    import numpy as np
    values = list(values)
    if not values:
        return dict(n=0, mean=None, median=None, p95=None, worst=None)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('nonfinite metric')
    return dict(n=len(values), mean=float(np.mean(values)), median=float(np.median(values)),
                p95=float(np.percentile(values, 95)), worst=float(max(values)))


def aggregate(cells):
    """No missing-value imputation; pair only explicitly qualified endpoints."""
    output = []
    for dataset in ('DS16', 'DS17', 'DS18', 'pilot'):
        group = [c for c in cells if dataset == 'pilot' or c['dataset'] == dataset]
        for arm in ARMS:
            full = {c['label']: c for c in group if c['arm'] == arm and c['mode'] == 'full'}
            for mode in MODES:
                rows = [c for c in group if c['arm'] == arm and c['mode'] == mode]
                valid = [c for c in rows if c['status'] == 'qualified' and c.get('error_km') is not None]
                pairs = [(full[c['label']], c) for c in valid
                         if full[c['label']]['status'] == 'qualified'
                         and full[c['label']].get('error_km') is not None]
                deltas = [b['error_km'] - a['error_km'] for a, b in pairs]
                output.append(dict(dataset=dataset, arm=arm, mode=mode, attempted=len(rows),
                    qualified=sum(c['status'] == 'qualified' for c in rows),
                    errors=stats(c['error_km'] for c in valid), paired_delta=stats(deltas),
                    regressions=sum(d > 0 for d in deltas), improvements=sum(d < 0 for d in deltas),
                    paired_full=stats(a['error_km'] for a, b in pairs),
                    paired_candidate=stats(b['error_km'] for a, b in pairs)))
    return output


def predictive_pairs(cells):
    """Same held rows for c comparison; full controls remain in-sample."""
    index = {(c['label'], c['mode'], c['arm']): c for c in cells}
    rows = []
    for cell in cells:
        if cell['arm'] != 'fitted-c' or cell['mode'] == 'full':
            continue
        mode = cell['mode']; held = '1' if mode == 'train0' else '0'
        zero = index[(cell['label'], mode, 'zero-c')]
        row = dict(label=cell['label'], dataset=cell['dataset'], mode=mode, held_fold=held,
                   delta_nll_per_row=None, delta_error_km=None)
        if cell['status'] == zero['status'] == 'qualified':
            a, b = (zero.get('scores') or {}).get(held), (cell.get('scores') or {}).get(held)
            if a and b and a.get('status') == b.get('status') == 'complete':
                if a['observations'] != b['observations'] or a['observations'] <= 0:
                    raise ValueError('held observation counts differ')
                row['delta_nll_per_row'] = (b['nll'] - a['nll']) / a['observations']
            if cell.get('error_km') is not None and zero.get('error_km') is not None:
                row['delta_error_km'] = cell['error_km'] - zero['error_km']
        rows.append(row)
    return rows


def plot(cells, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    labels = list(dict.fromkeys(c['label'] for c in cells))
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    colors = ('#606873', '#258e89', '#cc7832')
    for i, arm in enumerate(ARMS):
        for mode, color, offset in zip(MODES, colors, (-.22, 0, .22)):
            group = {c['label']: c for c in cells if c['arm'] == arm and c['mode'] == mode}
            errors = [group[label].get('error_km') if group[label]['status'] == 'qualified' else None for label in labels]
            axes[i, 0].scatter(np.arange(len(labels)) + offset,
                [v if v is not None else np.nan for v in errors], label=mode, color=color, s=23)
            if mode != 'full':
                held = '1' if mode == 'train0' else '0'
                nlls = []
                for label in labels:
                    c = group[label]; score = (c.get('scores') or {}).get(held) or {}
                    nlls.append(score['nll'] / score['observations'] if c['status'] == 'qualified'
                                and score.get('status') == 'complete' else np.nan)
                axes[i, 1].scatter(np.arange(len(labels)) + offset, nlls,
                                   label=mode + ' opposite fold', color=color, s=23)
        axes[i, 0].set_ylabel(arm + ' position error (km)')
        axes[i, 1].set_ylabel(arm + ' held NLL / observation')
        for ax in axes[i]:
            ax.set_xticks(range(len(labels)), labels, rotation=65, ha='right')
            ax.legend(fontsize=8); ax.grid(alpha=.2)
    axes[0, 0].set_title('Qualified endpoints; failures omitted, counted in table')
    axes[0, 1].set_title('Fixed-parameter prediction; smaller is better')
    fig.savefig(path, dpi=160)
    plt.close(fig)


def markdown(summary):
    lines = ['# Matched full-data and grouped-training fits', '',
        '![Position and predictive fit](comparison.png)', '',
        'This is a consumed-data pilot with four members per dataset, not the full DS16/DS17/DS18 cohorts. '
        'Both c arms use the same zero-c starting state. Training-fold solutions predict the opposite fold '
        'without updating parameters. Full-data controls are fresh fits; they are not historical B7 results.', '',
        '| Dataset | Arm | Fit rows | Qualified / attempted | Position mean | Median | p95 | Worst (km) | Paired mean change vs full (km) | Regressions / pairs |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    def show(value): return 'missing' if value is None else f'{value:.4f}'
    for r in summary['aggregates']:
        e, d = r['errors'], r['paired_delta']
        lines.append(f"| {r['dataset']} | {r['arm']} | {r['mode']} | {r['qualified']} / {r['attempted']} | "
            + ' | '.join(show(e[k]) for k in ('mean', 'median', 'p95', 'worst'))
            + f" | {show(d['mean'])} | {r['regressions']} / {d['n']} |")
    lines += ['', 'Means with missing endpoints describe only the explicitly reported qualified subset. '
        'Paired changes use the same members on both sides; no failed solution is replaced by a historical endpoint.', '',
        '## Coverage and failures', '', '| Member | Arm | Fit rows | Status | Position km | Failure |',
        '|---|---|---|---|---:|---|']
    for c in summary['cells']:
        error = str(c.get('error') or c.get('evaluation_error') or '').replace('|', '/').replace('\n', ' ')
        lines.append(f"| {c['label']} | {c['arm']} | {c['mode']} | {c['status']} | {show(c.get('error_km'))} | {error} |")
    lines += ['', '## Interpretation', '',
        'The satellite bank, retained region, starting state and satellite time centers are conditioned on full-data inference. '
        'The split keeps whole visits and overlapping sample support together but does not remove shared clock/orbit errors. '
        'Consequently this is conditional sensitivity on consumed data, not independent validation. '
        'Predictive frequency fit and localization are separate outcomes; neither selects a per-scan winner here.', '',
        'The official 193-member mean and production B7 remain unchanged. No new RF collection, retries, '
        'fallback successes or reference-guided fitting were used. See [fit plan](PLAN.md), '
        '[evaluation plan](EVALUATION_PLAN.md), [numerical protocol](protocol.json), '
        '[evaluation protocol](evaluation_protocol.json), [all results](SUMMARY.json) and '
        '[raw receipts](raw-receipts.tar.gz).', '']
    return '\n'.join(lines)
