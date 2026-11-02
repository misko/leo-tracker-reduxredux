"""Render all planned development variants, including rejected alternatives."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent


def endpoints(case):
    folder=ROOT/'combined'/case
    return [json.loads(p.read_text()) for pattern in ('*-c0.json','*-fitted_c.json')
            for p in sorted(folder.glob(pattern))]


def main():
    controls=json.loads((ROOT/'solver/results.json').read_text())
    rows=[]
    for r in controls:
        if r['variant']=='published':
            rows.append(dict(case=r['case'],arm=r['arm'],method='ALGO07',error_km=r['evaluation_error_m']/1000,
                rms_hz=r['rms_hz'],phase_closed=r['phase_closed'],qualified=None))
    for case in ('DS26-0070','DS26-0309'):
        data=endpoints(case)
        for r in data:
            if r['hypothesis']!='incumbent':continue
            rows.append(dict(case=case,arm=r['arm'],method=f"Damping + orbital SD ×{r['SD_scale']:g}",
                error_km=r['error_m']/1000,rms_hz=r['rms_hz'],phase_closed=r['phase_closed'],qualified=r['qualified']))
    with (ROOT/'development_results.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    methods=['ALGO07','Damping + orbital SD ×1','Damping + orbital SD ×2','Damping + orbital SD ×4']
    for ax,case in zip(axes,('DS26-0070','DS26-0309')):
        for arm,offset,color in [('c0',-.17,'#3b75a5'),('fitted_c',.17,'#bd5146')]:
            chosen=[next(r for r in rows if r['case']==case and r['arm']==arm and r['method']==m) for m in methods]
            bars=ax.bar(np.arange(4)+offset,[r['error_km'] for r in chosen],width=.31,label=arm,color=color)
            for b,r in zip(bars,chosen):ax.text(b.get_x()+b.get_width()/2,b.get_height()+.06,f"{r['error_km']:.2f}",ha='center',fontsize=9)
        ax.set(title=case,xticks=range(4),xticklabels=['ALGO07','Damped\nSD ×1','Damped\nSD ×2','Damped\nSD ×4'])
        ax.grid(alpha=.2,axis='y');ax.set_axisbelow(True)
    axes[0].set_ylabel('Postfit position error (km)');axes[0].legend()
    fig.suptitle('Development cases: keep the original satellite identities and native points\nSD ×4 is preferred by the tested RF scores; SD ×2 is not selected using GPS',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.90));fig.savefig(ROOT/'development_comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    allrows=[]
    for ax,case in zip(axes,('DS26-0070','DS26-0309')):
        data=endpoints(case)
        for r in data:
            if r['arm']!='fitted_c':continue
            incumbent=r['hypothesis']=='incumbent'
            ax.scatter(r['rms_hz'],r['error_m']/1000,marker='o' if r['qualified'] else 'x',
                color='#3b75a5' if incumbent else '#bd5146',s=55)
            label=f"{r['norad']} SD{r['SD_scale']:g}"
            group=[v['error_m'] for v in data if v['arm']=='fitted_c' and v['norad']==r['norad']]
            crowded=max(group)-min(group)<200
            offset=(.55,.07+.05*[1.,2.,4.].index(r['SD_scale'])) if crowded else (4,4)
            ax.annotate(label,(r['rms_hz'],r['error_m']/1000),xytext=offset,textcoords='axes fraction' if crowded else 'offset points',fontsize=8,
                arrowprops=dict(arrowstyle='-',color='0.6',lw=.5) if crowded else None)
            allrows.append(dict(case=case,arm=r['arm'],hypothesis=r['hypothesis'],SD_scale=r['SD_scale'],
                error_m=r['error_m'],rms_hz=r['rms_hz'],objective=r['objective'],
                phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],all_gates_pass=r['all_gates_pass'],
                qualified=r['qualified'],lost_ids_count=len(r['lost_ids']),minimum_gate_slack=r['minimum_gate_slack']))
        ax.set(title=case,xlabel='Conditional curved-point RMS (Hz)',ylabel='Postfit position error (km)')
        ax.grid(alpha=.2);ax.margins(x=.3)
    fig.suptitle('Alternative identities can approach GPS while violating RF evidence\nCircle: paired-capable full-data diagnostic; cross: rejected. Blue: incumbent identity.',fontsize=12)
    fig.tight_layout(rect=(0,0,1,.90));fig.savefig(ROOT/'identity_candidates.png',dpi=170);plt.close(fig)
    with (ROOT/'identity_candidates.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(allrows[0]),lineterminator='\n');writer.writeheader();writer.writerows(allrows)


if __name__=='__main__':main()
