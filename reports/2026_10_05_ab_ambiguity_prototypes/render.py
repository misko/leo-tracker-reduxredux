"""Render matched ambiguity experiments; no model or fit changes."""
import csv
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from experiment import HERE, ARMS, MODES, inputs, Objective, metrics, digest

COLORS = {'fitted-c': '#0072B2', 'zero-c': '#D55E00'}
NAMES = {'fitted-c': 'Fitted c', 'zero-c': 'c = 0'}


def collect():
    rows = []
    verification = []
    for scan in ('A', 'B'):
        data, meta, saved, frozen, receipt = inputs(scan)
        for mode in MODES:
            for arm in ARMS:
                path = HERE/'polished'/f'{scan}-{arm}-{mode}.json'
                record = json.loads(path.read_text())
                obj = Objective(data, meta['rf_center_hz'], frozen, arm, mode)
                actual = metrics(obj, data, frozen, record['best'], arm, meta['rf_center_hz'])
                np.testing.assert_allclose(actual['objective'], record['best']['objective'], atol=1e-7, rtol=0)
                if actual['hard_invisible_windows']:
                    raise ValueError('Hard-assignment fit violates horizon constraint')
                for key, value in actual.items():
                    np.testing.assert_allclose(value, record['metrics'][key], atol=1e-7, rtol=0)
                diagnostic = Objective(data, meta['rf_center_hz'], frozen, arm, 'penalty_1')
                diagnostic.evaluate(np.array(record['best']['vector']))
                actual['mean_conditional_minentropy'] = diagnostic.likelihood.last_result['ambiguity_penalty']/len(data.times)
                rows.append(dict(scan=scan, arm=arm, mode=mode, **actual,
                    roof_gradient_norm_per_100m=record['roof_metrics']['gradient_norm_per_100m'],
                    roof_gradient_east_per_100m=record['roof_metrics']['gradient_per_100m'][0],
                    roof_gradient_north_per_100m=record['roof_metrics']['gradient_per_100m'][1],
                    roof_nuisance_converged=record['roof_metrics']['converged'],
                    east_m=1000*record['best']['point_km'][0], north_m=1000*record['best']['point_km'][1],
                    elapsed_s=record['elapsed_s'], source_sha256=digest(path)))
                verification.append(dict(scan=scan, arm=arm, mode=mode,
                    objective_reconstruction_error=actual['objective']-record['best']['objective'],
                    mask_sha256=record['mask_sha256'], input_sha256=record['input_sha256']))
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    for r in rows:
        base = lookup[r['scan'], r['arm'], 'baseline']
        r['position_change_vs_baseline_m'] = r['position_error_m']-base['position_error_m']
        r['common_full_score_change'] = r['common_full_score']-base['common_full_score']
    with (HERE/'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (HERE/'verification.json').write_text(json.dumps(verification, indent=2))
    return rows, lookup


def decorate(ax):
    ax.set_xticks(range(len(MODES)), list(MODES.values()), fontsize=10)
    ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)


def position_plot(lookup):
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharey=True)
    for ax, scan in zip(axes, ('A', 'B')):
        for j, arm in enumerate(ARMS):
            series = [lookup[scan, arm, mode] for mode in MODES]
            x = np.arange(len(MODES))+(j-.5)*.36
            ys = [r['position_error_m'] for r in series]
            ax.bar(x, ys, width=.34, color=COLORS[arm], label=NAMES[arm], alpha=.9)
            for x0, y, row in zip(x, ys, series):
                ax.text(x0, y+35, f'{y:.0f}', ha='center', fontsize=10)
                if row['boundary']:
                    ax.scatter([x0], [y], marker='^', facecolor=COLORS[arm], edgecolor='black', s=65, zorder=4)
                if not row['converged']:
                    ax.scatter([x0], [y], marker='x', c='black', s=55, zorder=5)
        ax.set_title(f'Scan {scan} · independent position search', fontsize=15)
        ax.axhline(2000, color='.45', linestyle=':', linewidth=1)
        ax.set_ylim(0, 2260); ax.set_ylabel('Distance from known roof (m)')
        decorate(ax)
    axes[0].legend(frameon=False, loc='upper left')
    fig.suptitle('Ambiguity prototypes · do fewer competing explanations improve position?', fontsize=18, y=.99)
    fig.text(.5, .045, 'Same frozen input bank, timing priors, three starts and maximum search budgets in both RF arms. No new GLRT or greedy run.\n'
             'Drop = second responsibility >5%, plus clutter-dominated windows. Hard = fixed winner with Gaussian loss, no satellite switching or clutter fallback.\n'
             'Masks/identities frozen from the saved fitted-c position fit. Triangles = 2 km boundary; × = not converged. Development diagnostic, not blind validation.',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .95))
    fig.savefig(HERE/'position-error.png', dpi=160); plt.close(fig)


