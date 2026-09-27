"""Rebuild the report's figures and catalog from archived result receipts.

Run with Python, numpy and matplotlib from this directory or any working directory.
No IQ, native library, radio, database, or external checkout is required.
"""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent / '2026_09_27_ds5_cached_tracking'
FIGURES = HERE / 'figures'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                     'axes.spines.right': False, 'svg.fonttype': 'none'})


def read(name):
    path = RESEARCH / name
    data = json.loads(path.read_text())
    assert data.get('error') is None, name
    assert data.get('source_lock_stable', data.get('source_stable', False)), name
    return data


def save(fig, name):
    fig.savefig(FIGURES / (name + '.png'), dpi=170, bbox_inches='tight')
    fig.savefig(FIGURES / (name + '.svg'), bbox_inches='tight')
    plt.close(fig)


def main():
    FIGURES.mkdir(exist_ok=True)
    cohorts = [
        ('Constructed validation', 'tone_validation/results.timing_adapter.json'),
        ('Recorded development', 'native_tone_rescue/results.reporting_fix.real.json'),
        ('Recorded holdout', None),
    ]
    metrics = []
    sources = set()
    for cohort, name in cohorts:
        for rate in (2500000, 5000000):
            path = name or f'tone_recorded_holdout/results.{rate}.json'
            sources.add(path)
            data = read(path)
            s = data['summary']['by_rate'][str(rate)]
            methods = s['methods']
            cpu = {k: v['process_cpu']['sum_ms'] / v['process_cpu']['count']
                   for k, v in methods.items()}
            quality = s['quality']['tone_rescue']
            metrics.append(dict(cohort=cohort, rate=rate, reference_cpu_ms=cpu['application'],
                candidate_cpu_ms=cpu['tone_rescue'],
                speedup=methods['tone_rescue']['aggregate_cpu_speedup_vs_application'],
                retained=quality['matched_reference_receivers'],
                reference_positive=quality['reference_positive_receivers'],
                source=path))

    fig, ax = plt.subplots(figsize=(11, 5.6))
    y = np.arange(len(metrics))
    ax.barh(y-.18, [m['reference_cpu_ms'] for m in metrics], .32, color='#64748b', label='Main application')
    ax.barh(y+.18, [m['candidate_cpu_ms'] for m in metrics], .32, color='#0f766e', label='Native tracking + tone-aware rescue')
    for i, m in enumerate(metrics):
        ax.text(m['candidate_cpu_ms']*1.08, i+.18, f"{m['candidate_cpu_ms']:.1f} ms ({m['speedup']:.1f}×)", va='center', fontsize=10)
    ax.set_yticks(y, [f"{m['cohort']} · {m['rate']/1e6:g} MS/s" for m in metrics])
    ax.invert_yaxis(); ax.set_xscale('log'); ax.set_xlim(10, 15000)
    ax.set_xlabel('Mean process CPU per complete dual-receiver call, milliseconds (log scale)')
    ax.set_title('Measured CPU savings depend on the dataset', loc='left', weight='bold', pad=18)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.20), ncol=2, frameon=False)
    ax.grid(axis='x', alpha=.15); fig.tight_layout()
    save(fig, 'cpu-comparison')

    plotted = [m for m in metrics if m['cohort'] != 'Constructed validation']
    fig, ax = plt.subplots(figsize=(10, 4.8))
    vals = [100*m['retained']/m['reference_positive'] for m in plotted]
    bars = ax.barh(np.arange(len(plotted)), vals, color=['#0f766e']*2+['#b45309']*2, height=.55)
    ax.set_yticks(np.arange(len(plotted)), [f"{m['cohort']} · {m['rate']/1e6:g} MS/s" for m in plotted])
    ax.invert_yaxis(); ax.set_xlim(0, 112)
    ax.axvline(97, color='#991b1b', linestyle='--', label='Predeclared research target: 97%')
    for bar, m, value in zip(bars, plotted, vals):
        ax.text(value+1, bar.get_y()+bar.get_height()/2, f"{m['retained']}/{m['reference_positive']}", va='center')
    ax.set_xlabel('Reference-positive receiver identities retained (%)')
    ax.set_title('Development quality did not generalize to recorded holdout', loc='left', weight='bold', pad=18)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.19), frameon=False); fig.tight_layout()
    save(fig, 'quality-transfer')

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), sharey=True)
    proposal_metrics = []
    for ax, (label, path, expected_count) in zip(axes, [
        ('Recent development', 'distributed_proposal/results.json', 171),
        ('Expanded development', 'expanded_proposals/results.json', 318)]):
        data=read(path); assert data['complete'] and len(data['rows'])==expected_count
        sources.add(path)
        recovered=[]; extra=[]
        for probe in (0,5,10):
            rows=[r for r in data['rows'] if r['probe']==probe]
            recovered.append(sum(r['assessment']['reference_outcome']=='retained_associated' for r in rows))
            extra.append(sum(r['assessment']['candidate_active'] and r['assessment']['reference_outcome']!='retained_associated' for r in rows))
        x=np.arange(3)
        ax.bar(x-.18, recovered, .34, color='#0f766e', label='Recovered identities')
        ax.bar(x+.18, extra, .34, color='#b45309', label='Unmatched active outputs')
        for i in range(3):
            ax.text(i-.18,recovered[i]+.2,str(recovered[i]),ha='center')
            ax.text(i+.18,extra[i]+.2,str(extra[i]),ha='center')
        ax.set_xticks(x,['0 (early)','5 (middle)','10 (late)']);ax.set_xlabel('Seed window')
        ax.set_title(label);ax.set_ylim(0,13)
        proposal_metrics.append(dict(cohort=label,recovered=recovered,unmatched=extra,source=path))
    axes[0].set_ylabel('Receiver outcomes across both rates')
    axes[0].legend(loc='upper center',bbox_to_anchor=(1.1,-.22),ncol=2,fontsize=9,frameon=False)
    fig.suptitle('More fixed search windows did not recover more identities',weight='bold')
    fig.tight_layout(); save(fig,'proposal-coverage')

    (HERE/'chart_data.json').write_text(json.dumps({'cpu_and_quality':metrics,'proposals':proposal_metrics,
        'sources_sha256':{s:hashlib.sha256((RESEARCH/s).read_bytes()).hexdigest() for s in sorted(sources)}},indent=2)+'\n')
    inventory=json.loads((HERE/'archive_inventory.json').read_text())
    lines=['# Complete research document catalog','',
           'Historical reports retain their original conclusions and chronology. The [consolidated report](README.md) states the latest status.','']
    for scope in inventory['scope']:
        lines += [f'## {scope}','']
        for entry in inventory['files']:
            p=Path(entry['path'])
            if entry['included'] and p.suffix=='.md' and p.parts[1]==scope:
                lines.append(f'- [{p.relative_to(Path("reports")/scope)}](../{p.relative_to("reports")})')
        lines.append('')
    (HERE/'CATALOG.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
