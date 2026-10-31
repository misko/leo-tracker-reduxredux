"""Summarize every prespecified panel case without position-error selection."""
from pathlib import Path
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent

def run():
    out = ROOT / 'phase-panel'
    terminal = json.loads((out/'terminal.json').read_text())
    assert terminal['all_completed'], 'Retain failures and investigate before summarizing'
    panel = json.loads((ROOT/'phase-validation-panel.json').read_text())
    rows, details = [], []
    for case in panel['rows']:
        variants = {}
        for limit in (15,30):
            variants[limit] = json.loads((out/case['case']/f'reference{limit}/annotation/result.json').read_text())
        row = dict(case=case['case'], role=case['panel_role'], points=case['points'], norad=case['norad'])
        values = {}
        for limit, result in variants.items():
            row[f'status_{limit}'] = result['annotation']['status']
            row[f'minimum_margin_{limit}'] = result['annotation']['minimum_margin']
            values[limit] = []
            for fold in result['folds']:
                p = next(p for p in fold['proposals'] if p['norad']==case['norad'])
                for arm in ('c0','fitted_c'):
                    v=p['arms'][arm]
                    values[limit].append(dict(seed=fold['seed'],arm=arm,
                        rms=v['scores']['target']['rms_hz'],phase=v['final_phase_change_s'],
                        masks=v['mask_sha256'], frozen_score_difference=v.get('frozen_score_difference')))
            row[f'maximum_phase_change_{limit}_s'] = max(v['phase'] for v in values[limit])
            row[f'phase_passes_{limit}'] = sum(v['phase']<=.01 for v in values[limit])
        assert len(values[15])==len(values[30])==6
        for a,b in zip(values[15],values[30],strict=True):
            assert (a['seed'],a['arm'],a['masks']) == (b['seed'],b['arm'],b['masks'])
            assert abs(a['frozen_score_difference'])<1e-5
            details.append(dict(case=case['case'],role=case['panel_role'],seed=a['seed'],arm=a['arm'],
                phase15=a['phase'],phase30=b['phase'],rms15=a['rms'],rms30=b['rms'],
                delta_rms_hz=b['rms']-a['rms']))
        row['max_absolute_rms_change_hz'] = max(abs(a['rms']-b['rms']) for a,b in zip(values[15],values[30]))
        rows.append(row)
    result=dict(rows=rows,details=details,all_masks_matched=True,frozen_15s_scores_replayed=True,
                GPS_used=False,position_inclusion_tested=False,accepted_new_points=0)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (out/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    xs=np.arange(len(rows))
    axes[0].bar(xs-.18,[r['maximum_phase_change_15_s'] for r in rows],width=.36,color='#a6bddb',label='15 s reference')
    axes[0].bar(xs+.18,[r['maximum_phase_change_30_s'] for r in rows],width=.36,color='#2166ac',label='30 s reference')
    axes[0].set_yscale('log');axes[0].axhline(.01,color='crimson',ls='--',label='Convergence gate')
    axes[0].set_ylabel('Maximum final phase movement across six fits (s)');axes[0].legend(fontsize=8)
    axes[0].set_title('Convergence repaired in all three clipped cases')
    for i,row in enumerate(rows):
        ds=[d for d in details if d['case']==row['case']]
        for arm,dx,color in [('c0',-.07,'#2166ac'),('fitted_c',.07,'#df8700')]:
            axes[1].scatter([i+dx]*3,[d['delta_rms_hz'] for d in ds if d['arm']==arm],
                            color=color,s=26,label=arm if i==0 else None)
    axes[1].axhline(0,color='.5',lw=.7);axes[1].set_ylabel('Held target RMS: 30 s minus 15 s (Hz)')
    axes[1].set_title('Frequency scores change little; identity alone is insufficient');axes[1].legend()
    for ax in axes:
        ax.set_xticks(xs,[r['case'].replace('DS26-','')+'\n'+('clipped' if r['role']=='clipped_phase' else 'control') for r in rows])
        ax.axvline(2.5,color='.5',lw=.7);ax.grid(axis='y',alpha=.2)
    fig.suptitle('DS26 prespecified RF-only validation panel: three clipped cases + three qualified controls\nMatched random groups, physical priors and c arms; annotation only, no new accepted points')
    fig.savefig(out/'phase-panel.png',dpi=160);fig.savefig(out/'phase-panel.pdf');plt.close(fig)
    print(json.dumps(rows,indent=2))

if __name__=='__main__':run()