def diagnostics_plot(lookup):
    specs = [('full_ambiguous_percent', 'Windows with second satellite >5%', 'Share of original fitted windows (%)'),
             ('full_fixed_winner_rms_hz', 'Frequency fit on the SAME original windows', 'Frozen baseline-winner RMS (Hz)'),
             ('full_clutter_winner_percent', 'Windows where clutter beats every satellite', 'Share of original fitted windows (%)')]
    fig, axes = plt.subplots(2, 3, figsize=(19, 10))
    for i, scan in enumerate(('A', 'B')):
        for ax, (metric, title, ylabel) in zip(axes[i], specs):
            for arm in ARMS:
                rs = [lookup[scan, arm, mode] for mode in MODES]
                ys = [r[metric] for r in rs]
                ax.plot(range(len(MODES)), ys, '-o', color=COLORS[arm], label=NAMES[arm], ms=5)
                for j, row in enumerate(rs):
                    if not row['converged']:
                        ax.scatter([j], [ys[j]], marker='x', c='black', zorder=5)
            ax.set_title(f'Scan {scan} · {title}', fontsize=12)
            ax.set_ylabel(ylabel); decorate(ax)
            ax.set_xticks(range(len(MODES)), [x.replace('\n', ' ') for x in MODES.values()], rotation=38, ha='right', fontsize=9)
            high = max(lookup[scan, arm, mode][metric] for arm in ARMS for mode in MODES)
            ax.set_ylim(0, max(1., high*1.12))
    axes[0, 0].legend(frameon=False)
    fig.suptitle('Position accuracy and frequency fit are different outcomes', fontsize=19)
    fig.text(.5, .035, 'Every diagnostic re-evaluates the original soft model on ALL original fitted windows at the new parameters—even for hard/drop variants.\n'
             'Fixed-winner RMS uses the SAME saved baseline labels in every arm. It does not relabel difficult points or remove discarded windows from the comparison.\n'
             'Reduced ambiguity is not proof of correct satellite identity. Penalties can move competing orbits away; × marks unconverged position fits.',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .94))
    fig.savefig(HERE/'diagnostics.png', dpi=150); plt.close(fig)


