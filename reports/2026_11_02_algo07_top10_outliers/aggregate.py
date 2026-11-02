"""Combine sealed case diagnostics; never select inference using evaluation GPS."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def main():
    manifest = read(ROOT / 'run_manifest.json')
    cases = manifest['initial_top10']
    executions = {x['source_case']: x for x in read(ROOT / 'eval/summary.json')}
    assert all(c in executions for c in cases + manifest['ranking_controls'])
    rows = []
    for case in cases:
        a = read(ROOT / 'diagnostics' / case / 'audit.json')
        inv = read(ROOT / 'diagnostics' / case / 'inventory.json')
        run = executions[case]
        assert run['execution_status'] == 'complete', (case, run['execution_status'])
        for arm in ('c0', 'fitted_c'):
            q = a['arms'][arm]
            f = run['final'][arm]
            v = inv['arms'][arm]
            assert v['associated'] == f['associated'], (case, arm, v, f)
            rows.append(dict(case=case, arm=arm, error_m=f['error_m'],
                             selected=run['selected'], associated=f['associated'],
                             total_glrt=v['native'], percent_associated=v['percent'],
                             published_rms_hz=q['rms_hz'],
                             published_phase_reference_change_s=q['phase_reference_check']['phase_change_s']))
    with (ROOT / 'top10_results.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    reranked = []
    for row in manifest['rows']:
        row = dict(row)
        if row['case'] in executions:
            row['initial_error_m'] = row['error_m']
            row['error_m'] = executions[row['case']]['final']['fitted_c']['error_m']
            row['authority'] = 'fresh_promoted_ALGO07_execution_on_saved_research_inputs'
        reranked.append(row)
    reranked.sort(key=lambda r: -r['error_m'])
    assert [r['case'] for r in reranked[:10]] == cases
    (ROOT / 'verified_ranking.json').write_text(json.dumps(reranked, indent=2) + '\n')

    plt.rcParams.update({'font.size': 10})
    fig, axs = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={'width_ratios': [1.5, 1]})
    y = np.arange(len(cases))
    for arm, offset, color in [('c0', -.16, '#5175ac'), ('fitted_c', .16, '#b54843')]:
        rr = [r for r in rows if r['arm'] == arm]
        axs[0].barh(y + offset, [r['error_m']/1000 for r in rr], height=.3, label=arm, color=color)
    axs[0].set(yticks=y, yticklabels=cases, xlabel='Position error (km)', title='Fresh ALGO07 replay: ten largest saved-cohort outliers')
    axs[0].invert_yaxis()
    axs[0].legend()
    for r in rows:
        if r['arm'] != 'fitted_c':
            continue
        axs[1].scatter(r['percent_associated'], r['error_m']/1000, color='#b54843')
        axs[1].annotate(r['case'].split('-')[1], (r['percent_associated'], r['error_m']/1000), xytext=(5, 4), textcoords='offset points')
    axs[1].set(xlabel='Published native GLRT associated (%)', ylabel='Position error (km)', title='Coverage alone does not explain the errors', xlim=(38, 85))
    for ax in axs:
        ax.grid(alpha=.2, axis='x')
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(ROOT / 'top10_overview.png', dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(5, 2, figsize=(14, 19), sharex=False)
    for ax, case in zip(axes.flat, cases):
        folder = ROOT / 'diagnostics' / case
        plan = read(folder / 'fit-plan.json')
        tags = ['continue', 'regional_center', 'phase_sigma_x2'] + [f'omit_{n}' for n in plan['selected']]
        for arm, delta, color in [('c0', -.12, '#5175ac'), ('fitted_c', .12, '#b54843')]:
            baseline = executions[case]['final'][arm]['error_m']/1000
            ax.axvline(baseline, color=color, alpha=.6, linestyle='--')
            for i, tag in enumerate(tags):
                v = read(folder / (tag + '.json'))[arm]
                valid = v['all_gates_pass'] and v['phase_closed'] and v['optimizer_success']
                ax.scatter(v['error_m']/1000, i + delta, marker='o' if valid else 'x', color=color, s=30)
        ax.set(yticks=range(len(tags)), yticklabels=[t.replace('phase_sigma_x2','phase prior SD ×2').replace('regional_center', 'regional restart').replace('omit_', 'omit family ') for t in tags], xlabel='Diagnostic position error (km)', title=case)
        ax.invert_yaxis()
        ax.grid(alpha=.2, axis='x')
    fig.suptitle('Matched c0 (blue) / fitted-c (red) interventions; dashed = published error\nCircles: optimizer, phase closure and residual gates pass. Crosses: at least one fails.\nFamily omission removes evidence: diagnostic sensitivity, not an approved fix.', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .945))
    fig.savefig(ROOT / 'all_interventions.png', dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