def gradient_plot(lookup):
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, scan in zip(axes, ('A', 'B')):
        for arm in ARMS:
            rs = [lookup[scan, arm, mode] for mode in MODES]
            ys = [r['roof_gradient_norm_per_100m'] for r in rs]
            ax.plot(range(len(MODES)), ys, '-o', color=COLORS[arm], label=NAMES[arm])
            for j, row in enumerate(rs):
                if not row['roof_nuisance_converged']:
                    ax.scatter([j], [ys[j]], marker='x', c='black', zorder=5)
        decorate(ax)
        ax.set_xticks(range(len(MODES)), [x.replace('\n', ' ') for x in MODES.values()], rotation=30, ha='right', fontsize=9)
        ax.set_title(f'Scan {scan}'); ax.set_ylim(bottom=0)
        ax.set_ylabel('Profile-gradient magnitude (score / 100 m)')
    axes[0].legend(frameon=False)
    fig.suptitle('Remaining score gradient at the known roof', fontsize=18)
    fig.text(.5, .025, 'Nuisance parameters refitted at the roof after each variant. × = nuisance profile not converged.\n'
             'Raw score gradients are not directly comparable evidence strengths across different losses or numbers of retained windows.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .93))
    fig.savefig(HERE/'roof-gradient.png', dpi=160); plt.close(fig)


def report(rows, lookup):
    head = '<!doctype html><meta charset="utf-8"><title>A/B ambiguity prototypes</title><style>body{font:16px system-ui;max-width:1350px;margin:40px auto;padding:0 24px;line-height:1.55}img{width:100%}table{border-collapse:collapse}th,td{padding:7px;border-bottom:1px solid #ddd;text-align:right}th:first-child,td:first-child{text-align:left}code{background:#eee;padding:3px}</style>'
    body = '<h1>A/B ambiguity prototypes</h1><p>Independent 2 km searches; frozen top-one T1-AT v1 inputs; matched fitted-c and c=0 arms. No new calibration, greedy selection, GLRT refinement or orbit bank.</p>'
    body += '<p>Two-pass diagnostic: the saved fitted-c position solution provides responsibilities, masks and fixed winners. This is not a pre-position or blind-validation result. All retained windows enter training; no folds.</p>'
    body += '<h2>Models</h2><p>Baseline: original soft single-window finite-set likelihood, sigma 200 Hz, q=0.8/K, clutter=2; timing priors common sigma 10 s and relative sigma 1 s, total shift bounded ±20 s. Extra RX lines and common RF coefficient are refitted as before.</p>'
    body += '<p>Clutter-only filter removes windows whose top satellite does not beat clutter. Drop+soft also removes second-satellite responsibility &gt;5%. Hard-only uses the clutter-only mask; drop+hard uses the ambiguity+clutter mask. Hard loss is a pure wrapped Gaussian for the frozen winner, with no reassignment and no clutter fallback. No weights are renormalized after dropping.</p>'
    body += '<p>Penalty variants keep all original windows and add η × sum[-log(max satellite probability conditional on signal)], with η=1 or 2. Probabilities change with trial position and timings. This is an explicitly heuristic regularizer, and may favor artificial separation of legitimate competing predictions.</p>'
    body += '<p>Same satellite bank and masks in the two RF arms. The c=0 arm only disables c in the final position fit; the upstream saved fitted-c receiver baseline remains shared. Original satellite timing priors remain, even for satellites with no retained fixed-label windows.</p>'
    body += '<p>All variants receive the same maximum continuation policy (20 seconds SLSQP, 25 seconds Fisher), stopping early on convergence. Unconverged roof nuisance profiles receive up to 12 extra seconds and a joint cross-start if they uncover a lower score.</p>'
    body += '<h2>Main findings</h2><p>With fitted c, the original soft baseline remains best for A (180 m); neither prototype improves it. B improves modestly with ambiguity penalty η=2 (1,142 → 1,035 m). Drop+hard gives 406 m for A and 1,084 m for B. With c=0, the changes help more, but those gains must not be presented as improvements over the stronger fitted-c baseline.</p>'
    body += '<p>The hard-filtered fit retains 3,091/3,644 windows for A and 3,036/3,460 for B, including the separate clutter safeguard. The ambiguity penalties only modestly reduce conditional identity uncertainty. Ambiguous windows can still carry useful position information; this two-scan diagnostic does not justify replacing the baseline.</p>'
    body += '<h2>Position accuracy</h2><img src="position-error.png">'
    body += '<table><tr><th>Variant</th><th>A fitted c (m)</th><th>A c=0 (m)</th><th>B fitted c (m)</th><th>B c=0 (m)</th></tr>'
    for mode, label in MODES.items():
        body += '<tr><td>'+html.escape(label.replace('\n', ' '))+'</td>'
        for scan in ('A', 'B'):
            for arm in ARMS:
                r = lookup[scan, arm, mode]
                suffix = ' boundary' if r['boundary'] else ''
                suffix += ' UNCONVERGED' if not r['converged'] else ''
                body += f'<td>{r["position_error_m"]:.1f}{suffix}</td>'
        body += '</tr>'
    body += '</table><h2>Matched-window diagnostics</h2><img src="diagnostics.png"><h2>Roof gradient</h2><img src="roof-gradient.png">'
    body += '<h2>Scope and validation</h2><p>Raw objective values across models and subsets are not comparable. The CSV also includes the original full-window baseline score re-evaluated at every result. Position error is reported separately. Three shared archived starts plus polishing and roof cross-starts find local candidates; they do not certify a global minimum. A boundary optimum is not an unconstrained minimum.</p>'
    body += f'<p>{sum(r["converged"] for r in rows)}/{len(rows)} position fits pass the original 0.001 KKT threshold. All final objectives and diagnostics reproduce from saved parameters; no hard-assignment final result violates the visibility guard.</p>'
    body += '<p><a href="results.csv">Full metrics CSV</a> · <a href="protocol.json">Protocol</a> · <a href="verification.json">Reconstruction audit</a> · <a href="experiment.py">Experiment</a> · <a href="likelihood.py">Loss implementation</a></p>'
    (HERE/'report.html').write_text(head+body)


if __name__ == '__main__':
    rows, lookup = collect()
    position_plot(lookup); diagnostics_plot(lookup); gradient_plot(lookup); report(rows, lookup)
    print('Validated', len(rows), 'fits; converged', sum(r['converged'] for r in rows))
